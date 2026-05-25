"""Эвристики по тексту вопроса (модель, тема, код ошибки)."""



from __future__ import annotations







import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.web_wiki_index import WebWikiDoc, WebWikiIndex




_PRINTER_MENTION_RE = re.compile(



    r"(?i)(?<![a-z0-9])("



    r"kobra|photon|vyper|chiron|predator|anycubic|megax|mega[\s-]?x|mega[\s-]?pro|mega[\s-]?s|"



    r"wash[\s-]?(and|&)?[\s-]?cure|mono[\s-]?m|m5s|"



    r"кобра|фотон|вайпер|аникубик"



    r")(?![a-z0-9])"



)











def _printer_mentioned(text: str) -> bool:



    """В тексте явно названа линейка/семейство принтера (латиница или кириллица)."""



    if _PRINTER_MENTION_RE.search(text):



        return True



    tl = text.lower()



    # номера серий часто пишут отдельно: "s1", "k2", "m5" и т.п. — только с контекстом принтера



    if re.search(r"\bkobra\b", tl) and re.search(r"\b(s1|s2|go|max|neo|plus|combo|pro)\b", tl):



        return True



    if re.search(r"\bphoton\b", tl) and re.search(r"\b(m3|m5|mono|ultra|x6)\b", tl):



        return True



    return False











def _topic_needs_printer_model(text: str) -> bool:



    """Тема вопроса обычно специфична для модели (без модели ответ легко промахнется)."""



    t = text.lower()



    # Выбор марки/типа пластика (TPU и т.п.) — не путать с сервисом сопла.
    if _topic_is_filament_material_choice_intent(text):



        return False



    # Настройки слайсера под PETG/TPU (мост, поток, поддержки) — не привязка к модели Kobra.
    if _topic_is_filament_slicing_settings_intent(text):



        return False



    # Отверстия в вертикальных стенках / «капля» в CAD — не привязка к модели.
    if _topic_is_slicer_vertical_hole_intent(text):
        return False



    # Прошивка и многоцветная печать (ACE / Combo) — не смола Photon/M3.
    if _topic_is_multicolor_firmware_intent(text):



        return False



    # Подача филамента / шестерня — гайды различаются по модели.
    if _topic_is_filament_feed_intent(text) and not _printer_mentioned(text):
        return True



    ru = (



        "экструдер",



        "сопло",



        "хотэнд",



        "прошив",



        # "ошибка" слишком общее слово (напр. "ошибка природы") — модель по нему не уточняем.



        # Коды ошибок обрабатываются отдельно через _extract_error_code/_is_error_code_query.



        "калибр",



        "левел",



        "уровн",



        "настрой",



        "настрои",



        "не печатает",



        "ремень",



        "застрял",



        "заклинил",



        "стол",



        "подогрев",



        "сопл",



        "двер",



        "петл",



        "стекл",



    )



    en = (



        "extruder",



        "nozzle",



        "hotend",



        "hot end",



        "firmware",



        "calibrat",



        "leveling",



        "level ",



        " bed",



        "heated bed",



        "build plate",



        "belt",



        "jam",



        "clog",



        "stepper",



        "door",



        "glass door",



        "hinge",



        "enclosure",



    )



    if any(x in t for x in ru + en):



        return True



    # «кубы» / leveling cubes при настройке стола — разная инструкция по моделям



    if "куб" in t and any(



        k in t for k in ("стол", "калибр", "уровн", "настрой", "level", "bed", "скрейп", "царап", "сопл")



    ):



        return True



    return False











def _extract_error_code(text: str) -> str | None:



    """



    Возвращает числовой код ошибки (4–7 цифр), если он явно присутствует в тексте.



    Формат на вики обычно: /error-codes/<code>-code/...



    """



    m = re.search(r"\b(\d{4,7})\b", text.lower())



    return m.group(1) if m else None











def _is_error_code_query(text: str) -> bool:



    """



    Сообщение, где ключевой смысл — код ошибки (например "ошибка 11407").



    """



    code = _extract_error_code(text)



    if not code:



        return False



    t = text.lower()



    # если рядом есть явная "ошибка/err/error" — точно запрос по коду



    return any(k in t for k in ("ошибк", "error", "err"))











def _error_code_variant_suffix(code: str, url: str) -> str | None:



    """



    /en/error-codes/<code>-code/<suffix> -> suffix



    /en/error-codes/<code>-code -> None



    """



    u = (url or "").lower().rstrip("/")



    base = f"/error-codes/{code}-code"



    if base not in u:



        return None



    after = u.split(base, 1)[1]



    if not after:



        return None



    after = after.lstrip("/")



    if not after:



        return None



    return after.split("/", 1)[0] or None











def _error_code_target_suffix(text: str) -> str | None:



    """



    Пытаемся понять, для какой линейки нужна страница кода ошибки.



    Поддерживаем явные сокращения (s1/k3/k3m) и названия моделей (через hints).



    """



    tl = text.lower()



    # явные сокращения



    if re.search(r"\bk3m\b", tl):



        return "k3m"



    if re.search(r"\bk3\b", tl) or re.search(r"\bkobra\s*3\b", tl) or "kobra-3" in tl:



        return "k3"



    if re.search(r"\bs1\b", tl) or "kobra-s1" in tl or re.search(r"kobra\s*s\s*1\b", tl):



        return "s1"







    hints = _model_slug_hints(text)



    if "kobra-s1" in hints or "kobra-s1-combo" in hints:



        return "s1"



    if "kobra-3" in hints or "kobra-3-combo" in hints:



        return "k3"



    if "kobra-max" in hints or "kobra-max-combo" in hints:



        return "k3m"



    return None











def _error_code_candidates(index: WebWikiIndex, code: str) -> list[WebWikiDoc]:



    target = f"/error-codes/{code}-code"



    out: list[WebWikiDoc] = []



    for d in getattr(index, "_docs", []):  # type: ignore[attr-defined]



        try:



            u = (d.url or "").lower()



        except Exception:



            continue



        if target in u:



            out.append(d)



    return out











