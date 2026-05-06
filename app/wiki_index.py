from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+", re.UNICODE)


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_question(text: str) -> bool:
    t = _normalize(text)
    if "?" in text:
        return True
    # Коды ошибок (напр. 11518) считаем вопросом: пользователь ожидает расшифровку/гайд.
    # Слово "ошибка" само по себе НЕ считаем вопросом (напр. "ошибка природы").
    if re.search(r"\b\d{4,7}\b", t) and re.search(r"\b(ошибк\w*|error|err)\b", t):
        return True
    # "не помнит как ..." — обычно это комментарий, а не вопрос к боту (если нет "?").
    if re.search(r"\b(уже\s+)?не\s+помнит\s+как\b", t):
        return False
    return bool(
        re.search(
            r"\b(как|почему|зачем|что|где|когда|кто|можно ли|не работает)\b",
            t,
        )
    )


@dataclass(frozen=True)
class WikiDoc:
    title: str
    slug: str
    text: str


class WikiIndex:
    def __init__(self, docs: list[WikiDoc]) -> None:
        self._docs = docs
        self._texts = [d.text for d in docs]

    @property
    def doc_count(self) -> int:
        return len(self._docs)

    @staticmethod
    def from_markdown_dir(content_dir: str | Path) -> "WikiIndex":
        base = Path(content_dir)
        if not base.exists():
            raise RuntimeError(f"Папка с вики не найдена: {base}")

        md_files = sorted([p for p in base.rglob("*.md") if p.is_file()])
        docs: list[WikiDoc] = []
        for p in md_files:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            title = _extract_title(raw) or p.stem
            slug = _slug_from_path(base, p)
            text = _normalize(f"{title}\n{_strip_markdown(raw)}")
            docs.append(WikiDoc(title=title, slug=slug, text=text))

        if not docs:
            raise RuntimeError(f"В папке {base} нет .md файлов")

        return WikiIndex(docs)

    def search(self, query: str, *, top_k: int = 1) -> list[tuple[WikiDoc, int]]:
        q = _normalize(query)
        scored: list[tuple[int, int]] = []
        for i, text in enumerate(self._texts):
            score = int(fuzz.token_set_ratio(q, text))
            scored.append((score, i))
        scored.sort(reverse=True, key=lambda x: x[0])
        results: list[tuple[WikiDoc, int]] = []
        for score, idx in scored[: max(top_k, 1)]:
            results.append((self._docs[idx], score))
        return results

    @staticmethod
    def looks_like_question(text: str) -> bool:
        return _looks_like_question(text)


def _extract_title(md: str) -> str | None:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _strip_markdown(md: str) -> str:
    md = re.sub(r"```[\s\S]*?```", " ", md)  # code blocks
    md = re.sub(r"`[^`]*`", " ", md)  # inline code
    md = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", md)  # images
    md = re.sub(r"\[[^\]]*]\([^)]+\)", " ", md)  # links
    md = re.sub(r"[#>*_~\-]+", " ", md)  # markdown symbols
    words = _WORD_RE.findall(md)
    return " ".join(words)


def _slug_from_path(base: Path, p: Path) -> str:
    rel = p.relative_to(base).with_suffix("")
    parts = [str(x) for x in rel.parts]
    return "/".join(parts)
