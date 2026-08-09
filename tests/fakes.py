"""Hand-written in-memory fakes for the domain ports, used across application-layer unit tests -
mirrors the pattern used in this portfolio's AWS TypeScript sibling project's test suite."""

from __future__ import annotations

from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.domain.shared.page import Page


class InMemoryStateRepository:
    def __init__(self) -> None:
        self.store: dict[str, Appointment] = {}

    def save(self, appointment: Appointment) -> None:
        self.store[appointment.appointment_id] = appointment

    def find_by_id(self, appointment_id: str) -> Appointment | None:
        return self.store.get(appointment_id)

    def find_by_insured_id(self, insured_id: str) -> list[Appointment]:
        return [a for a in self.store.values() if a.insured_id == insured_id]

    def update_status(self, appointment: Appointment) -> None:
        self.store[appointment.appointment_id] = appointment

    def find_by_insured_id_page(self, insured_id: str, page_size: int, continuation_token):
        items = self.find_by_insured_id(insured_id)
        return Page(items=items, next_cursor=None)


class CapturingEventPublisher:
    def __init__(self) -> None:
        self.created: list[Appointment] = []

    def publish_created(self, appointment: Appointment) -> None:
        self.created.append(appointment)


class CapturingNotifier:
    def __init__(self) -> None:
        self.completed: list[Appointment] = []

    def notify_completed(self, appointment: Appointment) -> None:
        self.completed.append(appointment)


class InMemoryEventStore:
    def __init__(self) -> None:
        self.events: list[AppointmentEvent] = []

    def append(self, event: AppointmentEvent) -> None:
        self.events.append(event)

    def find_by_appointment_id(self, appointment_id: str) -> list[AppointmentEvent]:
        return [e for e in self.events if e.appointment_id == appointment_id]


class CapturingRelationalRepository:
    def __init__(self) -> None:
        self.persisted: list[Appointment] = []

    def persist(self, appointment: Appointment) -> None:
        self.persisted.append(appointment)


class CapturingConfirmationPublisher:
    def __init__(self) -> None:
        self.confirmed: list[str] = []

    def publish_confirmed(self, appointment_id: str) -> None:
        self.confirmed.append(appointment_id)
