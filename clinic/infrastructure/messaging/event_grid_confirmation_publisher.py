"""Event Grid adapter implementing the confirmation-publisher port. Azure equivalent of the AWS
project's EventBridge `PutEvents` call (`EventBridgeConfirmationBus`).

Authenticates via Managed Identity (DefaultAzureCredential) using the topic's HTTPS endpoint -
no key/connection string stored in config. Publishes a single CloudEvent per call; delivery to
the downstream Service Bus queue (`appointment-confirmations`) is handled by the Event Grid
Subscription's own resource-identity-based delivery (see infra/core.bicep), not by this class.
"""

from __future__ import annotations

from azure.core.messaging import CloudEvent
from azure.eventgrid import EventGridPublisherClient

from clinic.infrastructure.config.resilience import CircuitBreaker, with_retry

EVENT_SOURCE = "appointment-service"
EVENT_TYPE = "AppointmentConfirmed"


class EventGridConfirmationPublisher:
    def __init__(
        self,
        topic_endpoint: str,
        circuit_breaker: CircuitBreaker,
        client: EventGridPublisherClient | None = None,
    ) -> None:
        self._circuit_breaker = circuit_breaker
        if client is not None:
            self._client = client
        else:
            from azure.identity import DefaultAzureCredential

            self._client = EventGridPublisherClient(topic_endpoint, DefaultAzureCredential())

    def publish_confirmed(self, appointment_id: str) -> None:
        self._resilient(lambda: self._send(appointment_id))

    def _send(self, appointment_id: str) -> None:
        try:
            event = CloudEvent(
                source=EVENT_SOURCE,
                type=EVENT_TYPE,
                data={"appointmentId": appointment_id},
            )
            self._client.send(event)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("Failed to publish AppointmentConfirmed event") from e

    def _resilient(self, fn) -> None:
        self._circuit_breaker.execute(lambda: with_retry(fn))
