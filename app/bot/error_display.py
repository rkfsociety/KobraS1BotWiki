"""Форматирование карточек кодов ошибок (ручной JSON + перевод)."""
from __future__ import annotations

import html
import json
from pathlib import Path

from telegram.ext import ContextTypes

from app.bot.i18n import _t
from app.error_codes_catalog import ErrorCodeInfo
from app.translate_ru import Translator

def _load_manual_error_codes() -> dict[str, ErrorCodeInfo]:
    try:
        path = Path("wiki/error-codes-manual.json")
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, ErrorCodeInfo] = {}
        for k, v in raw.items():
            if not isinstance(v, dict):
                continue
            code = str(v.get("code") or k).strip()
            if not code.isdigit():
                continue
            out[code] = ErrorCodeInfo(
                code=code,
                title=str(v.get("title") or "").strip(),
                cause=str(v.get("cause") or "").strip(),
                fix=str(v.get("fix") or "").strip(),
            )
        return out
    except Exception:
        return {}


def _format_error_code_info(info: ErrorCodeInfo, *, lang: str) -> str:
    def tr(s: str) -> str:
        s2 = (s or "").strip()
        if not s2:
            return ""
        if lang != "ru":
            return s2
        # Точечные переводы для часто встречающихся ошибок ACE Pro.
        # Если строка не распознана — оставляем EN, но с русскими подписью/контекстом ниже.
        mapping = {
            "The number of filaments in the ACE Pro does not meet the requirements of the model": "Количество филамента в ACE Pro не соответствует требованиям модели",
            "The number of filaments placed in the ACE Pro is too small to perform color mapping of the multi-color model.": "В ACE Pro установлено слишком мало филамента, чтобы выполнить цветовое сопоставление для многоцветной модели.",
            "ACE Pro is working and cannot be upgraded": "ACE Pro занят и не может быть обновлён",
            "ACE Pro is performing other tasks.": "ACE Pro выполняет другие задачи.",
            "The firmware of ACE Pro needs to be upgraded after the tasks are completed.": "Обновите прошивку ACE Pro после завершения текущих задач.",
        }
        return mapping.get(s2, s2)

    code = html.escape(info.code)
    title = tr(info.title)
    cause = tr(info.cause)
    fix = tr(info.fix)

    parts: list[str] = [f"<b>{html.escape(_t(lang, 'err_header').format(code=code))}</b>"]
    if title:
        parts.append(f"<b>{html.escape(title)}</b>")
    if cause:
        parts.append(html.escape(_t(lang, "err_cause").format(text=cause)))
    if fix:
        parts.append(html.escape(_t(lang, "err_fix").format(text=fix)))
    return "\n".join(parts).strip()


async def _format_error_code_info_ru(*, context: ContextTypes.DEFAULT_TYPE, info: ErrorCodeInfo) -> str:
    """
    Переводим title/cause/fix на русский (лениво) и кэшируем.
    Делается только для ответа из каталога, чтобы не блочить основной поиск/индексацию.
    """
    tr = context.application.bot_data.get("ru_translator")
    if not isinstance(tr, Translator):
        tr = Translator(cache_path=Path(".cache/ru_translations.json"))
        context.application.bot_data["ru_translator"] = tr

    # Язык выбираем по последнему сообщению пользователя (проставляем в on_message).
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    if lang != "ru":
        return _format_error_code_info(info, lang="en")

    title = await tr.translate_en_ru(info.title)
    cause = await tr.translate_en_ru(info.cause)
    fix = await tr.translate_en_ru(info.fix)
    return _format_error_code_info(ErrorCodeInfo(code=info.code, title=title, cause=cause, fix=fix), lang="ru")
