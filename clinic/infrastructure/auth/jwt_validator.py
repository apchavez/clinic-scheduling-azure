"""Minimal HS256 JWT verifier - mirrors the sibling AWS Lambda project's hand-rolled ``verifyJwt``
(``src/infra/jwt.ts``) so both platforms accept the same token shape (``sub`` / ``role`` / ``exp``)
without pulling in a JWT library.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str | None
    role: str | None


class AuthenticationError(RuntimeError):
    """Raised when a JWT fails to verify (missing/malformed/expired/bad signature)."""


def _base64url_decode(value: str) -> bytes:
    padding = (4 - len(value) % 4) % 4
    padded = value + ("=" * padding)
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("Malformed base64url segment") from exc


def _hmac_sha256(data: str, secret: str) -> bytes:
    if secret == "":
        raise RuntimeError("HMAC computation failed: Empty key")
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()


def verify(token: str | None, secret: str) -> AuthenticatedUser:
    if token is None or token.strip() == "":
        raise AuthenticationError("Missing token")

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Malformed JWT")

    header_b64, payload_b64, sig_b64 = parts

    expected_sig = _hmac_sha256(f"{header_b64}.{payload_b64}", secret)
    actual_sig = _base64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise AuthenticationError("Invalid signature")

    try:
        payload = json.loads(_base64url_decode(payload_b64))
    except AuthenticationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("Malformed JWT payload") from exc

    exp = payload.get("exp")
    if exp is None or not isinstance(exp, int | float):
        raise AuthenticationError("Missing exp claim")
    if time.time() > exp:
        raise AuthenticationError("Token expired")

    return AuthenticatedUser(sub=payload.get("sub"), role=payload.get("role"))