def _pick_error_code_doc(index: WebWikiIndex, code: str, *, context_text: str) -> WebWikiDoc | None:



    """



    Для кодов ошибок не используем fuzzy-поиск (он может путать коды).



    Ищем только страницы вида /error-codes/<code>-code...



    """



    candidates = _error_code_candidates(index, code)



    if not candidates:



        return None



    # Если вариантов несколько — пытаемся выбрать по модели из текста.



    target_suffix = _error_code_target_suffix(context_text)



    if target_suffix:



        for d in candidates:



            if _error_code_variant_suffix(code, d.url) == target_suffix:



                return d



    # Предпочитаем базовую страницу кода без суффиксов (/s1, /k3, и т.п.)



    base = f"https://wiki.anycubic.com/en/error-codes/{code}-code"



    for d in candidates:



        if d.url.rstrip("/") == base:



            return d



    # Если суффикса не нашли и базовой нет — неоднозначно, пусть вызывающий уточнит модель.



    return candidates[0] if len(candidates) == 1 else None







def _ace_mentioned(text: str) -> bool:



    t = text.lower()



    return bool(



        any(



            k in t



            for k in (



                "ace pro",



                "ace-pro",



                "аська",



                "аска",



                "аськ",



                "эйс",



            )



        )



        or re.search(r"\bace\b", t)



    )











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












def _topic_is_ace_filament_drying_intent(text: str | None) -> bool:
    """ACE Pro как сушилка / сушка филамента в станции — не замена катушки в ACE."""
    if not text:
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


def _user_already_replaced_motherboard(text: str) -> bool:



    t = text.lower()



    if not any(k in t for k in ("материн", "motherboard", "mainboard", "main board")):



        return False



    return any(



        k in t



        for k in (



            "поменял",



            "заменил",



            "сменил",



            "прислали",



            "поставил",



            "менял",



            "replaced",



            "already",



        )



    )











def _has_geo_social_cues(text: str) -> bool:



    """Просьба найти владельцев принтера поблизости (не тех. вопрос)."""



    t = text.lower()



    people = ("кто", "есть ли", "найдётся", "найдется", "познаком", "встрет", "живёт", "живет", "живут")



    geo = (



        "рядом",



        "поблизости",



        "недалеко",



        "област",



        "город",



        "обнинск",



        "наро-фоминск",



        "наро фоминск",



        "москв",



        "питер",



        "спб",



        "санкт-петербург",



        "район",



    )



    return any(p in t for p in people) and any(g in t for g in geo)











def _is_geo_social_only_request(text: str) -> bool:



    """



    Координация встреч/обмена с соседями — бот молчит.



    Если в том же сообщении есть тех. проблема (ACE, код ошибки) — ищем вики.



    """



    if not _has_geo_social_cues(text):



        return False



    if _topic_is_ace_not_detected_intent(text) or _is_error_code_query(text):



        return False



    if _topic_needs_printer_model(text) and _printer_mentioned(text):



        return False



    return True











def _needs_model_clarification(text: str) -> bool:



    # Для кодов ошибок модель не спрашиваем — либо найдём страницу по коду, либо промолчим.



    if _is_error_code_query(text):



        return False

    # Наблюдения и бытовой чат — модель не уточняем.
    if _is_non_wiki_chatter_message(text):
        return False

    return _topic_needs_printer_model(text) and not _printer_mentioned(text)











_MARKETPLACE_HOST_RE = re.compile(

    r"(?i)\b("

    r"aliexpress|ali\.click|amazon\.|ozon\.|wildberries|market\.yandex|"

    r"tmall|taobao|banggood|gearbest|joom\.|ebay\."

    r")\b"

)





def _is_marketplace_promo_message(text: str | None) -> bool:

    """Рекламная ссылка на маркетплейс — не вопрос к вики."""

    if not text:

        return False

    t = text.lower()

    if _MARKETPLACE_HOST_RE.search(t):

        return True

    if re.search(r"https?://\S+", t) and re.search(r"смотри,?\s+что\s+есть\s+на\b", t):

        return True

    if re.search(r"https?://\S+", t) and any(k in t for k in ("скидк", "₽", " руб", "промокод")):

        if re.search(r"(?i)\b(aliexpress|ozon|wildberries|amazon|ali\.click)\b", t):

            return True

    return False






def _is_chat_meta_discussion(text: str) -> bool:
    """Цитата чужого «помогите» или разговор об истории чата — не запрос к боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    help_words = ("помогите", "спасите", "help", "памагити", "спаситипамагити")
    has_help = any(k in t for k in help_words)
    cited_help = bool(
        re.search(r'["«\'][^"\']*(?:помогите|спасите|help)', t)
        or re.search(r"(?:помогите|спасите)\s*(?:\.\.\.|…)", t)
    )
    reminisce = bool(
        re.search(
            r"\b(?:"
            r"не\s+помню|перечитал|"
            r"в\s+чат\s+приш|пришел\s+в\s+чат|"
            r"впервые\s+вопрос|написал\s+чату|"
            r"в\s+июн|в\s+чате\b"
            r")\b",
            t,
        )
    )
    if reminisce and (has_help or re.search(r"\bвопросами?\b", t)):
        return True
    if cited_help and reminisce:
        return True
    if cited_help:
        outside = re.sub(r'["«][^"»]*?[»"]', " ", t)
        outside = re.sub(r"(?:помогите|спасите)\s*(?:\.\.\.|…)", " ", outside, flags=re.I)
        if not any(k in outside for k in help_words):
            return True
    return False


def _is_material_strength_discussion(text: str) -> bool:
    """Обсуждение прочности TPU/слои vs поперёк — не запрос к вики и не clarify модели."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:настро|печатать|печат|сделать)|что\s+делать)\b",
        t,
    ):
        return False
    material = bool(
        re.search(r"\b(?:tpu|тпу|pla|пла|petg|петг|abs|абс|нейлон|nylon|пластик|филамент)\w*\b", t)
    )
    mechanics = bool(
        re.search(
            r"\b(?:"
            r"прочн\w*|слом\w*|послойн\w*|поперёк|поперек|под\s+углом|"
            r"спекан\w*|по\s+слоям|анизотроп"
            r")\w*\b",
            t,
        )
    )
    curiosity = bool(
        re.search(r"\b(?:мне\s+интересно|интересно\s*,?\s*будет|как\s+я\s+понял)\b", t)
    )
    return material and mechanics and curiosity


