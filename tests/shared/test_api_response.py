import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from clinic.shared import api_response


def test_error_builds_json_body_with_status_code():
    resp = api_response.error(404, "not found")
    assert resp.status_code == 404
    assert json.loads(resp.get_body()) == {"error": "not found"}
    assert resp.mimetype == "application/json"


def test_ok_serializes_plain_dict():
    resp = api_response.ok({"a": 1})
    assert resp.status_code == 200
    assert json.loads(resp.get_body()) == {"a": 1}


def test_accepted_returns_202():
    resp = api_response.accepted({"message": "received"})
    assert resp.status_code == 202
    assert json.loads(resp.get_body()) == {"message": "received"}


class _Color(str, Enum):
    RED = "RED"


@dataclass
class _Thing:
    name: str
    color: _Color
    when: datetime


def test_ok_serializes_dataclass_with_enum_and_datetime_as_iso_z():
    when = datetime(2026, 6, 28, 15, 30, 0, tzinfo=UTC)
    resp = api_response.ok(_Thing(name="x", color=_Color.RED, when=when))
    body = json.loads(resp.get_body())
    assert body == {"name": "x", "color": "RED", "when": "2026-06-28T15:30:00Z"}


def test_ok_serializes_list_of_dataclasses():
    when = datetime(2026, 1, 1, tzinfo=UTC)
    resp = api_response.ok([_Thing(name="a", color=_Color.RED, when=when)])
    body = json.loads(resp.get_body())
    assert body == [{"name": "a", "color": "RED", "when": "2026-01-01T00:00:00Z"}]


@dataclass
class _Wrapper:
    next_cursor: str | None
    schedule_id: int


def test_ok_camel_cases_snake_case_dataclass_fields():
    resp = api_response.ok(_Wrapper(next_cursor="abc", schedule_id=10))
    body = json.loads(resp.get_body())
    assert body == {"nextCursor": "abc", "scheduleId": 10}


def test_ok_camel_cases_nested_dataclasses_in_lists():
    resp = api_response.ok({"items": [_Wrapper(next_cursor=None, schedule_id=20)]})
    body = json.loads(resp.get_body())
    assert body == {"items": [{"nextCursor": None, "scheduleId": 20}]}
