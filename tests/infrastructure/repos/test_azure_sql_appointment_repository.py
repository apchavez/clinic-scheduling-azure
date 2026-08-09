from unittest.mock import MagicMock

from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.config.resilience import CircuitBreaker
from clinic.infrastructure.repos.azure_sql_appointment_repository import (
    AzureSqlAppointmentRepository,
)


def _make_repo():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    factory = MagicMock(return_value=conn)

    repo = AzureSqlAppointmentRepository(
        "sql.example.com",
        "clinicdb",
        "SqlPassword",
        "user",
        "pass",
        CircuitBreaker("test-sql"),
        connection_factory=factory,
    )
    return repo, factory, conn, cursor


def test_migrate_schema_runs_at_construction():
    repo, factory, conn, cursor = _make_repo()
    assert factory.call_count == 1
    cursor.execute.assert_called_once()
    conn.commit.assert_called_once()


def test_persist_executes_merge_and_commits():
    repo, factory, conn, cursor = _make_repo()
    factory.reset_mock()
    cursor.reset_mock()
    conn.reset_mock()

    a = Appointment.create("a1", "12345", 10)
    a.mark_completed()

    repo.persist(a)

    factory.assert_called_once()
    cursor.execute.assert_called_once()
    args = cursor.execute.call_args[0][1]
    assert args[0] == "a1"
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_ping_up_and_down():
    repo, factory, conn, cursor = _make_repo()
    assert repo.ping() == "UP"

    factory.side_effect = RuntimeError("connection refused")
    assert repo.ping().startswith("DOWN")
