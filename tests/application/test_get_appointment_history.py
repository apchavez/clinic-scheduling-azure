import pytest

from clinic.application.usecases.get_appointment_history import GetAppointmentHistoryUseCase
from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.domain.exceptions import ForbiddenError, IllegalStateError
from clinic.infrastructure.auth.jwt_validator import AuthenticatedUser
from tests.fakes import InMemoryEventStore, InMemoryStateRepository

AGENT = AuthenticatedUser(sub="agent-1", role="agent")
OWNER = AuthenticatedUser(sub="12345", role="insured")
OTHER_INSURED = AuthenticatedUser(sub="99999", role="insured")


def test_returns_events_for_owner():
    state = InMemoryStateRepository()
    events = InMemoryEventStore()
    appt = Appointment.create("appt-1", "12345", 10)
    state.save(appt)
    events.append(AppointmentEvent.of("APPOINTMENT_CREATED", appt))

    result = GetAppointmentHistoryUseCase(state, events).execute("appt-1", OWNER)

    assert len(result) == 1
    assert result[0].event_type == "APPOINTMENT_CREATED"


def test_agent_can_view_any_appointment_history():
    state = InMemoryStateRepository()
    events = InMemoryEventStore()
    appt = Appointment.create("appt-1", "12345", 10)
    state.save(appt)

    result = GetAppointmentHistoryUseCase(state, events).execute("appt-1", AGENT)
    assert result == []


def test_throws_when_appointment_not_found():
    state = InMemoryStateRepository()
    events = InMemoryEventStore()
    with pytest.raises(IllegalStateError):
        GetAppointmentHistoryUseCase(state, events).execute("missing", AGENT)


def test_insured_cannot_view_someone_elses_history_even_with_no_events():
    """Regression test for the ownership-check gap fixed during the Python port: the original
    Java handler derived ownership from events[0], which let a zero-event appointment bypass the
    403 entirely. This use case checks the appointment's insuredId directly instead."""
    state = InMemoryStateRepository()
    events = InMemoryEventStore()
    state.save(Appointment.create("appt-1", "12345", 10))

    with pytest.raises(ForbiddenError):
        GetAppointmentHistoryUseCase(state, events).execute("appt-1", OTHER_INSURED)
