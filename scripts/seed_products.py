"""
Product catalog seeder: creates a detailed, realistic e-commerce catalog via the
HTTP API as an admin (exactly how the admin panel would).

Pipeline:
  1. Log in as admin                         (API: POST /auth/login)
  2. (default) Skip products already present (API: GET  /products/admin/all)
  3. Create each product, all fields filled  (API: POST /products)

Every product is fully populated: name, description, short_description, price,
discount_price (+ auto discount_percentage), sku, category, brand, image_urls,
stock_quantity, is_active, is_featured, tags, weight, and B2B wholesale pricing.

Images: by default uses LoremFlickr (real, tag-matched product photos that always
load). Switch with --images {loremflickr,unsplash,picsum}.

Usage (backend running, venv active):
    python scripts/seed_products.py
    python scripts/seed_products.py --images unsplash
    python scripts/seed_products.py --force          # create even if name exists
    python scripts/seed_products.py --base-url http://localhost:8000/api/v1
"""

import argparse
import random
import sys

import requests

# Windows consoles default to cp1252, which can't encode ₹/é in product names.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"

ADMIN_EMAIL = "787alisniazi787@gmail.com"   # role = admin
ADMIN_PASSWORD = "Safdar@1234"

# Per-category tags used by the LoremFlickr image provider (real product photos).
CATEGORY_IMAGE_TAGS = {
    "Haircare": "shampoo,haircare",
    "Skincare": "skincare,cosmetics",
    "Makeup": "makeup,cosmetics",
    "Fragrance": "perfume,bottle",
    "Bath & Body": "soap,bodycare",
    "Nails & Tools": "nailpolish,cosmetics",
}

# Curated Unsplash cosmetic/product photo IDs (used only with --images unsplash).
UNSPLASH_POOL = [
    "1556228720-195a672e8a03", "1556228578-567ba127e37f", "1571875257727-256c39da42af",
    "1598440947619-2c35fc9aa908", "1612817288484-6f916006741a", "1620916566398-39f1143ab7be",
    "1611930022073-b7a4ba5fcccd", "1599733589046-75e3c41e84d6", "1608248543803-ba4f8c70ae0b",
    "1596462502278-27bfdc403348", "1631729371254-42c2892f0e6e", "1585652757141-8837d676fe75",
]

