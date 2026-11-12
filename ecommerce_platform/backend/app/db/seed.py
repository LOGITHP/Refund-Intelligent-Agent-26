from decimal import Decimal
import logging
from app.core.config import settings
from app.core.minio_client import minio_storage
from app.db.database import SessionLocal
from app.db.models import Product

logger = logging.getLogger(__name__)

# Starter Shipkart catalog (no hardcoded user accounts)
SAMPLE_PRODUCTS = [
    {
        "title": "Apple iPhone 15 (Blue, 128 GB)",
        "brand": "Apple",
        "category": "Mobiles",
        "description": "Experience dynamic island, 48MP main camera with 2x Telephoto, durable color-infused glass and aluminum design, and USB-C connectivity.",
        "highlights": ["128 GB ROM", "15.49 cm (6.1 inch) Super Retina XDR Display", "48MP + 12MP Dual Rear Camera", "A16 Bionic Chip Processor"],
        "specifications": {"Model": "iPhone 15", "Color": "Blue", "SIM Type": "Dual SIM (nano + eSIM)", "Battery": "3349 mAh"},
        "price": Decimal("69999.00"),
        "mrp": Decimal("79900.00"),
        "sandbox_usd_price": Decimal("799.00"),
        "stock": 25,
        "rating": 4.7,
        "reviews_count": 8420,
        "filename": "iphone_15.svg",
        "color": "#3880ff",
    },
    {
        "title": "Samsung Galaxy S24 Ultra 5G (Titanium Gray, 512 GB)",
        "brand": "Samsung",
        "category": "Mobiles",
        "description": "Meet Galaxy S24 Ultra with Galaxy AI, titanium frame, flat 6.8 inch display, and 200MP camera system with ProVisual engine.",
        "highlights": ["12 GB RAM | 512 GB ROM", "17.27 cm (6.8 inch) Dynamic AMOLED 2X", "200MP Quad Camera", "Snapdragon 8 Gen 3"],
        "specifications": {"Model": "Galaxy S24 Ultra", "Color": "Titanium Gray", "RAM": "12 GB", "Battery": "5000 mAh"},
        "price": Decimal("129999.00"),
        "mrp": Decimal("144999.00"),
        "sandbox_usd_price": Decimal("1299.00"),
        "stock": 14,
        "rating": 4.8,
        "reviews_count": 3150,
        "filename": "s24_ultra.svg",
        "color": "#4a5568",
    },
    {
        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "Industry-leading noise cancellation with two processors and eight microphones for unprecedented sound quality and crystal clear hands-free calling.",
        "highlights": ["Industry Leading Active Noise Cancelling", "Up to 30 Hours Battery Life", "Speak-to-Chat Technology", "Ultra-comfortable, lightweight design"],
        "specifications": {"Type": "Over-Ear", "Connectivity": "Bluetooth 5.2", "Battery Life": "30 hrs", "Microphones": "8 Mics"},
        "price": Decimal("26990.00"),
        "mrp": Decimal("34990.00"),
        "sandbox_usd_price": Decimal("329.00"),
        "stock": 40,
        "rating": 4.6,
        "reviews_count": 1420,
        "filename": "sony_xm5.svg",
        "color": "#1a202c",
    },
    {
        "title": "Apple MacBook Air M3 (16GB Unified Memory, 512GB SSD, Space Gray)",
        "brand": "Apple",
        "category": "Electronics",
        "description": "Supercharged by the next-generation M3 chip, MacBook Air delivers incredible performance and up to 18 hours of battery life in an ultraportable design.",
        "highlights": ["Apple M3 8-core CPU / 10-core GPU", "16GB Unified RAM", "512GB Fast SSD", "Liquid Retina display with True Tone"],
        "specifications": {"Screen Size": "13.6 inch", "Weight": "1.24 kg", "OS": "macOS Sonoma", "Ports": "MagSafe 3, 2x Thunderbolt"},
        "price": Decimal("134900.00"),
        "mrp": Decimal("144900.00"),
        "sandbox_usd_price": Decimal("1499.00"),
        "stock": 18,
        "rating": 4.9,
        "reviews_count": 920,
        "filename": "macbook_air_m3.svg",
        "color": "#718096",
    },
    {
        "title": "Nike Air Jordan 1 Retro High OG (Chicago Reimagined)",
        "brand": "Nike",
        "category": "Fashion",
        "description": "The timeless sneaker icon return with heritage colors, premium aged leather, encapsulated Air-Sole cushioning, and high-top padded collar.",
        "highlights": ["Genuine Leather Upper", "Air-Sole Unit Cushioning", "Solid Rubber Outsole with Deep Flex Grooves"],
        "specifications": {"Size": "UK 9 / US 10", "Color": "Varsity Red / Black / Sail", "Closure": "Lace-Up", "Material": "Full Grain Leather"},
        "price": Decimal("16995.00"),
        "mrp": Decimal("19995.00"),
        "sandbox_usd_price": Decimal("199.00"),
        "stock": 12,
        "rating": 4.9,
        "reviews_count": 540,
        "filename": "jordan_1.svg",
        "color": "#e53e3e",
    },
    {
        "title": "LG 43 inch 4K Ultra HD Smart LED TV (43UR7500PSC)",
        "brand": "LG",
        "category": "Appliances",
        "description": "Real 4K clarity with vivid colors and α5 AI Processor Gen6 for enhanced viewing experience, paired with AI Sound and webOS 23.",
        "highlights": ["4K Ultra HD (3840 x 2160)", "α5 AI Processor 4K Gen6", "webOS with ThinQ AI", "20W 2.0 Ch Speaker with AI Sound"],
        "specifications": {"Screen": "43 Inch", "Resolution": "3840 x 2160", "Refresh Rate": "60 Hz", "HDMI Ports": "3 Ports"},
        "price": Decimal("28990.00"),
        "mrp": Decimal("49990.00"),
        "sandbox_usd_price": Decimal("349.00"),
        "stock": 20,
        "rating": 4.4,
        "reviews_count": 6800,
        "filename": "lg_tv.svg",
        "color": "#2d3748",
    },
]


