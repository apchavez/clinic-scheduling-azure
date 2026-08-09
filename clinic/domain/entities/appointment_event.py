"""Immutable record of a single state transition in an appointment's lifecycle. Written once, never
updated - this is the "event" in lightweight event sourcing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clinic.domain.entities.appointment import Appointment


@dataclass
class AppointmentEvent:
    event_id: str
    appointment_id: str
    event_type: str
    insured_id: str
    schedule_id: int
    status: str
    occurred_at: datetime

    @staticmethod
    def of(event_type: str, appointment: Appointment) -> AppointmentEvent:
        return AppointmentEvent(
            event_id=str(uuid.uuid4()),
            appointment_id=appointment.appointment_id,
            event_type=event_type,
            insured_id=appointment.insured_id,
            schedule_id=appointment.schedule_id,
            status=appointment.status.value,
            occurred_at=datetime.now(UTC),
        )
