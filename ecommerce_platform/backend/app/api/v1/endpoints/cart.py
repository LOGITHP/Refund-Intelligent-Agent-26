from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_customer
from app.db.database import get_db
from app.db.models import CartItem, Product, User, quantize_money
from app.schemas.order import CartItemCreate, CartItemOut, CartItemUpdate, CartSummary
from app.services.inventory_service import get_available_stock

router = APIRouter()


def build_cart_summary(items: list[CartItem]) -> CartSummary:
    total_items = sum(item.quantity for item in items)
    total_mrp = Decimal("0.00")
    total_selling = Decimal("0.00")
    paypal_amount = Decimal("0.00")

    for item in items:
        q = Decimal(item.quantity)
        total_mrp += quantize_money(item.product.mrp) * q
        total_selling += quantize_money(item.product.price) * q
        paypal_amount += quantize_money(item.product.sandbox_usd_price) * q

    total_mrp = quantize_money(total_mrp)
    total_selling = quantize_money(total_selling)
    total_discount = quantize_money(total_mrp - total_selling)
    paypal_amount = quantize_money(paypal_amount)
    delivery_fee = (
        Decimal("0.00")
        if total_selling >= Decimal("500.00") or total_items == 0
        else Decimal("40.00")
    )

    return CartSummary(
        items=[CartItemOut.model_validate(item) for item in items],
        total_items=total_items,
        total_mrp=total_mrp,
        total_selling_price=total_selling,
        total_discount=total_discount,
        delivery_fee=delivery_fee,
        final_amount=quantize_money(total_selling + delivery_fee),
        paypal_currency="USD",
        paypal_amount=paypal_amount,
    )


@router.get("/", response_model=CartSummary)
def get_cart(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    return build_cart_summary(items)


@router.post("/items", response_model=CartSummary, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    item_in: CartItemCreate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    if item_in.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    product = db.query(Product).filter(Product.id == item_in.product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    available = get_available_stock(db, product.id)
    if available < item_in.quantity:
        raise HTTPException(status_code=400, detail="Insufficient product stock")

    existing = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user.id, CartItem.product_id == item_in.product_id)
        .first()
    )
    if existing:
        existing.quantity += item_in.quantity
        if existing.quantity > available:
            existing.quantity = available
    else:
        existing = CartItem(
            user_id=current_user.id,
            product_id=item_in.product_id,
            quantity=item_in.quantity,
        )
        db.add(existing)

    db.commit()
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    return build_cart_summary(items)


@router.put("/items/{item_id}", response_model=CartSummary)
def update_cart_item(
    item_id: int,
    item_in: CartItemUpdate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    cart_item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if item_in.quantity <= 0:
        db.delete(cart_item)
    else:
        available = get_available_stock(db, cart_item.product_id)
        if item_in.quantity > available:
            raise HTTPException(status_code=400, detail="Requested quantity exceeds stock")
        cart_item.quantity = item_in.quantity

    db.commit()
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    return build_cart_summary(items)


@router.delete("/items/{item_id}", response_model=CartSummary)
def remove_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    cart_item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(cart_item)
    db.commit()
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    return build_cart_summary(items)


@router.delete("/", response_model=CartSummary)
def clear_cart(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()
    db.commit()
    return build_cart_summary([])
