"""Azure SQL Database adapter implementing the relational persistence port. Azure equivalent of
the AWS project's MySQL store for completed appointments.

Uses pymssql (pure client over TDS, no system ODBC driver install required - simpler for CI/
portfolio purposes than pyodbc). Schema is created idempotently at construction time (there is no
bundled Flyway-for-Python equivalent, so migration/V1__create_appointments_table.sql is executed
guarded by an ``IF NOT EXISTS`` check). Uses MERGE for idempotent upsert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.config.resilience import CircuitBreaker, with_retry

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "db_migration" / "V1__create_appointments_table.sql"
)

_MERGE_SQL = """
MERGE appointments AS target
USING (SELECT %s AS appointment_id) AS source
ON target.appointment_id = source.appointment_id
WHEN MATCHED THEN
    UPDATE SET status = %s, completed_at = %s
WHEN NOT MATCHED THEN
    INSERT (appointment_id, insured_id, schedule_id, status, created_at, completed_at)
    VALUES (%s, %s, %s, %s, %s, %s);
"""


class AzureSqlAppointmentRepository:
    def __init__(
        self,
        host: str,
        database: str,
        authentication: str,
        user: str,
        password: str,
        circuit_breaker: CircuitBreaker,
        connection_factory: Any = None,
    ) -> None:
        self._circuit_breaker = circuit_breaker
        self._host = host
        self._database = database
        self._authentication = authentication or "SqlPassword"
        self._user = user
        self._password = password
        self._connection_factory = connection_factory or self._default_connection_factory
        self._migrate_schema()

    def _default_connection_factory(self) -> Any:
        import pymssql

        if self._authentication == "ActiveDirectoryManagedIdentity":
            from azure.identity import DefaultAzureCredential

            token = DefaultAzureCredential().get_token("https://database.windows.net/.default")
            return pymssql.connect(server=self._host, database=self._database, password=token.token)
        return pymssql.connect(
            server=self._host,
            database=self._database,
            user=self._user,
            password=self._password,
            login_timeout=30,
        )

    def _migrate_schema(self) -> None:
        sql = _MIGRATION_PATH.read_text(encoding="utf-8")
        guarded = f"""
IF NOT EXISTS (
    SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'appointments') AND type = 'U'
)
BEGIN
{sql}
END
"""
        conn = self._connection_factory()
        try:
            cur = conn.cursor()
            cur.execute(guarded)
            conn.commit()
        finally:
            conn.close()

    def persist(self, appointment: Appointment) -> None:
        def op() -> None:
            try:
                conn = self._connection_factory()
                try:
                    cur = conn.cursor()
                    completed_at = appointment.completed_at
                    cur.execute(
                        _MERGE_SQL,
                        (
                            appointment.appointment_id,
                            appointment.status.value,
                            completed_at,
                            appointment.appointment_id,
                            appointment.insured_id,
                            appointment.schedule_id,
                            appointment.status.value,
                            appointment.created_at,
                            completed_at,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"Failed to persist appointment to Azure SQL: {e}") from e

        self._resilient(op)

    def ping(self) -> str:
        try:
            conn = self._connection_factory()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchall()
            finally:
                conn.close()
            return "UP"
        except Exception as e:  # noqa: BLE001
            return f"DOWN: {e}"

    def _resilient(self, fn: Any) -> Any:
        return self._circuit_breaker.execute(lambda: with_retry(fn))
