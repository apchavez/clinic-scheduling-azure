from clinic.application.usecases.get_appointments import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    GetAppointmentsUseCase,
)
from clinic.domain.entities.appointment import Appointment
from tests.fakes import InMemoryStateRepository


def test_by_insured_returns_all_matching():
    state = InMemoryStateRepository()
    state.save(Appointment.create("a1", "12345", 1))
    state.save(Appointment.create("a2", "12345", 2))
    state.save(Appointment.create("a3", "99999", 3))

    result = GetAppointmentsUseCase(state).by_insured("12345")

    assert {a.appointment_id for a in result} == {"a1", "a2"}


def test_by_insured_paged_uses_default_size_for_invalid_input():
    state = InMemoryStateRepository()
    use_case = GetAppointmentsUseCase(state)

    page = use_case.by_insured_paged("12345", 0, None)
    assert page.items == []

    page2 = use_case.by_insured_paged("12345", MAX_PAGE_SIZE + 1, None)
    assert page2.items == []


def test_by_insured_paged_accepts_valid_page_size():
    state = InMemoryStateRepository()
    state.save(Appointment.create("a1", "12345", 1))

    page = GetAppointmentsUseCase(state).by_insured_paged("12345", DEFAULT_PAGE_SIZE, None)

    assert len(page.items) == 1
    assert page.next_cursor is None
