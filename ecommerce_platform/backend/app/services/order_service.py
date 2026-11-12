"""Shared order computation, timeline, and multi-merchant allocation helpers."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    CartItem,
    MerchantOrderAllocation,
    Product,
    quantize_money,
)


def initial_tracking_timeline(
    *,
    ordered_completed: bool = True,
    ordered_detail: str = "Your order has been placed and confirmed.",
) -> List[Dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat() if ordered_completed else None
    return [
        {
            "step": "ORDERED",
            "title": "Order Placed",
            "detail": ordered_detail,
            "time": now_iso,
            "completed": ordered_completed,
        },
        {
            "step": "PACKED",
            "title": "Packed",
            "detail": "Seller is packing your item with Shipkart Assured quality check.",
            "time": None,
            "completed": False,
        },
        {
            "step": "SHIPPED",
            "title": "Shipped",
            "detail": "Package is in transit via Express Logistics.",
            "time": None,
            "completed": False,
        },
        {
            "step": "OUT_FOR_DELIVERY",
            "title": "Out for Delivery",
            "detail": "Delivery executive will deliver today.",
            "time": None,
            "completed": False,
        },
        {
            "step": "DELIVERED",
            "title": "Delivered",
            "detail": "Package delivered to recipient.",
            "time": None,
            "completed": False,
        },
    ]


def resolve_checkout_items(
    db: Session,
    user_id: int,
    buy_now_product_id: Optional[int],
    buy_now_quantity: Optional[int],
) -> List[Tuple[Product, int]]:
    """Resolves either a single buy-now product or the customer's active cart items."""
    if buy_now_product_id:
        product = (
            db.query(Product)
            .filter(Product.id == buy_now_product_id, Product.is_active == True)
            .first()
        )
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        qty = int(buy_now_quantity or 1)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be at least 1")
        return [(product, qty)]

    cart_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    items: List[Tuple[Product, int]] = []
    for ci in cart_items:
        if not ci.product or not ci.product.is_active:
            raise HTTPException(status_code=404, detail="One or more cart products are unavailable")
        if ci.quantity <= 0:
            raise HTTPException(status_code=400, detail="Invalid cart item quantity")
        items.append((ci.product, int(ci.quantity)))
    return items


def resolve_checkout_groups(
    db: Session,
    user_id: int,
    buy_now_product_id: Optional[int],
    buy_now_quantity: Optional[int],
) -> Dict[Optional[int], List[Tuple[Product, int]]]:
    """Groups active checkout items by owning merchant_id (None for starter platform catalog)."""
    items_to_order = resolve_checkout_items(
        db,
        user_id,
        buy_now_product_id,
        buy_now_quantity,
    )
    grouped: Dict[Optional[int], List[Tuple[Product, int]]] = {}
    for product, qty in items_to_order:
        grouped.setdefault(product.merchant_id, []).append((product, qty))
    return grouped


def compute_order_totals(
    items_to_order: List[Tuple[Product, int]],
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns exact Decimal (total_mrp, total_selling_inr, total_discount_inr, total_usd)."""
    total_mrp = Decimal("0.00")
    total_selling = Decimal("0.00")
    total_usd = Decimal("0.00")

    for product, qty in items_to_order:
        q = Decimal(qty)
        total_mrp += quantize_money(product.mrp) * q
        total_selling += quantize_money(product.price) * q
        total_usd += quantize_money(product.sandbox_usd_price) * q

    total_mrp = quantize_money(total_mrp)
    total_selling = quantize_money(total_selling)
    total_discount = quantize_money(total_mrp - total_selling)
    total_usd = quantize_money(total_usd)
    return total_mrp, total_selling, total_discount, total_usd


def create_merchant_allocations(
    db: Session,
    order_id: int,
    items_to_order: List[Tuple[Product, int]],
    *,
    fulfillment_status: str,
    settlement_status: str,
) -> List[MerchantOrderAllocation]:
    """Creates per-merchant gross/net ledger allocation splits inside the parent order."""
    grouped: Dict[Optional[int], Dict[str, Decimal]] = {}
    for product, qty in items_to_order:
        mid = product.merchant_id
        q = Decimal(qty)
        bucket = grouped.setdefault(
            mid,
            {"gross_inr": Decimal("0.00"), "gross_usd": Decimal("0.00")},
        )
        bucket["gross_inr"] += quantize_money(product.price) * q
        bucket["gross_usd"] += quantize_money(product.sandbox_usd_price) * q

    allocations: List[MerchantOrderAllocation] = []
    for mid, sums in grouped.items():
        gross_inr = quantize_money(sums["gross_inr"])
        gross_usd = quantize_money(sums["gross_usd"])
        platform_fee_usd = Decimal("0.00")
        net_merchant_usd = quantize_money(gross_usd - platform_fee_usd)
        alloc = MerchantOrderAllocation(
            order_id=order_id,
            merchant_id=mid,
            gross_inr=gross_inr,
            gross_usd=gross_usd,
            platform_fee_usd=platform_fee_usd,
            net_merchant_usd=net_merchant_usd,
            refunded_usd=Decimal("0.00"),
            fulfillment_status=fulfillment_status,
            settlement_status=settlement_status,
        )
        db.add(alloc)
        allocations.append(alloc)

    db.flush()
    return allocations
