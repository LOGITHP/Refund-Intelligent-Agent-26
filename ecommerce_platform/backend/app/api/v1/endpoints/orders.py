from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.crypto import redact_sensitive_data
from app.core.security import (
    get_current_customer,
    get_current_merchant,
    get_current_service_actor,
    get_current_user,
)
from app.core.timeline import ORDER_STEP_SEQUENCE, sync_timeline_status
from app.db.database import get_db
from app.db.models import (
    CartItem,
    MerchantOrderAllocation,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ReturnRequest,
    User,
    UserRole,
)
from app.schemas.money import MoneyField, OptionalMoneyField
from app.schemas.order import OrderCreate, OrderOut
from app.services.inventory_service import (
    get_available_stock_map,
    release_expired_reservations,
)
from app.services.invoice_service import generate_order_invoice_pdf
from app.services.order_service import (
    compute_order_totals,
    create_merchant_allocations,
    initial_tracking_timeline,
    resolve_checkout_items,
)
from app.services.paypal_service import (
    PayPalAPIError,
    PayPalService,
    get_paypal_service,
    resolve_paypal_service_for_merchant,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class BridgeOrderItemContext(BaseModel):
    id: int
    merchant_id: Optional[int] = None
    product_id: int
    title: str
    price: MoneyField
    sandbox_usd_price: OptionalMoneyField = None
    quantity: int


class BridgeAllocationContext(BaseModel):
    id: int
    merchant_id: Optional[int] = None
    gross_inr: MoneyField
    gross_usd: MoneyField
    platform_fee_usd: MoneyField
    net_merchant_usd: MoneyField
    refunded_usd: MoneyField
    fulfillment_status: str
    settlement_status: str


class BridgeReturnContext(BaseModel):
    id: int
    return_number: str
    order_item_id: int
    merchant_id: Optional[int] = None
    product_id: int
    reason: str
    comments: Optional[str] = None
    evidence_urls: List[str]
    refund_amount: MoneyField
    refund_currency: str
    refund_paypal_amount: OptionalMoneyField = None
    status: str
    refund_transaction_id: Optional[str] = None
    created_at: datetime


class OrderBridgeContextOut(BaseModel):
    id: int
    order_number: str
    user_id: int
    total_amount: MoneyField
    original_currency: str
    paypal_currency: Optional[str] = None
    paypal_amount: OptionalMoneyField = None
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    payment_status: str
    status: str
    created_at: datetime
    delivered_at: Optional[str] = None
    items: List[BridgeOrderItemContext]
    allocations: List[BridgeAllocationContext]
    returns: List[BridgeReturnContext]


def _merchant_can_access_order(order: Order, merchant_id: int) -> bool:
    if order.merchant_id is not None and order.merchant_id != merchant_id:
        return False
    return any(item.merchant_id == merchant_id or item.merchant_id is None for item in order.items)


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    order_in: OrderCreate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    release_expired_reservations(db, auto_commit=False)
    items_to_order = resolve_checkout_items(
        db,
        current_user.id,
        order_in.buy_now_product_id,
        order_in.buy_now_quantity,
    )

    # Verify available sellable stock (physical stock minus active PayPal reservations)
    stock_map = get_available_stock_map(
        db, [p for p, _ in items_to_order], auto_commit=False
    )
    for product, qty in items_to_order:
        if stock_map.get(product.id, 0) < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.title}",
            )

    total_mrp, total_selling, total_discount, _ = compute_order_totals(items_to_order)

    random_suffix = uuid.uuid4().hex[:6].upper()
    order_number = f"OD-SK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random_suffix}"

    order = Order(
        order_number=order_number,
        user_id=current_user.id,
        total_mrp=total_mrp,
        total_discount=total_discount,
        total_amount=total_selling,
        original_currency="INR",
        payment_method=order_in.payment_method,
        payment_status="CONFIRMED",
        payment_provider_mode="PLATFORM_SANDBOX",
        status=OrderStatus.ORDERED,
        shipping_address=order_in.shipping_address,
        tracking_history=initial_tracking_timeline(ordered_completed=True),
    )
    db.add(order)
    db.flush()

    # Lock product rows deterministically on PostgreSQL before deducting stock
    product_ids = sorted({p.id for p, _ in items_to_order})
    bind = db.get_bind()
    prod_q = db.query(Product).filter(Product.id.in_(product_ids)).order_by(Product.id.asc())
    if bind is not None and bind.dialect.name == "postgresql":
        prod_q = prod_q.with_for_update()
    locked_products = {p.id: p for p in prod_q.all()}

    # Re-verify available stock under row lock before deduction
    locked_stock_map = get_available_stock_map(db, locked_products.values(), auto_commit=False)
    for product, qty in items_to_order:
        locked_prod = locked_products[product.id]
        if locked_stock_map.get(locked_prod.id, 0) < qty:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {locked_prod.title}")

        order_item = OrderItem(
            order_id=order.id,
            product_id=locked_prod.id,
            merchant_id=locked_prod.merchant_id,
            title=locked_prod.title,
            image_url=locked_prod.image_url,
            quantity=qty,
            price=locked_prod.price,
            mrp=locked_prod.mrp,
        )
        db.add(order_item)
        locked_prod.stock = int(locked_prod.stock) - qty

    create_merchant_allocations(
        db,
        order.id,
        items_to_order,
        fulfillment_status="ORDERED",
        settlement_status="STANDARD_CONFIRMED",
    )

    if not order_in.buy_now_product_id:
        db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()

    db.commit()
    db.refresh(order)

    # Automatically generate invoice PDF and upload to MinIO
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
        logger.warning("Invoice generation failed for order %s: %s", order.order_number, exc)

    return order


