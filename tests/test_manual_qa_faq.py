"""Базовый набор FAQ в data/manual_qa.json: типичные вопросы находят ответ."""
from __future__ import annotations

from app.bot.manual_qa import (
    _extract_phrases,
    _normalize_keys,
    add_manual_qa_entry,
    find_manual_qa_answer,
    load_manual_qa_store,
)

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
    "сколько процентов заполнения ставить",
    "почему тянет нити между деталями",
    "когда нужны поддержки",
    "что такое ironing",
    "деталь ломается по слоям",
    "petg намертво прилип к стеклу как снять",
]


def test_faq_store_loads_nonempty():
    entries = load_manual_qa_store()
    assert len(entries) >= 20
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


# --- Автоизвлечение ключей из длинных предложений ---

def test_extract_phrases_produces_short_tokens():
    phrases = _extract_phrases("А вот как проверить износ механики? Вернее как его оценить не разобрав принтер?")
    assert len(phrases) > 0
    assert all(len(p.split()) <= 3 for p in phrases)
    assert any("износ" in p for p in phrases)


def test_normalize_keys_short_kept_as_is():
    # Короткие ключи (≤ 5 слов) не трогаются
    result = _normalize_keys(["износ механики", "проверить люфт"])
    assert result == ["износ механики", "проверить люфт"]


def test_normalize_keys_long_sentence_expands():
    # Длинное предложение разбивается на короткие фразы
    result = _normalize_keys(["А вот как проверить износ механики? Вернее как его оценить не разобрав принтер?"])
    assert len(result) > 1
    assert all(len(r.split()) <= 3 for r in result)


def test_add_entry_with_sentence_key_is_matchable(tmp_path):
    import json
    qa_path = tmp_path / "data" / "manual_qa.json"
    qa_path.parent.mkdir(parents=True)
    qa_path.write_text("[]", encoding="utf-8")

    import app.bot.manual_qa as mqa
    orig = mqa._manual_qa_path
    mqa._manual_qa_path = lambda: qa_path
    try:
        entries: list = []
        ok, detail = add_manual_qa_entry(
            entries=entries,
            raw_keys=["А вот как проверить износ механики? Вернее как его оценить не разобрав принтер?"],
            answer="Смотри на люфты и ремни.",
            title="Износ механики",
        )
        assert ok, detail
        # Должно найтись по коротким подстрокам
        assert find_manual_qa_answer(entries, "как оценить износ механики?") is not None
        assert find_manual_qa_answer(entries, "изношеный ремень у принтера") is not None
    finally:
        mqa._manual_qa_path = orig
