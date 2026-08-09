"""Centralized HTTP response builder to avoid raw JSON string construction in handlers.

Mirrors the Java version's Jackson configuration: datetimes serialize as ISO-8601 strings (e.g.
"2026-06-28T15:30:00Z"), matching what src/docs/openapi.yaml documents, and enums serialize as
their plain string value.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from typing import Any

import azure.functions as func


def _camel_case(snake: str) -> str:
    first, *rest = snake.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _camel_case_deep(value: Any) -> Any:
    if isinstance(value, dict):
        return {_camel_case(k): _camel_case_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_camel_case_deep(v) for v in value]
    return value


class _ApiJsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return _camel_case_deep(dataclasses.asdict(o))
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, datetime):
            iso = o.isoformat()
            return iso.replace("+00:00", "Z") if iso.endswith("+00:00") else iso
        return super().default(o)


def _dumps(payload: Any) -> str:
    return json.dumps(payload, cls=_ApiJsonEncoder)


def error(status_code: int, message: str) -> func.HttpResponse:
    return func.HttpResponse(
        _dumps({"error": message}),
        status_code=status_code,
        mimetype="application/json",
    )


def ok(payload: Any) -> func.HttpResponse:
    try:
        body = _dumps(payload)
    except (TypeError, ValueError):
        return error(500, "Response serialization failed")
    return func.HttpResponse(body, status_code=200, mimetype="application/json")


def accepted(payload: Any) -> func.HttpResponse:
    try:
        body = _dumps(payload)
    except (TypeError, ValueError):
        return error(500, "Response serialization failed")
    return func.HttpResponse(body, status_code=202, mimetype="application/json")
