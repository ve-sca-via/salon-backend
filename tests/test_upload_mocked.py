"""
Mocked route tests for the storage_service module (app/api/upload.py +
app/services/storage_service.py, plus the admin service-category icon upload).

These run WITHOUT a real Supabase stack or a Cloudinary account. The Supabase
storage client is replaced with a small in-memory fake (via monkeypatching
`get_storage_client` / the `get_db_client` dependency), and CloudinaryService's
network methods are monkeypatched so nothing leaves the process. They exercise
the full HTTP path:

    HTTP -> FastAPI (auth dep overridden, rate limiter disabled) -> route ->
    StorageService / CloudinaryService (faked).

Scope: every endpoint the module still exposes (happy path + key error cases),
the dual-read agreement signed-url contract the web frontend + admin panel rely
on, and regressions for the two endpoints removed in this cleanup.

No marker -> these run in the fast (no-stack) job alongside the smoke suite.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api.upload as upload_module
from app.core.config import settings
from app.core.auth import get_current_user, require_admin, TokenData
from app.core.database import get_db_client
from app.services.cloudinary_service import CloudinaryService

API = settings.API_PREFIX


# =====================================================================
# In-memory fake Supabase storage client
# =====================================================================
class _FakeBucketOps:
    def __init__(self, store, bucket):
        self.store = store
        self.bucket = bucket

    def upload(self, path, file, file_options=None):
        if self.store.upload_should_fail:
            raise Exception(self.store.upload_error)
        self.store.uploaded.append({"bucket": self.bucket, "path": path})
        return {"path": path}

    def get_public_url(self, path):
        return f"https://fake.supabase/storage/v1/object/public/{self.bucket}/{path}"

    def create_signed_url(self, path, expires_in):
        if self.store.sign_should_fail:
            raise Exception("supabase signing boom")
        return {
            "signedURL": f"https://fake.supabase/storage/v1/object/sign/"
                         f"{self.bucket}/{path}?token=abc&exp={expires_in}"
        }

    def remove(self, paths):
        return {}


class _FakeStorage:
    def __init__(self, store):
        self.store = store

    def from_(self, bucket):
        return _FakeBucketOps(self.store, bucket)


class FakeStorageClient:
    """Stands in for both get_storage_client() and the get_db_client dependency
    (the admin icon route only touches the `.storage` surface)."""

    def __init__(self):
        self.uploaded = []
        self.upload_should_fail = False
        self.upload_error = "storage boom"
        self.sign_should_fail = False
        self.storage = _FakeStorage(self)


# =====================================================================
# Test handle + fixture
# =====================================================================
class UploadHandle:
    def __init__(self, app, storage, db):
        self.app = app
        self.storage = storage          # fake used by get_storage_client()
        self.db = db                    # fake injected as get_db_client
        self.client = None
        # Cloudinary behaviour knobs (consumed by the monkeypatched methods):
        self.cloudinary_should_fail = False
        self.last_cloudinary_upload = None
        self.last_signed_input = None

    def login_as(self, role="relationship_manager", user_id="u-test"):
        td = TokenData(
            user_id=user_id,
            email=f"{role}@example.com",
            user_role=role,
            jti="jti-test",
            exp=datetime.utcnow() + timedelta(hours=1),
        )
        self.app.dependency_overrides[get_current_user] = lambda: td
        self.app.dependency_overrides[require_admin] = lambda: td
        return td

    def logout(self):
        self.app.dependency_overrides.pop(get_current_user, None)
        self.app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def mock_upload(app, monkeypatch):
    storage = FakeStorageClient()
    db = FakeStorageClient()
    handle = UploadHandle(app=app, storage=storage, db=db)

    # get_storage_client is a plain module function (not a dependency) -> patch
    # the name as imported into the upload module.
    monkeypatch.setattr(upload_module, "get_storage_client", lambda: storage)

    # The admin icon route injects the DB client as a dependency.
    app.dependency_overrides[get_db_client] = lambda: db

    # Replace CloudinaryService network methods with in-process fakes.
    async def _cloudinary_upload(self, file, folder, custom_filename=None):
        if handle.cloudinary_should_fail:
            raise Exception("cloudinary boom")
        await file.read()  # mirror real read of the UploadFile
        handle.last_cloudinary_upload = {"folder": folder, "filename": file.filename}
        return f"https://res.cloudinary.com/demo/image/private/{folder}/generated-id.pdf"

    def _cloudinary_signed(self, db_url, expires_in=None):
        handle.last_signed_input = db_url
        return f"https://res.cloudinary.com/demo/signed/{db_url.rsplit('/', 1)[-1]}?sig=xyz"

    monkeypatch.setattr(CloudinaryService, "upload_file", _cloudinary_upload)
    monkeypatch.setattr(CloudinaryService, "generate_download_url", _cloudinary_signed)

    handle.login_as()  # most routes need an authenticated user
    handle.client = TestClient(app)
    yield handle

    handle.logout()
    app.dependency_overrides.pop(get_db_client, None)


def _img(name="pic.jpg", content_type="image/jpeg", data=b"binarydata"):
    return {"file": (name, data, content_type)}


def _doc(name="agreement.pdf", content_type="application/pdf", data=b"%PDF-1.4 fake"):
    return {"file": (name, data, content_type)}


# =====================================================================
# POST /upload/salon-image  (Supabase storage)
# =====================================================================
def test_salon_image_happy(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/salon-image", files=_img())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "salon-images" in body["url"]      # public URL from Supabase
    assert body["path"].startswith("covers/")  # default folder
    assert mock_upload.storage.uploaded[0]["bucket"] == "salon-images"


def test_salon_image_custom_folder(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/salon-image?folder=gallery", files=_img())
    assert r.status_code == 200, r.text
    assert r.json()["path"].startswith("gallery/")


def test_salon_image_invalid_folder(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/salon-image?folder=evil", files=_img())
    assert r.status_code == 400, r.text


def test_salon_image_invalid_type(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/salon-image", files=_img(content_type="application/x-msdownload", name="x.exe"))
    assert r.status_code == 400, r.text


def test_salon_image_too_large(mock_upload, monkeypatch):
    monkeypatch.setattr(upload_module, "MAX_FILE_SIZE", 4)
    r = mock_upload.client.post(f"{API}/upload/salon-image", files=_img(data=b"way too big"))
    assert r.status_code == 400, r.text


def test_salon_image_storage_failure_returns_500(mock_upload):
    mock_upload.storage.upload_should_fail = True
    r = mock_upload.client.post(f"{API}/upload/salon-image", files=_img())
    assert r.status_code == 500, r.text


def test_salon_image_requires_auth(mock_upload):
    mock_upload.logout()
    r = mock_upload.client.post(f"{API}/upload/salon-image", files=_img())
    assert r.status_code in (401, 403), r.text


# =====================================================================
# POST /upload/cloudinary-product-image  (Cloudinary)
# =====================================================================
def test_product_image_happy(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/cloudinary-product-image", files=_img())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "res.cloudinary.com" in body["url"]
    assert mock_upload.last_cloudinary_upload["folder"] == "products"


def test_product_image_invalid_type(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/cloudinary-product-image", files=_doc())
    assert r.status_code == 400, r.text  # PDF not allowed for product images


def test_product_image_cloudinary_failure_returns_500(mock_upload):
    mock_upload.cloudinary_should_fail = True
    r = mock_upload.client.post(f"{API}/upload/cloudinary-product-image", files=_img())
    assert r.status_code == 500, r.text


# =====================================================================
# POST /upload/agreement-document  (migrated to Cloudinary)
# =====================================================================
def test_agreement_upload_happy_goes_to_cloudinary(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/agreement-document", files=_doc())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    # Persisted value is a Cloudinary URL stored under the 'agreements' folder,
    # returned as both url and path (the frontend stores `path`).
    assert "res.cloudinary.com" in body["path"]
    assert body["url"] == body["path"]
    assert mock_upload.last_cloudinary_upload["folder"] == "agreements"
    # And it must NOT have touched Supabase storage at all.
    assert mock_upload.storage.uploaded == []


def test_agreement_upload_accepts_image(mock_upload):
    r = mock_upload.client.post(f"{API}/upload/agreement-document", files=_img(name="scan.png", content_type="image/png"))
    assert r.status_code == 200, r.text


def test_agreement_upload_invalid_mime(mock_upload):
    r = mock_upload.client.post(
        f"{API}/upload/agreement-document",
        files=_doc(name="a.txt", content_type="text/plain"),
    )
    assert r.status_code == 400, r.text


def test_agreement_upload_invalid_extension(mock_upload):
    # MIME is allowed but extension is not on the document allow-list.
    r = mock_upload.client.post(
        f"{API}/upload/agreement-document",
        files=_doc(name="a.docx", content_type="application/pdf"),
    )
    assert r.status_code == 400, r.text


def test_agreement_upload_too_large(mock_upload, monkeypatch):
    monkeypatch.setattr(upload_module, "MAX_DOCUMENT_SIZE", 4)
    r = mock_upload.client.post(f"{API}/upload/agreement-document", files=_doc(data=b"too large"))
    assert r.status_code == 400, r.text


def test_agreement_upload_failure_is_500_not_fake_401(mock_upload):
    # Regression: the old Supabase path relabelled any error containing
    # 'auth'/'token'/etc as a misleading 401 "Authentication expired". The
    # Cloudinary path must surface real failures as 500.
    mock_upload.cloudinary_should_fail = True
    r = mock_upload.client.post(f"{API}/upload/agreement-document", files=_doc())
    assert r.status_code == 500, r.text
    assert "expired" not in r.text.lower()


# =====================================================================
# GET /upload/agreement-document/signed-url  (dual-read)
# =====================================================================
def test_signed_url_cloudinary_path(mock_upload):
    cloud_url = "https://res.cloudinary.com/demo/image/private/agreements/generated-id.pdf"
    r = mock_upload.client.get(f"{API}/upload/agreement-document/signed-url", params={"path": cloud_url})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "res.cloudinary.com/demo/signed" in body["signedUrl"]
    assert body["expiresIn"] == settings.CAREER_CLOUDINARY_SIGNED_URL_TTL
    assert mock_upload.last_signed_input == cloud_url


def test_signed_url_legacy_supabase_path(mock_upload):
    # A bare storage path (no scheme, not Cloudinary) -> legacy Supabase branch.
    r = mock_upload.client.get(
        f"{API}/upload/agreement-document/signed-url",
        params={"path": "agreements/legacy-abc.pdf"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "fake.supabase" in body["signedUrl"]
    assert body["expiresIn"] == 3600
    assert mock_upload.last_signed_input is None  # Cloudinary not used


def test_signed_url_legacy_supabase_failure_returns_500(mock_upload):
    mock_upload.storage.sign_should_fail = True
    r = mock_upload.client.get(
        f"{API}/upload/agreement-document/signed-url",
        params={"path": "agreements/legacy-abc.pdf"},
    )
    assert r.status_code == 500, r.text


def test_signed_url_missing_path_param(mock_upload):
    r = mock_upload.client.get(f"{API}/upload/agreement-document/signed-url")
    assert r.status_code == 422, r.text


# =====================================================================
# POST /admin/service-categories/upload-icon  (StorageService + Supabase)
# =====================================================================
def test_admin_icon_upload_happy(mock_upload):
    r = mock_upload.client.post(
        f"{API}/admin/service-categories/upload-icon",
        files=_img(name="icon.png", content_type="image/png"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "service-category-icons" in body["url"]
    assert mock_upload.db.uploaded[0]["bucket"] == "service-category-icons"


def test_admin_icon_upload_invalid_type(mock_upload):
    r = mock_upload.client.post(
        f"{API}/admin/service-categories/upload-icon",
        files=_doc(),  # PDF not allowed for icons
    )
    assert r.status_code == 400, r.text


# =====================================================================
# Regressions: endpoints removed in this cleanup must be gone
# =====================================================================
def test_removed_multiple_upload_endpoint_is_gone(mock_upload):
    r = mock_upload.client.post(
        f"{API}/upload/salon-images/multiple",
        files=[("files", ("a.jpg", b"x", "image/jpeg"))],
    )
    assert r.status_code == 404, r.text


def test_removed_delete_salon_image_endpoint_is_gone(mock_upload):
    # POST /upload/salon-image still exists, so DELETE on it -> 405 Method Not Allowed.
    r = mock_upload.client.delete(f"{API}/upload/salon-image", params={"path": "covers/x.jpg"})
    assert r.status_code == 405, r.text
