"""Application use case: list appointments for an insured. Mirrors the AWS "list appointments by
insuredId" query handler.
"""

from __future__ import annotations

from clinic.domain.entities.appointment import Appointment
from clinic.domain.ports.appointment_state_repository import AppointmentStateRepository
from clinic.domain.shared.page import Page

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class GetAppointmentsUseCase:
    def __init__(self, state_repository: AppointmentStateRepository) -> None:
        self._state_repository = state_repository

    def by_insured(self, insured_id: str) -> list[Appointment]:
        return self._state_repository.find_by_insured_id(insured_id)

    def by_insured_paged(
        self, insured_id: str, page_size: int, cursor: str | None
    ) -> Page[Appointment]:
        size = DEFAULT_PAGE_SIZE if page_size < 1 or page_size > MAX_PAGE_SIZE else page_size
        return self._state_repository.find_by_insured_id_page(insured_id, size, cursor)
