"""Ручные пары «вопрос → ответ»: файл ``data/manual_qa.json`` в корне репозитория (в git).

После изменений через /qaadd и /qadel при ``MANUAL_QA_GIT_PUSH=1`` (по умолчанию включено)
выполняются ``git add``, ``git commit``, ``git push`` — запись попадает на GitHub
(нужны настроенные credentials на сервере).

При первом запуске данные из ``.cache/manual_qa.json`` копируются в ``data/manual_qa.json``.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from app.bot.git_autopull import project_repo_root
from app.bot.stores import _norm_text

_MAX_ENTRIES = 250
_MIN_SUBSTR_LEN = 6


def _manual_qa_path() -> Path:
    return project_repo_root() / "data" / "manual_qa.json"


def _migrate_legacy_cache_if_needed() -> None:
    p = _manual_qa_path()
    if p.exists():
        return
    legacy = project_repo_root() / ".cache" / "manual_qa.json"
    if not legacy.exists():
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, p)
        logging.info("manual_qa: скопировано %s -> %s", legacy, p)
    except Exception as e:
        logging.warning("manual_qa: миграция из .cache не удалась: %s", e)


def _default_entries() -> list[dict[str, Any]]:
    return []


def load_manual_qa_store() -> list[dict[str, Any]]:
    _migrate_legacy_cache_if_needed()
    p = _manual_qa_path()
    try:
        if not p.exists():
            return _default_entries()
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
            return [x for x in raw["entries"] if isinstance(x, dict)]
    except Exception:
        pass
    return _default_entries()


def save_manual_qa_store(entries: list[dict[str, Any]]) -> None:
    p = _manual_qa_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def try_git_push_manual_qa() -> tuple[bool, str]:
    """
    git add data/manual_qa.json && commit && push в корне репозитория.
    """
    repo = project_repo_root()
    rel = "data/manual_qa.json"
    path = repo / rel
    if not path.is_file():
        return False, "нет файла data/manual_qa.json"
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    if not (repo / ".git").exists():
        return False, "нет .git — только локальный файл"

    ad = run(["git", "add", "--", rel])
    if ad.returncode != 0:
        return False, (ad.stderr or ad.stdout or "git add").strip()[:500]

    diff = run(["git", "diff", "--staged", "--quiet"])
    if diff.returncode == 0:
        return True, "в git без изменений"

    cm = run(
        [
            "git",
            "-c",
            "user.email=bot@kobra-wiki.local",
            "-c",
            "user.name=KobraS1BotWiki",
            "commit",
            "-m",
            "chore(bot): update manual_qa.json",
        ]
    )
    if cm.returncode != 0:
        err = (cm.stderr or cm.stdout or "").strip()
        if "nothing to commit" in err.lower():
            return True, "нечего коммитить"
        return False, err[:500] if err else "git commit failed"

    ps = run(["git", "push"])
    if ps.returncode != 0:
        return False, (ps.stderr or ps.stdout or "git push").strip()[:500]
    return True, "отправлено в origin"


def _normalize_keys(raw_keys: list[str]) -> list[str]:
    out: list[str] = []
    for k in raw_keys:
        n = _norm_text(k)
        if n and n not in out:
            out.append(n)
    return out


def _dedupe_keys_across(entries: list[dict[str, Any]], new_keys: list[str]) -> None:
    """Убираем те же ключи из старых записей (новая запись главнее)."""
    nk = set(new_keys)
    for e in entries:
        ks = e.get("keys")
        if not isinstance(ks, list):
            continue
        kept = [x for x in ks if isinstance(x, str) and _norm_text(x) not in nk]
        e["keys"] = kept


def add_manual_qa_entry(
    *,
    entries: list[dict[str, Any]],
    raw_keys: list[str],
    answer: str,
    title: str,
) -> tuple[bool, str]:
    keys = _normalize_keys(raw_keys)
    if not keys:
        return False, "нет ни одного ключа после нормализации"
    ans = (answer or "").strip()
    if not ans:
        return False, "пустой ответ"
    _dedupe_keys_across(entries, keys)
    entries[:] = [e for e in entries if isinstance(e.get("keys"), list) and len(e["keys"]) > 0]
    ttl = (title or "").strip() or keys[0][:80]
    now = time.time()
    new_e: dict[str, Any] = {"keys": keys, "answer": ans, "title": ttl, "ts": now}
    entries.insert(0, new_e)
    if len(entries) > _MAX_ENTRIES:
        del entries[_MAX_ENTRIES:]
    save_manual_qa_store(entries)
    return True, f"добавлено, ключей: {len(keys)}"


def delete_manual_qa_by_index(*, entries: list[dict[str, Any]], one_based: int) -> tuple[bool, str]:
    if one_based < 1 or one_based > len(entries):
        return False, "нет такого номера"
    entries.pop(one_based - 1)
    save_manual_qa_store(entries)
    return True, "удалено"


def find_manual_qa_answer(entries: list[dict[str, Any]], user_text: str) -> tuple[str, str] | None:
    """
    Ищет ответ: точное совпадение нормализованного текста с любым ключом
    или ключ длиной >= _MIN_SUBSTR_LEN входит в нормализованный вопрос.
    Более новые записи (в начале списка) проверяются первыми.
    """
    tn = _norm_text(user_text)
    if not tn:
        return None
    for e in entries:
        if not isinstance(e, dict):
            continue
        ks = e.get("keys")
        if not isinstance(ks, list):
            continue
        ans = e.get("answer")
        if not isinstance(ans, str) or not ans.strip():
            continue
        ttl = e.get("title") if isinstance(e.get("title"), str) else ""
        ttl = ttl.strip() or (ks[0] if ks and isinstance(ks[0], str) else "manual")
        for k in ks:
            if not isinstance(k, str):
                continue
            kn = _norm_text(k)
            if not kn:
                continue
            if tn == kn or (len(kn) >= _MIN_SUBSTR_LEN and kn in tn):
                return ans.strip(), ttl
    return None
