"""Core domain entity - mirrors the TypeScript "Appointment" entity from the AWS project. Pure
business object: no framework, no Azure, no persistence concerns. This is the heart of the Clean
Architecture domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError


@dataclass
class Appointment:
    appointment_id: str | None = None
    insured_id: str | None = None
    schedule_id: int = 0
    status: AppointmentStatus | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    contact_email: str | None = None

    @staticmethod
    def create(appointment_id: str, insured_id: str, schedule_id: int) -> Appointment:
        return Appointment(
            appointment_id=appointment_id,
            insured_id=insured_id,
            schedule_id=schedule_id,
            status=AppointmentStatus.PENDING,
            created_at=datetime.now(UTC),
        )

    def mark_completed(self) -> None:
        if self.status != AppointmentStatus.PENDING:
            raise IllegalStateError(
                f"Only a PENDING appointment can be completed (current: {self.status})"
            )
        self.status = AppointmentStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
