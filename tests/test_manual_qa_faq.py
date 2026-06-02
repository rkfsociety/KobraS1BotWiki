"""Базовый набор FAQ в data/manual_qa.json: типичные вопросы находят ответ."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store

_CASES = [
    "ребят как настроить стол на s1?",
    "какая температура для petg нужна",
    "какая температура для pla",
    "надо ли сушить пластик перед печатью",
    "принтер не видит ace pro что делать",
    "как почистить сопло, забилось",
    "как обновить прошивку на кобре",
    "первый слой не прилипает совсем",
    "как печатать в несколько цветов",
]


def test_faq_store_loads_nonempty():
    entries = load_manual_qa_store()
    assert len(entries) >= 10
    for e in entries:
        assert isinstance(e.get("keys"), list) and e["keys"]
        assert isinstance(e.get("answer"), str) and e["answer"].strip()


def test_basic_questions_resolve_to_faq():
    entries = load_manual_qa_store()
    for q in _CASES:
        hit = find_manual_qa_answer(entries, q)
        assert hit is not None, q


def test_plain_chatter_does_not_match_faq():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "просто болтаю про погоду сегодня") is None
