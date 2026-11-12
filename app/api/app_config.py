"""
Native app configuration: the version policy a mobile build checks on launch.

Public, unauthenticated, and cheap - one cached system_config read per process
per CLIENT_POLICY_CACHE_SECONDS. Exempt from the 426 version gate, because it is
how an outdated build finds out it is outdated.

Contract: docs/CLIENT_APPS_AND_VERSIONING.md.
"""
from typing import Optional

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.core.client_app import (
    APP_PLATFORM_HEADER,
    APP_VERSION_HEADER,
    CLIENT_APP_HEADER,
    NATIVE_CLIENT_APPS,
    NATIVE_PLATFORMS,
    build_app_config,
    get_client_policy,
)
from app.core.exceptions import AppException

router = APIRouter(tags=["App Config"])


class AppConfigResponse(BaseModel):
    success: bool = True
    client_app: str = Field(..., description="customer-app | partner-app")
    platform: str = Field(..., description="ios | android")
    current_version: Optional[str] = Field(None, description="The version the caller reported, echoed back")
    min_supported_version: Optional[str] = Field(None, description="Builds below this are blocked with HTTP 426")
    latest_version: Optional[str] = Field(None, description="Newest release in the store")
    update_required: bool = Field(..., description="current_version < min_supported_version")
    update_available: bool = Field(..., description="current_version < latest_version")
    store_url: Optional[str] = None
    message: Optional[str] = None


def _pick(query_value: Optional[str], request: Request, header: str) -> Optional[str]:
    value = query_value if query_value not in (None, "") else request.headers.get(header)
    return value.strip() if value else None


@router.get("/app-config", response_model=AppConfigResponse)
async def get_app_config(
    request: Request,
    response: Response,
    client_app: Optional[str] = Query(
        None, description="customer-app | partner-app. Falls back to the X-Client-App header."
    ),
    platform: Optional[str] = Query(
        None, description="ios | android. Falls back to the X-App-Platform header."
    ),
    version: Optional[str] = Query(
        None, description="Semver of the running build. Falls back to the X-App-Version header."
    ),
):
    """
    Version policy for a native app build.

    Query parameters win; the X-Client-App / X-App-Platform / X-App-Version
    headers are the fallback. Unknown app or platform is a 422. No policy
    configured means nulls and both booleans false.
    """
    resolved_app = (_pick(client_app, request, CLIENT_APP_HEADER) or "").lower()
    resolved_platform = (_pick(platform, request, APP_PLATFORM_HEADER) or "").lower()
    resolved_version = _pick(version, request, APP_VERSION_HEADER)

    if resolved_app not in NATIVE_CLIENT_APPS:
        raise AppException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"client_app must be one of: {', '.join(NATIVE_CLIENT_APPS)} "
            f"(got {resolved_app or 'nothing'}).",
            error_code="INVALID_CLIENT_APP",
        )
    if resolved_platform not in NATIVE_PLATFORMS:
        raise AppException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"platform must be one of: {', '.join(NATIVE_PLATFORMS)} "
            f"(got {resolved_platform or 'nothing'}).",
            error_code="INVALID_PLATFORM",
        )

    policy = await get_client_policy()
    # Short shared caching is safe: the answer depends only on the inputs, which
    # are all in the URL or the headers named in Vary.
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Vary"] = f"{CLIENT_APP_HEADER}, {APP_PLATFORM_HEADER}, {APP_VERSION_HEADER}"
    return build_app_config(policy, resolved_app, resolved_platform, resolved_version)
