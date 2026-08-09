from clinic.infrastructure.config import correlation_context


def test_set_get_clear_roundtrip():
    correlation_context.set_correlation_id("abc-123")
    assert correlation_context.get_correlation_id() == "abc-123"
    correlation_context.clear()
    assert correlation_context.get_correlation_id() is None
