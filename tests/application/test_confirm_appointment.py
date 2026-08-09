import pytest

from clinic.application.usecases.confirm_appointment import ConfirmAppointmentUseCase
from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError
from tests.fakes import CapturingNotifier, InMemoryEventStore, InMemoryStateRepository


def test_confirms_pending_appointment():
    state = InMemoryStateRepository()
    notifier = CapturingNotifier()
    event_store = InMemoryEventStore()
    appt = Appointment.create("appt-1", "12345", 10)
    state.save(appt)

    ConfirmAppointmentUseCase(state, notifier, event_store).execute("appt-1")

    updated = state.find_by_id("appt-1")
    assert updated.status == AppointmentStatus.COMPLETED
    assert notifier.completed == [updated]
    assert len(event_store.events) == 1
    assert event_store.events[0].event_type == "APPOINTMENT_COMPLETED"


def test_is_idempotent_for_already_completed_appointment():
    state = InMemoryStateRepository()
    notifier = CapturingNotifier()
    event_store = InMemoryEventStore()
    appt = Appointment.create("appt-1", "12345", 10)
    appt.mark_completed()
    state.save(appt)

    ConfirmAppointmentUseCase(state, notifier, event_store).execute("appt-1")

    assert notifier.completed == []
    assert event_store.events == []


def test_throws_when_appointment_not_found():
    state = InMemoryStateRepository()
    with pytest.raises(IllegalStateError):
        ConfirmAppointmentUseCase(state, CapturingNotifier(), InMemoryEventStore()).execute(
            "missing"
        )