def generate_svg_icon(title: str, category: str, bg_color: str) -> bytes:
    """Generates an aesthetic SVG product illustration for MinIO storage."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f8fafc" />
      <stop offset="100%" stop-color="#e2e8f0" />
    </linearGradient>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" flood-opacity="0.12" />
    </filter>
  </defs>
  <rect width="400" height="400" rx="16" fill="url(#bgGrad)"/>
  <rect x="50" y="50" width="300" height="300" rx="24" fill="{bg_color}" filter="url(#shadow)"/>
  <circle cx="200" cy="170" r="60" fill="#ffffff" opacity="0.15" />
  <text x="200" y="180" font-family="-apple-system, Roboto, sans-serif" font-size="28" font-weight="bold" fill="#ffffff" text-anchor="middle">{category}</text>
  <text x="200" y="275" font-family="-apple-system, Roboto, sans-serif" font-size="14" font-weight="600" fill="#ffffff" opacity="0.9" text-anchor="middle">{title[:28]}</text>
  <rect x="140" y="300" width="120" height="24" rx="12" fill="#ffe11b" />
  <text x="200" y="316" font-family="-apple-system, Roboto, sans-serif" font-size="11" font-weight="bold" fill="#212121" text-anchor="middle">Shipkart Assured</text>
</svg>"""
    return svg.encode("utf-8")


def seed_initial_data():
    if not settings.SEED_SAMPLE_CATALOG:
        logger.info("Sample catalog seeding skipped (SEED_SAMPLE_CATALOG=false).")
        return

    db = SessionLocal()
    try:
        for item in SAMPLE_PRODUCTS:
            existing = db.query(Product).filter(Product.title == item["title"]).first()
            if not existing:
                svg_data = generate_svg_icon(item["title"], item["category"], item["color"])
                img_url = minio_storage.upload_bytes(
                    bucket=settings.BUCKET_PRODUCT_IMAGES,
                    object_name=item["filename"],
                    data=svg_data,
                    content_type="image/svg+xml",
                )

                prod = Product(
                    merchant_id=None,
                    title=item["title"],
                    brand=item["brand"],
                    category=item["category"],
                    description=item["description"],
                    highlights=item["highlights"],
                    specifications=item["specifications"],
                    price=item["price"],
                    mrp=item["mrp"],
                    sandbox_usd_price=item["sandbox_usd_price"],
                    stock=item["stock"],
                    rating=item["rating"],
                    reviews_count=item["reviews_count"],
                    image_url=img_url,
                    gallery_urls=[img_url],
                    is_assured=True,
                    return_window_days=7,
                )
                db.add(prod)
                logger.info("Seeded starter catalog item: %s", item["title"])
            elif existing.sandbox_usd_price is None or Decimal(str(existing.sandbox_usd_price)) == Decimal("10.00"):
                existing.sandbox_usd_price = item["sandbox_usd_price"]

            if existing:
                existing_bytes, _ = minio_storage.get_file(settings.BUCKET_PRODUCT_IMAGES, item["filename"])
                if existing_bytes is None:
                    svg_data = generate_svg_icon(item["title"], item["category"], item["color"])
                    minio_storage.upload_bytes(
                        bucket=settings.BUCKET_PRODUCT_IMAGES,
                        object_name=item["filename"],
                        data=svg_data,
                        content_type="image/svg+xml",
                    )
                    logger.info("Restored missing starter product image: %s", item["filename"])

        db.commit()
    except Exception as exc:
        logger.error("Error during starter catalog seed: %s", exc)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_initial_data()
