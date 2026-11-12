from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from app.db.models import OrderStatus, ReturnStatus
from app.schemas.money import MoneyField, OptionalMoneyField
from app.schemas.product import ProductOut


class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int


class CartItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    created_at: datetime
    product: ProductOut

    model_config = ConfigDict(from_attributes=True)


class CartSummary(BaseModel):
    items: List[CartItemOut]
    total_items: int
    total_mrp: MoneyField
    total_selling_price: MoneyField
    total_discount: MoneyField
    delivery_fee: MoneyField = Decimal("0.00")
    final_amount: MoneyField
    paypal_currency: str = "USD"
    paypal_amount: OptionalMoneyField = None


class OrderCreate(BaseModel):
    shipping_address: Dict[str, Any]
    payment_method: str = "STANDARD_CHECKOUT"
    # Optional buy_now single item bypass:
    buy_now_product_id: Optional[int] = None
    buy_now_quantity: Optional[int] = 1


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    merchant_id: Optional[int] = None
    title: str
    image_url: str
    quantity: int
    price: MoneyField
    mrp: MoneyField

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    order_number: str
    user_id: int
    merchant_id: Optional[int] = None
    total_mrp: MoneyField
    total_discount: MoneyField
    total_amount: MoneyField
    original_currency: str = "INR"
    paypal_currency: Optional[str] = None
    paypal_amount: OptionalMoneyField = None
    payment_method: str
    payment_status: str
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    payment_provider_mode: str = "MERCHANT_DIRECT"
    status: OrderStatus
    shipping_address: Dict[str, Any]
    invoice_object_name: Optional[str] = None
    tracking_history: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemOut]

    model_config = ConfigDict(from_attributes=True)


class ReturnCreate(BaseModel):
    order_id: int
    order_item_id: int
    reason: str
    comments: Optional[str] = None
    evidence_urls: List[str] = []


class ReturnDecisionUpdate(BaseModel):
    status: ReturnStatus
    merchant_notes: Optional[str] = None
    refund_transaction_id: Optional[str] = None


class ReturnOut(BaseModel):
    id: int
    return_number: str
    order_id: int
    order_item_id: int
    user_id: int
    merchant_id: Optional[int] = None
    product_id: int
    reason: str
    comments: Optional[str] = None
    evidence_urls: List[str]
    refund_amount: MoneyField
    refund_currency: str = "USD"
    refund_paypal_amount: OptionalMoneyField = None
    status: ReturnStatus
    merchant_notes: Optional[str] = None
    agent_risk_score: Optional[float] = None
    agent_reasoning: Optional[str] = None
    refund_transaction_id: Optional[str] = None
    tracking_history: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    product: Optional[ProductOut] = None

    model_config = ConfigDict(from_attributes=True)
