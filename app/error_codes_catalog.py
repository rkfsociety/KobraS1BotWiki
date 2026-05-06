from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ErrorCodeInfo:
    code: str
    title: str = ""
    cause: str = ""
    fix: str = ""


def _now() -> float:
    return time.time()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_code(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("CODE:", "").replace("code:", "").strip()
    if s.isdigit() and 4 <= len(s) <= 7:
        return s
    return None


def _extract_text(el) -> str:
    if el is None:
        return ""
    txt = " ".join(el.get_text(" ", strip=True).split())
    return txt.strip()


def parse_error_codes_page(html: str) -> dict[str, ErrorCodeInfo]:
    """
    Пытаемся вытащить коды/названия/описания с https://wiki.anycubic.com/en/error-codes
    Вёрстка может меняться, поэтому парсер максимально «снисходительный».
    """
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, ErrorCodeInfo] = {}

    # 1) Пробуем табличный формат (tr/td).
    for tr in soup.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) < 2:
            continue
        code = _normalize_code(_extract_text(tds[0]))
        if not code:
            continue
        title = _extract_text(tds[1]) if len(tds) >= 2 else ""
        cause = _extract_text(tds[2]) if len(tds) >= 3 else ""
        fix = _extract_text(tds[3]) if len(tds) >= 4 else ""
        out[code] = ErrorCodeInfo(code=code, title=title, cause=cause, fix=fix)

    # 2) Пробуем карточки/списки: ищем блоки, где встречается CODE:xxxxx.
    if not out:
        text = soup.get_text("\n", strip=True)
        # грубое выделение блоков по пустым строкам
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        for b in blocks:
            if "CODE" not in b and "code" not in b:
                continue
            parts = [p.strip() for p in b.splitlines() if p.strip()]
            code = None
            for p in parts[:5]:
                if "CODE" in p.upper():
                    # CODE:11527
                    maybe = p.split(":", 1)[-1].strip()
                    code = _normalize_code(maybe)
                    if code:
                        break
            if not code:
                continue
            # эвристика: первая строка после CODE — заголовок
            title = ""
            for p in parts:
                if p.upper().startswith("CODE"):
                    continue
                title = p
                break
            cause = ""
            fix = ""
            for p in parts:
                pl = p.lower()
                if pl.startswith("cause"):
                    cause = p.split(":", 1)[-1].strip()
                if pl.startswith("solution") or pl.startswith("fix") or pl.startswith("action"):
                    fix = p.split(":", 1)[-1].strip()
            out[code] = ErrorCodeInfo(code=code, title=title, cause=cause, fix=fix)

    # 3) Если текст "пустой" (часть страницы рендерится/инжектится скриптами) —
    # пробуем вытащить прямо из HTML по заголовкам вида:
    # <h3 ...> CODE:11527 Title...</h3> <p>Cause of error: ...</p> <p>...upgrade...</p>
    if not out:
        for m in re.finditer(
            r"<h3[^>]*>.*?CODE\s*:\s*(\d{4,7})\s+([^<]+)</h3>\s*(.*?)(?=<h3[^>]*>.*?CODE\s*:|\Z)",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            code = m.group(1)
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            chunk = m.group(3)
            # вытащим абзацы внутри chunk
            ps = [re.sub(r"\s+", " ", p).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", chunk, flags=re.IGNORECASE | re.DOTALL)]
            ps_txt = [re.sub(r"<[^>]+>", " ", p) for p in ps]
            ps_txt = [re.sub(r"\s+", " ", p).strip() for p in ps_txt if p.strip()]

            cause = ""
            fix = ""
            for p in ps_txt:
                pl = p.lower()
                if "cause of error" in pl or pl.startswith("cause"):
                    cause = p.split(":", 1)[-1].strip()
                # на странице часто нет явного "solution", поэтому берём первую "instruction" строку
                if not fix and ("need" in pl or "upgrade" in pl or "after" in pl or pl.startswith("solution")):
                    fix = p.split(":", 1)[-1].strip()
            # если fix не нашли — не дублируем cause
            if fix == cause:
                fix = ""
            out[code] = ErrorCodeInfo(code=code, title=title, cause=cause, fix=fix)

    return out


async def ensure_error_codes_catalog(
    *,
    base_url: str,
    cache_path: str | Path,
    refresh_hours: int = 24,
) -> dict[str, ErrorCodeInfo]:
    """
    Загружает и кэширует каталог с /en/error-codes.
    Возвращает словарь code -> ErrorCodeInfo (может быть пустым).
    """
    cache_file = Path(cache_path)
    cached = _load_json(cache_file)
    if cached and isinstance(cached, dict):
        ts = float(cached.get("ts", 0.0))
        cached_count = int(cached.get("count", 0) or 0)
        # Если в кэше 0 записей — считаем кэш невалидным и перекачиваем сразу
        # (обычно это результат старого парсера или временной проблемы загрузки страницы).
        if cached_count > 0 and ts and (_now() - ts) < float(refresh_hours) * 3600.0:
            data = cached.get("codes", {})
            if isinstance(data, dict):
                return {k: ErrorCodeInfo(**v) for k, v in data.items() if isinstance(v, dict)}

    url = base_url.rstrip("/") + "/en/error-codes"
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            codes = parse_error_codes_page(r.text)
            # Если парсер не вытащил ничего, не перетираем возможный непустой кэш.
            if not codes and cached and isinstance(cached, dict):
                data = cached.get("codes", {})
                if isinstance(data, dict) and data:
                    return {k: ErrorCodeInfo(**v) for k, v in data.items() if isinstance(v, dict)}
            _save_json(
                cache_file,
                {
                    "ts": _now(),
                    "source": url,
                    "count": len(codes),
                    "codes": {k: v.__dict__ for k, v in codes.items()},
                },
            )
            return codes
    except Exception:
        # если сеть/парсинг упали — отдаём что есть в кэше, либо пусто
        if cached and isinstance(cached, dict):
            data = cached.get("codes", {})
            if isinstance(data, dict):
                return {k: ErrorCodeInfo(**v) for k, v in data.items() if isinstance(v, dict)}
        return {}


def merge_manual_overrides(
    base: dict[str, ErrorCodeInfo],
    overrides: dict[str, ErrorCodeInfo],
) -> dict[str, ErrorCodeInfo]:
    out = dict(base)
    out.update(overrides)
    return out

