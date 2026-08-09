import pytest

from clinic.infrastructure.config.app_context import (
    REQUIRED_ENV_VARS,
    find_missing_env_vars,
    validate_none_missing,
)


def test_find_missing_env_vars_returns_all_when_none_set():
    missing = find_missing_env_vars(REQUIRED_ENV_VARS, lambda _name: None)
    assert set(missing) == set(REQUIRED_ENV_VARS)


def test_find_missing_env_vars_returns_empty_when_all_set():
    missing = find_missing_env_vars(REQUIRED_ENV_VARS, lambda _name: "value")
    assert missing == []


def test_find_missing_env_vars_treats_blank_as_missing():
    def lookup(name):
        return "   " if name == "JWT_SECRET" else "value"

    missing = find_missing_env_vars(REQUIRED_ENV_VARS, lookup)
    assert missing == ["JWT_SECRET"]


def test_validate_none_missing_passes_for_empty_list():
    validate_none_missing([])


def test_validate_none_missing_raises_for_nonempty_list():
    with pytest.raises(RuntimeError):
        validate_none_missing(["JWT_SECRET"])
