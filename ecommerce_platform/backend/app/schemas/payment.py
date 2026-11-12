from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.schemas.money import MoneyField


class CheckoutGroupItemSummary(BaseModel):
    product_id: int
    title: str
    image_url: str
    quantity: int
    price_inr: MoneyField
    sandbox_usd_price: MoneyField


class MerchantCheckoutPayPalGroup(BaseModel):
    merchant_id: Optional[int] = None
    is_platform_catalog: bool = False
    merchant_name: str
    configured: bool
    eligible: bool
    client_id: str
    environment: str
    original_currency: str = "INR"
    original_amount: MoneyField
    paypal_currency: str = "USD"
    paypal_amount: MoneyField
    items_count: int
    items: List[CheckoutGroupItemSummary] = []
    reason: Optional[str] = None


class PayPalClientConfigOut(BaseModel):
    configured: bool
    eligible: bool
    client_id: str
    environment: str
    original_currency: str
    original_amount: MoneyField
    paypal_currency: str
    paypal_amount: MoneyField
    items_count: int
    reason: Optional[str] = None
    requires_split_checkout: bool = False
    groups: List[MerchantCheckoutPayPalGroup] = []


class PayPalOrderCreateIn(BaseModel):
    shipping_address: Dict[str, Any]
    buy_now_product_id: Optional[int] = None
    buy_now_quantity: Optional[int] = 1
    merchant_id: Optional[int] = None
    is_platform_catalog: bool = False


class PayPalOrderCreateOut(BaseModel):
    local_order_id: int
    order_number: str
    paypal_order_id: str
    status: str
    payment_status: str
    original_currency: str
    original_amount: MoneyField
    paypal_currency: str
    paypal_amount: MoneyField
    reservation_expires_at: Optional[datetime] = None


class PayPalOrderCaptureIn(BaseModel):
    local_order_id: int
    paypal_order_id: str


class PayPalOrderCancelIn(BaseModel):
    local_order_id: int


class MerchantPaymentPreferenceIn(BaseModel):
    payout_paypal_email: Optional[EmailStr] = None
    payout_currency: str = "USD"
    auto_refund_limit_usd: MoneyField = Decimal("150.00")
    return_window_days: int = 7
    is_active: bool = True
    paypal_environment: str = "SANDBOX"
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_webhook_id: Optional[str] = None
    verify_before_save: bool = False

    @field_validator("payout_paypal_email", mode="before")
    @classmethod
    def _empty_email_to_none(cls, val: Any) -> Any:
        if isinstance(val, str) and not val.strip():
            return None
        return val

    @field_validator("paypal_client_id", "paypal_client_secret", "paypal_webhook_id", mode="before")
    @classmethod
    def _strip_empty_to_none(cls, val: Any) -> Any:
        if isinstance(val, str):
            cleaned = val.strip()
            return cleaned if cleaned else None
        return val

    @field_validator("paypal_webhook_id")
    @classmethod
    def _reject_url_in_webhook_id(cls, val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        lowered = val.lower()
        if lowered.startswith("http://") or lowered.startswith("https://") or "://" in val or "/" in val:
            raise ValueError(
                "Enter the PayPal Webhook ID from PayPal Developer Dashboard (e.g. 8PT597350X239142B), not a callback URL."
            )
        return val

    @field_validator("paypal_environment", mode="before")
    @classmethod
    def _normalize_environment(cls, val: Any) -> str:
        cleaned = str(val or "SANDBOX").strip().upper()
        if cleaned not in ("SANDBOX", "LIVE"):
            raise ValueError("paypal_environment must be SANDBOX or LIVE")
        return cleaned

    @field_validator("payout_currency")
    @classmethod
    def _normalize_currency(cls, val: str) -> str:
        cleaned = (val or "USD").strip().upper()
        if cleaned != "USD":
            raise ValueError("Sandbox platform allocations settle in USD")
        return cleaned

    @field_validator("auto_refund_limit_usd")
    @classmethod
    def _non_negative_limit(cls, val: Decimal) -> Decimal:
        if val < Decimal("0.00"):
            raise ValueError("auto_refund_limit_usd cannot be negative")
        return val

    @field_validator("return_window_days")
    @classmethod
    def _valid_return_window(cls, val: int) -> int:
        if val < 1 or val > 90:
            raise ValueError("return_window_days must be between 1 and 90")
        return val


class MerchantPayPalVerifyIn(BaseModel):
    paypal_environment: Optional[str] = None
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None

    @field_validator("paypal_client_id", "paypal_client_secret", mode="before")
    @classmethod
    def _strip_empty_to_none(cls, val: Any) -> Any:
        if isinstance(val, str):
            cleaned = val.strip()
            return cleaned if cleaned else None
        return val

    @field_validator("paypal_environment", mode="before")
    @classmethod
    def _normalize_optional_environment(cls, val: Any) -> Optional[str]:
        if val is None:
            return None
        cleaned = str(val).strip().upper()
        if not cleaned:
            return None
        if cleaned not in ("SANDBOX", "LIVE"):
            raise ValueError("paypal_environment must be SANDBOX or LIVE")
        return cleaned


class MerchantPaymentPreferenceOut(BaseModel):
    merchant_id: int
    payout_paypal_email: Optional[str] = None
    payout_currency: str
    auto_refund_limit_usd: MoneyField
    return_window_days: int
    is_active: bool
    payment_provider_mode: str = "MERCHANT_DIRECT"
    paypal_sandbox_enabled: bool = True
    paypal_configured: bool = False
    paypal_environment: str = "SANDBOX"
    paypal_client_id: Optional[str] = None
    has_client_secret: bool = False
    client_secret_last4: Optional[str] = None
    paypal_webhook_id: Optional[str] = None
    webhook_callback_path: str = ""
    credential_verified_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MerchantOrderAllocationOut(BaseModel):
    id: int
    order_id: int
    order_number: Optional[str] = None
    merchant_id: Optional[int] = None
    gross_inr: MoneyField
    gross_usd: MoneyField
    platform_fee_usd: MoneyField
    net_merchant_usd: MoneyField
    refunded_usd: MoneyField
    fulfillment_status: str
    settlement_status: str
    payment_status: Optional[str] = None
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
