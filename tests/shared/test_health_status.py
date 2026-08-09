from clinic.shared.health_status import DOWN, UP, HealthStatus


def test_health_status_sets_timestamp_and_fields():
    hs = HealthStatus(status=UP, checks={"db": "UP"})
    assert hs.status == UP
    assert hs.checks == {"db": "UP"}
    assert hs.timestamp is not None


def test_up_down_constants():
    assert UP == "UP"
    assert DOWN == "DOWN"
