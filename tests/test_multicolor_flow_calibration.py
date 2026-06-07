"""Вопрос про авто-калибровку потока в многоцветной печати — не отдаём filament-guide/print-tpu."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_multicolor_flow_calibration_chat,
    _topic_is_filament_material_choice_intent,
    _topic_is_filament_slicing_settings_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable

_MSG = (
    "Если ставить калибровку потока и пускать многоцветную печать, "
    "он будет калибровать поток для каждого пластика? Или только в самом начале "
    "откалибрует поток одного пластика и пойдет печатать?"
)

_PRINT_TPU = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu"
_FILAMENT_GUIDE = "https://wiki.anycubic.com/en/filament-and-resin/filament-guide"


def test_multicolor_flow_calibration_detected():
    assert _is_multicolor_flow_calibration_chat(_MSG)


def test_not_treated_as_slicing_or_material_choice():
    assert not _topic_is_filament_slicing_settings_intent(_MSG)
    assert not _topic_is_filament_material_choice_intent(_MSG)


def test_filament_pages_rejected():
    assert not _response_wiki_url_acceptable(_MSG, _PRINT_TPU)
    assert not _response_wiki_url_acceptable(_MSG, _FILAMENT_GUIDE)


def test_specific_material_slicing_still_works():
    # Конкретный материал + поток — это уже настройки слайсинга, не общий вопрос о фиче.
    msg = "Какой поток ставить для TPU при печати?"
    assert not _is_multicolor_flow_calibration_chat(msg)
