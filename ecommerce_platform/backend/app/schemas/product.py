from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.money import MoneyField, OptionalMoneyField


class ProductBase(BaseModel):
    title: str
    brand: str
    category: str
    description: str
    highlights: List[str] = []
    specifications: Dict[str, str] = {}
    price: MoneyField
    mrp: MoneyField
    sandbox_usd_price: OptionalMoneyField = None
    stock: int = 10
    image_url: str
    gallery_urls: List[str] = []
    is_assured: bool = True
    return_window_days: int = 7


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    highlights: Optional[List[str]] = None
    specifications: Optional[Dict[str, str]] = None
    price: OptionalMoneyField = None
    mrp: OptionalMoneyField = None
    sandbox_usd_price: OptionalMoneyField = None
    stock: Optional[int] = None
    image_url: Optional[str] = None
    gallery_urls: Optional[List[str]] = None
    is_assured: Optional[bool] = None
    return_window_days: Optional[int] = None
    is_active: Optional[bool] = None


class ProductOut(ProductBase):
    id: int
    merchant_id: Optional[int] = None
    seller_name: Optional[str] = None
    paypal_ready: bool = False
    sandbox_usd_price: MoneyField
    rating: float
    reviews_count: int
    is_active: bool
    created_at: datetime
    available_stock: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ClaimStarterOut(BaseModel):
    claimed_count: int
    products: List[ProductOut]
