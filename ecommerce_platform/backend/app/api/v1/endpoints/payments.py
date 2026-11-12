from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.crypto import redact_sensitive_data
from app.core.security import get_current_customer
from app.core.timeline import ORDER_STEP_SEQUENCE, sync_timeline_status
from app.db.database import get_db
from app.db.models import (
    CartItem,
    MerchantOrderAllocation,
    MerchantPaymentPreference,
    Order,
    OrderItem,
    OrderStatus,
    PaymentLedgerEvent,
    User,
    quantize_money,
)
from app.schemas.order import OrderOut
from app.schemas.payment import (
    CheckoutGroupItemSummary,
    MerchantCheckoutPayPalGroup,
    PayPalClientConfigOut,
    PayPalOrderCancelIn,
    PayPalOrderCaptureIn,
    PayPalOrderCreateIn,
    PayPalOrderCreateOut,
)
from app.services.inventory_service import (
    InsufficientStockError,
    convert_reservations_on_capture,
    get_available_stock_map,
    release_expired_reservations,
    release_order_reservations,
    reserve_items_for_order,
)
from app.services.invoice_service import generate_order_invoice_pdf
from app.services.order_service import (
    compute_order_totals,
    create_merchant_allocations,
    initial_tracking_timeline,
    resolve_checkout_groups,
)
from app.services.paypal_service import (
    PayPalAPIError,
    PayPalService,
    get_paypal_service,
    resolve_paypal_service_for_merchant,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/paypal/client-config", response_model=PayPalClientConfigOut)
def get_paypal_client_config(
    buy_now_product_id: Optional[int] = Query(None),
    buy_now_quantity: int = Query(1, ge=1),
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    release_expired_reservations(db, auto_commit=True)

    default_env = (settings.PAYPAL_ENV or "SANDBOX").strip().upper()
    if default_env not in ("SANDBOX", "LIVE"):
        default_env = "SANDBOX"

    try:
        grouped = resolve_checkout_groups(
            db, current_user.id, buy_now_product_id, buy_now_quantity
        )
    except HTTPException as exc:
        return PayPalClientConfigOut(
            configured=bool(paypal_svc.client_id and paypal_svc.client_secret),
            eligible=False,
            client_id="",
            environment=default_env,
            original_currency="INR",
            original_amount=Decimal("0.00"),
            paypal_currency="USD",
            paypal_amount=Decimal("0.00"),
            items_count=0,
            reason=str(exc.detail),
            requires_split_checkout=False,
            groups=[],
        )

    all_products = [p for items in grouped.values() for p, _ in items]
    stock_map = get_available_stock_map(db, all_products, auto_commit=False)

    groups: list[MerchantCheckoutPayPalGroup] = []
    for mid, group_items in grouped.items():
        if mid is None:
            merchant_name = "Shipkart Platform Catalog"
            is_platform_catalog = True
            pref = None
            group_env = default_env
        else:
            merchant_user = db.query(User).filter(User.id == mid).first()
            merchant_name = (
                (merchant_user.business_name or merchant_user.full_name)
                if merchant_user
                else f"Merchant #{mid}"
            )
            is_platform_catalog = False
            pref = (
                db.query(MerchantPaymentPreference)
                .filter(MerchantPaymentPreference.merchant_id == mid)
                .first()
            )
            group_env = (
                (pref.paypal_environment if pref and pref.paypal_environment else "SANDBOX")
                .strip()
                .upper()
            )
            if group_env not in ("SANDBOX", "LIVE"):
                group_env = "SANDBOX"

        decrypt_error: Optional[str] = None
        try:
            svc = resolve_paypal_service_for_merchant(db, mid, fallback_service=paypal_svc)
            group_configured = bool(svc.client_id and svc.client_secret)
            group_client_id = svc.client_id if group_configured else ""
        except PayPalAPIError as exc:
            group_configured = False
            group_client_id = ""
            decrypt_error = str(exc)

        _, group_inr, _, group_usd = compute_order_totals(group_items)
        group_items_count = sum(qty for _, qty in group_items)
        stock_ok = all(stock_map.get(p.id, 0) >= qty for p, qty in group_items)
        pref_active = True if (pref is None or pref.is_active) else False

        group_reason: Optional[str] = None
        if decrypt_error:
            group_reason = decrypt_error
        elif not group_configured:
            group_reason = (
                f"{merchant_name} has not connected their Direct PayPal credentials in Seller Hub yet."
                if mid is not None
                else "This starter catalog item is not assigned to a merchant store yet. Claim starter listings in Seller Hub → My Listings or use Standard Checkout."
            )
        elif not pref_active:
            group_reason = "Merchant PayPal checkout is currently disabled."
        elif not stock_ok:
            group_reason = "One or more items have insufficient available stock."
        elif group_usd <= Decimal("0.00"):
            group_reason = "PayPal settlement amount must be greater than zero."

        group_eligible = (
            group_configured
            and pref_active
            and group_items_count > 0
            and stock_ok
            and group_usd > Decimal("0.00")
        )

        item_summaries = [
            CheckoutGroupItemSummary(
                product_id=p.id,
                title=p.title,
                image_url=p.image_url,
                quantity=qty,
                price_inr=quantize_money(p.price),
                sandbox_usd_price=quantize_money(p.sandbox_usd_price),
            )
            for p, qty in group_items
        ]

        groups.append(
            MerchantCheckoutPayPalGroup(
                merchant_id=mid,
                is_platform_catalog=is_platform_catalog,
                merchant_name=merchant_name,
                configured=group_configured,
                eligible=group_eligible,
                client_id=group_client_id,
                environment=group_env,
                original_currency="INR",
                original_amount=group_inr,
                paypal_currency="USD",
                paypal_amount=group_usd,
                items_count=group_items_count,
                items=item_summaries,
                reason=None if group_eligible else group_reason,
            )
        )

    if len(groups) == 1:
        sole = groups[0]
        return PayPalClientConfigOut(
            configured=sole.configured,
            eligible=sole.eligible,
            client_id=sole.client_id,
            environment=sole.environment,
            original_currency="INR",
            original_amount=sole.original_amount,
            paypal_currency="USD",
            paypal_amount=sole.paypal_amount,
            items_count=sole.items_count,
            reason=sole.reason,
            requires_split_checkout=False,
            groups=groups,
        )

    total_inr = quantize_money(sum((g.original_amount for g in groups), Decimal("0.00")))
    total_usd = quantize_money(sum((g.paypal_amount for g in groups), Decimal("0.00")))
    total_items = sum(g.items_count for g in groups)
    any_configured = any(g.configured for g in groups)
    any_eligible = any(g.eligible for g in groups)
    top_reason = None if any_eligible else "No merchant group in cart is eligible for PayPal checkout."

    return PayPalClientConfigOut(
        configured=any_configured,
        eligible=any_eligible,
        client_id="",
        environment=default_env,
        original_currency="INR",
        original_amount=total_inr,
        paypal_currency="USD",
        paypal_amount=total_usd,
        items_count=total_items,
        reason=top_reason,
        requires_split_checkout=True,
        groups=groups,
    )


@router.post("/paypal/create-order", response_model=PayPalOrderCreateOut, status_code=status.HTTP_201_CREATED)
def create_paypal_order(
    payload: PayPalOrderCreateIn,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    release_expired_reservations(db, auto_commit=True)

    grouped = resolve_checkout_groups(
        db, current_user.id, payload.buy_now_product_id, payload.buy_now_quantity
    )

    if payload.buy_now_product_id:
        target_merchant_id, items_to_order = next(iter(grouped.items()))
    elif payload.is_platform_catalog:
        if None not in grouped:
            raise HTTPException(status_code=400, detail="No platform catalog items found in cart")
        target_merchant_id = None
        items_to_order = grouped[None]
    elif payload.merchant_id is not None:
        if payload.merchant_id not in grouped:
            raise HTTPException(status_code=400, detail="Specified merchant has no items in cart")
        target_merchant_id = payload.merchant_id
        items_to_order = grouped[payload.merchant_id]
    else:
        if len(grouped) > 1:
            raise HTTPException(
                status_code=400,
                detail="Multiple merchants in cart; specify merchant_id for direct PayPal checkout",
            )
        target_merchant_id, items_to_order = next(iter(grouped.items()))

    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, target_merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Merchant PayPal credentials are not configured"
                if target_merchant_id is not None
                else "PayPal Sandbox credentials are not configured"
            ),
        )

    total_mrp, total_selling, total_discount, paypal_amount = compute_order_totals(items_to_order)
    if paypal_amount <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="PayPal settlement amount must be greater than zero")

    random_suffix = uuid.uuid4().hex[:6].upper()
    order_number = f"OD-SK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random_suffix}"
    create_request_id = str(uuid.uuid4())
    capture_request_id = str(uuid.uuid4())
    checkout_source = "BUY_NOW" if payload.buy_now_product_id else "CART"
    provider_mode = "MERCHANT_DIRECT" if target_merchant_id is not None else "PLATFORM_SANDBOX"

    # 1. Order-first local transaction (PENDING_PAYMENT + InventoryReservation + MerchantOrderAllocation + Request IDs)
    order = Order(
        order_number=order_number,
        user_id=current_user.id,
        merchant_id=target_merchant_id,
        total_mrp=total_mrp,
        total_discount=total_discount,
        total_amount=total_selling,
        original_currency="INR",
        paypal_currency="USD",
        paypal_amount=paypal_amount,
        payment_method="PAYPAL_SANDBOX",
        payment_status="PENDING_PAYMENT",
        paypal_create_request_id=create_request_id,
        paypal_capture_request_id=capture_request_id,
        payment_provider_mode=provider_mode,
        status=OrderStatus.PENDING_PAYMENT,
        shipping_address=payload.shipping_address,
        tracking_history=initial_tracking_timeline(
            ordered_completed=False,
            ordered_detail="Order initialized; awaiting PayPal authorization.",
        ),
    )
    db.add(order)
    db.flush()

    for product, qty in items_to_order:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                merchant_id=product.merchant_id,
                title=product.title,
                image_url=product.image_url,
                quantity=qty,
                price=product.price,
                mrp=product.mrp,
            )
        )

    try:
        reservations = reserve_items_for_order(
            db,
            order.id,
            items_to_order,
            ttl_minutes=settings.RESERVATION_TTL_MINUTES,
        )
    except InsufficientStockError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    create_merchant_allocations(
        db,
        order.id,
        items_to_order,
        fulfillment_status="PENDING_PAYMENT",
        settlement_status="PENDING",
    )

    reservation_expires_at = reservations[0].expires_at if reservations else None
    db.commit()
    db.refresh(order)

    # 2. Call PayPal Orders v2 AFTER committing local reservations (avoid holding DB locks across network I/O)
    try:
        pp_resp = merchant_svc.create_order(
            request_id=create_request_id,
            amount_usd=paypal_amount,
            currency_code="USD",
            reference_id=order.order_number,
            description=f"Shipkart Order {order.order_number}",
            custom_id=str(order.id),
        )
        paypal_order_id = pp_resp.get("id")
        if not paypal_order_id:
            raise PayPalAPIError("PayPal create-order response missing id", details=pp_resp)
    except PayPalAPIError as exc:
        release_order_reservations(db, order.id, new_status="RELEASED")
        order.status = OrderStatus.CANCELLED
        order.payment_status = "PAYPAL_CREATE_FAILED"
        db.query(MerchantOrderAllocation).filter(
            MerchantOrderAllocation.order_id == order.id
        ).update(
            {"fulfillment_status": "CANCELLED", "settlement_status": "FAILED"},
            synchronize_session=False,
        )
        db.add(
            PaymentLedgerEvent(
                order_id=order.id,
                merchant_id=target_merchant_id,
                event_type="ORDER_CREATE_FAILED",
                idempotency_key=create_request_id,
                amount=paypal_amount,
                currency="USD",
                status_snapshot="PAYPAL_CREATE_FAILED",
                redacted_payload=redact_sensitive_data(
                    {"error": str(exc), "details": exc.details, "checkout_source": checkout_source}
                ),
            )
        )
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    order.paypal_order_id = paypal_order_id
    db.add(
        PaymentLedgerEvent(
            order_id=order.id,
            merchant_id=target_merchant_id,
            event_type="ORDER_CREATED",
            paypal_order_id=paypal_order_id,
            idempotency_key=create_request_id,
            amount=paypal_amount,
            currency="USD",
            status_snapshot=pp_resp.get("status", "CREATED"),
            redacted_payload={
                **redact_sensitive_data(pp_resp),
                "checkout_source": checkout_source,
            },
        )
    )
    db.commit()
    db.refresh(order)

    return PayPalOrderCreateOut(
        local_order_id=order.id,
        order_number=order.order_number,
        paypal_order_id=paypal_order_id,
        status=order.status.value,
        payment_status=order.payment_status,
        original_currency=order.original_currency,
        original_amount=order.total_amount,
        paypal_currency=order.paypal_currency or "USD",
        paypal_amount=order.paypal_amount,
        reservation_expires_at=reservation_expires_at,
    )


