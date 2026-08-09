"""Application use case: fetch the ordered event log for a single appointment.

Unlike the original Java implementation (where this logic was inlined directly in
``GetAppointmentHistoryHandler`` and derived the owning insuredId from the *first event*, which
let an appointment with zero events bypass the ownership check entirely), this use case looks up
the appointment itself first and applies the same ownership-check pattern used by
cancel/reschedule/get-appointments - closing that gap.
"""

from __future__ import annotations

from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.domain.exceptions import ForbiddenError, IllegalStateError
from clinic.domain.ports.appointment_event_store import AppointmentEventStore
from clinic.domain.ports.appointment_state_repository import AppointmentStateRepository
from clinic.infrastructure.auth.jwt_validator import AuthenticatedUser


class GetAppointmentHistoryUseCase:
    def __init__(
        self,
        state_repository: AppointmentStateRepository,
        event_store: AppointmentEventStore,
    ) -> None:
        self._state_repository = state_repository
        self._event_store = event_store

    def execute(
        self, appointment_id: str, requesting_user: AuthenticatedUser
    ) -> list[AppointmentEvent]:
        appointment = self._state_repository.find_by_id(appointment_id)
        if appointment is None:
            raise IllegalStateError(f"Appointment not found: {appointment_id}")
        if requesting_user.role == "insured" and appointment.insured_id != requesting_user.sub:
            raise ForbiddenError("insured can only view their own appointment history")

        return self._event_store.find_by_appointment_id(appointment_id)
