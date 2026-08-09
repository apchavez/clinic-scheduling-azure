"""Port for final relational persistence. Implemented by an Azure SQL Database adapter
(equivalent to MySQL in the AWS project).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinic.domain.entities.appointment import Appointment


@runtime_checkable
class AppointmentRelationalRepository(Protocol):
    def persist(self, appointment: Appointment) -> None: ...
