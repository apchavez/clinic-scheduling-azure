import time

import pytest

from clinic.infrastructure.config.resilience import (
    CB_HALF_OPEN_PROBES,
    CB_OPEN_DURATION_SECONDS,
    CB_WINDOW_SIZE,
    CircuitBreaker,
    CircuitOpenError,
    with_resilience,
    with_retry,
)


def test_with_retry_succeeds_on_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert with_retry(fn) == "ok"
    assert len(calls) == 1


def test_with_retry_retries_up_to_3_times_then_raises(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        with_retry(fn)
    assert len(calls) == 3


def test_with_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("transient")
        return "ok"

    assert with_retry(fn) == "ok"
    assert len(calls) == 2


def test_with_retry_never_retries_circuit_open_error():
    calls = []

    def fn():
        calls.append(1)
        raise CircuitOpenError("test")

    with pytest.raises(CircuitOpenError):
        with_retry(fn)
    assert len(calls) == 1


def test_circuit_breaker_opens_after_failure_threshold():
    cb = CircuitBreaker("test")

    def failing():
        raise ValueError("boom")

    for _ in range(CB_WINDOW_SIZE):
        with pytest.raises(ValueError):
            cb.execute(failing)

    with pytest.raises(CircuitOpenError):
        cb.execute(lambda: "ok")


def test_circuit_breaker_stays_closed_below_failure_threshold():
    cb = CircuitBreaker("test")
    successes = CB_WINDOW_SIZE // 2 + 1
    failures = CB_WINDOW_SIZE - successes

    for _ in range(successes):
        cb.execute(lambda: "ok")
    for _ in range(failures):
        with pytest.raises(ValueError):
            cb.execute(lambda: (_ for _ in ()).throw(ValueError("boom")))

    assert cb.execute(lambda: "still-closed") == "still-closed"


def test_circuit_breaker_half_open_after_wait_duration(monkeypatch):
    cb = CircuitBreaker("test")

    def failing():
        raise ValueError("boom")

    for _ in range(CB_WINDOW_SIZE):
        with pytest.raises(ValueError):
            cb.execute(failing)

    cb._opened_at -= CB_OPEN_DURATION_SECONDS + 1

    assert cb.execute(lambda: "probe-ok") == "probe-ok"


def test_circuit_breaker_half_open_limits_probe_calls(monkeypatch):
    cb = CircuitBreaker("test")
    cb._state = "half-open"
    cb._half_open_probes_in_flight = CB_HALF_OPEN_PROBES

    with pytest.raises(CircuitOpenError):
        cb.execute(lambda: "ok")


def test_with_resilience_wraps_retry_and_circuit_breaker(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    run = with_resilience("combo")
    assert run(lambda: "ok") == "ok"


def test_with_resilience_records_one_failure_per_logical_call_despite_retries(monkeypatch):
    """Regression test: circuit breaker must wrap retry, not the other way around. Each failing
    logical operation retries RETRY_ATTEMPTS times internally but must only count as ONE failure
    in the breaker's window - otherwise a handful of real incidents (each inflated by
    RETRY_ATTEMPTS) trips the breaker far below its intended failure-rate threshold and stalls
    unrelated, healthy calls for the full open-circuit cooldown.
    """
    monkeypatch.setattr(time, "sleep", lambda _: None)
    run = with_resilience("combo")

    def always_fails():
        raise ValueError("boom")

    for _ in range(CB_WINDOW_SIZE // 2):
        with pytest.raises(ValueError):
            run(always_fails)

    assert run(lambda: "still-closed") == "still-closed"
