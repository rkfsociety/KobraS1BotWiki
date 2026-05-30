"""Проверка git_sync_from_remote (нужен .git и доступ к origin)."""
from __future__ import annotations

import subprocess
import unittest

from app.bot.git_autopull import git_ping_compare_with_remote, git_sync_from_remote, project_repo_root


def _is_safe_to_hard_reset(repo) -> tuple[bool, str]:
    """Проверяет, что hard_reset не уничтожит локальные данные."""
    # Незакоммиченные изменения
    st = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    if (st.stdout or "").strip():
        return False, "рабочая копия не чистая (есть локальные изменения)"

    # Локальные коммиты, не запушенные на remote
    ahead = subprocess.run(
        ["git", "rev-list", "--count", "origin/master..HEAD"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    if (ahead.stdout or "").strip() not in ("", "0"):
        return False, f"есть {ahead.stdout.strip()} локальных коммитов впереди origin"

    return True, ""


class GitUpdateTests(unittest.TestCase):
    def test_sync_uptodate_when_clean_tree(self) -> None:
        repo = project_repo_root()
        if not (repo / ".git").is_dir():
            self.skipTest("нет .git")

        safe, reason = _is_safe_to_hard_reset(repo)
        if not safe:
            self.skipTest(reason)

        git_sync_from_remote(
            repo=repo,
            remote="origin",
            branch="master",
            hard_reset=True,
        )

        updated, msg = git_sync_from_remote(
            repo=repo,
            remote="origin",
            branch="master",
            hard_reset=True,
        )
        self.assertFalse(updated, msg=msg)
        self.assertEqual(msg, "уже актуально")

    def test_ping_after_sync_matches(self) -> None:
        repo = project_repo_root()
        if not (repo / ".git").is_dir():
            self.skipTest("нет .git")

        safe, reason = _is_safe_to_hard_reset(repo)
        if not safe:
            self.skipTest(reason)

        git_sync_from_remote(
            repo=repo,
            remote="origin",
            branch="master",
            hard_reset=True,
        )
        local, remote, avail, err = git_ping_compare_with_remote(
            repo=repo,
            remote="origin",
            branch="master",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(local)
        self.assertIsNotNone(remote)
        self.assertEqual(local, remote)
        self.assertFalse(avail)


if __name__ == "__main__":
    unittest.main()
