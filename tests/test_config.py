from __future__ import annotations

from app.config import _get_int, _get_optional_int, _parse_literouter_models


def test_get_int_falls_back_for_invalid_environment_value(monkeypatch):
    monkeypatch.setenv("TEST_INTEGER_SETTING", "not-a-number")

    assert _get_int("TEST_INTEGER_SETTING", 42) == 42


def test_get_optional_int_disables_invalid_environment_value(monkeypatch):
    monkeypatch.setenv("TEST_OPTIONAL_INTEGER_SETTING", "broken")

    assert _get_optional_int("TEST_OPTIONAL_INTEGER_SETTING") is None


def test_get_optional_int_parses_valid_value(monkeypatch):
    monkeypatch.setenv("TEST_OPTIONAL_INTEGER_SETTING", "-100")

    assert _get_optional_int("TEST_OPTIONAL_INTEGER_SETTING") == -100


def test_literouter_models_use_ordered_list_and_remove_duplicates():
    assert _parse_literouter_models("first, second,first,, third", "") == ("first", "second", "third")


def test_literouter_single_model_override_is_backward_compatible():
    assert _parse_literouter_models("", "legacy-model") == ("legacy-model",)
