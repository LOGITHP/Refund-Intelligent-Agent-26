from decimal import Decimal
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_merchant
from app.db.database import get_db
from app.db.models import MerchantPaymentPreference, Product, User, quantize_money
from app.schemas.product import ClaimStarterOut, ProductCreate, ProductOut, ProductUpdate
from app.services.inventory_service import get_available_stock, get_available_stock_map

router = APIRouter()


def _enrich_products(
    db: Session,
    products: List[Product],
    stock_map: Optional[Dict[int, int]] = None,
) -> List[Product]:
    if not products:
        return products

    if stock_map is None:
        stock_map = get_available_stock_map(db, products)

    merchant_ids = {p.merchant_id for p in products if p.merchant_id is not None}
    seller_names: Dict[int, str] = {}
    ready_merchants: set[int] = set()

    if merchant_ids:
        users = db.query(User).filter(User.id.in_(merchant_ids)).all()
        for u in users:
            seller_names[u.id] = u.business_name or u.full_name

        prefs = (
            db.query(MerchantPaymentPreference)
            .filter(MerchantPaymentPreference.merchant_id.in_(merchant_ids))
            .all()
        )
        for pref in prefs:
            if (
                pref.is_active
                and (pref.paypal_client_id or "").strip()
                and (pref.encrypted_paypal_client_secret or "").strip()
            ):
                ready_merchants.add(pref.merchant_id)

    platform_ready = settings.is_paypal_configured

    for prod in products:
        prod.available_stock = stock_map.get(prod.id, int(prod.stock))
        if prod.merchant_id is None:
            prod.seller_name = "Shipkart Platform Catalog"
            prod.paypal_ready = platform_ready
        else:
            prod.seller_name = seller_names.get(prod.merchant_id) or f"Merchant #{prod.merchant_id}"
            prod.paypal_ready = prod.merchant_id in ready_merchants

    return products


@router.get("/", response_model=List[ProductOut])
def list_products(
    search: Optional[str] = Query(None, description="Search term in title, brand, or description"),
    category: Optional[str] = Query(None, description="Category filter"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    only_assured: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.is_active == True)

    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.title.ilike(search_fmt),
                Product.brand.ilike(search_fmt),
                Product.description.ilike(search_fmt),
                Product.category.ilike(search_fmt),
            )
        )
    if category and category.lower() != "all":
        query = query.filter(Product.category.ilike(f"%{category.strip()}%"))
    if min_price is not None:
        query = query.filter(Product.price >= quantize_money(min_price))
    if max_price is not None:
        query = query.filter(Product.price <= quantize_money(max_price))
    if only_assured:
        query = query.filter(Product.is_assured == True)

    products = query.order_by(Product.rating.desc(), Product.id.asc()).all()
    return _enrich_products(db, products)


@router.get("/merchant/my", response_model=List[ProductOut])
def list_merchant_products(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    products = (
        db.query(Product)
        .filter(or_(Product.merchant_id == current_merchant.id, Product.merchant_id.is_(None)))
        .order_by(Product.id.desc())
        .all()
    )
    return _enrich_products(db, products)


@router.post("/claim-starter", response_model=ClaimStarterOut)
def claim_starter_products(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    starter_ids = [
        row[0]
        for row in db.query(Product.id)
        .filter(Product.merchant_id.is_(None), Product.is_active == True)
        .order_by(Product.id.asc())
        .all()
    ]
    if not starter_ids:
        return ClaimStarterOut(claimed_count=0, products=[])

    claimed_count = (
        db.query(Product)
        .filter(
            Product.id.in_(starter_ids),
            Product.merchant_id.is_(None),
            Product.is_active == True,
        )
        .update({"merchant_id": current_merchant.id}, synchronize_session=False)
    )
    db.commit()

    claimed_products = (
        db.query(Product)
        .filter(Product.id.in_(starter_ids), Product.merchant_id == current_merchant.id)
        .order_by(Product.id.asc())
        .all()
    )
    _enrich_products(db, claimed_products)
    return ClaimStarterOut(claimed_count=int(claimed_count), products=claimed_products)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    _enrich_products(db, [product])
    return product


@router.post("/{product_id}/claim", response_model=ProductOut)
def claim_product(
    product_id: int,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True,
        Product.merchant_id.is_(None),
    ).update({"merchant_id": current_merchant.id}, synchronize_session=False)
    db.commit()

    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.merchant_id != current_merchant.id:
        raise HTTPException(status_code=409, detail="Product is already claimed by another merchant")

    _enrich_products(db, [product])
    return product


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    prod_in: ProductCreate,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    data = prod_in.model_dump()
    if data.get("sandbox_usd_price") is None or data["sandbox_usd_price"] <= Decimal("0.00"):
        derived = quantize_money(Decimal(data["price"]) / Decimal("85"))
        data["sandbox_usd_price"] = max(Decimal("1.00"), derived)

    product = Product(
        merchant_id=current_merchant.id,
        **data,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    _enrich_products(db, [product], stock_map={product.id: int(product.stock)})
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    prod_in: ProductUpdate,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.merchant_id is not None and product.merchant_id != current_merchant.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify another merchant's product")

    if product.merchant_id is None:
        product.merchant_id = current_merchant.id

    update_data = prod_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if field == "sandbox_usd_price" and val is not None and val <= Decimal("0.00"):
            raise HTTPException(status_code=400, detail="sandbox_usd_price must be positive")
        setattr(product, field, val)

    db.commit()
    db.refresh(product)
    _enrich_products(db, [product])
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.merchant_id is not None and product.merchant_id != current_merchant.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete another merchant's product")

    product.is_active = False
    db.commit()
    return None
