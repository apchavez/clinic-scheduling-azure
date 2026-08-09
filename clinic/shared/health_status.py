from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

UP = "UP"
DOWN = "DOWN"


@dataclass
class HealthStatus:
    status: str
    checks: dict[str, str]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
