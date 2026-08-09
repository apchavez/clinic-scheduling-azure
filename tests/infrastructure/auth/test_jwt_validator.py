import base64
import hashlib
import hmac
import json
import time

import pytest

from clinic.infrastructure.auth.jwt_validator import AuthenticationError, verify

SECRET = "test-only-secret-do-not-use-in-production"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(claims: dict, secret: str = SECRET) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    sig = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def _valid_token(sub="agent-001", role="agent", secret=SECRET):
    return _sign({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, secret)


def test_verify_accepts_valid_token():
    user = verify(_valid_token(), SECRET)
    assert user.sub == "agent-001"
    assert user.role == "agent"


def test_verify_rejects_missing_token():
    with pytest.raises(AuthenticationError):
        verify(None, SECRET)
    with pytest.raises(AuthenticationError):
        verify("", SECRET)


def test_verify_rejects_malformed_token():
    with pytest.raises(AuthenticationError):
        verify("not-a-jwt", SECRET)


def test_verify_rejects_wrong_signature():
    token = _valid_token(secret="wrong-secret")
    with pytest.raises(AuthenticationError):
        verify(token, SECRET)


def test_verify_rejects_expired_token():
    token = _sign({"sub": "x", "role": "agent", "exp": int(time.time()) - 10})
    with pytest.raises(AuthenticationError):
        verify(token, SECRET)


def test_verify_rejects_missing_exp_claim():
    token = _sign({"sub": "x", "role": "agent"})
    with pytest.raises(AuthenticationError):
        verify(token, SECRET)


def test_verify_rejects_malformed_base64_segment():
    with pytest.raises(AuthenticationError):
        verify("not!base64.also!bad.sig!bad", SECRET)