def _is_technical_opinion_sharing(text: str) -> bool:
    """Мнение в обсуждении (люфт, печать) — не запрос помощи у бота."""
    if not text or not text.strip():
        return False
    if _message_has_help_intent(text):
        return False
    if _is_material_strength_discussion(text):
        return True
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкак\s+по\s+мне\b", t):
        return True
    if re.search(r"\b(?:по\s+мне|мне\s+кажется|я\s+считаю|имхо)\b", t) and re.search(
        r"\b(?:люфт|backlash|зазор|на\s+печать|печат|не\s+влияет|не\s+страшн|не\s+смертел|по\s+сути)\b",
        t,
    ):
        return True
    return False


def _is_technical_observation_sharing(text: str) -> bool:
    """Делится находкой о настройках/параметрах — не просит помощи у бота."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    noticed = bool(
        re.search(
            r"\b(?:"
            r"заметил(?:\s*,)?\s*что|заметила(?:\s*,)?\s*что|"
            r"оказалось\s+что|выяснил(?:ся|а)?\s+что|оказывается|"
            r"понял(?:\s*,)?\s*что|разобрал(?:ся|а)?\s+что"
            r")\b",
            t,
        )
    )
    tinkering = bool(re.search(r"\b(?:разбирал(?:ся|а)?|копал(?:ся|а)?)\b.{0,50}\bнастрой", t))
    param_talk = bool(
        re.search(r"\b(?:это\s+)?(?:вовсе\s+)?не\s+(?:параметр|тот|то)\b", t)
        or re.search(r"\b[a-z][a-z0-9_]{5,}\b", t)
    )
    if noticed and (tinkering or param_talk):
        return True
    if tinkering and noticed:
        return True
    return False


def _is_partial_manual_find_observation(text: str) -> bool:
    """«Нашёл только инструкцию как…» — делится находкой в чате, не просит бота."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # «не нашёл / не могу найти» — это запрос помощи, не бытовая реплика.
    if re.search(r"\bне\s+(?:могу\s+)?найти\b", t) or re.search(r"\bне\s+наш", t):
        return False
    if re.search(r"\b(?:наш[её]л|нашла|нашли|нашлось)\s+(?:тока|только|лишь|одну)\b", t):
        return True
    if re.search(r"\b(?:наш[её]л|нашла|нашли|нашлось)\b", t) and "инструкц" in t:
        return True
    if re.search(r"\bесть\s+только\b", t) and any(k in t for k in ("инструкц", "гайд", "мануал")):
        return True
    return False



def _is_slicer_app_disambiguation(text: str) -> bool:
    """«Это в ChiTu или Orca?» — уточнение в треде, не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкак\s+(?:настро|установ|использов|скачать|сделать|выбрать)\b", t):
        return False
    if _is_error_code_query(text) or _printer_mentioned(text):
        return False
    has_slicer = bool(re.search(r"\b(?:слайсер\w*|slicer)\b", t))
    has_app = bool(
        re.search(
            r"\b(?:чиди|чити|chitu|chitubox|orca|орка|anycubic|cura|prusaslicer|bambu\s*studio)\b",
            t,
        )
    )
    if not (has_slicer or has_app):
        return False
    choice = bool(re.search(r"\bили\b", t) or t.count("?") >= 2)
    demonstrative = bool(re.search(r"^\s*это\s+", t))
    if (has_slicer and has_app and (choice or demonstrative)) or (has_app and choice and len(t) <= 100):
        return True
    return False


def _is_filament_testing_plan_sharing(text: str) -> bool:
    """Планы по катушке/тестам — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкатушк", t) and re.search(r"\bтест", t):
        return True
    if re.search(r"\b(?:буду|будем)\s+(?:всякое\s+)?тест", t):
        return True
    if re.search(r"\b(?:определил|выбрал|отвёл|отвел)\b.{0,30}\bтест", t):
        return True
    return False


def _is_sarcastic_printer_banter(text: str) -> bool:
    """Шутки про А4/бумагу или тред с люфтом — не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкак\s+(?:убрать|устранить|уменьшить|настро)\b", t):
        return False
    if re.search(r"\b(?:а4|a4)\b", t) and re.search(r"\b(?:принтер|вставля|бумаг)\b", t):
        return True
    if re.search(r"\bбумаг\w*\b", t) and re.search(r"\bпечата", t):
        if re.search(r"\bэто\s+же\s+принтер\b", t) or "?" in text:
            return True
    if (t.count("·") >= 2 or t.count("?") >= 2) and re.search(r"\bлюфт\b", t):
        if not re.search(r"\b(?:помогите|подскаж)\b", t):
            return True
    return False


def _is_sarcastic_thread_banter(text: str) -> bool:
    """Сарказм в треде («спал бы», «зачем тебе») — не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба о помощи — не отсекаем.
    if re.search(
        r"\b(?:"
        r"как\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)|"
        r"помогите|подскаж|не\s+работает|что\s+делать"
        r")\b",
        t,
    ):
        return False
    shrug = bool(re.search(r"\bчто\s+могу\s+сказать\b", t))
    rhetorical_why = bool(re.search(r"\bзачем\s+(?:оно|тебе|вам|это|мне|нам)\b", t))
    sleep_advice = bool(re.search(r"\b(?:спал\s+бы|спи\s+бы|уснул\s+бы)\b.{0,25}\bспокойн", t))
    wished_ignorance = bool(re.search(r"\bне\s+знал\s+про\b", t))
    if shrug and (rhetorical_why or sleep_advice or wished_ignorance):
        return True
    if rhetorical_why and (sleep_advice or wished_ignorance):
        return True
    if sleep_advice and wished_ignorance:
        return True
    if shrug and re.search(r"^н+u+\s*,?\s*что\s+могу", t):
        return True
    # Риторика в треде: «оно тебе не надо · а как же печать миниатюр по вахе».
    not_needed = bool(re.search(r"\b(?:оно\s+)?тебе\s+(?:точно\s+)?не\s+надо\b", t))
    rhetorical_but = bool(re.search(r"\bа\s+как\s+же\b", t))
    hobby_print = bool(
        re.search(r"\b(?:вах\w*|warhammer|wh40k|40k)\b", t)
        and re.search(r"\b(?:миниатюр|фигурк|шлем)\w*\b", t)
    )
    if not_needed and rhetorical_but:
        return True
    if rhetorical_but and hobby_print:
        return True
    if hobby_print and "?" in text:
        return True
    # «А я говорил про сушить и калибровать пластик?» — риторическое «я же не про это».
    if re.search(r"\b(?:а\s+)?я\s+говорил\s+про\b", t) and "?" in text:
        return True
    # «Перехвалил, вот что сейчас увидел» — реакция в треде, не запрос к боту.
    if re.search(r"\bперехвал\w*\b", t) and re.search(r"\b(?:увидел|увидела|сейчас)\b", t):
        return True
    return False


