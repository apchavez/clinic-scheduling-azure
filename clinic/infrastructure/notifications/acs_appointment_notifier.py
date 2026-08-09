"""Azure Communication Services adapter implementing the notification port. Sends transactional
emails to the insured party on appointment lifecycle events.

Best-effort: failures are logged but never propagated. A notification failure must not prevent
the appointment lifecycle from completing.

Authenticates via Managed Identity (DefaultAzureCredential). Skips silently when contact_email is
absent or ACS endpoint is not configured.
"""

from __future__ import annotations

import logging

from clinic.domain.entities.appointment import Appointment

log = logging.getLogger(__name__)


class AcsAppointmentNotifier:
    def __init__(self, acs_endpoint: str, sender_address: str, email_client=None) -> None:
        self._sender_address = sender_address
        if email_client is not None:
            self._email_client = email_client
        else:
            from azure.communication.email import EmailClient
            from azure.identity import DefaultAzureCredential

            self._email_client = EmailClient(acs_endpoint, DefaultAzureCredential())

    def notify_completed(self, appointment: Appointment) -> None:
        if not self._has_email(appointment):
            return
        self._send(
            appointment.contact_email,
            "Your appointment has been confirmed",
            f"Your appointment (ID: {appointment.appointment_id}, schedule: "
            f"{appointment.schedule_id}) has been successfully processed.",
        )

    def _send(self, to: str, subject: str, body: str) -> None:
        try:
            message = {
                "senderAddress": self._sender_address,
                "recipients": {"to": [{"address": to}]},
                "content": {"subject": subject, "plainText": body},
            }
            poller = self._email_client.begin_send(message)
            poller.result()
            log.info("Notification sent to %s - %s", to, subject)
        except Exception as e:  # noqa: BLE001
            log.warning("Notification failed (best-effort, continuing): %s", e)

    @staticmethod
    def _has_email(appointment: Appointment) -> bool:
        return bool(appointment.contact_email and appointment.contact_email.strip())
