"""Очереди аналитики не должны терять записи из-за искусственного лимита."""

from __future__ import annotations

import json

from app.bot.bad_answers import flag_bad_answer, load_bad_answers
from app.bot.missed_questions import add_missed_question, load_missed_questions
from app.bot.reply_logging import add_to_recent_replies, load_recent_replies


def test_missed_questions_keeps_more_than_500_entries(tmp_path, monkeypatch):
    path = tmp_path / "missed_questions.json"
    monkeypatch.setattr("app.bot.missed_questions._path", lambda: path)

    for i in range(501):
        add_missed_question(
            text=f"Неизвестный вопрос о принтере номер {i}",
            score=None,
            best_url=None,
            chat_id=-1,
        )

    entries = load_missed_questions()
    assert len(entries) == 501
    assert entries[-1]["text"].endswith("номер 0")


def test_bad_answers_keeps_more_than_500_entries(tmp_path, monkeypatch):
    path = tmp_path / "bad_answers.json"
    monkeypatch.setattr("app.bot.bad_answers._bad_answers_path", lambda: path)

    for i in range(501):
        flag_bad_answer(
            question=f"Вопрос {i}",
            answer="Ответ",
            url="",
            source="manual_qa",
        )

    entries = load_bad_answers()
    assert len(entries) == 501
    assert entries[-1]["question"] == "Вопрос 0"


def test_recent_replies_keeps_more_than_50_entries(tmp_path, monkeypatch):
    path = tmp_path / "recent_replies.json"
    monkeypatch.setattr("app.bot.reply_logging._replies_path", lambda: path)
    bot_data = {"recent_replies": []}

    for i in range(51):
        add_to_recent_replies(
            bot_data,
            question=f"Вопрос {i}",
            answer="Ответ",
            url="",
            source="manual_qa",
            chat_id=-1,
        )

    load_recent_replies(bot_data)
    assert len(bot_data["recent_replies"]) == 51
    assert bot_data["recent_replies"][-1]["question"] == "Вопрос 0"
    assert json.loads(path.read_text(encoding="utf-8"))[-1]["question"] == "Вопрос 0"
