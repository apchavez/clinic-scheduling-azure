from unittest.mock import MagicMock

from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.notifications.acs_appointment_notifier import AcsAppointmentNotifier


def _appointment_with_email():
    a = Appointment.create("a1", "12345", 10)
    a.contact_email = "insured@example.com"
    return a


def test_notify_completed_sends_email():
    client = MagicMock()
    notifier = AcsAppointmentNotifier("https://acs.example.com", "sender@example.com", client)

    notifier.notify_completed(_appointment_with_email())

    client.begin_send.assert_called_once()
    sent_message = client.begin_send.call_args[0][0]
    assert sent_message["senderAddress"] == "sender@example.com"
    assert sent_message["recipients"]["to"][0]["address"] == "insured@example.com"


def test_notify_completed_skips_when_no_email():
    client = MagicMock()
    notifier = AcsAppointmentNotifier("https://acs.example.com", "sender@example.com", client)
    a = Appointment.create("a1", "12345", 10)

    notifier.notify_completed(a)

    client.begin_send.assert_not_called()


def test_send_failure_is_swallowed_not_propagated():
    client = MagicMock()
    client.begin_send.side_effect = RuntimeError("ACS down")
    notifier = AcsAppointmentNotifier("https://acs.example.com", "sender@example.com", client)

    notifier.notify_completed(_appointment_with_email())  # must not raise