def _is_conversational_skepticism(text: str) -> bool:
    """Скепсис в треде — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:сомневаюсь|сомневаемся|не\s+думаю|вряд\s+ли|сомнев)\b", t) and re.search(r"\bчто\b", t):
        return True
    if re.search(r"\b(?:пустят|напечатают|запустят|заморачив)\b", t) and re.search(
        r"\b(?:кубик|куб|печат)\b", t
    ):
        return True
    if re.search(r"\bвс[её]\s+на\s+этом\b", t) and re.search(r"\bпечат", t):
        return True
    # Мнение в споре про филамент: «нить не так плоха, раздувают — ошибка статистики»
    filament_thread = bool(
        re.search(r"\b(?:нит\w*|нить|филамент|пруток|катушк|пластик)\w*\b", t)
        or re.search(r"\bошибка\s+статистик\w*\b", t)
    )
    downplay = bool(
        re.search(r"\bдумаю\b", t)
        and re.search(r"\bчто\b", t)
        and re.search(r"\b(?:раздува|не\s+так\s+плох|преувелич|перегиб|раздули)\w*\b", t)
    )
    stats_dismiss = bool(re.search(r"\bошибка\s+статистик\w*\b", t))
    if filament_thread and (downplay or stats_dismiss):
        return True
    return False


def _is_printing_status_announcement(text: str) -> bool:
    """«Запускаю первый слой» — статус в чате, не вопрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bчто\s+(?:делать|значит|не\s+так|не\s+работает)\b", t):
        return False
    printing_action = bool(
        re.search(
            r"\b(?:запускаю|запустил|начинаю|начал|печатаю|пошл[ао]\s+печать|калибрую)\b",
            t,
        )
    )
    layer_ctx = bool(re.search(r"\b(?:первый\s+слой|слой|печат|калибр)\b", t))
    casual_start = bool(re.search(r"^(?:ну\s+что|ну\s*,|поехали|погнали)\b", t))
    if printing_action and layer_ctx:
        return True
    if casual_start and (printing_action or layer_ctx):
        return True
    return False


def _is_layer_profile_thread_opinion(text: str) -> bool:
    """Мнение в треде про первый слой / профиль сопла — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _is_error_code_query(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж|не\s+работает|что\s+делать)\b", t):
        return False
    # «как убрать сдвиг слоя» — это уже запрос помощи, не бытовая реплика.
    if re.search(r"\bкак\s+(?:убрать|исправ|устранить|настро|сделать)\b", t):
        return False
    layer_ctx = bool(re.search(r"\b(?:первый\s+слой|слой\w*|layer)\b", t))
    # «соковом» — опечатка «сопловом» в обсуждении профиля
    profile_ctx = bool(re.search(r"\b(?:профил\w*|сопл\w*|соков\w*|nozzle)\b", t))
    if not (layer_ctx or profile_ctx):
        return False
    opinion = bool(
        re.search(r"\b(?:не\s+повлия|не\s+влия|думаю|кажется|норм|сырой|сыр\w+)\b", t)
        or re.search(r"\b(?:сомнева|вряд\s+ли|не\s+думаю)\b", t)
    )
    return opinion


def _is_first_days_experience_sharing(text: str) -> bool:
    """Рассказ «когда взял кобру / в первый день узнал части» — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкак\s+(?:замен|почин|исправ|настро|сделать|убрать|подключ)\b", t):
        return False
    # Покупка / первые дни с принтером
    got_printer = bool(
        re.search(
            r"\b(?:когда|как\s+только)\s+.{0,50}\b(?:взял|взяла|купил|купила|получил|получила)\b",
            t,
        )
        or re.search(r"\bкобр\w*\s+взял\b", t)
        or re.search(r"\bв\s+первый\s+(?:же\s+)?день\b", t)
    )
    # Узнал устройство узлов без вопроса к боту
    discovery = bool(
        re.search(
            r"\b(?:узнал|узнала|понял|поняла|разобрался|разобралась)\b.{0,80}\b(?:"
            r"устройств\w*|голов\w*|хаб\w*|аська\w*|аськ\w*|сопл\w*|экструдер\w*|"
            r"портал\w*|ремен\w*"
            r")\b",
            t,
        )
    )
    leftover_print = bool(
        re.search(r"\b(?:остатк|стары[мх]|ломк)\b", t) and re.search(r"\bпечатал", t)
    )
    casual_wrap = bool(re.search(r"\bкороче\b", t))
    if discovery and (got_printer or leftover_print or casual_wrap):
        return True
    if got_printer and leftover_print:
        return True
    return False


