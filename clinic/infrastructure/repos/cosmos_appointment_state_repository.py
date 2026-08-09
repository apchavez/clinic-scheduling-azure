"""Cosmos DB adapter implementing the state repository port. This is the Azure equivalent of the
AWS project's DynamoDB repository: fast key-value state tracking for the pending/completed
lifecycle.

Authenticates via Managed Identity (DefaultAzureCredential) - no key in config. Only this class
knows about Cosmos. The domain/application layers depend solely on the
AppointmentStateRepository port.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from azure.core.exceptions import ResourceNotFoundError

from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.shared.page import Page
from clinic.infrastructure.config.resilience import CircuitBreaker, with_retry


class CosmosAppointmentStateRepository:
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

    def save(self, appointment: Appointment) -> None:
        self._resilient(lambda: self._container.create_item(self._to_item(appointment)))

    def find_by_id(self, appointment_id: str) -> Appointment | None:
        def op() -> Appointment | None:
            try:
                item = self._container.read_item(item=appointment_id, partition_key=appointment_id)
                return self._to_domain(item)
            except ResourceNotFoundError:
                return None

        return self._resilient(op)

    def find_by_insured_id(self, insured_id: str) -> list[Appointment]:
        def op() -> list[Appointment]:
            items = self._container.query_items(
                query="SELECT * FROM c WHERE c.insuredId = @insuredId",
                parameters=[{"name": "@insuredId", "value": insured_id}],
                enable_cross_partition_query=True,
            )
            return [self._to_domain(item) for item in items]

        return self._resilient(op)

    def find_by_insured_id_page(
        self, insured_id: str, page_size: int, continuation_token: str | None
    ) -> Page[Appointment]:
        def op() -> Page[Appointment]:
            pager = self._container.query_items(
                query="SELECT * FROM c WHERE c.insuredId = @insuredId",
                parameters=[{"name": "@insuredId", "value": insured_id}],
                enable_cross_partition_query=True,
                max_item_count=page_size,
            ).by_page(continuation_token)
            try:
                items_page = next(pager)
            except StopIteration:
                return Page(items=[], next_cursor=None)
            items = [self._to_domain(item) for item in items_page]
            next_token = pager.continuation_token
            return Page(items=items, next_cursor=next_token)

        return self._resilient(op)

    def update_status(self, appointment: Appointment) -> None:
        self._resilient(
            lambda: self._container.replace_item(
                item=appointment.appointment_id, body=self._to_item(appointment)
            )
        )

    def ping(self) -> str:
        try:
            self._container.read()
            return "UP"
        except Exception as e:  # noqa: BLE001
            return f"DOWN: {e}"

    def _resilient(self, fn: Any) -> Any:
        return self._circuit_breaker.execute(lambda: with_retry(fn))

    @staticmethod
    def _to_item(a: Appointment) -> dict[str, Any]:
        return {
            "id": a.appointment_id,
            "insuredId": a.insured_id,
            "scheduleId": a.schedule_id,
            "status": a.status.value,
            "createdAt": a.created_at.isoformat() if a.created_at else None,
            "completedAt": a.completed_at.isoformat() if a.completed_at else None,
            "contactEmail": a.contact_email,
        }

    @staticmethod
    def _to_domain(item: dict[str, Any]) -> Appointment:
        return Appointment(
            appointment_id=item["id"],
            insured_id=item["insuredId"],
            schedule_id=item["scheduleId"],
            status=AppointmentStatus(str(item["status"]).lower()),
            created_at=datetime.fromisoformat(item["createdAt"]) if item.get("createdAt") else None,
            completed_at=(
                datetime.fromisoformat(item["completedAt"]) if item.get("completedAt") else None
            ),
            contact_email=item.get("contactEmail"),
        )
