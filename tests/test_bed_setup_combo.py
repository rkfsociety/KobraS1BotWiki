"""Настройка стола S1 Combo: не отдавать обзорную страницу модели."""
from __future__ import annotations

from app.bot.wiki_ranking import (
    _topic_is_bed_setup_intent,
    _response_wiki_url_acceptable as response_wiki_url_acceptable,
)

# Реальный вопрос из лога: прошивка + стол + combo, в ответ ушла только обзорная вики.
_BED_COMBO = (
    "Это актуально для прошивки 2.7.2.1? На днях купил kobra s1 combo, "
    "хочу стол настроить. Кстати, пришел сразу с биметалл горлом"
)
_S1_COMBO_OVERVIEW = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-Combo"
_S1_COMBO_BED_GUIDE = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/nozzle-scraping-hot-bed"
)


def test_bed_setup_intent_recognizes_nastroit():
    assert _topic_is_bed_setup_intent(_BED_COMBO)


def test_combo_overview_rejected_for_bed_question():
    assert not response_wiki_url_acceptable(_BED_COMBO, _S1_COMBO_OVERVIEW)


def test_combo_bed_guide_acceptable():
    # Не отклонять из‑за ложного firmware_update_intent («актуально для прошивки …»).
    assert response_wiki_url_acceptable(_BED_COMBO, _S1_COMBO_BED_GUIDE)
