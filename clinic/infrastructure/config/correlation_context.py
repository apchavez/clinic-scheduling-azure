"""Context-local holder for the correlation ID derived from the incoming X-Correlation-Id header
(or the Azure Functions invocation_id as fallback). Set at the HTTP handler entry point and
cleared in a finally block.

Uses contextvars rather than thread-locals since Python's Azure Functions worker may run handlers
concurrently on the same thread (asyncio) - contextvars is the correct isolation primitive here.
"""

from __future__ import annotations

from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def clear() -> None:
    _correlation_id.set(None)
