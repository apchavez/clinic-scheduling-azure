"""Cosmos DB adapter for the append-only event store. Writes to the appointment-events container
(separate from the state container) using appointment_id as the partition key so all events for
one appointment are co-located and can be retrieved in a single cross-partition-free query.

Documents are written once and never updated - immutability is enforced by always using
create_item (never replace_item).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from clinic.domain.entities.appointment_event import AppointmentEvent
from clinic.infrastructure.config.resilience import CircuitBreaker, with_retry


class CosmosAppointmentEventStore:
    def __init__(
        self,
        endpoint: str,
        database_name: str,
        container_name: str,
        circuit_breaker: CircuitBreaker,
        container: Any = None,
    ) -> None:
        self._circuit_breaker = circuit_breaker
        if container is not None:
            self._container = container
        else:
            self._container = self._build_container(endpoint, database_name, container_name)

    @staticmethod
    def _build_container(endpoint: str, database_name: str, container_name: str) -> Any:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        return client.get_database_client(database_name).get_container_client(container_name)

    def append(self, event: AppointmentEvent) -> None:
        self._resilient(lambda: self._container.create_item(self._to_item(event)))

    def find_by_appointment_id(self, appointment_id: str) -> list[AppointmentEvent]:
        def op() -> list[AppointmentEvent]:
            items = self._container.query_items(
                query=(
                    "SELECT * FROM c WHERE c.appointmentId = @appointmentId "
                    "ORDER BY c.occurredAt ASC"
                ),
                parameters=[{"name": "@appointmentId", "value": appointment_id}],
                partition_key=appointment_id,
            )
            events = [self._to_domain(item) for item in items]
            events.sort(key=lambda e: e.occurred_at)
            return events

        return self._resilient(op)

    def _resilient(self, fn: Any) -> Any:
        return self._circuit_breaker.execute(lambda: with_retry(fn))

    @staticmethod
    def _to_item(e: AppointmentEvent) -> dict[str, Any]:
        return {
            "id": e.event_id,
            "appointmentId": e.appointment_id,
            "eventType": e.event_type,
            "insuredId": e.insured_id,
            "scheduleId": e.schedule_id,
            "status": e.status,
            "occurredAt": e.occurred_at.isoformat() if e.occurred_at else None,
        }

    @staticmethod
    def _to_domain(item: dict[str, Any]) -> AppointmentEvent:
        return AppointmentEvent(
            event_id=item["id"],
            appointment_id=item["appointmentId"],
            event_type=item["eventType"],
            insured_id=item["insuredId"],
            schedule_id=item["scheduleId"],
            status=item["status"],
            occurred_at=datetime.fromisoformat(item["occurredAt"])
            if item.get("occurredAt")
            else None,
        )