def _is_printer_comparison_opinion(text: str) -> bool:
    """Сравнение с другим принтером («лучше чем на кобре») — бытовая реплика, не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явный запрос «как настроить» — не отсекаем.
    if re.search(
        r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен|почист|смаз|провер)\b",
        t,
    ):
        return False
    on_other = bool(re.search(r"\b(?:чем|как)\s+на\s+(?:кобр|фотон|вайпер|друг\w+)\b", t))
    better_worse = bool(re.search(r"\b(?:лучше|хуже|удобнее|проще)\b", t))
    looks_cmp = bool(re.search(r"\bвыглядит\s+(?:лучше|хуже|норм|ок)\b", t))
    # «не сверху как на кобре», «регулируется иначе как на кобре»
    unlike_other = bool(re.search(r"\b(?:не\s+\w+\s+)?как\s+на\s+(?:кобр|фотон|вайпер)\b", t))
    if on_other and (better_worse or looks_cmp or unlike_other):
        return True
    if looks_cmp and (on_other or re.search(r"\bстол\w*\b", t)):
        return True
    if unlike_other:
        return True
    # «сравню с тем, что напечатала кобра» / план xyz-куба «ради интереса» — не запрос к вики.
    cube_compare = bool(
        re.search(r"\bсравн\w*\b", t)
        and re.search(r"\b(?:напечатал\w*|куб|xyz)\b", t)
    )
    future_cube_test = bool(
        re.search(r"\b(?:попробую|попробуем|напечатаю)\b", t)
        and re.search(r"\b(?:куб|xyz)\b", t)
        and (
            re.search(r"\bсравн\w*\b", t)
            or re.search(r"\bради\s+интереса\b", t)
            or re.search(r"\bнапечатал\w*\b", t)
        )
    )
    if cube_compare or future_cube_test:
        return True
    # «кобра 3 стоит как Х» — сравнение в треде, не «как настроить».
    if re.search(r"\bстоит\s+как\b", t) and _printer_mentioned(text):
        return True
    return False


def _is_printer_purchase_material_opinion(text: str) -> bool:
    """Размышления о покупке/возврате и опыт с пластиками — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|что\s+делать|как\s+(?:настро|почин|исправ|сделать|убрать))\b",
        t,
    ):
        return False
    # Возврат / замена принтера / «толку нет от s1 max»
    purchase_thought = bool(
        re.search(r"\b(?:вот\s+)?думаю\b", t)
        or re.search(r"\b(?:проще|лучше)\s+.{0,25}\bвзять\b", t)
        or re.search(r"\bтолку\s+нет\b", t)
        or re.search(r"\b(?:верн\w*|возврат)\b.{0,50}\b(?:деньг|курс)\b", t)
    )
    printer_ctx = bool(
        re.search(r"\b(?:s1\s*max|kobra|кобр\w*|vyper|вайпер|фотон|mono|принтер\w*)\b", t)
        or re.search(r"\b(?:шлем|маск)\w*\s+печат", t)
    )
    # «в основном pla/petg печатал», «побаловался с abs»
    material_past = bool(
        re.search(r"\b(?:pla|пла|petg|петг|abs|абс|композит|нейлон|nylon|tpu|тпу)\b", t)
        and re.search(r"\b(?:печатал|печатала|побаловал|пробовал|забил)\b", t)
    )
    # «хз стал ли бы … попробовать … и забил»
    casual_try = bool(
        (re.search(r"\bхз\b", t) or re.search(r"\bстал\s+ли\s+бы\b", t))
        and re.search(r"\b(?:попробовать|интересно|акци\w*)\b", t)
    )
    if purchase_thought and printer_ctx:
        return True
    if material_past and (purchase_thought or casual_try or printer_ctx):
        return True
    if casual_try and re.search(r"\bкомпозит", t):
        return True
    ace_ctx = bool(re.search(r"\b(?:аська\w*|аськ\w*|ace)\b", t))
    # «смотря как купил», б/у, уценка, «пробег» — обсуждение покупки, не вики.
    if re.search(r"\bкак\s+(?:купить|заказать)\b", t):
        return False
    used_purchase = bool(
        (
            re.search(r"\b(?:б/?у|бу\b|уценк\w*|пробег\w*|скручен\w*)\b", t)
            or re.search(r"\b(?:смотря|зависит)\s+как\b", t)
        )
        and re.search(r"\bкупил\w*\b", t)
    )
    if used_purchase and (printer_ctx or ace_ctx):
        return True
    # «ты говорил, что та без аськи лежала» — пересказ в треде.
    if re.search(r"\bты\s+говорил\b", t) and (ace_ctx or re.search(r"\bлежал\w*\b", t)):
        return True
    return False


