"""Port for sending notifications to the insured party. The domain/application layer depends
only on this interface; the infrastructure adapter targets Azure Communication Services Email
without the domain knowing.

Implementations are expected to be best-effort: a notification failure must NOT propagate to
the caller - the appointment lifecycle takes precedence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinic.domain.entities.appointment import Appointment


@runtime_checkable
class AppointmentNotifier(Protocol):
    def notify_completed(self, appointment: Appointment) -> None: ...
