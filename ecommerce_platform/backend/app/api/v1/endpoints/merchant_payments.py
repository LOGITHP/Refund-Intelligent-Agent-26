from decimal import Decimal
from typing import List
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.security import get_current_merchant
from app.db.database import get_db
from app.db.models import MerchantOrderAllocation, MerchantPaymentPreference, Order, User, utcnow
from app.schemas.payment import (
    MerchantOrderAllocationOut,
    MerchantPayPalVerifyIn,
    MerchantPaymentPreferenceIn,
    MerchantPaymentPreferenceOut,
)
from app.services.paypal_service import (
    PayPalAPIError,
    PayPalService,
    get_paypal_base_url,
    get_paypal_service,
    invalidate_merchant_paypal_cache,
    merchant_paypal_aad,
)

router = APIRouter()


def _serialize_pref(
    merchant_id: int,
    pref: MerchantPaymentPreference | None,
) -> MerchantPaymentPreferenceOut:
    has_client_id = bool(pref and (pref.paypal_client_id or "").strip())
    has_secret = bool(pref and (pref.encrypted_paypal_client_secret or "").strip())
    env = (pref.paypal_environment if pref and pref.paypal_environment else "SANDBOX").strip().upper()
    if env not in ("SANDBOX", "LIVE"):
        env = "SANDBOX"

    return MerchantPaymentPreferenceOut(
        merchant_id=merchant_id,
        payout_paypal_email=pref.payout_paypal_email if pref else None,
        payout_currency=pref.payout_currency if pref else "USD",
        auto_refund_limit_usd=pref.auto_refund_limit_usd if pref else Decimal("150.00"),
        return_window_days=pref.return_window_days if pref else 7,
        is_active=pref.is_active if pref else True,
        payment_provider_mode="MERCHANT_DIRECT",
        paypal_sandbox_enabled=True,
        paypal_configured=has_client_id and has_secret,
        paypal_environment=env,
        paypal_client_id=pref.paypal_client_id if pref else None,
        has_client_secret=has_secret,
        client_secret_last4=pref.paypal_client_secret_last4 if (pref and has_secret) else None,
        paypal_webhook_id=pref.paypal_webhook_id if pref else None,
        webhook_callback_path=f"/api/v1/webhooks/paypal/{merchant_id}",
        credential_verified_at=pref.credential_verified_at if pref else None,
        updated_at=pref.updated_at if pref else None,
    )


@router.get("/payment-settings", response_model=MerchantPaymentPreferenceOut)
def get_merchant_payment_settings(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    pref = (
        db.query(MerchantPaymentPreference)
        .filter(MerchantPaymentPreference.merchant_id == current_merchant.id)
        .first()
    )
    return _serialize_pref(current_merchant.id, pref)


@router.put("/payment-settings", response_model=MerchantPaymentPreferenceOut)
def upsert_merchant_payment_settings(
    payload: MerchantPaymentPreferenceIn,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    pref = (
        db.query(MerchantPaymentPreference)
        .filter(MerchantPaymentPreference.merchant_id == current_merchant.id)
        .first()
    )
    if not pref:
        pref = MerchantPaymentPreference(merchant_id=current_merchant.id)
        db.add(pref)

    pref.payout_paypal_email = str(payload.payout_paypal_email) if payload.payout_paypal_email else None
    pref.payout_currency = payload.payout_currency
    pref.auto_refund_limit_usd = payload.auto_refund_limit_usd
    pref.return_window_days = payload.return_window_days
    pref.is_active = payload.is_active

    if "paypal_environment" in payload.model_fields_set or not pref.paypal_environment:
        if pref.paypal_environment != payload.paypal_environment:
            pref.paypal_environment = payload.paypal_environment
            pref.credential_verified_at = None

    if "paypal_client_id" in payload.model_fields_set:
        if pref.paypal_client_id != payload.paypal_client_id:
            pref.paypal_client_id = payload.paypal_client_id
            pref.credential_verified_at = None

    if "paypal_webhook_id" in payload.model_fields_set:
        pref.paypal_webhook_id = payload.paypal_webhook_id

    if payload.paypal_client_secret is not None:
        if not (settings.APP_DATA_ENCRYPTION_KEY or "").strip():
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail="APP_DATA_ENCRYPTION_KEY is not configured; cannot securely encrypt PayPal client secret",
            )
        ciphertext = encrypt_secret(
            payload.paypal_client_secret,
            associated_data=merchant_paypal_aad(current_merchant.id),
        )
        pref.encrypted_paypal_client_secret = ciphertext
        pref.paypal_client_secret_last4 = payload.paypal_client_secret[-4:]
        pref.credential_verified_at = None

    if payload.verify_before_save:
        effective_client_id = (pref.paypal_client_id or "").strip()
        effective_secret = payload.paypal_client_secret
        if effective_secret is None and pref.encrypted_paypal_client_secret:
            try:
                effective_secret = decrypt_secret(
                    pref.encrypted_paypal_client_secret,
                    associated_data=merchant_paypal_aad(current_merchant.id),
                )
            except Exception as exc:
                db.rollback()
                raise HTTPException(
                    status_code=503,
                    detail="Stored PayPal client secret could not be decrypted",
                ) from exc

        if not effective_client_id or not effective_secret:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Both PayPal client_id and client_secret are required to verify credentials",
            )

        temp_svc = PayPalService(
            client_id=effective_client_id,
            client_secret=effective_secret,
            webhook_id=pref.paypal_webhook_id or "",
            base_url=get_paypal_base_url(pref.paypal_environment),
            transport=paypal_svc._transport,
            http_client=paypal_svc._http_client,
        )
        try:
            temp_svc.get_access_token(force_refresh=True)
        except PayPalAPIError as exc:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="PayPal credential verification failed; please verify client_id, client_secret, and environment",
            ) from exc
        pref.credential_verified_at = utcnow()

    db.commit()
    db.refresh(pref)
    invalidate_merchant_paypal_cache(current_merchant.id)
    return _serialize_pref(current_merchant.id, pref)


