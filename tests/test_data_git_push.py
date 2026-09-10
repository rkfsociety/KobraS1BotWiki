from __future__ import annotations

import subprocess

import pytest

import app.bot.bad_answers as bad_answers
import app.bot.manual_qa as manual_qa
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


@pytest.mark.parametrize(
    ("module", "push_name", "relative_path"),
    [
        (bad_answers, "try_git_push_bad_answers", "data/bad_answers.json"),
        (manual_qa, "try_git_push_manual_qa", "data/manual_qa.json"),
        (missed_questions, "try_git_push_missed_questions", "data/missed_questions.json"),
    ],
)
def test_data_git_push_pulls_before_push(tmp_path, monkeypatch, module, push_name, relative_path):
    repo = tmp_path
    path = repo / relative_path
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")
    (repo / ".git").mkdir()
    monkeypatch.setattr(module, "project_repo_root", lambda: repo)
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    ok, message = getattr(module, push_name)()

    assert ok is True, message
    assert calls.index(["git", "pull", "--ff-only"]) < calls.index(["git", "push"])
