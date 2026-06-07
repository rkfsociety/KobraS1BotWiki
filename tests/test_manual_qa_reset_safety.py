"""Страховка: git reset --hard не теряет неотправленные ручные ответы."""
from __future__ import annotations

import json

from app.bot.git_autopull import _read_manual_qa_entries, _restore_manual_qa_after_reset


def _write_qa(repo, entries):
    p = repo / "data" / "manual_qa.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def test_restore_readds_missing_entry(tmp_path):
    # Версия с GitHub (после reset) — без локального ответа.
    _write_qa(tmp_path, [{"keys": ["a"], "title": "A", "answer": "ans-a"}])
    # Снимок до reset содержал ещё один (локальный, неотправленный).
    backup = [
        {"keys": ["b"], "title": "B", "answer": "ans-b"},
        {"keys": ["a"], "title": "A", "answer": "ans-a"},
    ]
    n = _restore_manual_qa_after_reset(tmp_path, backup)
    assert n == 1
    entries = _read_manual_qa_entries(tmp_path)
    titles = {e["title"] for e in entries}
    assert titles == {"A", "B"}
    # локальный — наверху (более новый)
    assert entries[0]["title"] == "B"


def test_restore_no_duplicates_when_present(tmp_path):
    _write_qa(tmp_path, [{"keys": ["a"], "title": "A", "answer": "ans-a"}])
    backup = [{"keys": ["a"], "title": "A", "answer": "ans-a"}]
    n = _restore_manual_qa_after_reset(tmp_path, backup)
    assert n == 0
    assert len(_read_manual_qa_entries(tmp_path)) == 1


def test_restore_empty_backup_noop(tmp_path):
    _write_qa(tmp_path, [{"keys": ["a"], "title": "A", "answer": "ans-a"}])
    assert _restore_manual_qa_after_reset(tmp_path, []) == 0


def test_restore_ignores_entries_without_answer(tmp_path):
    _write_qa(tmp_path, [])
    backup = [{"keys": ["b"], "title": "B", "answer": ""}]
    assert _restore_manual_qa_after_reset(tmp_path, backup) == 0
