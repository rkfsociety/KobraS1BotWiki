"""Проверка git_sync_from_remote (нужен .git и доступ к origin)."""
from __future__ import annotations

import subprocess
import unittest

from app.bot.git_autopull import git_ping_compare_with_remote, git_sync_from_remote, project_repo_root


class GitUpdateTests(unittest.TestCase):
    def test_sync_uptodate_when_clean_tree(self) -> None:
        repo = project_repo_root()
        if not (repo / ".git").is_dir():
            self.skipTest("нет .git")

        git_sync_from_remote(
            repo=repo,
            remote="origin",
            branch="master",
            hard_reset=True,
        )
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if (st.stdout or "").strip():
            self.skipTest("рабочая копия не чистая (есть локальные изменения)")

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
