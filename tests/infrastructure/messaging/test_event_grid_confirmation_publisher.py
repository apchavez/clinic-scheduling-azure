from unittest.mock import MagicMock

from clinic.infrastructure.config.resilience import CircuitBreaker
from clinic.infrastructure.messaging.event_grid_confirmation_publisher import (
    EventGridConfirmationPublisher,
)


def _make_publisher():
    client = MagicMock()
    publisher = EventGridConfirmationPublisher(
        "https://topic.region-1.eventgrid.azure.net/api/events",
        CircuitBreaker("test-eventgrid"),
        client=client,
    )
    return publisher, client


def test_publish_confirmed_sends_a_cloud_event():
    publisher, client = _make_publisher()

    publisher.publish_confirmed("appt-1")

    client.send.assert_called_once()
    (event,) = client.send.call_args[0]
    assert event.source == "appointment-service"
    assert event.type == "AppointmentConfirmed"
    assert event.data == {"appointmentId": "appt-1"}


def test_publish_failure_is_wrapped_in_runtime_error():
    publisher, client = _make_publisher()
    client.send.side_effect = RuntimeError("send failed")

    raised = False
    try:
        publisher.publish_confirmed("appt-1")
    except RuntimeError:
        raised = True
    assert raised
