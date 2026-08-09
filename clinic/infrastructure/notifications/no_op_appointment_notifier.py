"""No-op implementation used when ACS is not configured (ACS_ENDPOINT is absent)."""

from __future__ import annotations

from clinic.domain.entities.appointment import Appointment


class NoOpAppointmentNotifier:
    def notify_completed(self, appointment: Appointment) -> None:
        pass
