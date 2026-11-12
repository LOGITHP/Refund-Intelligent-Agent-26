"""Inventory reservation and atomic stock conversion service."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Iterable, List, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    InventoryReservation,
    MerchantOrderAllocation,
    Order,
    OrderStatus,
    PaymentLedgerEvent,
    Product,
    utcnow,
)

logger = logging.getLogger(__name__)


class InsufficientStockError(Exception):
    """Raised when available (physical minus active reserved) stock cannot satisfy order quantity."""


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _supports_row_lock(db: Session) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def release_expired_reservations(db: Session, *, auto_commit: bool = True) -> int:
    """Marks expired ACTIVE reservations as EXPIRED, cancels PENDING_PAYMENT orders, and logs ledger events."""
    now = utcnow()
    query = db.query(InventoryReservation).filter(InventoryReservation.status == "ACTIVE")
    if _supports_row_lock(db):
        query = query.with_for_update()

    active_rows = query.all()
    expired_rows = [row for row in active_rows if _as_utc(row.expires_at) <= now]
    if not expired_rows:
        return 0

    affected_order_ids = sorted({row.order_id for row in expired_rows})
    for row in expired_rows:
        row.status = "EXPIRED"

    orders_query = db.query(Order).filter(Order.id.in_(affected_order_ids))
    if _supports_row_lock(db):
        orders_query = orders_query.with_for_update()

    for order in orders_query.all():
        if order.status == OrderStatus.PENDING_PAYMENT:
            order.status = OrderStatus.CANCELLED
            order.payment_status = "EXPIRED"
            db.query(MerchantOrderAllocation).filter(
                MerchantOrderAllocation.order_id == order.id,
                MerchantOrderAllocation.settlement_status == "PENDING",
            ).update(
                {
                    "fulfillment_status": "CANCELLED",
                    "settlement_status": "EXPIRED",
                },
                synchronize_session=False,
            )
            db.add(
                PaymentLedgerEvent(
                    order_id=order.id,
                    event_type="RESERVATION_EXPIRED",
                    paypal_order_id=order.paypal_order_id,
                    amount=order.paypal_amount,
                    currency=order.paypal_currency,
                    status_snapshot="EXPIRED",
                    redacted_payload={
                        "order_number": order.order_number,
                        "reason": "Inventory reservation TTL expired before capture",
                    },
                )
            )

    if auto_commit:
        db.commit()
    else:
        db.flush()

    logger.info("Expired %d inventory reservation(s) across %d order(s).", len(expired_rows), len(affected_order_ids))
    return len(expired_rows)


def get_available_stock(db: Session, product_id: int, *, auto_commit: bool = True) -> int:
    """Returns sellable stock: physical Product.stock minus active unexpired reservations."""
    release_expired_reservations(db, auto_commit=auto_commit)
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        return 0

    now = utcnow()
    active_holds = (
        db.query(InventoryReservation)
        .filter(
            InventoryReservation.product_id == product_id,
            InventoryReservation.status == "ACTIVE",
        )
        .all()
    )
    reserved_qty = sum(r.quantity for r in active_holds if _as_utc(r.expires_at) > now)
    return max(0, int(product.stock) - int(reserved_qty))


def get_available_stock_map(db: Session, products: Iterable[Product], *, auto_commit: bool = True) -> dict[int, int]:
    """Batch-computes sellable stock for multiple products without N+1 queries."""
    release_expired_reservations(db, auto_commit=auto_commit)
    prod_list = list(products)
    if not prod_list:
        return {}

    product_ids = [p.id for p in prod_list]
    now = utcnow()
    active_holds = (
        db.query(InventoryReservation)
        .filter(
            InventoryReservation.product_id.in_(product_ids),
            InventoryReservation.status == "ACTIVE",
        )
        .all()
    )
    reserved_map: dict[int, int] = {}
    for hold in active_holds:
        if _as_utc(hold.expires_at) > now:
            reserved_map[hold.product_id] = reserved_map.get(hold.product_id, 0) + int(hold.quantity)

    return {
        p.id: max(0, int(p.stock) - reserved_map.get(p.id, 0))
        for p in prod_list
    }


def reserve_items_for_order(
    db: Session,
    order_id: int,
    items: Iterable[Tuple[Product, int]],
    ttl_minutes: int | None = None,
) -> List[InventoryReservation]:
    """Locks product rows in deterministic order, checks available stock, and inserts ACTIVE reservations."""
    release_expired_reservations(db, auto_commit=False)

    item_list = list(items)
    if not item_list:
        raise InsufficientStockError("Cannot reserve empty item list")

    # Aggregate requested quantity per product_id in case duplicate lines appear
    qty_by_product: dict[int, int] = {}
    for prod, qty in item_list:
        if qty <= 0:
            raise InsufficientStockError(f"Invalid quantity {qty} for {prod.title}")
        qty_by_product[prod.id] = qty_by_product.get(prod.id, 0) + int(qty)

    sorted_product_ids = sorted(qty_by_product.keys())
    prod_query = (
        db.query(Product)
        .filter(Product.id.in_(sorted_product_ids), Product.is_active == True)
        .order_by(Product.id.asc())
    )
    if _supports_row_lock(db):
        prod_query = prod_query.with_for_update()

    locked_products = {p.id: p for p in prod_query.all()}
    if len(locked_products) != len(sorted_product_ids):
        raise InsufficientStockError("One or more products are unavailable")

    res_query = db.query(InventoryReservation).filter(
        InventoryReservation.product_id.in_(sorted_product_ids),
        InventoryReservation.status == "ACTIVE",
    )
    if _supports_row_lock(db):
        res_query = res_query.with_for_update()

    now = utcnow()
    reserved_by_product: dict[int, int] = {}
    for hold in res_query.all():
        if _as_utc(hold.expires_at) > now:
            reserved_by_product[hold.product_id] = reserved_by_product.get(hold.product_id, 0) + int(hold.quantity)

    ttl = ttl_minutes if ttl_minutes is not None else settings.RESERVATION_TTL_MINUTES
    expires_at = now + timedelta(minutes=ttl)

    created_reservations: List[InventoryReservation] = []
    for pid in sorted_product_ids:
        product = locked_products[pid]
        requested = qty_by_product[pid]
        already_reserved = reserved_by_product.get(pid, 0)
        available = int(product.stock) - already_reserved
        if available < requested:
            raise InsufficientStockError(
                f"Insufficient stock for {product.title} (available: {max(0, available)}, requested: {requested})"
            )

        reservation = InventoryReservation(
            order_id=order_id,
            product_id=pid,
            quantity=requested,
            status="ACTIVE",
            expires_at=expires_at,
        )
        db.add(reservation)
        created_reservations.append(reservation)

    db.flush()
    return created_reservations


def release_order_reservations(db: Session, order_id: int, new_status: str = "RELEASED") -> int:
    """Releases ACTIVE reservations belonging to an order (e.g. failed PayPal order creation)."""
    query = db.query(InventoryReservation).filter(
        InventoryReservation.order_id == order_id,
        InventoryReservation.status == "ACTIVE",
    )
    if _supports_row_lock(db):
        query = query.with_for_update()

    rows = query.all()
    for row in rows:
        row.status = new_status
    if rows:
        db.flush()
    return len(rows)


def convert_reservations_on_capture(db: Session, order: Order) -> bool:
    """Atomically deducts Product.stock and marks reservations CONVERTED on PayPal capture.

    Returns False without deducting stock if reservations expired and remaining available stock
    is insufficient so the caller places the order in CAPTURE_EXCEPTION instead of overselling.
    """
    if not order.items:
        return False

    qty_by_product: dict[int, int] = {}
    for item in order.items:
        qty_by_product[item.product_id] = qty_by_product.get(item.product_id, 0) + int(item.quantity)

    sorted_product_ids = sorted(qty_by_product.keys())
    prod_query = (
        db.query(Product)
        .filter(Product.id.in_(sorted_product_ids))
        .order_by(Product.id.asc())
    )
    if _supports_row_lock(db):
        prod_query = prod_query.with_for_update()

    locked_products = {p.id: p for p in prod_query.all()}

    order_res_query = db.query(InventoryReservation).filter(
        InventoryReservation.order_id == order.id
    )
    if _supports_row_lock(db):
        order_res_query = order_res_query.with_for_update()
    order_reservations = {r.product_id: r for r in order_res_query.all()}

    other_res_query = db.query(InventoryReservation).filter(
        InventoryReservation.product_id.in_(sorted_product_ids),
        InventoryReservation.order_id != order.id,
        InventoryReservation.status == "ACTIVE",
    )
    if _supports_row_lock(db):
        other_res_query = other_res_query.with_for_update()

    now = utcnow()
    other_reserved: dict[int, int] = {}
    for hold in other_res_query.all():
        if _as_utc(hold.expires_at) > now:
            other_reserved[hold.product_id] = other_reserved.get(hold.product_id, 0) + int(hold.quantity)

    # First pass: verify EVERY line item can be fulfilled without overselling
    for pid in sorted_product_ids:
        product = locked_products.get(pid)
        needed = qty_by_product[pid]
        if not product or int(product.stock) < needed:
            _expire_order_active_holds(order_reservations.values())
            return False

        res = order_reservations.get(pid)
        is_active_unexpired = (
            res is not None
            and res.status == "ACTIVE"
            and _as_utc(res.expires_at) > now
            and res.quantity >= needed
        )
        if not is_active_unexpired:
            available_without_this_hold = int(product.stock) - other_reserved.get(pid, 0)
            if available_without_this_hold < needed:
                _expire_order_active_holds(order_reservations.values())
                return False

    # Second pass: atomically deduct stock and convert reservations
    for pid in sorted_product_ids:
        product = locked_products[pid]
        product.stock = int(product.stock) - qty_by_product[pid]
        res = order_reservations.get(pid)
        if res is not None:
            res.status = "CONVERTED"

    db.flush()
    return True


def _expire_order_active_holds(reservations: Iterable[InventoryReservation]) -> None:
    for res in reservations:
        if res.status == "ACTIVE":
            res.status = "EXPIRED"
