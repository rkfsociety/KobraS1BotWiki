from __future__ import annotations

import subprocess

import pytest

import app.bot.bad_answers as bad_answers
import app.bot.missed_questions as missed_questions


@pytest.mark.parametrize(
    ("module", "push_name", "relative_path"),
    [
        (bad_answers, "try_git_push_bad_answers", "data/bad_answers.json"),
        (missed_questions, "try_git_push_missed_questions", "data/missed_questions.json"),
    ],
)
def test_data_git_push_reports_git_add_failure(tmp_path, monkeypatch, module, push_name, relative_path):
    repo = tmp_path
    path = repo / relative_path
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")
    (repo / ".git").mkdir()
    monkeypatch.setattr(module, "project_repo_root", lambda: repo)

    def fake_run(args, **kwargs):
        assert args[:3] == ["git", "add", "--"]
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="git add failed")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    ok, message = getattr(module, push_name)()

    assert ok is False
    assert message == "git add failed"
