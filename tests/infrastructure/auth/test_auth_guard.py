import pytest

from clinic.infrastructure.auth.auth_guard import require_configured
from clinic.infrastructure.auth.jwt_validator import AuthenticationError


def test_require_configured_returns_secret_when_present():
    assert require_configured("a-real-secret") == "a-real-secret"


def test_require_configured_raises_when_none():
    with pytest.raises(RuntimeError):
        require_configured(None)


def test_require_configured_raises_when_blank():
    with pytest.raises(RuntimeError):
        require_configured("   ")


class _FakeRequest:
    def __init__(self, headers: dict):
        self.headers = headers


def test_authenticate_raises_on_missing_header(monkeypatch):
    import clinic.infrastructure.auth.auth_guard as auth_guard_module

    monkeypatch.setattr(auth_guard_module, "_cached_secret", "s")
    with pytest.raises(AuthenticationError):
        auth_guard_module.authenticate(_FakeRequest({}))


def test_authenticate_raises_on_malformed_header(monkeypatch):
    import clinic.infrastructure.auth.auth_guard as auth_guard_module

    monkeypatch.setattr(auth_guard_module, "_cached_secret", "s")
    with pytest.raises(AuthenticationError):
        auth_guard_module.authenticate(_FakeRequest({"authorization": "NotBearer xyz"}))
