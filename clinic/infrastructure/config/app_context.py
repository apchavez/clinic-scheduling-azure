"""Manual composition root (no DI framework). Works with the Azure Functions Python worker.
Adapters and use cases are created once (lazy module-level singletons) and reused across warm
invocations, reading configuration from environment variables (the Function App's app settings).
"""

from __future__ import annotations

import os

from clinic.application.usecases.confirm_appointment import ConfirmAppointmentUseCase
from clinic.application.usecases.create_appointment import CreateAppointmentUseCase
from clinic.application.usecases.get_appointment_history import GetAppointmentHistoryUseCase
from clinic.application.usecases.get_appointments import GetAppointmentsUseCase
from clinic.application.usecases.process_appointment import ProcessAppointmentUseCase
from clinic.infrastructure.config.resilience import CircuitBreaker
from clinic.infrastructure.messaging.event_grid_confirmation_publisher import (
    EventGridConfirmationPublisher,
)
from clinic.infrastructure.messaging.service_bus_event_publisher import ServiceBusEventPublisher
from clinic.infrastructure.notifications.acs_appointment_notifier import AcsAppointmentNotifier
from clinic.infrastructure.notifications.no_op_appointment_notifier import (
    NoOpAppointmentNotifier,
)
from clinic.infrastructure.repos.azure_sql_appointment_repository import (
    AzureSqlAppointmentRepository,
)
from clinic.infrastructure.repos.cosmos_appointment_event_store import CosmosAppointmentEventStore
from clinic.infrastructure.repos.cosmos_appointment_state_repository import (
    CosmosAppointmentStateRepository,
)
from clinic.shared.health_status import DOWN, UP, HealthStatus

REQUIRED_ENV_VARS = [
    "COSMOS_ENDPOINT",
    "SERVICEBUS__fullyQualifiedNamespace",
    "SQL_HOST",
    "SQL_USER",
    "SQL_PASSWORD",
    "JWT_SECRET",
    "EVENTGRID_TOPIC_ENDPOINT",
]


def find_missing_env_vars(required: list[str], env_lookup) -> list[str]:
    """Extracted for testability - see validate_none_missing."""
    return [name for name in required if not (env_lookup(name) or "").strip()]


def validate_none_missing(missing: list[str]) -> None:
    """Extracted for testability alongside find_missing_env_vars."""
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {missing}. Application cannot start."
        )


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v and v.strip() else default


class _Registry:
    """Holds lazily-built singletons. A plain object (rather than module globals) so tests can
    construct a fresh registry and avoid cross-test state leaking through module-level caches.
    """

    def __init__(self) -> None:
        self.state_repository: CosmosAppointmentStateRepository | None = None
        self.event_publisher: ServiceBusEventPublisher | None = None
        self.relational_repository: AzureSqlAppointmentRepository | None = None
        self.event_store: CosmosAppointmentEventStore | None = None
        self.notifier: object | None = None
        self.confirmation_publisher: EventGridConfirmationPublisher | None = None
        self.create_use_case: CreateAppointmentUseCase | None = None
        self.process_use_case: ProcessAppointmentUseCase | None = None
        self.confirm_use_case: ConfirmAppointmentUseCase | None = None
        self.get_use_case: GetAppointmentsUseCase | None = None
        self.history_use_case: GetAppointmentHistoryUseCase | None = None


_registry = _Registry()
_validated = False


def _ensure_validated() -> None:
    global _validated
    if not _validated:
        validate_none_missing(find_missing_env_vars(REQUIRED_ENV_VARS, os.environ.get))
        _validated = True


def _state_repository() -> CosmosAppointmentStateRepository:
    _ensure_validated()
    if _registry.state_repository is None:
        _registry.state_repository = CosmosAppointmentStateRepository(
            _env("COSMOS_ENDPOINT"),
            _env("COSMOS_DATABASE", "clinicdb"),
            _env("COSMOS_CONTAINER", "appointments"),
            CircuitBreaker("cosmos"),
        )
    return _registry.state_repository


def _event_publisher() -> ServiceBusEventPublisher:
    _ensure_validated()
    if _registry.event_publisher is None:
        _registry.event_publisher = ServiceBusEventPublisher(
            _env("SERVICEBUS__fullyQualifiedNamespace"),
            _env("SERVICEBUS_CREATED_TOPIC", "appointment-created"),
            CircuitBreaker("servicebus"),
        )
    return _registry.event_publisher


def _relational_repository() -> AzureSqlAppointmentRepository:
    _ensure_validated()
    if _registry.relational_repository is None:
        _registry.relational_repository = AzureSqlAppointmentRepository(
            _env("SQL_HOST"),
            _env("SQL_DATABASE", "clinicdb"),
            _env("SQL_AUTHENTICATION", "SqlPassword"),
            _env("SQL_USER"),
            _env("SQL_PASSWORD"),
            CircuitBreaker("sql"),
        )
    return _registry.relational_repository


def event_store() -> CosmosAppointmentEventStore:
    _ensure_validated()
    if _registry.event_store is None:
        _registry.event_store = CosmosAppointmentEventStore(
            _env("COSMOS_ENDPOINT"),
            _env("COSMOS_DATABASE", "clinicdb"),
            _env("COSMOS_EVENTS_CONTAINER", "appointment-events"),
            CircuitBreaker("cosmos-events"),
        )
    return _registry.event_store


def _notifier():
    _ensure_validated()
    if _registry.notifier is None:
        endpoint = _env("ACS_ENDPOINT")
        sender = _env("ACS_SENDER_ADDRESS")
        _registry.notifier = (
            NoOpAppointmentNotifier() if not endpoint else AcsAppointmentNotifier(endpoint, sender)
        )
    return _registry.notifier


def _confirmation_publisher() -> EventGridConfirmationPublisher:
    _ensure_validated()
    if _registry.confirmation_publisher is None:
        _registry.confirmation_publisher = EventGridConfirmationPublisher(
            _env("EVENTGRID_TOPIC_ENDPOINT"),
            CircuitBreaker("eventgrid"),
        )
    return _registry.confirmation_publisher


def create_appointment() -> CreateAppointmentUseCase:
    if _registry.create_use_case is None:
        _registry.create_use_case = CreateAppointmentUseCase(
            _state_repository(), _event_publisher(), event_store()
        )
    return _registry.create_use_case


def process_appointment() -> ProcessAppointmentUseCase:
    if _registry.process_use_case is None:
        _registry.process_use_case = ProcessAppointmentUseCase(
            _state_repository(),
            _relational_repository(),
            _confirmation_publisher(),
        )
    return _registry.process_use_case


def confirm_appointment() -> ConfirmAppointmentUseCase:
    if _registry.confirm_use_case is None:
        _registry.confirm_use_case = ConfirmAppointmentUseCase(
            _state_repository(),
            _notifier(),
            event_store(),
        )
    return _registry.confirm_use_case


def get_appointments() -> GetAppointmentsUseCase:
    if _registry.get_use_case is None:
        _registry.get_use_case = GetAppointmentsUseCase(_state_repository())
    return _registry.get_use_case


def get_appointment_history() -> GetAppointmentHistoryUseCase:
    if _registry.history_use_case is None:
        _registry.history_use_case = GetAppointmentHistoryUseCase(
            _state_repository(), event_store()
        )
    return _registry.history_use_case


def health_check() -> HealthStatus:
    checks = {
        "cosmosDb": _state_repository().ping(),
        "azureSql": _relational_repository().ping(),
        "serviceBus": _event_publisher().ping(),
    }
    all_up = all(v == "UP" for v in checks.values())
    return HealthStatus(status=UP if all_up else DOWN, checks=checks)
