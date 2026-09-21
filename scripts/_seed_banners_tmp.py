import os, sys
sys.path.insert(0, os.getcwd())
from app.core.config import settings
from supabase import create_client
assert any(h in settings.SUPABASE_URL for h in ("127.0.0.1", "localhost")), "local only"
db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
extra = [
    {"title": "Monsoon hair care offer", "image_url": "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=1600&q=80", "link_url": "/salons", "sort_order": 1, "is_active": True},
    {"title": "Spa week", "image_url": "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=1600&q=80", "link_url": "https://www.instagram.com/lubist_official", "sort_order": 2, "is_active": True},
]
for row in extra:
    found = db.table("banners").select("id").eq("title", row["title"]).execute().data
    if found:
        db.table("banners").update(row).eq("id", found[0]["id"]).execute(); print("updated", row["title"])
    else:
        db.table("banners").insert(row).execute(); print("created", row["title"])
print("total", db.table("banners").select("id", count="exact").execute().count)