def _is_price_negotiation_chatter(text: str) -> bool:
    """Торг о цене б/у узлов (аська, запчасти) — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|что\s+делать|как\s+(?:купить|продать|замен|настро|почин))\b",
        t,
    ):
        return False
    # «сколько стоит» — вопрос о рынке, не переписка «давай за N»
    if re.search(r"\bсколько\s+стоит\b", t):
        return False
    numbers = re.findall(r"\b\d{1,5}\b", t)
    # «стоит 20 минут» — не цена
    if re.search(r"\bстоит\s+\d+\s*(?:минут|мин\.?|секунд|сек\.?|часов|час\.?)\b", t):
        return False
    bargain_offer = bool(
        re.search(
            r"\b(?:предлагал|предложил|предложи|предлагаю|торгуюсь|сброшу|уступлю)\b",
            t,
        )
    )
    counter_deal = bool(re.search(r"\bдавай\s+за\b", t))
    relay_price = bool(
        re.search(r"\b(?:говорит|сказал|сказала|просит|хочет|берёт|берет)\b", t)
        and re.search(r"\bстоит\s+\d+\b", t)
    )
    price_numbers = len(numbers) >= 2
    if bargain_offer and (counter_deal or relay_price or price_numbers):
        return True
    if counter_deal and relay_price:
        return True
    if relay_price and price_numbers:
        return True
    return False


def _is_peer_social_printer_question(text: str) -> bool:
    """Вопрос к человеку в чате (гарантия, «у тебя ещё кобра»), не к боту/вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явный запрос инструкции или справки по вики — не отсекаем.
    if re.search(
        r"\b(?:"
        r"как\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен|провер|узнать)|"
        r"где\s+(?:найти|взять|скачать|посмотреть)|"
        r"что\s+(?:делать|значит|не\s+так)|"
        r"помогите|подскаж|не\s+работает|"
        r"сколько\s+(?:длится|месяц|лет|дней)\b"
        r")\b",
        t,
    ):
        return False
    # Обращение к собеседнику, а не к боту.
    second_person = bool(
        re.search(
            r"\b(?:"
            r"у\s+тебя|тебе|твой|твоя|твоё|твои|"
            r"у\s+вас|вам|ваш|ваша|ваши|"
            r"ты\s+ещё|ты\s+еще"
            r")\b",
            t,
        )
    )
    # «Вася, …» или «Вася у тебя …» — не «какая гарантия …».
    addressed = bool(
        re.match(r"^[а-яёa-z]{2,15}\s*,\s+", text.strip(), re.I | re.UNICODE)
        or (
            re.match(r"^[а-яёa-z]{2,15}\s+", text.strip(), re.I | re.UNICODE)
            and second_person
            and not re.match(
                r"^(?:как|что|где|когда|почему|зачем|сколько|какая|какой|какие|какое|кто|есть\s+ли|можно\s+ли)\b",
                t,
                re.I | re.UNICODE,
            )
        )
    )
    social_topic = bool(
        re.search(
            r"\b(?:"
            r"гарант\w*|"
            r"ещё\s+на\s+гарант|еще\s+на\s+гарант|"
            r"купил\w*|купишь|продал\w*|"
            r"взял\w*|получил\w*|"
            r"остал\w*|"
            r"работает\s+ли|"
            r"еще\s+есть|ещё\s+есть"
            r")\b",
            t,
        )
    )
    printer_ctx = bool(re.search(r"\b(?:кобр|фотон|вайпер|принтер|printer|s1|s2|combo)\w*\b", t))
    if social_topic and (second_person or addressed) and printer_ctx:
        return True
    if social_topic and second_person:
        return True
    return False


