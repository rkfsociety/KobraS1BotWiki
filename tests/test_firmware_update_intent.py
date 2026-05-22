"""Вопрос про установку прошивки: не error-codes, уточнение без кода ошибки."""
from __future__ import annotations

import app.bot.layer_model_gate  # noqa: F401

from app.bot.text_heuristics import (
    _is_error_code_query,
    _needs_model_clarification,
    _topic_is_firmware_update_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import (
    _printer_firmware_guide_url_plausible,
    _response_wiki_url_acceptable,
)

_FW_MSG = "Здравствуйте,  прилетела новая прошивка, можно ставить?"
_BED_FW_VERSION_MSG = (
    "Это актуально для прошивки 2.7.2.1? На днях купил kobra s1 combo, хочу стол настроить."
)
_ERR_URL = "https://wiki.anycubic.com/en/error-codes/10802-code/k3"
_FW_URL = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"


def test_firmware_question_detected():
    assert _topic_is_firmware_update_intent(_FW_MSG)
    assert not _is_error_code_query(_FW_MSG)


def test_firmware_version_with_bed_setup_not_update_intent():
    assert not _topic_is_firmware_update_intent(_BED_FW_VERSION_MSG)


def test_firmware_needs_model_but_not_error_code_in_clarify():
    assert _topic_needs_printer_model(_FW_MSG)
    assert _needs_model_clarification(_FW_MSG)


def test_error_code_url_rejected_for_firmware_question():
    assert not _response_wiki_url_acceptable(_FW_MSG, _ERR_URL)
    assert not _printer_firmware_guide_url_plausible(_ERR_URL)


def test_firmware_guide_url_acceptable():
    assert _printer_firmware_guide_url_plausible(_FW_URL)
    assert _response_wiki_url_acceptable(
        _FW_MSG + " Kobra S1",
        _FW_URL,
    )
