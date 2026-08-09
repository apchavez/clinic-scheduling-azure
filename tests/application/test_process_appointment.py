import pytest

from clinic.application.usecases.process_appointment import ProcessAppointmentUseCase
from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError
from tests.fakes import (
    CapturingConfirmationPublisher,
    CapturingRelationalRepository,
    InMemoryStateRepository,
)


def test_persists_relational_record_and_publishes_confirmation():
    state = InMemoryStateRepository()
    relational = CapturingRelationalRepository()
    confirmation_publisher = CapturingConfirmationPublisher()
    appt = Appointment.create("appt-1", "12345", 10)
    state.save(appt)

    ProcessAppointmentUseCase(state, relational, confirmation_publisher).execute("appt-1")

    assert len(relational.persisted) == 1
    assert relational.persisted[0].status == AppointmentStatus.COMPLETED
    assert confirmation_publisher.confirmed == ["appt-1"]


def test_is_idempotent_for_already_completed_appointment():
    state = InMemoryStateRepository()
    relational = CapturingRelationalRepository()
    confirmation_publisher = CapturingConfirmationPublisher()
    appt = Appointment.create("appt-1", "12345", 10)
    appt.mark_completed()
    state.save(appt)

    ProcessAppointmentUseCase(state, relational, confirmation_publisher).execute("appt-1")

    assert relational.persisted == []
    assert confirmation_publisher.confirmed == []


def test_throws_when_appointment_not_found():
    state = InMemoryStateRepository()
    with pytest.raises(IllegalStateError):
        ProcessAppointmentUseCase(
            state,
            CapturingRelationalRepository(),
            CapturingConfirmationPublisher(),
        ).execute("missing")
