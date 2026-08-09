"""OpenTelemetry tracing setup. Configures the Azure Monitor exporter when
APPLICATIONINSIGHTS_CONNECTION_STRING is set; otherwise leaves tracing unconfigured (no-op) so
local dev and environments without App Insights are unaffected.

Set APPLICATIONINSIGHTS_CONNECTION_STRING in the Function App settings for production.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.trace import Tracer

_INSTRUMENTATION_NAME = "clinic"
_configured = False


def _configure(connection_string: str | None) -> None:
    global _configured
    if _configured:
        return
    if connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
    _configured = True


def tracer() -> Tracer:
    _configure(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    return trace.get_tracer(_INSTRUMENTATION_NAME)