# ----------------------------------------------------------------------------
# Catalog — 24 detailed products across 6 categories (6 featured).
# Fields: brand, name, weight, price, disc (sale price), featured, short, long, tags
# ----------------------------------------------------------------------------
CATALOG = [
    # ---------------- Haircare ----------------
    {
        "category": "Haircare", "brand": "L'Oréal Paris",
        "name": "Elvive Total Repair 5 Shampoo", "weight": "640ml",
        "price": 799, "disc": 599, "featured": False,
        "short": "Repairs the 5 signs of damaged hair: split ends, weakness, roughness, dullness & dehydration.",
        "long": "L'Oréal Paris Elvive Total Repair 5 Shampoo is formulated with Pro-Keratin and Ceramide "
                "to repair the five visible signs of hair damage. Gently cleanses while restoring strength "
                "and shine, leaving hair smoother, healthier-looking and more manageable after every wash.",
        "tags": ["shampoo", "damage-repair", "keratin", "everyday"],
    },
    {
        "category": "Haircare", "brand": "Olaplex",
        "name": "No.4 Bond Maintenance Shampoo", "weight": "250ml",
        "price": 2950, "disc": 2655, "featured": False,
        "short": "Reparative, highly-moisturising shampoo that relinks broken bonds for stronger hair.",
        "long": "Olaplex No.4 is a salon-grade bond maintenance shampoo that repairs and protects hair from "
                "the inside out. The patented bond-building technology re-links broken disulphide bonds, "
                "leaving even the most compromised hair visibly healthier, shinier and easier to manage.",
        "tags": ["shampoo", "bond-repair", "salon", "sulphate-free"],
    },
    {
        "category": "Haircare", "brand": "Moroccanoil",
        "name": "Treatment Original Hair Oil", "weight": "100ml",
        "price": 3200, "disc": 2880, "featured": False,
        "short": "Argan oil-infused treatment that tames frizz and boosts shine for all hair types.",
        "long": "The original foundation for hairstyling, Moroccanoil Treatment is infused with antioxidant-rich "
                "argan oil and shine-boosting vitamins. It absorbs instantly to detangle, speed up drying time "
                "and deliver lasting smoothness, softness and a healthy, radiant shine.",
        "tags": ["hair-oil", "argan", "anti-frizz", "shine"],
    },
    {
        "category": "Haircare", "brand": "WOW Skin Science",
        "name": "Apple Cider Vinegar Shampoo", "weight": "500ml",
        "price": 499, "disc": 349, "featured": True,
        "short": "Clarifying, sulphate-free shampoo that restores scalp balance and adds natural shine.",
        "long": "WOW Apple Cider Vinegar Shampoo gently clarifies the scalp, removing build-up and excess oil "
                "without stripping moisture. Free from sulphates, parabens and mineral oil, it helps balance "
                "scalp pH for healthier roots and naturally glossy, bouncy hair.",
        "tags": ["shampoo", "apple-cider-vinegar", "sulphate-free", "clarifying"],
    },

    # ---------------- Skincare ----------------
    {
        "category": "Skincare", "brand": "Cetaphil",
        "name": "Gentle Skin Cleanser", "weight": "250ml",
        "price": 525, "disc": 449, "featured": False,
        "short": "Soap-free, non-irritating cleanser for all skin types, even sensitive skin.",
        "long": "Cetaphil Gentle Skin Cleanser is a dermatologist-recommended, soap-free formula that cleanses "
                "without stripping the skin's natural protective oils. It hydrates as it cleanses, leaving skin "
                "soft, smooth and comfortable — gentle enough for everyday use on sensitive skin.",
        "tags": ["cleanser", "sensitive-skin", "soap-free", "dermatologist"],
    },
    {
        "category": "Skincare", "brand": "The Ordinary",
        "name": "Niacinamide 10% + Zinc 1%", "weight": "30ml",
        "price": 750, "disc": 675, "featured": True,
        "short": "High-strength vitamin and mineral serum that visibly reduces blemishes and congestion.",
        "long": "The Ordinary Niacinamide 10% + Zinc 1% is a water-based serum that targets blemishes, enlarged "
                "pores and uneven texture. Niacinamide supports a clearer complexion while zinc balances visible "
                "sebum activity, making it ideal for oily and blemish-prone skin.",
        "tags": ["serum", "niacinamide", "blemish", "pores"],
    },
    {
        "category": "Skincare", "brand": "Neutrogena",
        "name": "Hydro Boost Water Gel", "weight": "50g",
        "price": 1099, "disc": 879, "featured": False,
        "short": "Lightweight hyaluronic acid gel that quenches dry skin with all-day hydration.",
        "long": "Neutrogena Hydro Boost Water Gel is a fast-absorbing, oil-free moisturiser powered by hyaluronic "
                "acid. It plumps skin with intense hydration and locks in moisture for a smooth, supple, dewy "
                "finish — without feeling heavy or greasy.",
        "tags": ["moisturiser", "hyaluronic-acid", "hydration", "oil-free"],
    },
    {
        "category": "Skincare", "brand": "Minimalist",
        "name": "Vitamin C 10% Face Serum", "weight": "30ml",
        "price": 699, "disc": 559, "featured": False,
        "short": "Stable 10% vitamin C serum for brighter, more even-toned and glowing skin.",
        "long": "Minimalist Vitamin C 10% Face Serum uses a stabilised form of ethyl ascorbic acid to brighten "
                "the complexion, fade dark spots and even out skin tone. Lightweight and non-sticky, it layers "
                "easily under sunscreen for a visibly radiant glow.",
        "tags": ["serum", "vitamin-c", "brightening", "glow"],
    },

    # ---------------- Makeup ----------------
    {
        "category": "Makeup", "brand": "Maybelline New York",
        "name": "Fit Me Matte + Poreless Foundation", "weight": "30ml",
        "price": 549, "disc": 429, "featured": True,
        "short": "Mattifying liquid foundation that blurs pores for a natural, seamless finish.",
        "long": "Maybelline Fit Me Matte + Poreless Foundation is designed for normal to oily skin. The "
                "lightweight formula controls shine and minimises the look of pores, delivering a natural matte "
                "finish that blends effortlessly and lasts all day.",
        "tags": ["foundation", "matte", "oily-skin", "base"],
    },
    {
        "category": "Makeup", "brand": "Lakmé",
        "name": "9to5 Primer + Matte Lipstick", "weight": "3.6g",
        "price": 650, "disc": 520, "featured": False,
        "short": "Primer-infused matte lipstick with intense colour and a comfortable, long-stay finish.",
        "long": "Lakmé 9to5 Primer + Matte Lipstick combines a built-in primer with rich, velvety colour. The "
                "creamy matte formula glides on smoothly, resists fading through the day and keeps lips looking "
                "bold yet comfortable from morning to evening.",
        "tags": ["lipstick", "matte", "primer", "long-stay"],
    },
    {
        "category": "Makeup", "brand": "M.A.C",
        "name": "Studio Fix Powder Plus Foundation", "weight": "15g",
        "price": 3200, "disc": 2880, "featured": False,
        "short": "Iconic all-in-one powder foundation with buildable, medium-to-full matte coverage.",
        "long": "M.A.C Studio Fix Powder Plus Foundation is a professional favourite that delivers medium-to-full "
                "coverage in a single sweep. The smooth, matte finish evens skin tone and controls shine, and "
                "works as both foundation and powder for effortless, all-day wear.",
        "tags": ["foundation", "powder", "full-coverage", "pro"],
    },
    {
        "category": "Makeup", "brand": "SUGAR Cosmetics",
        "name": "Ace Of Face Foundation Stick", "weight": "12g",
        "price": 999, "disc": 799, "featured": False,
        "short": "Creamy, blendable foundation stick with full coverage and a soft matte finish.",
        "long": "SUGAR Ace Of Face Foundation Stick offers high-impact, full coverage in a travel-friendly format. "
                "The creamy formula blends seamlessly into skin, covers blemishes and uneven tone, and sets to a "
                "natural soft-matte finish that lasts for hours.",
        "tags": ["foundation", "stick", "full-coverage", "travel"],
    },

    # ---------------- Fragrance ----------------
    {
        "category": "Fragrance", "brand": "Bella Vita Organic",
        "name": "CEO Man Eau De Parfum", "weight": "100ml",
        "price": 999, "disc": 699, "featured": True,
        "short": "Bold, long-lasting woody-aromatic perfume for the confident modern man.",
        "long": "Bella Vita CEO Man Eau De Parfum opens with fresh citrus and spice, settling into a sophisticated "
                "woody-amber base. Long-lasting and versatile, it's crafted for boardrooms and evenings out alike — "
                "a signature scent that commands presence.",
        "tags": ["perfume", "men", "woody", "long-lasting"],
    },
    {
        "category": "Fragrance", "brand": "Engage",
        "name": "W1 Perfume Spray For Women", "weight": "120ml",
        "price": 399, "disc": 319, "featured": False,
        "short": "Floral-fruity body perfume with a fresh, lingering trail for everyday wear.",
        "long": "Engage W1 Perfume Spray wraps you in a cheerful floral-fruity accord balanced with soft musk. "
                "Light, fresh and skin-friendly, it's perfect for daily wear and keeps you feeling confident "
                "and refreshed through the day.",
        "tags": ["perfume", "women", "floral", "daily"],
    },
    {
        "category": "Fragrance", "brand": "Skinn by Titan",
        "name": "Raw Eau De Parfum For Men", "weight": "100ml",
        "price": 1495, "disc": 1196, "featured": False,
        "short": "Premium aromatic-fougère fragrance with a rugged, masculine character.",
        "long": "Skinn Raw by Titan is a premium Eau De Parfum built around crisp aromatic top notes, a spicy "
                "heart and a warm woody-leather base. Elegantly masculine and impressively long-wearing, it's an "
                "everyday signature for the discerning man.",
        "tags": ["perfume", "men", "aromatic", "premium"],
    },
    {
        "category": "Fragrance", "brand": "Wild Stone",
        "name": "Ultra Sensual Body Perfume", "weight": "120ml",
        "price": 350, "disc": 280, "featured": False,
        "short": "Intense musky body perfume that keeps you fresh and charged all day.",
        "long": "Wild Stone Ultra Sensual Body Perfume delivers a bold, musky-spicy burst that lasts for hours. "
                "The no-gas, skin-friendly spray is built for an active day, keeping you fresh, confident and "
                "irresistibly charged from morning to night.",
        "tags": ["body-perfume", "men", "musk", "value"],
    },

    # ---------------- Bath & Body ----------------
    {
        "category": "Bath & Body", "brand": "Dove",
        "name": "Deeply Nourishing Body Wash", "weight": "800ml",
        "price": 699, "disc": 559, "featured": False,
        "short": "Sulphate-free body wash with NutriumMoisture for soft, deeply nourished skin.",
        "long": "Dove Deeply Nourishing Body Wash is powered by NutriumMoisture, a blend of skin-natural nutrients "
                "that nourishes deep into the surface layers. The gentle, sulphate-free lather cleanses while "
                "leaving skin softer and smoother after just one shower.",
        "tags": ["body-wash", "nourishing", "sulphate-free", "everyday"],
    },
    {
        "category": "Bath & Body", "brand": "The Body Shop",
        "name": "British Rose Body Butter", "weight": "200ml",
        "price": 1545, "disc": 1390, "featured": True,
        "short": "48-hour moisture body butter with real rose extract for dewy, fresh skin.",
        "long": "The Body Shop British Rose Body Butter melts into skin to deliver 48 hours of moisture. Enriched "
                "with community-trade rose essence and rosehip oil, it leaves skin feeling fresh, dewy and "
                "delicately scented with the fragrance of freshly picked English roses.",
        "tags": ["body-butter", "moisturiser", "rose", "dry-skin"],
    },
    {
        "category": "Bath & Body", "brand": "Mamaearth",
        "name": "Ubtan Body Wash", "weight": "300ml",
        "price": 349, "disc": 279, "featured": False,
        "short": "Turmeric & saffron body wash that brightens and gently cleanses dull skin.",
        "long": "Mamaearth Ubtan Body Wash combines traditional turmeric and saffron with walnut beads to gently "
                "exfoliate and brighten. Free from sulphates and parabens, it cleanses without dryness, revealing "
                "smoother, more radiant skin with a warm natural fragrance.",
        "tags": ["body-wash", "ubtan", "brightening", "natural"],
    },
    {
        "category": "Bath & Body", "brand": "Nivea",
        "name": "Cocoa Nourish Body Lotion", "weight": "400ml",
        "price": 425, "disc": 340, "featured": False,
        "short": "Deep-moisture body lotion with cocoa butter for 48-hour smoothness.",
        "long": "Nivea Cocoa Nourish Body Lotion is enriched with cocoa butter and deep-moisture serum to nourish "
                "very dry skin. It absorbs quickly for a non-greasy feel and keeps skin visibly smooth, supple "
                "and glowing for up to 48 hours.",
        "tags": ["body-lotion", "cocoa-butter", "dry-skin", "moisturiser"],
    },

    # ---------------- Nails & Tools ----------------
    {
        "category": "Nails & Tools", "brand": "FACES CANADA",
        "name": "Ultime Pro Gel Nail Lacquer", "weight": "9ml",
        "price": 499, "disc": 399, "featured": False,
        "short": "High-shine gel-finish nail lacquer with rich, chip-resistant colour.",
        "long": "FACES CANADA Ultime Pro Gel Nail Lacquer delivers salon-style gel shine without a UV lamp. The "
                "highly pigmented formula glides on evenly in one or two strokes, dries to a glossy finish and "
                "resists chipping for long-lasting, vibrant nails.",
        "tags": ["nail-polish", "gel", "high-shine", "long-wear"],
    },
    {
        "category": "Nails & Tools", "brand": "Vega",
        "name": "Professional Hair Dryer 1800W", "weight": "1 pc",
        "price": 1899, "disc": 1519, "featured": True,
        "short": "1800W salon-style dryer with hot/cold settings and a concentrator nozzle.",
        "long": "The Vega Professional Hair Dryer packs 1800 watts of power with multiple heat and speed settings "
                "plus a cool-shot button to set your style. The lightweight body and concentrator nozzle give you "
                "fast, frizz-free, salon-quality blow-drying at home.",
        "tags": ["hair-dryer", "styling", "tool", "1800w"],
    },
    {
        "category": "Nails & Tools", "brand": "Sally Hansen",
        "name": "Miracle Gel Top Coat", "weight": "14.7ml",
        "price": 850, "disc": 680, "featured": False,
        "short": "Gel-finish top coat for high-gloss, long-lasting wear — no UV lamp needed.",
        "long": "Sally Hansen Miracle Gel Top Coat locks in colour with a chip-resistant, gel-like shine that "
                "lasts. Paired with any Miracle Gel shade, it cures in natural light — no UV lamp required — and "
                "peels off easily without harsh removers.",
        "tags": ["top-coat", "gel", "nail-care", "high-gloss"],
    },
    {
        "category": "Nails & Tools", "brand": "Vega",
        "name": "Wooden Paddle Hair Brush", "weight": "1 pc",
        "price": 399, "disc": 319, "featured": False,
        "short": "Cushioned wooden paddle brush that detangles and smooths without breakage.",
        "long": "The Vega Wooden Paddle Hair Brush features a natural wooden body and cushioned base that glides "
                "through knots gently. Ideal for medium-to-long hair, it detangles, smooths and adds shine while "
                "minimising static and breakage.",
        "tags": ["hair-brush", "wooden", "detangle", "tool"],
    },
]


