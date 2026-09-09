"""Регрессии по разбору аналитики missed/recent за 2026-09-02…09."""

from __future__ import annotations

import pytest

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store


@pytest.mark.parametrize(
    ("question", "title"),
    [
        ("Когда печатаю в режиме спорт качество становится хуже", "Скорости печати на Kobra S1"),
        ("Как часто нужно принтер смазывать?", "Периодическое обслуживание принтера"),
        ("Почему принтер перед стартом цепляет пластину?", "Сопло царапает печатную платформу"),
        ("Какая максимальная температура стола для PETG?", "PETG: какую температуру установить"),
        ("Можно ли откатить прошивку Kobra S1?", "Обновление прошивки (Kobra S1)"),
        ("Какие сопла взять для Kobra X?", "Расходники и сопло Kobra X"),
        ("Есть гайд по LW-филаментам PLA и TPU?", "Настройка LW-филамента"),
    ],
)
def test_fresh_analytics_questions_match_manual_qa(question: str, title: str) -> None:
    match = find_manual_qa_answer(load_manual_qa_store(), question)
    assert match is not None
    assert match[1] == title


@pytest.mark.parametrize(
    "question",
    [
        "Спасибо, теперь понятно",
        "Когда дома буду, то скину",
        "Подскажите, как откалибровать стол на Kobra S1, первый слой не липнет?",
        "После Load пластик не выходит из сопла, что проверить?",
    ],
)
def test_new_keys_do_not_turn_chatter_or_real_questions_into_wrong_matches(question: str) -> None:
    if question.startswith(("Спасибо", "Когда дома")):
        assert find_manual_qa_answer(load_manual_qa_store(), question) is None
    else:
        assert find_manual_qa_answer(load_manual_qa_store(), question) is not None
