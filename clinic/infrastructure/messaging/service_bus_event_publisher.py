"""Service Bus adapter implementing the event publisher port. Azure equivalent of the AWS
project's SNS+SQS / EventBridge publishing.

Authenticates via Managed Identity (DefaultAzureCredential) using the fully-qualified namespace
name. No connection string stored in config. Single topic, single subscription
(`appointment-worker`) - see `appointment_worker` in function_app.py for the consumer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus.management import ServiceBusAdministrationClient

from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.config import correlation_context
from clinic.infrastructure.config.resilience import CircuitBreaker, with_retry


class ServiceBusEventPublisher:
    def __init__(
        self,
        fully_qualified_namespace: str,
        created_topic: str,
        circuit_breaker: CircuitBreaker,
        client: ServiceBusClient | None = None,
        admin_client: ServiceBusAdministrationClient | None = None,
    ) -> None:
        self._fully_qualified_namespace = fully_qualified_namespace
        self._circuit_breaker = circuit_breaker
        self._created_topic = created_topic

        if client is not None:
            self._client = client
        else:
            from azure.identity import DefaultAzureCredential

            self._client = ServiceBusClient(fully_qualified_namespace, DefaultAzureCredential())

        if admin_client is not None:
            self._admin_client = admin_client
        elif client is None:
            from azure.identity import DefaultAzureCredential

            self._admin_client = ServiceBusAdministrationClient(
                fully_qualified_namespace, DefaultAzureCredential()
            )
        else:
            self._admin_client = None

    def ping(self) -> str:
        try:
            if self._admin_client is None:
                raise RuntimeError("Administration client not configured")
            self._admin_client.get_namespace_properties()
            return "UP"
        except Exception as e:  # noqa: BLE001
            return f"DOWN: {e}"

    def publish_created(self, appointment: Appointment) -> None:
        self._resilient(
            lambda: self._send(
                self._created_topic, "APPOINTMENT_CREATED", appointment, include_schedule=True
            )
        )

    def _send(
        self, topic: str, event_type: str, appointment: Appointment, include_schedule: bool
    ) -> None:
        try:
            corr_id = self._correlation_id(appointment)
            body: dict[str, Any] = {
                "eventType": event_type,
                "appointmentId": appointment.appointment_id,
                "correlationId": corr_id,
                "insuredId": appointment.insured_id,
                "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            if include_schedule:
                body["scheduleId"] = appointment.schedule_id

            message = ServiceBusMessage(json.dumps(body))
            message.correlation_id = corr_id
            message.application_properties = {
                "eventType": event_type,
            }
            with self._client.get_topic_sender(topic_name=topic) as sender:
                sender.send_messages(message)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Failed to publish {event_type} event") from e

    @staticmethod
    def _correlation_id(appointment: Appointment) -> str:
        ctx = correlation_context.get_correlation_id()
        return ctx if ctx else appointment.appointment_id

    def _resilient(self, fn: Any) -> None:
        self._circuit_breaker.execute(lambda: with_retry(fn))
