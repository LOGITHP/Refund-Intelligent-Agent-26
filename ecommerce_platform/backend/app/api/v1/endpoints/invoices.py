from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.minio_client import minio_storage
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Order, OrderStatus, User, UserRole
from app.services.invoice_service import generate_order_invoice_pdf

router = APIRouter()


@router.get("/{order_id}")
def download_invoice(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if current_user.role == UserRole.CUSTOMER and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized to access this invoice")
    if current_user.role == UserRole.MERCHANT:
        owns_item = any(
            item.merchant_id == current_user.id or item.merchant_id is None
            for item in order.items
        )
        if not owns_item:
            raise HTTPException(status_code=403, detail="Unauthorized to access this invoice")

    if order.status == OrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail="Invoice unavailable until payment is captured")

    object_name = order.invoice_object_name
    if not object_name:
        object_name = generate_order_invoice_pdf(
            order,
            customer_name=order.user.full_name,
            customer_email=order.user.email,
        )
        order.invoice_object_name = object_name
        db.commit()

    data, content_type = minio_storage.get_file(settings.BUCKET_INVOICES, object_name)
    if data is None:
        # Regenerate if missing
        object_name = generate_order_invoice_pdf(
            order,
            customer_name=order.user.full_name,
            customer_email=order.user.email,
        )
        data, content_type = minio_storage.get_file(settings.BUCKET_INVOICES, object_name)

    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{object_name}"',
        },
    )
