"""
Fixed, re-runnable catalogue products for local testing of the web apps.

The home page and `/products` both render product cards, and neither can be
verified against an empty catalogue: with no rows the sections simply return
null, so a broken card looks exactly like a working one. This seeds a small
spread that exercises every branch those cards have:

  - a plain product (no discount)
  - a discounted product (strike-through price + SAVE %)
  - a B2B-priced product (the "B2B PRICE" badge, vendors/regular buyers)
  - an out-of-stock product
  - a product with no image (placeholder path)
  - featured and non-featured, across several categories

Matched on `slug`, so re-running updates in place rather than duplicating.

LOCAL ONLY — refuses to run unless SUPABASE_URL points at localhost.

Usage (venv active; the backend does not need to be running):
    python scripts/seed_products.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from supabase import create_client  # noqa: E402

# Unsplash, same host the rest of the seeded data uses, so next/image needs no
# new remotePattern.
IMG = "https://images.unsplash.com/photo-{id}?w=600&q=80"

PRODUCTS = [
    {
        "name": "Argan Oil Repair Shampoo",
        "slug": "argan-oil-repair-shampoo",
        "short_description": "Sulphate-free repair shampoo for dry, colour-treated hair.",
        "description": (
            "A sulphate-free daily shampoo with cold-pressed argan oil. Rebuilds "
            "the cuticle on colour-treated and heat-damaged hair without stripping "
            "tone. Salon size, 500 ml."
        ),
        "price": 1299,
        "discount_price": 999,
        "category": "Hair Care",
        "brand": "Lubist Pro",
        "sku": "LB-HC-001",
        "image_urls": [IMG.format(id="1608248543803-ba4f8c70ae0b")],
        "stock_quantity": 40,
        "is_featured": True,
        "tags": ["shampoo", "argan", "colour-safe"],
        "weight": "500 ml",
    },
    {
        "name": "Keratin Smoothing Mask",
        "slug": "keratin-smoothing-mask",
        "short_description": "Weekly deep-conditioning mask with hydrolysed keratin.",
        "description": (
            "A weekly treatment mask with hydrolysed keratin and shea butter. "
            "Leave on for ten minutes to cut frizz and drying time."
        ),
        "price": 1599,
        "discount_price": None,
        "category": "Hair Care",
        "brand": "Lubist Pro",
        "sku": "LB-HC-002",
        "image_urls": [IMG.format(id="1571781926291-c477ebfd024b")],
        "stock_quantity": 25,
        "is_featured": True,
        "tags": ["mask", "keratin"],
        "weight": "250 g",
    },
    {
        "name": "Vitamin C Brightening Serum",
        "slug": "vitamin-c-brightening-serum",
        "short_description": "15% vitamin C serum for dull, uneven skin tone.",
        "description": (
            "A 15% L-ascorbic acid serum buffered with vitamin E and ferulic acid. "
            "Use in the morning under sunscreen."
        ),
        "price": 2499,
        "discount_price": 1799,
        "category": "Skin Care",
        "brand": "Glow Theory",
        "sku": "LB-SC-001",
        "image_urls": [IMG.format(id="1620916566398-39f1143ab7be")],
        "stock_quantity": 60,
        "is_featured": True,
        "tags": ["serum", "vitamin-c"],
        "weight": "30 ml",
    },
    {
        "name": "Professional Salon Hair Dryer 2200W",
        "slug": "professional-salon-hair-dryer-2200w",
        "short_description": "Ionic 2200W dryer with two concentrator nozzles.",
        "description": (
            "An ionic AC-motor dryer built for salon floors: 2200 W, three heat "
            "settings, cool shot, and two concentrator nozzles. Two-year warranty."
        ),
        "price": 8999,
        "discount_price": 7499,
        "b2b_discount_price": 5999,
        "category": "Salon Equipment",
        "brand": "Vantix",
        "sku": "LB-EQ-001",
        "image_urls": [IMG.format(id="1522337360788-8b13dee7a37e")],
        "stock_quantity": 12,
        "is_featured": True,
        "tags": ["dryer", "equipment", "b2b"],
        "weight": "780 g",
    },
    {
        "name": "Salon Towel Set (Pack of 24)",
        "slug": "salon-towel-set-pack-of-24",
        "short_description": "Bleach-resistant cotton towels, wholesale pack.",
        "description": (
            "Bleach-resistant 100% cotton towels, 400 GSM, 40 x 70 cm. Sold as a "
            "pack of 24 for salon use."
        ),
        "price": 4800,
        "discount_price": None,
        "b2b_discount_price": 3600,
        "category": "Salon Equipment",
        "brand": "Vantix",
        "sku": "LB-EQ-002",
        "image_urls": [IMG.format(id="1600857544200-b2f666a9a2ec")],
        "stock_quantity": 30,
        "is_featured": False,
        "tags": ["towels", "b2b", "wholesale"],
        "weight": "6 kg",
    },
    {
        "name": "Gel Polish Starter Kit",
        "slug": "gel-polish-starter-kit",
        "short_description": "Twelve gel shades with base, top coat and LED lamp.",
        "description": (
            "Twelve salon gel shades with base coat, top coat and a 48 W LED lamp. "
            "Cures in 30 seconds."
        ),
        "price": 3499,
        "discount_price": 2799,
        "category": "Nail Care",
        "brand": "Lumelle",
        "sku": "LB-NC-001",
        "image_urls": [IMG.format(id="1604654894610-df63bc536371")],
        "stock_quantity": 0,  # out of stock on purpose
        "is_featured": False,
        "tags": ["nails", "gel"],
        "weight": "1.2 kg",
    },
    {
        "name": "Matte Liquid Lipstick — Terracotta",
        "slug": "matte-liquid-lipstick-terracotta",
        "short_description": "Transfer-proof matte liquid lipstick.",
        "description": "A transfer-proof matte liquid lipstick with an eight-hour wear claim.",
        "price": 899,
        "discount_price": None,
        "category": "Makeup",
        "brand": "Glow Theory",
        "sku": "LB-MU-001",
        "image_urls": [],  # no image on purpose — exercises the placeholder
        "stock_quantity": 85,
        "is_featured": False,
        "tags": ["lipstick", "matte"],
        "weight": "6 ml",
    },
    {
        "name": "Tea Tree Scalp Tonic",
        "slug": "tea-tree-scalp-tonic",
        "short_description": "Leave-in tonic for flaky, itchy scalps.",
        "description": (
            "A leave-in tonic with tea tree and salicylic acid for flaky, itchy "
            "scalps. Apply to the roots three times a week."
        ),
        "price": 1099,
        "discount_price": 879,
        "category": "Hair Care",
        "brand": "Lubist Pro",
        "sku": "LB-HC-003",
        "image_urls": [IMG.format(id="1556228720-195a672e8a03")],
        "stock_quantity": 44,
        "is_featured": False,
        "tags": ["scalp", "tea-tree"],
        "weight": "150 ml",
    },
]


def discount_percentage(price: float, discounted) -> float | None:
    """The column is a stored percentage, not derived — keep it consistent."""
    if not discounted:
        return None
    return round((price - float(discounted)) / price * 100, 2)


def main() -> None:
    if not any(host in settings.SUPABASE_URL for host in ("127.0.0.1", "localhost")):
        sys.exit(f"refusing to seed products into {settings.SUPABASE_URL} (not local)")

    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    for item in PRODUCTS:
        row = dict(item)
        row["is_active"] = True
        row["discount_percentage"] = discount_percentage(row["price"], row.get("discount_price"))
        row["b2b_discount_percentage"] = discount_percentage(
            row["price"], row.get("b2b_discount_price")
        )

        existing = (
            db.table("products").select("id").eq("slug", row["slug"]).execute().data
        )
        if existing:
            db.table("products").update(row).eq("id", existing[0]["id"]).execute()
            print(f"  updated  {row['slug']}")
        else:
            db.table("products").insert(row).execute()
            print(f"  created  {row['slug']}")

    total = db.table("products").select("id", count="exact").execute()
    print(f"\n{len(PRODUCTS)} products seeded; {total.count} in the table.")


if __name__ == "__main__":
    main()
