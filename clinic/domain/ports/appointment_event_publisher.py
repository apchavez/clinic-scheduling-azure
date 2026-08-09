"""Port for publishing appointment events to the messaging backbone.

The AWS sibling project used SNS(topic)->SQS(queue) for fan-out. Here the adapter targets a
single Azure Service Bus topic, but the application layer doesn't know that.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinic.domain.entities.appointment import Appointment


@runtime_checkable
class AppointmentEventPublisher(Protocol):
    def publish_created(self, appointment: Appointment) -> None:
        """Publishes the "appointment created" event for async processing by the worker."""
