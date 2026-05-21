#!/usr/bin/env python3
"""Проверка: есть ли несохранённые правки в git (для агента после редактирования)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    r = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "").strip()
    if out:
        print(out)
        return 0
    print("git diff пуст — правки на диск не попали или уже закоммичены")
    return 1


if __name__ == "__main__":
    sys.exit(main())
