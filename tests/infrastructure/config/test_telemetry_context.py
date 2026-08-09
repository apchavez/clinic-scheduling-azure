import clinic.infrastructure.config.telemetry_context as telemetry_context_module
from clinic.infrastructure.config.telemetry_context import tracer


def test_tracer_returns_a_tracer_when_no_connection_string(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    telemetry_context_module._configured = False
    t = tracer()
    assert t is not None
