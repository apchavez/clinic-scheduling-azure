"""Application use case executed by the handler consuming the `appointment-confirmations`
Service Bus queue (fed by an Event Grid Subscription off the "AppointmentConfirmed" topic - see
function_app.py and infra/core.bicep). This is stage 2 of the completion pipeline, mirroring the
AWS sibling's `confirmAppointment` Lambda:
1. load the appointment state (Cosmos, still PENDING - stage 1/ProcessAppointmentUseCase already
   persisted the final relational record but never touched Cosmos)
2. mark it completed (domain invariant)
3. update state to completed (Cosmos)
4. record the completion in the event store and notify the insured party

Idempotent: mark_completed() only transitions from PENDING, so a redelivered message (Event Grid
retry, or a duplicate publish from stage 1) won't double-process.
"""

from __future__ import annotations

from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError
from clinic.domain.ports.appointment_event_store import AppointmentEventStore
from clinic.domain.ports.appointment_notifier import AppointmentNotifier
from clinic.domain.ports.appointment_state_repository import AppointmentStateRepository


class ConfirmAppointmentUseCase:
    def __init__(
        self,
        state_repository: AppointmentStateRepository,
        notifier: AppointmentNotifier,
        event_store: AppointmentEventStore,
    ) -> None:
        self._state_repository = state_repository
        self._notifier = notifier
        self._event_store = event_store

    def execute(self, appointment_id: str) -> None:
        appointment = self._state_repository.find_by_id(appointment_id)
        if appointment is None:
            raise IllegalStateError(f"Appointment not found: {appointment_id}")

        if appointment.status == AppointmentStatus.COMPLETED:
            return

        appointment.mark_completed()
        self._state_repository.update_status(appointment)
        self._event_store.append(AppointmentEvent.of("APPOINTMENT_COMPLETED", appointment))
        self._notifier.notify_completed(appointment)
