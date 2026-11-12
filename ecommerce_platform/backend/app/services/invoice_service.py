from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.core.minio_client import minio_storage


def _fmt_money(value) -> str:
    dec = Decimal(str(value if value is not None else "0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{dec:,.2f}"


def generate_order_invoice_pdf(order, customer_name: str, customer_email: str) -> str:
    """Generates a styled PDF invoice for an Order and stores it in MinIO 'invoices' bucket."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Header Background (Shipkart Blue)
    c.setFillColor(colors.HexColor("#2874f0"))
    c.rect(0, height - 85, width, 85, fill=1, stroke=0)

    # Title
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, height - 45, "Shipkart")
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.HexColor("#ffe11b"))
    c.drawString(40, height - 62, "Tax Invoice / Bill of Supply")

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 40, height - 45, f"Order ID: {order.order_number}")
    c.setFont("Helvetica", 9)
    date_str = (
        order.created_at.strftime("%d %b %Y, %H:%M UTC")
        if order.created_at
        else datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    )
    c.drawRightString(width - 40, height - 62, f"Order Date: {date_str}")

    # Customer & Billing Block
    y = height - 125
    c.setFillColor(colors.HexColor("#212121"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Billing & Shipping Details:")
    c.setFont("Helvetica", 10)
    addr = order.shipping_address or {}
    c.drawString(40, y - 18, f"Customer: {addr.get('full_name', customer_name)} ({customer_email})")
    c.drawString(40, y - 34, f"Address: {addr.get('street_address', '')}, {addr.get('locality', '')}")
    c.drawString(40, y - 50, f"{addr.get('city', '')}, {addr.get('state', '')} - {addr.get('pincode', '')}")
    c.drawString(40, y - 66, f"Phone: {addr.get('phone', 'N/A')}")

    # Payment Status Block
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 40, y, "Payment Status:")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 40, y - 18, f"Method: {order.payment_method}")
    c.drawRightString(width - 40, y - 34, f"State: {order.payment_status}")
    c.drawRightString(width - 40, y - 50, f"Order Status: {order.status.value}")

    # Line Separator
    y -= 90
    c.setStrokeColor(colors.HexColor("#e0e0e0"))
    c.line(40, y, width - 40, y)

    # Table Header
    y -= 25
    c.setFillColor(colors.HexColor("#f1f3f6"))
    c.rect(40, y - 6, width - 80, 22, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#212121"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, y, "Item Description")
    c.drawRightString(width - 190, y, "Qty")
    c.drawRightString(width - 115, y, "MRP")
    c.drawRightString(width - 48, y, "Total (INR)")

    # Line Items
    y -= 25
    c.setFont("Helvetica", 9.5)
    for item in order.items:
        title = item.title[:58] + "..." if len(item.title) > 58 else item.title
        line_total = Decimal(str(item.price)) * int(item.quantity)
        c.drawString(48, y, title)
        c.drawRightString(width - 190, y, str(item.quantity))
        c.drawRightString(width - 115, y, f"Rs. {_fmt_money(item.mrp)}")
        c.drawRightString(width - 48, y, f"Rs. {_fmt_money(line_total)}")
        y -= 20
        if y < 140:
            c.showPage()
            y = height - 60

    # Totals Section
    y -= 15
    c.line(40, y, width - 40, y)
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 160, y, "Total MRP:")
    c.drawRightString(width - 48, y, f"Rs. {_fmt_money(order.total_mrp)}")

    y -= 18
    c.setFillColor(colors.HexColor("#388e3c"))
    c.drawRightString(width - 160, y, "Discount Savings:")
    c.drawRightString(width - 48, y, f"- Rs. {_fmt_money(order.total_discount)}")

    y -= 22
    c.setFillColor(colors.HexColor("#212121"))
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 160, y, "Grand Total:")
    c.drawRightString(width - 48, y, f"Rs. {_fmt_money(order.total_amount)}")

    # PayPal Settlement Details (if paid via PayPal)
    if getattr(order, "paypal_order_id", None) or getattr(order, "paypal_capture_id", None):
        y -= 32
        if y < 110:
            c.showPage()
            y = height - 60
        c.setFillColor(colors.HexColor("#f4f8ff"))
        c.rect(40, y - 52, width - 80, 68, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#003087"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "PayPal Settlement Receipt Details")
        c.setFillColor(colors.HexColor("#212121"))
        c.setFont("Helvetica", 9)
        c.drawString(50, y - 16, f"PayPal Order ID: {order.paypal_order_id or 'N/A'}")
        c.drawString(50, y - 30, f"PayPal Capture ID: {order.paypal_capture_id or 'N/A'}")
        if getattr(order, "paypal_amount", None) is not None:
            currency = getattr(order, "paypal_currency", None) or "USD"
            c.drawString(50, y - 44, f"Settlement Amount ({currency}): {currency} {_fmt_money(order.paypal_amount)}")

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#878787"))
    c.drawCentredString(
        width / 2,
        40,
        "Generated automatically by Shipkart E-Commerce Platform | Thank you for shopping with Shipkart!",
    )

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    object_name = f"INV_{order.order_number}.pdf"
    minio_storage.upload_bytes(
        bucket=settings.BUCKET_INVOICES,
        object_name=object_name,
        data=pdf_bytes,
        content_type="application/pdf",
    )
    return object_name
