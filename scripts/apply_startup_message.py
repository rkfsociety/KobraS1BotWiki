"""Патч: одно нормальное сообщение о старте бота в зеркале лога."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "app" / "bot" / "telegram_log_mirror.py"
LIFE = ROOT / "app" / "bot" / "lifecycle.py"
TEST = ROOT / "tests" / "test_telegram_log_mirror.py"


def patch_mirror() -> None:
    t = MIRROR.read_text(encoding="utf-8")

    # 1) startup_ready обрабатываем в format_log_for_telegram без ℹ️-обёртки
    old_fmt = '''    if msg.startswith("update kind="):

        return None

    body = _format_body(msg, record)

    if body is None:

        return None

    ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

    icon = _LEVEL_ICON.get(record.levelname, "•")

    return f"{icon} <b>{ts}</b>\\n{body}"
'''
    new_fmt = '''    if msg.startswith("update kind="):

        return None

    m_ready = _RE_STARTUP_READY.match(msg)
    if m_ready:
        bot = m_ready.group(1).lstrip("@")
        wiki, qa, codes = m_ready.group(2), m_ready.group(3), m_ready.group(4)
        pid = m_ready.group(6)
        idx_ok = m_ready.group(7) == "true"
        idx = "индекс из кэша" if idx_ok else "индекс ещё качается"
        return (
            f"🚀 <b>Бот запущен</b> · @{_esc(bot)}\\n"
            f"Вики: {wiki} · QA: {qa} · коды: {codes}\\n"
            f"{idx} · pid {pid}"
        )

    body = _format_body(msg, record)

    if body is None:

        return None

    ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

    icon = _LEVEL_ICON.get(record.levelname, "•")

    return f"{icon} <b>{ts}</b>\\n{body}"
'''
    if old_fmt not in t:
        raise SystemExit("format_log_for_telegram block not found")
    t = t.replace(old_fmt, new_fmt)

    # 2) Убрать дубль startup из _format_body + расширить suppress noise
    old_body = '''    m = _RE_STARTUP_READY.match(msg)
    if m:
        bot = m.group(1).lstrip("@")
        # Распаковываем счётчики из лог-строки: wiki/QA/коды/fix-store; fix-store не показываем в зеркале
        wiki, qa, codes, _ = m.group(2), m.group(3), m.group(4), m.group(5)
        idx_ok = m.group(7) == "true"
        tail = " · индекс из кэша" if idx_ok else ""
        return (
            f"🚀 <b>Бот запущен</b> · @{_esc(bot)}\\n"
            f"Вики: {wiki} · QA: {qa} · коды: {codes}{tail}"
        )

    if (
        msg.startswith("Бот запущен. Wiki docs:")
        or msg.startswith("Bot username:")
        or msg.startswith("Загружен кэш индекса")
        or msg.startswith("Manual QA:")
        or msg.startswith("Каталог кодов ошибок загружен:")
        or msg.startswith("Fix-store загружен:")
    ):
        return None
'''
    new_body = '''    if (
        msg.startswith("Бот запущен. Wiki docs:")
        or msg.startswith("Bot username:")
        or msg.startswith("Загружен кэш индекса")
        or msg.startswith("Manual QA:")
        or msg.startswith("Каталог кодов ошибок загружен:")
        or msg.startswith("Fix-store загружен:")
        or msg.startswith("Автопроверка обновлений вики:")
        or msg.startswith("Бэкап missed_questions.json")
        or msg.startswith("Веб-панель запущена:")
        or msg.startswith("recent_replies:")
        or msg.startswith("bot_stats:")
        or msg.startswith("Мониторинг sitemap")
        or msg.startswith("Зеркало лога в Telegram")
        or msg.startswith("Лог-файл:")
    ):
        return None
'''
    if old_body not in t:
        raise SystemExit("startup body block not found")
    t = t.replace(old_body, new_body)

    # 3) Убрать дублирующий suppress ниже (Зеркало/Лог-файл уже в списке)
    old_dup = '''    if msg.startswith("Зеркало лога в Telegram") or msg.startswith("Лог-файл:"):

        return None

    if record.levelno >= logging.WARNING:
'''
    new_dup = '''    if record.levelno >= logging.WARNING:
'''
    if old_dup in t:
        t = t.replace(old_dup, new_dup)

    MIRROR.write_text(t, encoding="utf-8")
    print("mirror ok")


def patch_lifecycle() -> None:
    t = LIFE.read_text(encoding="utf-8")
    old = '''        try:
            wix = application.bot_data.get("wiki_index")
            nd = wix.doc_count if wix is not None else "?"
            await notify_ops(
                application,
                f"Старт @{me.username} · wiki={nd} · pid={os.getpid()}",
            )
        except Exception as e:
            logging.warning("ops_notify при старте: %s", e)
        try:
            idxr = application.bot_data["wiki_indexer"]
'''
    new = '''        # Одно сообщение о старте уходит через зеркало лога (startup_ready), без дубля notify_ops.
        try:
            idxr = application.bot_data["wiki_indexer"]
'''
    if old not in t:
        raise SystemExit("lifecycle notify_ops block not found")
    LIFE.write_text(t.replace(old, new), encoding="utf-8")
    print("lifecycle ok")


def patch_tests() -> None:
    t = TEST.read_text(encoding="utf-8")
    old = '''def test_startup_ready_compact_mirror():
    msg = "startup_ready bot=AnycubicWiki_bot wiki=1703 qa=1 codes=92 fix=0 pid=12345 index_done=true"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Бот запущен" in out
    assert "@AnycubicWiki_bot" in out
    assert "1703" in out
    assert "индекс из кэша" in out
    assert "@@" not in out


def test_startup_noise_suppressed():
    for msg in (
        "Загружен кэш индекса: /path (страниц: 1703)",
        "Manual QA: 1 записей",
        "Bot username: @AnycubicWiki_bot",
    ):
        record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
        assert format_log_for_telegram(record) is None
'''
    new = '''def test_startup_ready_compact_mirror():
    msg = "startup_ready bot=AnycubicWiki_bot wiki=1703 qa=1 codes=92 fix=0 pid=12345 index_done=true"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Бот запущен" in out
    assert "@AnycubicWiki_bot" in out
    assert "1703" in out
    assert "индекс из кэша" in out
    assert "pid 12345" in out
    assert "@@" not in out
    # без обёртки ℹ️ timestamp — одно чистое сообщение
    assert not out.startswith("ℹ️")
    assert out.count("\\n") <= 2


def test_startup_noise_suppressed():
    for msg in (
        "Загружен кэш индекса: /path (страниц: 1703)",
        "Manual QA: 1 записей",
        "Bot username: @AnycubicWiki_bot",
        "Автопроверка обновлений вики: каждые 3600 секунд",
        "Бэкап missed_questions.json в git: каждые 1800 секунд",
        "Веб-панель запущена: http://0.0.0.0:8080 (логин: admin)",
        "recent_replies: загружено 0 записей с диска",
        "bot_stats: загружено wiki_pages=23 вопросов=104 итого=106",
        "Мониторинг sitemap инициализирован",
    ):
        record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
        assert format_log_for_telegram(record) is None, msg
'''
    if old not in t:
        raise SystemExit("tests block not found")
    TEST.write_text(t.replace(old, new), encoding="utf-8")
    print("tests ok")


def main() -> None:
    patch_mirror()
    patch_lifecycle()
    patch_tests()


if __name__ == "__main__":
    main()
