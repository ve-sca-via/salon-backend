"""
Smoke tests — prove the application boots with a valid configuration and that
DB-free endpoints respond. These require NO running Supabase stack and are the
first line of defense: if config drifts or an import breaks, these go red.
"""


def test_app_imports(app):
    """Settings() validated and the FastAPI app object was constructed."""
    assert app.title


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "version" in resp.json()
