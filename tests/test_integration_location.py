"""
Integration tests for the location endpoints.

Focus: the canonical `/location/salons/nearby` endpoint, which delegates to
`SalonService.get_nearby_salons` (PostGIS `get_nearby_salons` RPC + regular_buyer
exclusion + discount flags). This is the single nearby-salons endpoint after the
`/salons/search/nearby` duplicate was removed.

Requires a running local Supabase stack (`supabase start`); skipped otherwise.
"""
import pytest

from app.core.config import settings

API = settings.API_PREFIX


@pytest.mark.integration
def test_nearby_salons_returns_valid_shape(integration_client):
    """A valid lat/lon returns 200 with the documented response envelope."""
    resp = integration_client.get(
        f"{API}/location/salons/nearby",
        params={"lat": 19.07, "lon": 72.87, "radius": 10, "limit": 5},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert {"salons", "count", "query"}.issubset(body.keys())
    assert isinstance(body["salons"], list)
    assert body["count"] == len(body["salons"])
    assert body["query"]["radius_km"] == 10


@pytest.mark.integration
def test_nearby_salons_requires_coordinates(integration_client):
    """Missing lat/lon is a 422 validation error (both are required)."""
    resp = integration_client.get(f"{API}/location/salons/nearby")
    assert resp.status_code == 422, resp.text
