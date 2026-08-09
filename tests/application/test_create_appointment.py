from clinic.application.usecases.create_appointment import CreateAppointmentUseCase
from clinic.domain.entities.appointment_status import AppointmentStatus
from tests.fakes import CapturingEventPublisher, InMemoryEventStore, InMemoryStateRepository


def test_create_persists_publishes_and_records_event():
    state = InMemoryStateRepository()
    publisher = CapturingEventPublisher()
    event_store = InMemoryEventStore()

    use_case = CreateAppointmentUseCase(state, publisher, event_store)
    appointment = use_case.execute("12345", 10, "a@b.com")

    assert appointment.status == AppointmentStatus.PENDING
    assert appointment.contact_email == "a@b.com"
    assert state.find_by_id(appointment.appointment_id) is appointment
    assert publisher.created == [appointment]
    assert len(event_store.events) == 1
    assert event_store.events[0].event_type == "APPOINTMENT_CREATED"
    assert event_store.events[0].appointment_id == appointment.appointment_id


def test_create_generates_unique_ids():
    state = InMemoryStateRepository()
    publisher = CapturingEventPublisher()
    event_store = InMemoryEventStore()
    use_case = CreateAppointmentUseCase(state, publisher, event_store)

    a1 = use_case.execute("12345", 10, None)
    a2 = use_case.execute("12345", 11, None)

    assert a1.appointment_id != a2.appointment_id