@router.post("/payment-settings/verify-paypal")
def verify_merchant_paypal_credentials(
    payload: MerchantPayPalVerifyIn = Body(default_factory=MerchantPayPalVerifyIn),
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    pref = (
        db.query(MerchantPaymentPreference)
        .filter(MerchantPaymentPreference.merchant_id == current_merchant.id)
        .first()
    )

    env = payload.paypal_environment or (pref.paypal_environment if pref and pref.paypal_environment else "SANDBOX")
    client_id = payload.paypal_client_id or (pref.paypal_client_id if pref else None)
    secret = payload.paypal_client_secret
    stored_secret_plain: str | None = None

    if pref and pref.encrypted_paypal_client_secret:
        try:
            stored_secret_plain = decrypt_secret(
                pref.encrypted_paypal_client_secret,
                associated_data=merchant_paypal_aad(current_merchant.id),
            )
        except Exception as exc:
            if secret is None:
                raise HTTPException(
                    status_code=503,
                    detail="Stored PayPal client secret could not be decrypted",
                ) from exc

    if secret is None:
        secret = stored_secret_plain

    if not client_id or not secret:
        raise HTTPException(
            status_code=400,
            detail="PayPal client_id and client_secret are required for verification",
        )

    temp_svc = PayPalService(
        client_id=client_id.strip(),
        client_secret=secret.strip(),
        webhook_id=(pref.paypal_webhook_id or "") if pref else "",
        base_url=get_paypal_base_url(env),
        transport=paypal_svc._transport,
        http_client=paypal_svc._http_client,
    )
    try:
        temp_svc.get_access_token(force_refresh=True)
    except PayPalAPIError as exc:
        raise HTTPException(
            status_code=400,
            detail="PayPal credential verification failed; please verify client_id, client_secret, and environment",
        ) from exc

    verified_at = None
    if (
        pref is not None
        and (pref.paypal_client_id or "").strip() == client_id.strip()
        and (pref.paypal_environment or "SANDBOX").strip().upper() == env.strip().upper()
        and stored_secret_plain is not None
        and stored_secret_plain == secret
    ):
        pref.credential_verified_at = utcnow()
        db.commit()
        db.refresh(pref)
        verified_at = pref.credential_verified_at

    return {
        "verified": True,
        "paypal_environment": env,
        "credential_verified_at": verified_at,
        "message": "PayPal credentials verified successfully",
    }


@router.delete("/payment-settings/credentials", response_model=MerchantPaymentPreferenceOut)
def clear_merchant_paypal_credentials(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    pref = (
        db.query(MerchantPaymentPreference)
        .filter(MerchantPaymentPreference.merchant_id == current_merchant.id)
        .first()
    )
    if pref:
        pref.paypal_client_id = None
        pref.encrypted_paypal_client_secret = None
        pref.paypal_client_secret_last4 = None
        pref.paypal_webhook_id = None
        pref.credential_verified_at = None
        db.commit()
        db.refresh(pref)

    invalidate_merchant_paypal_cache(current_merchant.id)
    return _serialize_pref(current_merchant.id, pref)


@router.get("/allocations", response_model=List[MerchantOrderAllocationOut])
def list_merchant_allocations(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(MerchantOrderAllocation, Order)
        .join(Order, MerchantOrderAllocation.order_id == Order.id)
        .filter(MerchantOrderAllocation.merchant_id == current_merchant.id)
        .order_by(MerchantOrderAllocation.id.desc())
        .all()
    )

    result: List[MerchantOrderAllocationOut] = []
    for alloc, order in rows:
        result.append(
            MerchantOrderAllocationOut(
                id=alloc.id,
                order_id=alloc.order_id,
                order_number=order.order_number,
                merchant_id=alloc.merchant_id,
                gross_inr=alloc.gross_inr,
                gross_usd=alloc.gross_usd,
                platform_fee_usd=alloc.platform_fee_usd,
                net_merchant_usd=alloc.net_merchant_usd,
                refunded_usd=alloc.refunded_usd,
                fulfillment_status=alloc.fulfillment_status,
                settlement_status=alloc.settlement_status,
                payment_status=order.payment_status,
                paypal_order_id=order.paypal_order_id,
                paypal_capture_id=order.paypal_capture_id,
                created_at=alloc.created_at,
                updated_at=alloc.updated_at,
            )
        )
    return result