def _reconcile_order(order: Order, db: Session) -> Order:
    if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED, OrderStatus.CAPTURE_EXCEPTION):
        return order
    synced = sync_timeline_status(order.tracking_history, order.status.value, ORDER_STEP_SEQUENCE)
    if synced != (order.tracking_history or []):
        order.tracking_history = synced
        flag_modified(order, "tracking_history")
        db.commit()
        db.refresh(order)
    return order


@router.get("/my", response_model=List[OrderOut])
def get_my_orders(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    release_expired_reservations(db, auto_commit=True)
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.id.desc()).all()
    return [_reconcile_order(o, db) for o in orders]


@router.get("/merchant", response_model=List[OrderOut])
def get_merchant_orders(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    release_expired_reservations(db, auto_commit=True)
    orders = (
        db.query(Order)
        .filter(
            Order.items.any(
                or_(OrderItem.merchant_id == current_merchant.id, OrderItem.merchant_id.is_(None))
            ),
            Order.status != OrderStatus.PENDING_PAYMENT,
        )
        .order_by(Order.id.desc())
        .all()
    )
    return [_reconcile_order(o, db) for o in orders]


@router.get("/{order_id}/bridge-context", response_model=OrderBridgeContextOut)
def get_order_bridge_context(
    order_id: int,
    _service_claims: Dict[str, Any] = Depends(get_current_service_actor),
    db: Session = Depends(get_db),
):
    """Authenticated service-to-service snapshot of an order, its allocations, and its returns."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    delivered_at: Optional[str] = None
    for step in order.tracking_history or []:
        if isinstance(step, dict) and step.get("step") == "DELIVERED" and step.get("completed"):
            delivered_at = step.get("time")
            break

    items_ctx = [
        BridgeOrderItemContext(
            id=item.id,
            merchant_id=item.merchant_id,
            product_id=item.product_id,
            title=item.title,
            price=item.price,
            sandbox_usd_price=item.product.sandbox_usd_price if item.product else None,
            quantity=item.quantity,
        )
        for item in order.items
    ]

    allocations_rows = (
        db.query(MerchantOrderAllocation)
        .filter(MerchantOrderAllocation.order_id == order.id)
        .order_by(MerchantOrderAllocation.id.asc())
        .all()
    )
    allocations_ctx = [
        BridgeAllocationContext(
            id=a.id,
            merchant_id=a.merchant_id,
            gross_inr=a.gross_inr,
            gross_usd=a.gross_usd,
            platform_fee_usd=a.platform_fee_usd,
            net_merchant_usd=a.net_merchant_usd,
            refunded_usd=a.refunded_usd,
            fulfillment_status=a.fulfillment_status,
            settlement_status=a.settlement_status,
        )
        for a in allocations_rows
    ]

    return_rows = (
        db.query(ReturnRequest)
        .filter(ReturnRequest.order_id == order.id)
        .order_by(ReturnRequest.id.asc())
        .all()
    )
    returns_ctx = [
        BridgeReturnContext(
            id=r.id,
            return_number=r.return_number,
            order_item_id=r.order_item_id,
            merchant_id=r.merchant_id,
            product_id=r.product_id,
            reason=r.reason,
            comments=r.comments,
            evidence_urls=list(r.evidence_urls or []),
            refund_amount=r.refund_amount,
            refund_currency=r.refund_currency,
            refund_paypal_amount=r.refund_paypal_amount,
            status=r.status.value,
            refund_transaction_id=r.refund_transaction_id,
            created_at=r.created_at,
        )
        for r in return_rows
    ]

    return OrderBridgeContextOut(
        id=order.id,
        order_number=order.order_number,
        user_id=order.user_id,
        total_amount=order.total_amount,
        original_currency=order.original_currency,
        paypal_currency=order.paypal_currency,
        paypal_amount=order.paypal_amount,
        paypal_order_id=order.paypal_order_id,
        paypal_capture_id=order.paypal_capture_id,
        payment_status=order.payment_status,
        status=order.status.value,
        created_at=order.created_at,
        delivered_at=delivered_at,
        items=items_ctx,
        allocations=allocations_ctx,
        returns=returns_ctx,
    )


@router.get("/{order_id}/paypal-capture-status")
def get_order_paypal_capture_status(
    order_id: int,
    _service_claims: Dict[str, Any] = Depends(get_current_service_actor),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    """Service-authenticated live PayPal capture status check using the owning merchant's credentials."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    capture_id = (order.paypal_capture_id or "").strip()
    if not capture_id or capture_id.startswith("CAP-SIM-"):
        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "merchant_id": order.merchant_id,
            "paypal_order_id": order.paypal_order_id,
            "paypal_capture_id": order.paypal_capture_id,
            "paypal_capture_status": None,
            "is_real_paypal_capture": False,
            "paypal_payload": {},
        }

    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, order.merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(status_code=503, detail="Merchant PayPal credentials are not configured")

    try:
        pp_capture = merchant_svc.get_capture(capture_id)
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    redacted = redact_sensitive_data(pp_capture)
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "merchant_id": order.merchant_id,
        "paypal_order_id": order.paypal_order_id,
        "paypal_capture_id": capture_id,
        "paypal_capture_status": redacted.get("status"),
        "is_real_paypal_capture": True,
        "amount": redacted.get("amount"),
        "paypal_payload": redacted,
    }


@router.get("/{order_id}", response_model=OrderOut)
def get_order_by_id(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if current_user.role == UserRole.CUSTOMER and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    if current_user.role == UserRole.MERCHANT and not _merchant_can_access_order(order, current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    return _reconcile_order(order, db)


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    new_status: OrderStatus,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not _merchant_can_access_order(order, current_merchant.id):
        raise HTTPException(status_code=403, detail="Not authorized to update status for this order")

    if order.status == OrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Cannot fulfill order before payment capture")

    order.status = new_status
    order.tracking_history = sync_timeline_status(
        order.tracking_history,
        new_status.value,
        ORDER_STEP_SEQUENCE,
    )
    flag_modified(order, "tracking_history")

    db.query(MerchantOrderAllocation).filter(
        MerchantOrderAllocation.order_id == order.id,
        or_(
            MerchantOrderAllocation.merchant_id == current_merchant.id,
            MerchantOrderAllocation.merchant_id.is_(None),
        ),
    ).update({"fulfillment_status": new_status.value}, synchronize_session=False)

    db.commit()
    db.refresh(order)
    return order