def die(msg: str, resp=None):
    print(f"[FAIL] {msg}")
    if resp is not None:
        print(f"       Response: {resp}")
    sys.exit(1)


def login(base_url: str, email: str, password: str) -> str:
    try:
        r = requests.post(f"{base_url}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]
    except requests.exceptions.RequestException as exc:
        die(f"login failed for {email}: {exc}", getattr(getattr(exc, "response", None), "text", None))


def existing_product_names(base_url: str, token: str) -> set[str]:
    """Lowercased names of all products (active + inactive) for idempotency."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base_url}/products/admin/all", params={"limit": 100}, headers=headers)
        r.raise_for_status()
        return {p.get("name", "").strip().lower() for p in r.json().get("products", [])}
    except requests.exceptions.RequestException as exc:
        print(f"  [warn] could not list existing products ({exc}); proceeding without skip-check")
        return set()


def make_images(provider: str, category: str, seed: int, count: int) -> list[str]:
    if provider == "unsplash":
        ids = random.sample(UNSPLASH_POOL, count)
        return [f"https://images.unsplash.com/photo-{pid}?w=600&q=80&fit=crop" for pid in ids]
    if provider == "picsum":
        return [f"https://picsum.photos/seed/{category}-{seed}-{i}/600/600" for i in range(count)]
    # default: loremflickr — real, tag-matched product photos that always load
    tags = CATEGORY_IMAGE_TAGS.get(category, "cosmetics")
    return [f"https://loremflickr.com/600/600/{tags}?lock={seed * 10 + i}" for i in range(count)]


def build_payload(item: dict, index: int, provider: str, force: bool) -> dict:
    price = item["price"]
    disc = item["disc"]
    discount_pct = round((price - disc) / price * 100, 2)

    # Wholesale (B2B) price ~25% off base, below the retail sale price.
    b2b_price = round(price * 0.75, 2)
    b2b_pct = round((price - b2b_price) / price * 100, 2)

    # SKU: stable per product (so re-runs are idempotent); randomised with --force.
    brand_code = "".join(c for c in item["brand"] if c.isalnum())[:3].upper()
    name_code = "".join(c for c in item["name"] if c.isalnum())[:4].upper()
    sku = f"{brand_code}-{name_code}-{index:02d}"
    if force:
        sku += "-" + "".join(random.choices("0123456789ABCDEF", k=4))

    n_images = random.randint(2, 3)
    images = make_images(provider, item["category"], index + 1, n_images)

    return {
        "name": item["name"],
        "description": item["long"],
        "short_description": item["short"],
        "price": price,
        "discount_price": disc,
        "discount_percentage": discount_pct,
        "sku": sku,
        "category": item["category"],
        "brand": item["brand"],
        "image_urls": images,
        "stock_quantity": random.randint(25, 250),
        "is_active": True,
        "is_featured": item["featured"],
        "tags": item["tags"],
        "weight": item["weight"],
        "b2b_discount_price": b2b_price,
        "b2b_discount_percentage": b2b_pct,
    }


def create_product(base_url: str, token: str, payload: dict):
    """Returns the created product dict, the string "exists" if a unique
    constraint (SKU/slug) already matches, or None on a real error."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.post(f"{base_url}/products", json=payload, headers=headers)
        r.raise_for_status()
        return r.json().get("product", {})
    except requests.exceptions.RequestException as exc:
        resp = getattr(exc, "response", None)
        body = getattr(resp, "text", "") or ""
        # A 400 about an existing SKU/slug means the product is already seeded
        # (e.g. a concurrent run beat us to it) — treat it as a skip, not an error.
        if resp is not None and resp.status_code == 400 and "already exists" in body:
            return "exists"
        print(f"  [error] {payload['name']}: {exc}")
        if body:
            print(f"          {body[:300]}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a detailed product catalog via the admin API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--admin-email", default=ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=ADMIN_PASSWORD)
    parser.add_argument("--images", choices=["loremflickr", "unsplash", "picsum"], default="loremflickr",
                        help="Image source for product photos (default: loremflickr).")
    parser.add_argument("--force", action="store_true",
                        help="Create products even if a product with the same name already exists.")
    args = parser.parse_args()

    print("1) Logging in as admin ...")
    token = login(args.base_url, args.admin_email, args.admin_password)

    skip = set()
    if not args.force:
        print("2) Checking for existing products ...")
        skip = existing_product_names(args.base_url, token)
        if skip:
            print(f"   {len(skip)} products already in catalog — those names will be skipped.")

    print(f"3) Creating products (images: {args.images}) ...")
    created, skipped, failed = 0, 0, 0
    for i, item in enumerate(CATALOG):
        if not args.force and item["name"].strip().lower() in skip:
            print(f"  [skip] {item['name']} (already exists)")
            skipped += 1
            continue

        payload = build_payload(item, i, args.images, args.force)
        product = create_product(args.base_url, token, payload)
        if product == "exists":
            print(f"  [skip] {item['name']} (SKU/slug already exists)")
            skipped += 1
        elif product:
            featured = " *featured*" if item["featured"] else ""
            print(f"  [ok]   {item['category']:<14} {item['name']}  "
                  f"(₹{item['disc']} was ₹{item['price']}){featured}")
            created += 1
        else:
            failed += 1

    print("\n[DONE] Product catalog seed complete.")
    print(f"   created: {created}   skipped: {skipped}   failed: {failed}")
    print(f"   categories: {', '.join(CATEGORY_IMAGE_TAGS)}")
    if created:
        print("   Open the mobile app → Shopping tab to see categories + trending products.")


if __name__ == "__main__":
    main()
