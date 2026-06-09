"""ACE-хаб: интенты и паттерны, связанные с ACE Pro."""
from __future__ import annotations

import re

from app.bot.heuristics._base import _ace_mentioned


def _topic_is_ace_not_detected_intent(text: str) -> bool:
    """Принтер/софт не видит ACE Pro (аська)."""
    t = text.lower()
    if not _ace_mentioned(text):
        return False
    has_not_seen = any(
        k in t
        for k in (
            "не видит",
            "не вид",
            "не определя",
            "не наход",
            "не подключа",
            "not detected",
            "doesn't see",
            "does not see",
            "not see",
            "can't see",
            "cannot see",
        )
    ) or ("видится" in t and any(k in t for k in ("аська", "аска", "ace")))
    return bool(has_not_seen)


def _topic_is_ace_connection_intent(text: str | None) -> bool:
    """ACE подключена, но сбои: ошибки/выброс из печати, неисправность связи."""
    if not text:
        return False
    if not _ace_mentioned(text):
        return False
    if _topic_is_ace_not_detected_intent(text):
        return False
    t = text.lower()
    has_connection_issue = any(
        k in t
        for k in (
            "подключен",
            "подключени",
            "connection",
            "неисправност",
            "ошибк",
            "выбрасыв",
            "сбой",
            "обрыв",
            "разрыв",
            "отвали",
            "disconnect",
        )
    )
    only_in_ace = ("только" in t or "only " in t) and _ace_mentioned(text)
    return has_connection_issue or only_in_ace


def _topic_is_ace_filament_slot_intent(text: str | None) -> bool:
    """ACE Pro: слот/RFID запомнил PETG, не сменить / сброс — не clarify принтера."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not _ace_mentioned(text):
        return False
    slot_ctx = bool(
        re.search(r"\b(?:слот\w*|slot|катушк\w*|spool)\b", t)
        or re.search(r"\b(?:филамент|filament|petg|pla|abs|тпу|tpu)\w*\b", t)
    )
    memory_issue = bool(
        re.search(
            r"\b(?:"
            r"запомн\w*|remember|"
            r"чип\w*|rfid|nfc|"
            r"не\s+да[ёе]т\s+смен|не\s+могу\s+смен|"
            r"сброс\w*|обнул\w*|очист\w*|reset|clear|"
            r"смен\w*|помен\w*"
            r")\b",
            t,
        )
    )
    if not (slot_ctx and memory_issue):
        return False
    return bool(
        "?" in text
        or re.search(
            r"\b(?:подскаж\w*|помогите|как\s+сброс|как\s+смен|вопрос|настрой\w*)\b",
            t,
        )
    )


def _is_ace_unit_trade_banter(text: str | None) -> bool:
    """«Продать? … ТПУ из аськи не сможет, сушить есть где» — тред про продажу ACE."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:замен|поменя|смени|загруз|настро|подключ|суш))\b",
        t,
    ):
        return False
    ace = bool(_ace_mentioned(text) or re.search(r"\bаськ\w*\b", t))
    if not ace:
        return False
    sell = bool(re.search(r"\b(?:продать|продам|продаю|купить|куплю|отдам|продаж)\w*\b", t))
    tpu_print = bool(
        re.search(r"\b(?:тпу|tpu)\b", t)
        and re.search(r"\b(?:печатать|печат|не\s+сможет|не\s+умеет|не\s+получится)\w*\b", t)
    )
    dry_elsewhere = bool(
        re.search(r"\bсуш\w*\b", t)
        and re.search(r"\b(?:есть\s+где|где[\s-]?то|дома|у\s+меня|не\s+нужн)\w*\b", t)
    )
    need_for_tpu = bool(re.search(r"\b(?:нужен|надо)\b", t) and re.search(r"\b(?:тпу|tpu)\b", t))
    if sell and (tpu_print or dry_elsewhere or need_for_tpu):
        return True
    return bool(tpu_print and dry_elsewhere)


def _topic_is_ace_filament_drying_intent(text: str | None) -> bool:
    """ACE Pro как сушилка / сушка филамента в станции — не замена катушки в ACE."""
    if not text:
        return False
    if _is_ace_unit_trade_banter(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not (_ace_mentioned(text) or re.search(r"\bаськ\w*\b", t)):
        return False
    if re.search(r"\b(?:замен|поменя|смени|установ|replace|remov|disassembl)\w*\b", t):
        return False
    has_dry = bool(
        re.search(
            r"\b(?:сушилк\w*|суш[иао]т|высуш|просуш|dryer|drying|dry\s*box|"
            r"влажн\w*|увлаж|moisture|desiccant|гигро)\w*\b",
            t,
        )
    )
    return has_dry


def _is_combo_ace_marketplace_chat(text: str | None) -> bool:
    """Цена ACE/комбо на маркетплейсе или «дорого?» в треде — не замена филамента."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bсколько\s+стоит\b", t):
        return False
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:замен|поменя|смени|загруз|встав|установ|сброс))\b",
        t,
    ) and re.search(r"\b(?:филамент|катушк|слот|filament)\w*\b", t):
        return False
    ace_unit_price = bool(
        re.search(r"\b(?:аська\w*|аськ\w*|ace)\b", t)
        and re.search(r"\d+\s*₽|\d+₽|\d+\s*(?:руб\.?|rub)\b", t)
        and re.search(r"\b(?:дорого|дешево|дороговато|вторая|первая|третья)\w*\b", t)
    )
    if ace_unit_price:
        return True
    marketplace = bool(
        re.search(
            r"\b(?:"
            r"aliexpress|алиэкспресс|алик\w*|"
            r"wb|вб|ozon|озон|wildberries|яндекс\.?\s*маркет|маркетплейс"
            r")\b",
            t,
        )
    )
    price_ctx = bool(
        re.search(r"\bстоит\b.{0,16}\d+", t)
        or re.search(r"\d+\s*₽|\d+₽|\d+\s*(?:руб\.?|rub)\b", t)
    )
    combo_ace = bool(
        re.search(r"\bкомбо\b", t)
        and re.search(r"\b(?:аська\w*|аськ\w*|ace)\b", t)
        and (
            "?" in text
            or re.search(r"\b(?:с\s+какой|какая|какой|что\s+в\s+комплект|в\s+комплекте|входит)\w*\b", t)
        )
    )
    if combo_ace and (marketplace or price_ctx):
        return True
    return bool(
        combo_ace
        and re.search(r"\b(?:в\s+комплект|комплектац|входит|идёт\s+в|ставят|поставля)\w*\b", t)
    )
