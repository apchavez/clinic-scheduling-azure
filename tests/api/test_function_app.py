import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock

import azure.functions as func
import pytest

import function_app
from clinic.domain.entities.appointment import Appointment
from clinic.domain.exceptions import ForbiddenError
from clinic.shared.health_status import DOWN, UP, HealthStatus

SECRET = "test-only-secret-do-not-use-in-production"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(sub="agent-001", role="agent"):
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps({"sub": sub, "role": role, "exp": int(time.time()) + 3600}).encode()
    )
    sig = hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def _auth_headers(sub="agent-001", role="agent"):
    return {"authorization": f"Bearer {_token(sub, role)}"}


class _MockContext:
    invocation_id = "test-invocation-id"


@pytest.fixture(autouse=True)
def _configured_secret(monkeypatch):
    monkeypatch.setattr(function_app.auth_guard, "_cached_secret", SECRET)
    yield


def _mock_use_case(monkeypatch, factory_name):
    use_case = MagicMock()
    monkeypatch.setattr(function_app.app_context, factory_name, lambda: use_case)
    return use_case


class TestCreateAppointment:
    def test_returns_202_on_success(self, monkeypatch):
        use_case = _mock_use_case(monkeypatch, "create_appointment")
        appt = Appointment.create("a1", "12345", 10)
        use_case.execute.return_value = appt

        req = func.HttpRequest(
            method="POST",
            url="/api/appointments",
            headers=_auth_headers(),
            params={},
            route_params={},
            body=json.dumps({"insuredId": "12345", "scheduleId": 10}).encode(),
        )
        resp = function_app.create_appointment(req, _MockContext())
        assert resp.status_code == 202
        body = json.loads(resp.get_body())
        assert body["appointmentId"] == "a1"

    def test_returns_400_for_invalid_body(self, monkeypatch):
        _mock_use_case(monkeypatch, "create_appointment")
        req = func.HttpRequest(
            method="POST",
            url="/api/appointments",
            headers=_auth_headers(),
            params={},
            route_params={},
            body=json.dumps({"insuredId": "", "scheduleId": 0}).encode(),
        )
        resp = function_app.create_appointment(req, _MockContext())
        assert resp.status_code == 400

    def test_returns_401_without_auth_header(self, monkeypatch):
        _mock_use_case(monkeypatch, "create_appointment")
        req = func.HttpRequest(
            method="POST",
            url="/api/appointments",
            headers={},
            params={},
            route_params={},
            body=b"{}",
        )
        resp = function_app.create_appointment(req, _MockContext())
        assert resp.status_code == 401

    def test_returns_403_when_insured_books_for_someone_else(self, monkeypatch):
        _mock_use_case(monkeypatch, "create_appointment")
        req = func.HttpRequest(
            method="POST",
            url="/api/appointments",
            headers=_auth_headers(sub="12345", role="insured"),
            params={},
            route_params={},
            body=json.dumps({"insuredId": "99999", "scheduleId": 10}).encode(),
        )
        resp = function_app.create_appointment(req, _MockContext())
        assert resp.status_code == 403


class TestGetAppointments:
    def test_returns_200_with_page(self, monkeypatch):
        use_case = _mock_use_case(monkeypatch, "get_appointments")
        from clinic.domain.shared.page import Page

        use_case.by_insured_paged.return_value = Page(items=[], next_cursor=None)

        req = func.HttpRequest(
            method="GET",
            url="/api/appointments/12345",
            headers=_auth_headers(),
            params={},
            route_params={"insuredId": "12345"},
            body=b"",
        )
        resp = function_app.get_appointments(req, _MockContext())
        assert resp.status_code == 200

    def test_returns_403_when_insured_views_someone_elses(self, monkeypatch):
        _mock_use_case(monkeypatch, "get_appointments")
        req = func.HttpRequest(
            method="GET",
            url="/api/appointments/99999",
            headers=_auth_headers(sub="12345", role="insured"),
            params={},
            route_params={"insuredId": "99999"},
            body=b"",
        )
        resp = function_app.get_appointments(req, _MockContext())
        assert resp.status_code == 403


class TestGetAppointmentHistory:
    def test_returns_200_with_events(self, monkeypatch):
        use_case = _mock_use_case(monkeypatch, "get_appointment_history")
        use_case.execute.return_value = []

        req = func.HttpRequest(
            method="GET",
            url="/api/appointments/a1/history",
            headers=_auth_headers(),
            params={},
            route_params={"appointmentId": "a1"},
            body=b"",
        )
        resp = function_app.get_appointment_history(req, _MockContext())
        assert resp.status_code == 200

    def test_returns_403_when_forbidden(self, monkeypatch):
        use_case = _mock_use_case(monkeypatch, "get_appointment_history")
        use_case.execute.side_effect = ForbiddenError("nope")

        req = func.HttpRequest(
            method="GET",
            url="/api/appointments/a1/history",
            headers=_auth_headers(sub="99999", role="insured"),
            params={},
            route_params={"appointmentId": "a1"},
            body=b"",
        )
        resp = function_app.get_appointment_history(req, _MockContext())
        assert resp.status_code == 403


class TestHealth:
    def test_returns_200_when_up(self, monkeypatch):
        monkeypatch.setattr(
            function_app.app_context,
            "health_check",
            lambda: HealthStatus(status=UP, checks={"cosmosDb": "UP"}),
        )
        req = func.HttpRequest(method="GET", url="/api/health", headers={}, params={}, body=b"")
        resp = function_app.health(req, _MockContext())
        assert resp.status_code == 200

    def test_returns_503_when_down(self, monkeypatch):
        monkeypatch.setattr(
            function_app.app_context,
            "health_check",
            lambda: HealthStatus(status=DOWN, checks={"cosmosDb": "DOWN: timeout"}),
        )
        req = func.HttpRequest(method="GET", url="/api/health", headers={}, params={}, body=b"")
        resp = function_app.health(req, _MockContext())
        assert resp.status_code == 503


class TestWorkers:
    def test_process_worker_message_success(self, monkeypatch):
        use_case = MagicMock()
        monkeypatch.setattr(function_app.app_context, "process_appointment", lambda: use_case)
        message = json.dumps({"appointmentId": "a1", "correlationId": "corr-1"})
        function_app._process_worker_message(message, _MockContext())
        use_case.execute.assert_called_once_with("a1")

    def test_process_worker_message_reraises_on_failure(self, monkeypatch):
        use_case = MagicMock()
        use_case.execute.side_effect = RuntimeError("boom")
        monkeypatch.setattr(function_app.app_context, "process_appointment", lambda: use_case)
        message = json.dumps({"appointmentId": "a1"})
        with pytest.raises(RuntimeError):
            function_app._process_worker_message(message, _MockContext())

    def test_process_confirmation_message_success(self, monkeypatch):
        use_case = MagicMock()
        monkeypatch.setattr(function_app.app_context, "confirm_appointment", lambda: use_case)
        message = json.dumps({"type": "AppointmentConfirmed", "data": {"appointmentId": "a1"}})
        function_app._process_confirmation_message(message, _MockContext())
        use_case.execute.assert_called_once_with("a1")

    def test_process_confirmation_message_reraises_on_failure(self, monkeypatch):
        use_case = MagicMock()
        use_case.execute.side_effect = RuntimeError("boom")
        monkeypatch.setattr(function_app.app_context, "confirm_appointment", lambda: use_case)
        message = json.dumps({"data": {"appointmentId": "a1"}})
        with pytest.raises(RuntimeError):
            function_app._process_confirmation_message(message, _MockContext())