@router.post("/paypal/capture-order", response_model=OrderOut)
def capture_paypal_order(
    payload: PayPalOrderCaptureIn,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    order = db.query(Order).filter(Order.id == payload.local_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Strict ownership and PayPal order binding checks
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to capture this order")
    if not order.paypal_order_id or order.paypal_order_id != payload.paypal_order_id:
        raise HTTPException(
            status_code=400,
            detail="PayPal order ID does not match local order",
        )

    # Idempotent replay if already captured or already marked capture exception
    if order.payment_status == "PAID" and order.status not in (
        OrderStatus.PENDING_PAYMENT,
        OrderStatus.CANCELLED,
    ):
        return order
    if order.status == OrderStatus.CAPTURE_EXCEPTION:
        return order
    if order.payment_status in ("PAYPAL_CREATE_FAILED", "DENIED", "REVERSED", "REFUNDED", "CANCELLED_BY_BUYER"):
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be captured in payment state {order.payment_status}",
        )

    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, order.merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(status_code=503, detail="Merchant PayPal credentials are not configured")

    if not order.paypal_capture_request_id:
        order.paypal_capture_request_id = str(uuid.uuid4())
        db.commit()

    # Call PayPal capture API with stable PayPal-Request-Id
    try:
        pp_capture = merchant_svc.capture_order(
            paypal_order_id=order.paypal_order_id,
            request_id=order.paypal_capture_request_id,
        )
    except PayPalAPIError as exc:
        db.add(
            PaymentLedgerEvent(
                order_id=order.id,
                merchant_id=order.merchant_id,
                event_type="CAPTURE_FAILED",
                paypal_order_id=order.paypal_order_id,
                idempotency_key=order.paypal_capture_request_id,
                amount=order.paypal_amount,
                currency=order.paypal_currency or "USD",
                status_snapshot="CAPTURE_FAILED",
                redacted_payload=redact_sensitive_data(
                    {"error": str(exc), "details": exc.details}
                ),
            )
        )
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # Verify capture status, currency, and exact Decimal amount
    top_status = pp_capture.get("status")
    captures = (
        (pp_capture.get("purchase_units") or [{}])[0]
        .get("payments", {})
        .get("captures", [])
    )
    capture_obj = captures[0] if captures else {}
    capture_id = capture_obj.get("id")
    capture_status = capture_obj.get("status")
    amt_obj = capture_obj.get("amount") or {}
    captured_currency = amt_obj.get("currency_code")
    captured_value_raw = amt_obj.get("value")

    expected_currency = order.paypal_currency or "USD"
    expected_amount = quantize_money(order.paypal_amount)

    try:
        captured_amount = quantize_money(captured_value_raw) if captured_value_raw is not None else None
    except Exception:
        captured_amount = None

    if (
        top_status != "COMPLETED"
        or capture_status != "COMPLETED"
        or not capture_id
        or captured_currency != expected_currency
        or captured_amount != expected_amount
    ):
        order.paypal_capture_id = capture_id
        order.status = OrderStatus.CAPTURE_EXCEPTION
        order.payment_status = "CAPTURE_AMOUNT_MISMATCH"
        db.query(MerchantOrderAllocation).filter(
            MerchantOrderAllocation.order_id == order.id
        ).update(
            {"fulfillment_status": "CAPTURE_EXCEPTION", "settlement_status": "EXCEPTION_REVIEW"},
            synchronize_session=False,
        )
        db.add(
            PaymentLedgerEvent(
                order_id=order.id,
                merchant_id=order.merchant_id,
                event_type="CAPTURE_EXCEPTION_MISMATCH",
                paypal_order_id=order.paypal_order_id,
                paypal_capture_id=capture_id,
                idempotency_key=order.paypal_capture_request_id,
                amount=captured_amount,
                currency=captured_currency,
                status_snapshot="CAPTURE_AMOUNT_MISMATCH",
                redacted_payload=redact_sensitive_data(pp_capture),
            )
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="PayPal capture status, currency, or amount verification failed",
        )

    order.paypal_capture_id = capture_id

    # Convert active reservations and atomically deduct physical stock
    converted = convert_reservations_on_capture(db, order)
    if not converted:
        order.status = OrderStatus.CAPTURE_EXCEPTION
        order.payment_status = "CAPTURE_EXCEPTION_OUT_OF_STOCK"
        db.query(MerchantOrderAllocation).filter(
            MerchantOrderAllocation.order_id == order.id
        ).update(
            {"fulfillment_status": "CAPTURE_EXCEPTION", "settlement_status": "EXCEPTION_REVIEW"},
            synchronize_session=False,
        )
        db.add(
            PaymentLedgerEvent(
                order_id=order.id,
                merchant_id=order.merchant_id,
                event_type="CAPTURE_EXCEPTION_OUT_OF_STOCK",
                paypal_order_id=order.paypal_order_id,
                paypal_capture_id=capture_id,
                idempotency_key=order.paypal_capture_request_id,
                amount=captured_amount,
                currency=captured_currency,
                status_snapshot="CAPTURE_EXCEPTION_OUT_OF_STOCK",
                redacted_payload=redact_sensitive_data(pp_capture),
            )
        )
        db.commit()
        db.refresh(order)
        return order

    order.status = OrderStatus.ORDERED
    order.payment_status = "PAID"
    order.tracking_history = sync_timeline_status(
        order.tracking_history or initial_tracking_timeline(ordered_completed=False),
        OrderStatus.ORDERED.value,
        ORDER_STEP_SEQUENCE,
    )
    flag_modified(order, "tracking_history")

    db.query(MerchantOrderAllocation).filter(
        MerchantOrderAllocation.order_id == order.id
    ).update(
        {"fulfillment_status": "ORDERED", "settlement_status": "CAPTURED"},
        synchronize_session=False,
    )

    db.add(
        PaymentLedgerEvent(
            order_id=order.id,
            merchant_id=order.merchant_id,
            event_type="CAPTURE_COMPLETED",
            paypal_order_id=order.paypal_order_id,
            paypal_capture_id=capture_id,
            idempotency_key=order.paypal_capture_request_id,
            amount=captured_amount,
            currency=captured_currency,
            status_snapshot="PAID",
            redacted_payload=redact_sensitive_data(pp_capture),
        )
    )

    # Clear cart ONLY for the purchased items in this merchant group (never clear other merchants' cart items)
    created_ledger = (
        db.query(PaymentLedgerEvent)
        .filter(
            PaymentLedgerEvent.order_id == order.id,
            PaymentLedgerEvent.event_type == "ORDER_CREATED",
        )
        .order_by(PaymentLedgerEvent.id.desc())
        .first()
    )
    checkout_source = (
        (created_ledger.redacted_payload or {}).get("checkout_source")
        if created_ledger
        else "CART"
    )
    if checkout_source != "BUY_NOW":
        purchased_product_ids = [item.product_id for item in order.items]
        if purchased_product_ids:
            db.query(CartItem).filter(
                CartItem.user_id == current_user.id,
                CartItem.product_id.in_(purchased_product_ids),
            ).delete(synchronize_session=False)

    db.commit()
    db.refresh(order)

    # Generate MinIO PDF Invoice with PayPal Order/Capture IDs
    try:
        inv_name = generate_order_invoice_pdf(
            order,
            customer_name=current_user.full_name,
            customer_email=current_user.email,
        )
        order.invoice_object_name = inv_name
        db.commit()
        db.refresh(order)
    except Exception as exc:
        logger.warning("Invoice generation failed for PayPal order %s: %s", order.order_number, exc)

    return order


@router.post("/paypal/cancel-order", response_model=OrderOut)
def cancel_pending_paypal_order(
    payload: PayPalOrderCancelIn,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == payload.local_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this order")
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Only pending payment orders can be cancelled here")

    release_order_reservations(db, order.id, new_status="RELEASED")
    order.status = OrderStatus.CANCELLED
    order.payment_status = "CANCELLED_BY_BUYER"
    db.query(MerchantOrderAllocation).filter(
        MerchantOrderAllocation.order_id == order.id
    ).update(
        {"fulfillment_status": "CANCELLED", "settlement_status": "CANCELLED"},
        synchronize_session=False,
    )
    db.add(
        PaymentLedgerEvent(
            order_id=order.id,
            event_type="ORDER_CANCELLED",
            paypal_order_id=order.paypal_order_id,
            amount=order.paypal_amount,
            currency=order.paypal_currency,
            status_snapshot="CANCELLED_BY_BUYER",
            redacted_payload={"order_number": order.order_number},
        )
    )
    db.commit()
    db.refresh(order)
    return order
