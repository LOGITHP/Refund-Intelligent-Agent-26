from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    cart,
    invoices,
    media,
    merchant_payments,
    orders,
    payments,
    products,
    returns,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(cart.router, prefix="/cart", tags=["Cart"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(returns.router, prefix="/returns", tags=["Returns & Refunds"])
api_router.include_router(media.router, prefix="/media", tags=["Media"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(merchant_payments.router, prefix="/merchant", tags=["Merchant Payments"])
