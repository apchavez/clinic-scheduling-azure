"""Port for the append-only event log. Each state transition produces one immutable
AppointmentEvent document. Implemented by a Cosmos DB adapter targeting the appointment-events
container.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinic.domain.entities.appointment_event import AppointmentEvent


@runtime_checkable
class AppointmentEventStore(Protocol):
    def append(self, event: AppointmentEvent) -> None: ...

    def find_by_appointment_id(self, appointment_id: str) -> list[AppointmentEvent]: ...
