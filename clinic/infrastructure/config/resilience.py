"""Minimal retry + circuit breaker, ported from the AWS sibling project's hand-rolled
implementation (src/shared/resilience.ts), which itself mirrors this project's original
Resilience4j config:
Retry - 3 attempts, exponential backoff starting at 100ms (100 -> 200 -> 400).
CircuitBreaker - count-based window of 10 calls, opens at >=50% failures, stays open 30s,
allows 3 probe calls in half-open state.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.1
CB_WINDOW_SIZE = 10
CB_FAILURE_RATE_THRESHOLD = 0.5
CB_OPEN_DURATION_SECONDS = 30.0
CB_HALF_OPEN_PROBES = 3


class CircuitOpenError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit breaker '{name}' is open")


class CircuitBreaker:
    def __init__(self, name: str) -> None:
        self._name = name
        self._state = "closed"
        self._results: deque[bool] = deque()
        self._opened_at = 0.0
        self._half_open_probes_in_flight = 0

    def execute(self, fn: Callable[[], T]) -> T:
        if self._state == "open":
            if time.monotonic() - self._opened_at < CB_OPEN_DURATION_SECONDS:
                raise CircuitOpenError(self._name)
            self._state = "half-open"
            self._half_open_probes_in_flight = 0

        if self._state == "half-open":
            if self._half_open_probes_in_flight >= CB_HALF_OPEN_PROBES:
                raise CircuitOpenError(self._name)
            self._half_open_probes_in_flight += 1

        try:
            result = fn()
            self._record(True)
            return result
        except Exception:
            self._record(False)
            raise

    def _record(self, success: bool) -> None:
        if self._state == "half-open":
            self._state = "closed" if success else "open"
            if self._state == "open":
                self._opened_at = time.monotonic()
            self._results.clear()
            return

        self._results.append(success)
        if len(self._results) > CB_WINDOW_SIZE:
            self._results.popleft()

        if len(self._results) == CB_WINDOW_SIZE:
            failure_rate = sum(1 for r in self._results if not r) / len(self._results)
            if failure_rate >= CB_FAILURE_RATE_THRESHOLD:
                self._state = "open"
                self._opened_at = time.monotonic()
                self._results.clear()


def with_retry(fn: Callable[[], T]) -> T:
    """Retries fn up to RETRY_ATTEMPTS times with exponential backoff. CircuitOpenError is never
    retried - a call rejected by an open circuit should fail fast, not burn through attempts.
    """
    last_err: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except CircuitOpenError:
            raise
        except Exception as err:  # noqa: BLE001
            last_err = err
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    assert last_err is not None
    raise last_err


def with_resilience(name: str) -> Callable[[Callable[[], T]], T]:
    breaker = CircuitBreaker(name)

    def run(fn: Callable[[], T]) -> T:
        return breaker.execute(lambda: with_retry(fn))

    return run
