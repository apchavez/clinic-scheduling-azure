"""Port (contract) for fast state tracking storage. Implemented by a Cosmos DB adapter in the
infrastructure layer (equivalent to DynamoDB in the AWS project).

The domain/application layers depend ONLY on this interface, never on Cosmos.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinic.domain.entities.appointment import Appointment
from clinic.domain.shared.page import Page


@runtime_checkable
class AppointmentStateRepository(Protocol):
    def save(self, appointment: Appointment) -> None: ...

    def find_by_id(self, appointment_id: str) -> Appointment | None: ...

    def find_by_insured_id(self, insured_id: str) -> list[Appointment]: ...

    def update_status(self, appointment: Appointment) -> None: ...

    def find_by_insured_id_page(
        self, insured_id: str, page_size: int, continuation_token: str | None
    ) -> Page[Appointment]: ...
