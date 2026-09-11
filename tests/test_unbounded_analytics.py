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


def test_bad_answers_save_replaces_file_atomically(tmp_path, monkeypatch):
    from app.bot.bad_answers import save_bad_answers

    path = tmp_path / "bad_answers.json"
    monkeypatch.setattr("app.bot.bad_answers._bad_answers_path", lambda: path)

    save_bad_answers([{"question": "тест"}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"question": "тест"}]
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".bad_answers.json.*.tmp"))


def test_analytics_loaders_reject_oversized_json_before_decode(tmp_path, monkeypatch):
    import app.bot.bad_answers as bad_answers
    import app.bot.manual_qa as manual_qa
    import app.bot.missed_questions as missed_questions

    bad_path = tmp_path / "bad.json"
    manual_path = tmp_path / "manual.json"
    missed_path = tmp_path / "missed.json"
    for path in (bad_path, manual_path, missed_path):
        path.write_text("x" * 20, encoding="utf-8")

    monkeypatch.setattr(bad_answers, "_bad_answers_path", lambda: bad_path)
    monkeypatch.setattr(manual_qa, "_manual_qa_path", lambda: manual_path)
    monkeypatch.setattr(missed_questions, "_path", lambda: missed_path)
    monkeypatch.setattr(bad_answers, "_MAX_FILE_BYTES", 10)
    monkeypatch.setattr(manual_qa, "_MAX_FILE_BYTES", 10)
    monkeypatch.setattr(missed_questions, "_MAX_FILE_BYTES", 10)

    assert bad_answers.load_bad_answers() == []
    assert manual_qa.load_manual_qa_store() == []
    assert missed_questions.load_missed_questions() == []


def test_missed_questions_save_replaces_file_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr("app.bot.missed_questions._path", lambda: tmp_path / "missed_questions.json")

    from app.bot.missed_questions import _save

    _save([{"text": "тест"}])

    assert json.loads((tmp_path / "missed_questions.json").read_text(encoding="utf-8")) == [{"text": "тест"}]
    assert not list(tmp_path.glob(".missed_questions.json.*.tmp"))
