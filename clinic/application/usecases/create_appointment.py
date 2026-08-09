"""Application use case: create a new appointment request.

Mirrors the AWS "createAppointment" handler logic, but keeps the business orchestration
framework-agnostic. Depends only on ports (interfaces).

Flow: generate id -> persist PENDING state (Cosmos) -> publish created event (Service Bus) for
downstream processing.
"""

from __future__ import annotations

import uuid

from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.domain.ports.appointment_event_publisher import AppointmentEventPublisher
from clinic.domain.ports.appointment_event_store import AppointmentEventStore
from clinic.domain.ports.appointment_state_repository import AppointmentStateRepository


class CreateAppointmentUseCase:
    def __init__(
        self,
        state_repository: AppointmentStateRepository,
        event_publisher: AppointmentEventPublisher,
        event_store: AppointmentEventStore,
    ) -> None:
        self._state_repository = state_repository
        self._event_publisher = event_publisher
        self._event_store = event_store

    def execute(
        self,
        insured_id: str,
        schedule_id: int,
        contact_email: str | None,
    ) -> Appointment:
        appointment_id = str(uuid.uuid4())
        appointment = Appointment.create(appointment_id, insured_id, schedule_id)
        appointment.contact_email = contact_email

        self._state_repository.save(appointment)
        self._event_publisher.publish_created(appointment)
        self._event_store.append(AppointmentEvent.of("APPOINTMENT_CREATED", appointment))

        return appointment
