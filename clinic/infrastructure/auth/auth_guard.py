"""Enforces Bearer JWT authentication at the Function entry point. Each HTTP-triggered handler
calls ``authenticate(req)`` explicitly - the ``auth_level=ANONYMOUS`` on the trigger only means
"no Azure Functions key required"; this module is the actual authorization gate, since API
Management JWT validation is optional and off by default (see infra/core.bicep's
``enableApiManagementJwtValidation``).
"""

from __future__ import annotations

import os

import azure.functions as func

from clinic.infrastructure.auth.jwt_validator import AuthenticatedUser, AuthenticationError, verify

_cached_secret: str | None = None


def authenticate(req: func.HttpRequest) -> AuthenticatedUser:
    auth_header = req.headers.get("authorization") or req.headers.get("Authorization")
    if auth_header is None or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or malformed Authorization header")
    token = auth_header[len("Bearer ") :]
    return verify(token, _secret())


def _secret() -> str:
    global _cached_secret
    if _cached_secret is None:
        _cached_secret = require_configured(os.environ.get("JWT_SECRET"))
    return _cached_secret


def require_configured(secret: str | None) -> str:
    """Extracted for testability - ``_cached_secret`` is a process-wide cache populated from the
    real env var on first use, mirroring the Java ``AuthGuard.requireConfigured`` split.
    """
    if secret is None or secret.strip() == "":
        raise RuntimeError("JWT_SECRET is not configured")
    return secret
