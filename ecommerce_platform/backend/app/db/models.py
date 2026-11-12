from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    event,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def quantize_money(value) -> Decimal:
    """Converts numeric/string input to exact 2-decimal Decimal using ROUND_HALF_UP."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ORDERED = "ORDERED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    CAPTURE_EXCEPTION = "CAPTURE_EXCEPTION"


class ReturnStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    PICKUP_SCHEDULED = "PICKUP_SCHEDULED"
    REFUND_INITIATED = "REFUND_INITIATED"
    REFUNDED = "REFUNDED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=True)
    role = Column(SqlEnum(UserRole), default=UserRole.CUSTOMER, nullable=False)
    business_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    products = relationship("Product", back_populates="merchant")
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", foreign_keys="[Order.user_id]", back_populates="user")
    return_requests = relationship("ReturnRequest", foreign_keys="[ReturnRequest.user_id]", back_populates="user")
    payment_preference = relationship(
        "MerchantPaymentPreference",
        back_populates="merchant",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=False)
    pincode = Column(String(20), nullable=False)
    locality = Column(String(255), nullable=False)
    street_address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    address_type = Column(String(32), default="HOME", nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="addresses")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(500), nullable=False, index=True)
    brand = Column(String(120), nullable=False, index=True)
    category = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=False)
    highlights = Column(JSON, default=list, nullable=False)
    specifications = Column(JSON, default=dict, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    mrp = Column(Numeric(12, 2), nullable=False)
    sandbox_usd_price = Column(Numeric(12, 2), nullable=False, default=Decimal("10.00"))
    stock = Column(Integer, default=10, nullable=False)
    rating = Column(Float, default=4.5, nullable=False)
    reviews_count = Column(Integer, default=120, nullable=False)
    image_url = Column(String(1000), nullable=False)
    gallery_urls = Column(JSON, default=list, nullable=False)
    is_assured = Column(Boolean, default=True, nullable=False)
    return_window_days = Column(Integer, default=7, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    merchant = relationship("User", back_populates="products")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    total_mrp = Column(Numeric(12, 2), nullable=False)
    total_discount = Column(Numeric(12, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    original_currency = Column(String(8), default="INR", nullable=False)
    paypal_currency = Column(String(8), nullable=True)
    paypal_amount = Column(Numeric(12, 2), nullable=True)
    payment_method = Column(String(64), default="STANDARD_CHECKOUT", nullable=False)
    payment_status = Column(String(64), default="CONFIRMED", nullable=False)
    paypal_order_id = Column(String(128), nullable=True, index=True)
    paypal_capture_id = Column(String(128), nullable=True, index=True)
    paypal_create_request_id = Column(String(128), nullable=True)
    paypal_capture_request_id = Column(String(128), nullable=True)
    payment_provider_mode = Column(String(64), default="MERCHANT_DIRECT", nullable=False)
    status = Column(SqlEnum(OrderStatus), default=OrderStatus.ORDERED, nullable=False)
    shipping_address = Column(JSON, nullable=False)
    invoice_object_name = Column(String(255), nullable=True)
    tracking_history = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    return_requests = relationship("ReturnRequest", back_populates="order")
    allocations = relationship("MerchantOrderAllocation", back_populates="order", cascade="all, delete-orphan")
    reservations = relationship("InventoryReservation", back_populates="order", cascade="all, delete-orphan")
    ledger_events = relationship("PaymentLedgerEvent", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(500), nullable=False)
    image_url = Column(String(1000), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    mrp = Column(Numeric(12, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id = Column(Integer, primary_key=True, index=True)
    return_number = Column(String(64), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    reason = Column(String(255), nullable=False)
    comments = Column(Text, nullable=True)
    evidence_urls = Column(JSON, default=list, nullable=False)
    refund_amount = Column(Numeric(12, 2), nullable=False)
    refund_currency = Column(String(8), default="USD", nullable=False)
    refund_paypal_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(SqlEnum(ReturnStatus), default=ReturnStatus.REQUESTED, nullable=False)
    merchant_notes = Column(Text, nullable=True)
    agent_risk_score = Column(Float, nullable=True)
    agent_reasoning = Column(Text, nullable=True)
    refund_transaction_id = Column(String(128), nullable=True)
    tracking_history = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    order = relationship("Order", back_populates="return_requests")
    order_item = relationship("OrderItem")
    user = relationship("User", foreign_keys=[user_id], back_populates="return_requests")
    product = relationship("Product")


class MerchantPaymentPreference(Base):
    __tablename__ = "merchant_payment_preferences"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    payout_paypal_email = Column(String(255), nullable=True)
    payout_currency = Column(String(8), default="USD", nullable=False)
    auto_refund_limit_usd = Column(Numeric(12, 2), default=Decimal("150.00"), nullable=False)
    return_window_days = Column(Integer, default=7, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    paypal_environment = Column(String(16), default="SANDBOX", nullable=False)
    paypal_client_id = Column(String(255), nullable=True)
    encrypted_paypal_client_secret = Column(Text, nullable=True)
    paypal_client_secret_last4 = Column(String(8), nullable=True)
    paypal_webhook_id = Column(String(255), nullable=True)
    credential_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    merchant = relationship("User", back_populates="payment_preference")


class MerchantOrderAllocation(Base):
    __tablename__ = "merchant_order_allocations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    gross_inr = Column(Numeric(12, 2), nullable=False)
    gross_usd = Column(Numeric(12, 2), nullable=False)
    platform_fee_usd = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    net_merchant_usd = Column(Numeric(12, 2), nullable=False)
    refunded_usd = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    fulfillment_status = Column(String(64), default="ORDERED", nullable=False)
    settlement_status = Column(String(64), default="PENDING", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    order = relationship("Order", back_populates="allocations")


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    order = relationship("Order", back_populates="reservations")
    product = relationship("Product")


class PaymentLedgerEvent(Base):
    """Append-only immutable financial & payment audit ledger."""

    __tablename__ = "payment_ledger_events"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    return_request_id = Column(Integer, ForeignKey("return_requests.id"), nullable=True, index=True)
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    paypal_order_id = Column(String(128), nullable=True, index=True)
    paypal_capture_id = Column(String(128), nullable=True, index=True)
    paypal_refund_id = Column(String(128), nullable=True, index=True)
    idempotency_key = Column(String(128), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(8), nullable=True)
    status_snapshot = Column(String(64), nullable=True)
    redacted_payload = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    order = relationship("Order", back_populates="ledger_events")


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    event_id = Column(String(128), primary_key=True, index=True)
    event_type = Column(String(128), nullable=False, index=True)
    transmission_id = Column(String(128), nullable=True)
    verification_status = Column(String(64), nullable=False)
    raw_redacted_payload = Column(JSON, default=dict, nullable=False)
    processed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


@event.listens_for(PaymentLedgerEvent, "before_update")
def _prevent_ledger_update(mapper, connection, target):
    raise ValueError("PaymentLedgerEvent is append-only and cannot be updated")


@event.listens_for(PaymentLedgerEvent, "before_delete")
def _prevent_ledger_delete(mapper, connection, target):
    raise ValueError("PaymentLedgerEvent is append-only and cannot be deleted")