def _is_peer_claim_debate_relay(text: str) -> bool:
    """Пересказ чужого спора в чате (маркетинг/отходы) — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # «чел в чате доказывает», «мне тут … твердит»
    relay = bool(
        re.search(
            r"\b(?:чел|чувак|тип|человек|один|кто-то)\b.{0,55}\b(?:доказывает|спорит|уверяет|твердит|настаивает)\b",
            t,
        )
        or re.search(r"\bмне\s+тут\b.{0,45}\b(?:доказывает|спорит|твердит|настаивает)\b", t)
    )
    # Скепсис к рекламным обещаниям (отходы, резка у сопла)
    marketing_skeptic = bool(
        re.search(r"\bмаркетинг\w*\b", t)
        and re.search(r"\b(?:фикци|врань|не\s+роляет|нихуя|ерунд|обман)\w*\b", t)
    )
    waste_claim = bool(
        re.search(r"\bотход\w*\b", t)
        and re.search(r"\b(?:филамент|режется|сопл)\w*\b", t)
    )
    if relay and (marketing_skeptic or waste_claim):
        return True
    if marketing_skeptic and waste_claim:
        return True
    return False


def _is_non_wiki_chatter_message(text: str) -> bool:
    """Сообщения чата, на которые бот не отвечает из вики."""
    return (
        _topic_is_marketplace_commerce_intent(text)
        or _is_peer_claim_debate_relay(text)
        or _is_peer_social_printer_question(text)
        or _is_price_negotiation_chatter(text)
        or _is_printer_purchase_material_opinion(text)
        or _is_printer_comparison_opinion(text)
        or _is_printing_status_announcement(text)
        or _is_layer_profile_thread_opinion(text)
        or _is_first_days_experience_sharing(text)
        or _is_conversational_skepticism(text)
        or _is_sarcastic_thread_banter(text)
        or _is_sarcastic_printer_banter(text)
        or _is_slicer_app_disambiguation(text)
        or _is_filament_testing_plan_sharing(text)
        or _is_technical_opinion_sharing(text)
        or _is_technical_observation_sharing(text)
        or _is_partial_manual_find_observation(text)
        or _is_chat_meta_discussion(text)
    )


# Сравнительное «как/чем на кобре», разговорное «ужас как» в конце — не вопрос к боту.
_COLOQUIAL_KAK_RE = re.compile(
    r"(?:"
    r"\bужас\s+как\b|"
    r"\bкак\s+по\s+мне\b|"
    r"\b\w+\s+как\s*[!?.…\U0001f300-\U0001faff]*\s*$|"
    r"\b(?:чем|как)\s+на\s+\w+|"
    r"\bкак\s+на\s+\w+|"
    r"\bстоит\s+как\s+\w+"
    r")",
    re.I | re.UNICODE,
)


def _message_has_help_intent(text: str) -> bool:
    """Пользователь ищет помощь / инструкцию, а не просто комментирует чат."""
    if not text or not text.strip():
        return False
    if (
        _is_printing_status_announcement(text)
        or _is_layer_profile_thread_opinion(text)
        or _is_conversational_skepticism(text)
        or _is_sarcastic_thread_banter(text)
        or _is_sarcastic_printer_banter(text)
        or _is_slicer_app_disambiguation(text)
        or _is_filament_testing_plan_sharing(text)
    ):
        return False
    raw = text.strip()
    t = re.sub(r"\s+", " ", raw.lower()).strip()
    if "?" in raw:
        return True
    if _is_error_code_query(text):
        return True
    if re.search(r"\b(кинь|скинь|дай|подкинь|киньте|скиньте|дайте)\w*\b.{0,30}\bссыл", t):
        return True
    if "ссыл" in t and any(w in t for w in ("вики", "wiki", "настрой", "калибр", "уровн", "стол", "куб")):
        return True
    if re.search(r"\bне\s+могу\s+найти\b", t):
        return True
    return bool(
        re.search(
            r"\b(?:"
            r"как\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен|почист|смаз|провер)|"
            r"почему|зачем(?!\s+(?:оно|тебе|вам|это|мне|нам)\b)|"
            r"что\s+(?:делать|значит|не\s+так)|"
            r"где\s+(?:найти|взять|скачать)|"
            r"кто\s+знает|"
            r"не\s+работает|"
            r"помогите|помоги|"
            r"подскаж|"
            r"скажите\s+как"
            r")\b",
            t,
        )
    )


def _is_conversational_chatter(text: str) -> bool:
    """Бытовая реплика в чате — не отвечать ссылкой из вики."""
    if not text or not text.strip():
        return False
    if _is_non_wiki_chatter_message(text):
        return True
    if _message_has_help_intent(text):
        return False
    if _is_marketplace_promo_message(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _COLOQUIAL_KAK_RE.search(t):
        return True
    if re.search(r"\bчто\s*ли\b|\bчтоли\b", t):
        return True
    if re.search(r"\bразберемся\b", t):
        return True
    if re.search(r"\bшумит\b|\bшум\b", t):
        return True
    if re.search(r"\b(?:они|у\s+них|тут\s+кстати)\b", t) and re.search(
        r"\b(?:приклеил|приклеили|сделал|сделали|кстати)\b", t
    ):
        return True
    return False


def _is_generic_help_without_context(text: str) -> bool:



    """



    "помогите/спасите" без конкретики — лучше попросить уточнение, а не искать по вики наугад.



    """



    t = (text or "").lower()

    # «помогите» в цитате про прошлый чат — не просьба к боту.
    if _is_chat_meta_discussion(text):
        return False

    if not any(k in t for k in ("помогите", "спасите", "help", "памагити", "спаситипамагити")):



        return False



    # если есть код ошибки или модель/принтер или тех. тема — это уже конкретика



    if _is_error_code_query(text) or _printer_mentioned(text) or _topic_needs_printer_model(text):



        return False



    return True











def _model_slug_hints(text: str) -> frozenset[str]:



    """Подстроки пути вики (латиница), по которым отличают линейки принтеров."""



    out: set[str] = set()



    tl = text.lower()



    combo = "combo" in tl or "комбо" in tl



    # Kobra 3 Max — до ветки «Kobra 3», иначе спутать с обычной тройкой



    is_kobra_3_max = bool(re.search(r"kobra\s*3\s*max\b", tl) or "kobra-3-max" in tl)



    if is_kobra_3_max:



        if combo:



            out.add("kobra-max-combo")



            out.add("kobra-max")



        else:



            out.add("kobra-max")



    elif re.search(r"kobra\s*max\b", tl) or "kobra-max" in tl:



        if combo:



            out.add("kobra-max-combo")



            out.add("kobra-max")



        else:



            out.add("kobra-max")







    is_kobra_s1 = bool(



        re.search(r"kobra\s*s\s*1\b", tl)



        or re.search(r"kobra\s*s1\b", tl)



        or "kobra-s1" in tl



        or re.search(r"кобра\s*s\s*1\b", tl)



        or re.search(r"кобра\s*s1\b", tl)



    )



    if is_kobra_s1:



        if combo or "kobra-s1-combo" in tl or "комбо" in tl:



            out.add("kobra-s1-combo")



            out.add("kobra-s1")  # тот же корпус; путь вики часто с суффиксом -combo



        else:



            out.add("kobra-s1")



            # Большинство гайдов S1 (подача, заторы) лежат в ветке -combo.



            out.add("kobra-s1-combo")



    if (re.search(r"kobra\s*3\b", tl) or "kobra-3" in tl or re.search(r"кобра\s*3\b", tl)) and not is_kobra_3_max:



        if combo or "kobra-3-combo" in tl:



            out.add("kobra-3-combo")



            out.add("kobra-3")



        else:



            out.add("kobra-3")



    if re.search(r"kobra\s*2\b", tl) or "kobra-2" in tl or re.search(r"кобра\s*2\b", tl):



        out.add("kobra-2")



    if re.search(r"kobra\s*go\b", tl) or "kobra-go" in tl:



        out.add("kobra-go")



    if re.search(r"kobra\s*neo\b", tl) or "kobra-neo" in tl:



        out.add("kobra-neo")



    if re.search(r"\bvyper\b", tl):



        out.add("vyper")



    if re.search(r"\bchiron\b", tl):



        out.add("chiron")



    if re.search(r"\bphoton\b", tl):



        out.add("photon")



    return frozenset(out)












def _topic_is_marketplace_commerce_intent(text: str | None) -> bool:
    """Продажа на WB/Ozon, ТН ВЭД готовых моделей — не тема вики Anycubic."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Таможенная классификация / коды для маркетплейса
    if re.search(r"\b(?:тн\s*вэд|тнвэд|hs\s*code|код\s*тн|вэд\s*код)\w*\b", t):
        return True
    marketplace = bool(
        re.search(
            r"\b(?:"
            r"wb|вб|wildberries|озон|ozon|яндекс\.?\s*маркет|market\.yandex|"
            r"маркетплейс|marketplace"
            r")\b",
            t,
        )
    )
    selling = bool(
        re.search(
            r"\b(?:"
            r"прода[еёюя]|продав|выставля|торгую|листинг|"
            r"кто\s+прода|есть\s+кто\s+прода"
            r")\w*\b",
            t,
        )
    )
    printed_goods = bool(
        re.search(
            r"\b(?:"
            r"напечатан\w*|печатн\w*\s+модел|готов\w*\s+издел|"
            r"3d\s*[-]?\s*print\w*\s+model|printed\s+model"
            r")\w*\b",
            t,
        )
    )
    if marketplace and (selling or printed_goods):
        return True
    return False



