"""Application use case executed by the worker consuming the `appointment-created` Service Bus
topic (subscription `appointment-worker`, see function_app.py). This is stage 1 of a 2-stage
completion pipeline, mirroring the AWS sibling's countryWorker -> EventBridge -> confirmAppointment
split:
1. load the appointment state (Cosmos, still PENDING)
2. persist the final relational record (Azure SQL)
3. publish "AppointmentConfirmed" to Event Grid for a separate, decoupled handler
   (ConfirmAppointmentUseCase) to finish the lifecycle - this stage never marks Cosmos completed
   or notifies the insured party itself.

Idempotent: guarded by Cosmos status, so a fully-completed appointment (stage 2 already ran)
short-circuits here too. A redelivered Service Bus message that races stage 2 is still safe: the
relational persist is an upsert (see AzureSqlAppointmentRepository) and a duplicate Event Grid
publish is absorbed by stage 2's own idempotency guard.
"""

from __future__ import annotations

from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError
from clinic.domain.ports.appointment_confirmation_publisher import AppointmentConfirmationPublisher
from clinic.domain.ports.appointment_relational_repository import AppointmentRelationalRepository
from clinic.domain.ports.appointment_state_repository import AppointmentStateRepository


class ProcessAppointmentUseCase:
    def __init__(
        self,
        state_repository: AppointmentStateRepository,
        relational_repository: AppointmentRelationalRepository,
        confirmation_publisher: AppointmentConfirmationPublisher,
    ) -> None:
        self._state_repository = state_repository
        self._relational_repository = relational_repository
        self._confirmation_publisher = confirmation_publisher

    def execute(self, appointment_id: str) -> None:
        appointment = self._state_repository.find_by_id(appointment_id)
        if appointment is None:
            raise IllegalStateError(f"Appointment not found: {appointment_id}")

        if appointment.status == AppointmentStatus.COMPLETED:
            return

        appointment.mark_completed()
        self._relational_repository.persist(appointment)
        self._confirmation_publisher.publish_confirmed(appointment.appointment_id)
