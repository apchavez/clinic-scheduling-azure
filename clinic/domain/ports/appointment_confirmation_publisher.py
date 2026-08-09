"""Port for publishing the "appointment confirmed" event to the eventing backbone.

Mirrors the AWS sibling project's EventBridge publish (`EventBridgeConfirmationBus`): the
relational-persist worker doesn't mark the appointment complete or notify itself - it publishes
an event that a separate, decoupled handler consumes to finish the lifecycle. Here the adapter
targets Azure Event Grid, but the application layer doesn't know that.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AppointmentConfirmationPublisher(Protocol):
    def publish_confirmed(self, appointment_id: str) -> None:
        """Publishes the "appointment confirmed" event for async completion by a separate
        handler (decoupled from this worker, matching the AWS EventBridge->SQS->Lambda hop)."""