def _topic_is_firmware_update_intent(text: str | None) -> bool:
    """Установка/обновление прошивки — не страницы /error-codes/."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _is_error_code_query(text):
        return False
    if not re.search(r"\b(?:прошив|фирмвар|firmware)\w*\b", t):
        return False
    # «Актуально для прошивки 2.7.x» при настройке стола — не запрос на прошивку.
    if re.search(r"\bактуаль\w*\b", t):
        if not re.search(
            r"\b(?:обнов|установ|залив|став\w*|update|flash|прошить)\w*\b",
            t,
        ):
            return False
    return bool(
        re.search(
            r"\b(?:"
            r"став|обнов|установ|залив|апдейт|update|flash|прошить|"
            r"прилетел|вышл|вышла|новая|новую|верси|version|"
            r"можно\s+ли|стоит\s+ли|надо\s+ли|нужно\s+ли"
            r")\w*\b",
            t,
        )
    )


def _topic_is_filament_material_choice_intent(text: str | None) -> bool:
    """Какой пластик/TPU/фирму взять — не замена сопла и не подача филамента."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # WB/ТН ВЭД с «пластиком» — не выбор филамента для печати
    if _topic_is_marketplace_commerce_intent(text):
        return False
    if _topic_is_filament_feed_intent(text):
        return False
    if re.search(r"\b(?:замен|поменя|смени|установ|replace|remov|disassembl)\w*\b", t):
        return False
    has_material = bool(
        re.search(
            r"\b(?:тпу|tpu|пластик|филамент|filament|petg|pla|abs|nylon|нейлон|гибк)\w*\b",
            t,
        )
    )
    if not has_material:
        return False
    wants_choice = bool(
        re.search(
            r"\b(?:какой|какая|какое|какие|что\s+взять|что\s+лучше|посовет|подскаж|рекоменд|"
            r"какую\s+фирм|бренд|марк[ау]|which|what\s+filament|brand)\w*\b",
            t,
        )
    )
    stock_nozzle_ctx = bool(re.search(r"\bродн\w*\s+сопл|\bstock\s+nozzle\b", t))
    return wants_choice or stock_nozzle_ctx


def _topic_is_filament_slicing_settings_intent(text: str | None) -> bool:
    """Параметры нарезки/печати под материал (PETG, TPU) — не уточнение модели принтера."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _topic_is_marketplace_commerce_intent(text):
        return False
    if _topic_is_filament_feed_intent(text):
        return False
    has_material = bool(
        re.search(
            r"\b(?:тпу|tpu|петг|petg|пла|pla|abs|абс|nylon|нейлон|пластик|филамент|filament)\w*\b",
            t,
        )
    )
    if not has_material:
        return False
    slicing_ctx = bool(
        re.search(
            r"\b(?:нарезк|слайс|slic|мост|bridge|поток|flow|поддержк|support|связующ|"
            r"interface|скорост|температур|охлажд|retraction|ретракт|шов|infill|заполн)\w*\b",
            t,
        )
    )
    layer_in_slicing = bool(
        re.search(r"\bслой\w*\b", t)
        and re.search(r"\b(?:нарезк|слайс|slic|мост|поддержк|support|связующ|поток)\w*\b", t)
    )
    return slicing_ctx or layer_in_slicing


def _topic_is_slicer_vertical_hole_intent(text: str | None) -> bool:
    """Отверстия в вертикальных стенках: слайсер vs моделирование «каплей» — не quick start."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\b", t):
        if not re.search(r"\b(?:слайс\w*|slicer)\b", t) and "слайсер" not in t:
            return False
    slicer_ctx = bool(re.search(r"\b(?:слайсер\w*|slicer|нарезк\w*|слайс\w*)\b", t))
    hole_ctx = bool(
        re.search(r"\b(?:отверст\w*|дыр\w*|hole)\b", t)
        or (re.search(r"\bстенк\w*\b", t) and re.search(r"\bвертикальн\w*\b", t))
    )
    fix_ctx = bool(
        re.search(r"\b(?:сплющ\w*|деформ\w*|овал\w*|капл\w*|dogbone|teardrop)\b", t)
        or re.search(r"\b(?:почин\w*|исправ\w*|модел\w*)\b", t)
    )
    return slicer_ctx and hole_ctx and fix_ctx


def _topic_is_multicolor_firmware_intent(text: str | None) -> bool:
    """Сравнение прошивок под многоцветную печать — FDM Combo, не resin."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not re.search(r"\b(?:прошив|firmware|firmwar)\w*\b", t):
        return False
    if re.search(
        r"\b(?:цветн|многоцвет|multi[\s-]?color|multicolor|ace\s*pro|"
        r"4[\s-]?in[\s-]?1|four[\s-]?in[\s-]?one|8[\s-]?color|eight[\s-]?color)\w*\b",
        t,
    ):
        return True
    # «цветная печать» без отдельного слова «цветн»
    return "цвет" in t and bool(re.search(r"\bпечат\w*\b", t))


def _topic_is_filament_feed_intent(text: str | None) -> bool:



    """



    Подача филамента / экструдер крутит, но не тянет, срывы шестерни, затор.



    Не путать с осью Z/X/Y и USB-драйверами.



    """



    if not text:



        return False



    tl = text.lower()



    has_filament = any(



        k in tl



        for k in (



            "филамент",



            "filament",



            "подач",



            "feeding",



            "feed ",



            "экструдер",



            "extruder",



            "шестерн",



            "gear",



            "ролик",



            "idler",



        )



    )



    has_problem = any(



        k in tl



        for k in (



            "не пода",



            "не тян",



            "не идёт",



            "не идет",



            "перестал",



            "срыв",



            "slip",



            "skipping",



            "застрял",



            "jam",



            "clog",



            "затор",



            "block",



            "не крут",



        )



    )



    has_feed_motor = ("мотор" in tl or "motor" in tl or "шагов" in tl or "stepper" in tl) and any(



        k in tl



        for k in (



            "подач",



            "филамент",



            "экструдер",



            "feed",



            "extruder",



            "шестерн",



            "filament",



        )



    )



    return (has_filament and has_problem) or has_feed_motor



