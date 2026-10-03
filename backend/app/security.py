"""Authentication-ready hooks.

If ``ADMIN_API_KEY`` is set, mutating endpoints require the header
``X-API-Key``. The key is entered by the operator at runtime in the UI and is
never bundled into frontend code. Swap ``require_admin`` for OAuth2/JWT later
without touching route handlers.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        return  # auth disabled (development / demo)
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")
