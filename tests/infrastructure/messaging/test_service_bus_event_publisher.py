import json
from unittest.mock import MagicMock, patch

from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.config.resilience import CircuitBreaker
from clinic.infrastructure.messaging.service_bus_event_publisher import ServiceBusEventPublisher


def _make_publisher():
    client = MagicMock()
    sender = MagicMock()
    client.get_topic_sender.return_value.__enter__.return_value = sender
    admin_client = MagicMock()
    publisher = ServiceBusEventPublisher(
        "ns.servicebus.windows.net",
        "appointment-created",
        CircuitBreaker("test-sb"),
        client=client,
        admin_client=admin_client,
    )
    return publisher, client, sender, admin_client


def test_publish_created_sends_to_created_topic_with_schedule_id():
    publisher, client, sender, _ = _make_publisher()
    a = Appointment.create("a1", "12345", 10)

    with patch(
        "clinic.infrastructure.messaging.service_bus_event_publisher.ServiceBusMessage"
    ) as mock_msg_cls:
        mock_msg = MagicMock()
        mock_msg_cls.return_value = mock_msg
        publisher.publish_created(a)

    client.get_topic_sender.assert_called_once_with(topic_name="appointment-created")
    sender.send_messages.assert_called_once_with(mock_msg)
    body = json.loads(mock_msg_cls.call_args[0][0])
    assert body["eventType"] == "APPOINTMENT_CREATED"
    assert body["scheduleId"] == 10
    assert body["appointmentId"] == "a1"
    assert mock_msg.application_properties == {
        "eventType": "APPOINTMENT_CREATED",
    }


def test_publish_failure_is_wrapped_in_runtime_error():
    publisher, client, sender, _ = _make_publisher()
    sender.send_messages.side_effect = RuntimeError("send failed")
    a = Appointment.create("a1", "12345", 10)

    try:
        publisher.publish_created(a)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_ping_returns_up_when_admin_call_succeeds():
    publisher, _, _, admin_client = _make_publisher()
    assert publisher.ping() == "UP"
    admin_client.get_namespace_properties.assert_called_once()


def test_ping_returns_down_on_failure():
    publisher, _, _, admin_client = _make_publisher()
    admin_client.get_namespace_properties.side_effect = RuntimeError("unreachable")
    assert publisher.ping().startswith("DOWN")
