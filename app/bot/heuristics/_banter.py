"""Болтовня/chatter: функции определения нерелевантных сообщений чата."""
from __future__ import annotations

import re

from app.bot.heuristics._base import (
    _ace_mentioned,
    _extract_error_code,
    _is_error_code_query,
    _mentions_competitor_printer,
    _model_slug_hints,
    _printer_mentioned,
)


_MARKETPLACE_HOST_RE = re.compile(
    r"(?i)\b("
    r"aliexpress|ali\.click|amazon\.|ozon\.|wildberries|market\.yandex|"
    r"tmall|taobao|banggood|gearbest|joom\.|ebay\.|"
    r"avito\.|youla\.|drom\.|farpost\."
    r")\b"
)

# Допрос автора проблемы о его прошлых параметрах: «температура какая была?».
_PEER_PAST_PARAM_NOUN_RE = re.compile(
    r"\b(?:температур\w*|градус\w*|скорост\w*|поток\w*|обдув\w*|ретракт\w*|"
    r"сопл\w*|стол\w*|пластик\w*|филамент\w*|материал\w*|слой|слоя|слоёв|слоев|"
    r"заполнен\w*|настройк\w*|профил\w*)\b",
    re.I | re.UNICODE,
)
_PEER_PAST_QUERY_RE = re.compile(
    r"\b(?:как(?:ая|ой|ие|ое|ую)|сколько|что)\b(?:\W+\w+){0,4}?\W+(?:был\w*|стоял\w*|ставил\w*)\b"
    r"|\b(?:был\w*|стоял\w*|ставил\w*)\b(?:\W+\w+){0,3}?\W+(?:как(?:ая|ой|ие|ое|ую)|сколько)\b",
    re.I | re.UNICODE,
)

_PEER_ACTION_PAST_RE = re.compile(
    r"\b(?:"
    r"ставил\w*|поставил\w*|"
    r"замер\w*л\w*|замерял\w*|мерял\w*|мерил\w*|измерял\w*|измерил\w*|"
    r"менял\w*|поменял\w*|сменил\w*|заменял\w*|заменил\w*|"
    r"пробовал\w*|попробовал\w*|пытал\w*|"
    r"обновлял\w*|обновил\w*|прошивал\w*|перепрошивал\w*|"
    r"калибровал\w*|откалибровал\w*|"
    r"проверял\w*|проверил\w*|"
    r"смотрел\w*|глядел\w*|"
    r"делал\w*|сделал\w*|"
    r"брал\w*|заказывал\w*|заказал\w*|покупал\w*|"
    r"чистил\w*|почистил\w*|сушил\w*|высушил\w*"
    r")\b",
    re.I | re.UNICODE,
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

# «лучше подождать / спросить опытного» — пользователь сам отсылает к людям, не к боту.
_DEFER_TO_EXPERT_RE = re.compile(
    r"\b(?:подожд\w*|дожд\w*|дожид\w*|спрос\w*|послуша\w*|пусть\s+(?:скаж\w*|ответ\w*|подскаж\w*))\b"
    r"(?:\W+\w+){0,3}\W+"
    r"(?:опытн\w*|знающ\w*|спец\w*|профи|мастер\w*|бывал\w*|тех,\s*кто)",
    re.I | re.UNICODE,
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


def _is_cross_chat_tip_sharing(text: str) -> bool:
    """«В чате по чиди увидел инфу, что…» — пересказ из другого чата, не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|не\s+работает|что\s+делать|"
        r"как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|решить))\b",
        t,
    ):
        return False
    other_chat = bool(
        re.search(r"\b(?:в\s+чате|в\s+чат\w*|из\s+чата)\b", t)
        and re.search(r"\b(?:по\s+)?(?:чиди|чити|chitu|chitubox|orca|орка)\b", t)
    )
    relay = bool(
        re.search(r"\b(?:увидел\w*|увил\w*|услышал\w*|наш\w*|прочитал\w*|инфу|информац)\b", t)
        or (re.search(r"\bчто\b", t) and other_chat)
    )
    return other_chat and relay


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


def _is_chat_past_incident_recollection(text: str) -> bool:
    """«Тут же было в чате как-то, кобра глюкнула когда свет отрубили» — байка из чата, не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|что\s+делать|не\s+работает|"
        r"как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|решить|подключ|замен))\b",
        t,
    ):
        return False
    chat_ref = bool(re.search(r"\bв\s+чат\w*\b", t))
    recollection = bool(
        re.search(
            r"\b(?:было|как[\s-]?то|помн\w*|обсужда\w*|рассказыва\w*|писа\w*|"
            r"уже\s+было|кто[\s-]?то\s+(?:писа|расск))\w*\b",
            t,
        )
    )
    return chat_ref and recollection


def _is_print_quality_meta_curiosity(text: str) -> bool:
    """«Как они так печатают / на видео кажется» — любопытство в чате, не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|не\s+работает|что\s+делать|"
        r"как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|решить))\b",
        t,
    ):
        return False
    # «Как они/он/она так печатают» — наблюдение над чужой печатью (мн. и ед. число)
    others_print = bool(
        re.search(r"\b(?:как\s+он\w*|как\s+она|как\s+они|они\s+так|у\s+них)\b", t)
        and re.search(r"\bпечата\w*\b", t)
    )
    # «Даже интересно как он первый слой без шайб печатает 😁» — ирония без вопроса
    curious_other = bool(
        re.search(r"\b(?:даже\s+)?интересно\s+как\b", t)
        and re.search(r"\bпечата\w*\b", t)
        and "?" not in text
    )
    not_like_3d = bool(
        re.search(r"\b(?:не\s+похож\w*|не\s+выглядит)\b", t)
        and re.search(r"\b(?:3\s*d|3д|три\s*д)\s*печат", t)
    )
    video_doubt = bool(re.search(r"\b(?:на\s+видео|в\s+ролике)\s+кажется\b", t))
    lingering = bool(re.search(r"\b(?:давно\s+)?возникает\s+вопрос\b", t))
    if curious_other:
        return True
    if others_print and (not_like_3d or video_doubt):
        return True
    if lingering and others_print and ("?" in text or video_doubt):
        return True
    return False


def _is_ace_chitu_hardware_observation(text: str) -> bool:
    """ChiTu Box / ACE: «на катушку движок», «как я понял» — не гайд по замене филамента."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|не\s+работает|что\s+делать|"
        r"как\s+(?:настро|замен|почин|исправ|сделать|подключ))\b",
        t,
    ):
        return False
    station = bool(
        re.search(r"\b(?:чиди|чити|chitu|chitubox|аська\w*|аськ\w*|ace)\b", t)
    )
    if not station:
        return False
    spool_motor = bool(
        re.search(r"\bкатушк\w*\b", t)
        and re.search(r"\b(?:движок|мотор|экструдер|feed)\w*\b", t)
    )
    understood = bool(re.search(r"\bкак\s+я\s+понял\b", t))
    also = bool(re.search(r"\b(?:тоже|так\s+же|аналогично)\b", t))
    if spool_motor:
        return True
    if understood and also:
        return True
    return understood and re.search(r"\b(?:чиди|аська|ace)\b", t)


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
    # «я думал … а сейчас вижу что» — коррекция предположения в треде.
    if re.search(r"\bя\s+думал\b", t) and re.search(r"\b(?:а\s+)?сейчас\s+вижу\b", t):
        return True
    # «с партийными печать не интересно как-то становится 😂 скучно как-то» — мнение о потере интереса.
    boredom_opinion = bool(
        re.search(r"\b(?:не\s*интересно|неинтересно|скучно|надоело|надоел\w*)\b", t)
        and re.search(r"\b(?:печат|принтер|3d|3д)\w*\b", t)
        and re.search(r"\b(?:как-то|становится|стало|как\s+то)\b", t)
    )
    if boredom_opinion:
        return True
    # «автокад это треш, рисую потому что знаю инструменты, хочу компас скачать» —
    # мнение о CAD-софте для 3D-моделирования, не запрос к вики.
    cad_software = bool(
        re.search(
            r"\b(?:"
            r"автокад|autocad|"
            r"компас(?:[\s-]*3[дd])?|kompas|"
            r"solidworks|солидворкс|"
            r"fusion(?:\s*360)?|"
            r"blender|блендер|"
            r"tinkercad|тинкеркад|"
            r"freecad|"
            r"sketchup|скетчап|"
            r"rhino(?:ceros)?|райно|"
            r"zbrush|збраш|"
            r"plasticity|"
            r"onshape|"
            r"inventor"
            r")\b",
            t,
        )
    )
    if cad_software:
        modeling_ctx = bool(
            re.search(
                r"\b(?:моделир\w*|чертит\w*|чертить|рисую|рисова\w*|"
                r"3[дd]\s*моделир|для\s+печат\w*|под\s+(?:3[дd]\s*)?печат\w*|"
                r"знаю\s+(?:все\s+)?инструмент)\b",
                t,
            )
        )
        opinion_marker = bool(
            re.search(
                r"\b(?:треш|трэш|удобн\w*|неудобн\w*|нравит\w*|скучн\w*|"
                r"хочу\s+(?:скача|поставит|установ|перейти|попроб)\w*|"
                r"люблю|ненавижу|привык\w*|"
                r"куча\s+(?:лишн\w*\s+)?движен\w*|лишн\w*\s+движен)\w*\b",
                t,
            )
        )
        if modeling_ctx and opinion_marker:
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
    # «Как через экструдер пропустили» — прош. время мн.ч. = вопрос о чужом действии в треде.
    thread_past_action = bool(
        re.search(r"\bкак\b", t)
        and re.search(r"\bчерез\s+\w+\b", t)
        and re.search(r"\b\w+(?:ил[иа]|пустили|вели|провели|вставили)\b", t)
        and len(t.split()) <= 7
    )
    if thread_past_action:
        return True
    # «меня удивляет / поражает как по-разному...» — наблюдение, не запрос к вики
    wonder = bool(
        re.search(r"\b(?:меня\s+)?(?:удивляет|поражает|удивил|поразил)\s+как\b", t)
    )
    if wonder:
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
    # «зачем для кобры orca? стандартный слайсер огонь» — мнение, не quick start.
    rhetorical = bool(
        re.search(r"\bзачем\s+(?:для|у)\s+кобр\w*\b", t) and re.search(r"\b(?:orca|орка)\b", t)
    )
    praise = bool(
        re.search(r"\b(?:огонь|класс|топ|зачёт|зашло|норм|крут)\b", t)
        and re.search(r"\b(?:слайсер\w*|slicer|orca|орка)\b", t)
    )
    if rhetorical or (praise and re.search(r"\bкобр\w*\b", t)):
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
    # «говорит многоцвет не печатает, зачем ему две аськи?» — сарказм в треде.
    relay_claim = bool(
        re.search(r"\b(?:говорит|говорят|сказал\w*|утвержда\w*)\b", t)
        and re.search(r"\b(?:не\s+)?печата\w*\b", t)
    )
    rhetorical_why_other = bool(re.search(r"\b(?:вот\s+)?зачем\s+(?:ему|ей|им|ем)\b", t))
    ace_multi = bool(
        re.search(r"\b(?:аська\w*|аськ\w*|ace)\b", t)
        or re.search(r"\b(?:многоцвет|multi[\s-]?color)\w*\b", t)
    )
    if relay_claim and rhetorical_why_other and ace_multi:
        return True
    # «Иначе нахрена они кастрировали новые модели на поддержку первой аськи?
    #  Ведь технически это одинаковые устройства» — риторическая претензия к вендору.
    vulgar_rhetoric = bool(
        re.search(r"\b(?:нахрена|на\s*хрена|на\s*кой|какого\s+(?:хрена|ч[ёе]рта|лешего))\b", t)
    )
    castrate_slang = bool(re.search(r"\bкастрир\w*\b", t))
    maker_decision = bool(
        re.search(r"\bон[иа]\b", t)
        and re.search(
            r"\b(?:модел\w*|устройств\w*|аська\w*|аськ\w*|ace|поддержк\w*|прошивк\w*)\b",
            t,
        )
    )
    assertion_same = bool(
        re.search(r"\bведь\b", t)
        and re.search(r"\b(?:одинаков\w*|то\s+же\s+самое|так\s+же|идентичн\w*)\b", t)
    )
    if (vulgar_rhetoric or castrate_slang) and (maker_decision or assertion_same):
        return True
    return False


def _is_multicolor_preset_banter(text: str) -> bool:
    """«кто-то наигрался с быстрым многоцветом» / пресет — комментарий, не гайд."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:настро|сделать|включ)|что\s+делать|не\s+работает)\b",
        t,
    ):
        return False
    multicolor = bool(
        re.search(r"\b(?:многоцвет|multi[\s-]?color|быстр\w*\s+многоцвет|цветн\w*\s+печат)\w*\b", t)
    )
    play = bool(re.search(r"\b(?:наиграл\w*|поиграл\w*|поэкспериментир\w*|поигра\w*)\b", t))
    third_party = bool(re.search(r"\b(?:кто[-\s]?то|ктото|кто\s+нибудь|какой[-\s]?то)\b", t))
    preset_share = bool(
        re.search(r"\b(?:сэам\w*|slicemaker|слайсмейк\w*)\b", t) and re.search(r"\b\d{3,6}\b", t)
    )
    if multicolor and (play or third_party):
        return True
    if preset_share and multicolor:
        return True
    return False


def _is_conversational_skepticism(text: str) -> bool:
    """Скепсис в треде — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # «не факт что» — разговорный скептицизм, всегда в контексте обсуждения.
    if re.search(r"\bне\s+факт\s*,?\s+что\b", t):
        return True
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
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if "?" in text and re.search(r"\b(?:есть\s+)?(?:ещё\s+)?вопрос\b", t):
        return False
    if "?" in text:
        return False
    if re.search(r"\bчто\s+(?:делать|значит|не\s+так|не\s+работает)\b", t):
        return False
    printing_action = bool(
        re.search(
            r"\b(?:запускаю|запустил|запустился|запустилась|начинаю|начал|печатаю|пошл[ао]\s+печать|калибрую)\b",
            t,
        )
    )
    layer_ctx = bool(re.search(r"\b(?:первый\s+слой|слой|печат|калибр|многоцвет)\b", t))
    casual_start = bool(re.search(r"^(?:ну\s+что|ну\s*,|поехали|погнали)\b", t))
    # «посмотрим на что способна / что из этого выйдет» — эмоциональный старт, не вопрос к боту
    lets_see = bool(
        re.search(r"\b(?:посмотрим|поглядим|интересно\s+что\s+(?:получится|выйдет|будет))\b", t)
        and re.search(r"\b(?:способн\w*|получится|выйдет|будет|эта\s+лошадк\w*)\b", t)
    )
    if printing_action and layer_ctx:
        return True
    if casual_start and (printing_action or layer_ctx):
        return True
    if printing_action and lets_see:
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


def _is_other_printer_experience_story(text: str) -> bool:
    """Личная история про чужой принтер (Bambu/P2S) — не гайд Kobra по экструдеру."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:разобр|замен|почин|настро)|что\s+делать|не\s+работает)\b",
        t,
    ):
        return False
    if not _mentions_competitor_printer(text):
        if not (
            re.search(r"\bэкструдер\w*\b", t)
            and re.search(r"\b(?:нажрал\w*|трезв\w*|другое\s+дело)\b", t)
            and not _printer_mentioned(text)
        ):
            return False
    story = bool(
        re.search(r"\b(?:мне\s+)?когда\s+.{0,40}\b(?:первый\s+раз|пришлось)\b", t)
        or re.search(r"\b(?:нажрал\w*|трезв\w*|рука\s+не\s+поднял\w*)\b", t)
        or re.search(r"\bдругое\s+дело\b", t)
    )
    maint = bool(
        re.search(r"\bэкструдер\w*\b", t) and re.search(r"\b(?:разобр\w*|разбира\w*)\b", t)
    )
    return story and (maint or _mentions_competitor_printer(text))


def _is_other_printer_maintenance_story(text: str) -> bool:
    """Личная история про Bambu/P2S и разбор экструдера — не гайд Kobra."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:разобр|замен|почин|настро)|что\s+делать|не\s+работает)\b",
        t,
    ):
        return False
    if _printer_mentioned(text):
        return False
    other_brand = bool(
        re.search(
            r"\b(?:"
            r"bambu|бамбук|п2с|p2s|x1c|x1\s*c|"
            r"prusa|пруса|creality|криалити|flashforge|raise3d"
            r")\b",
            t,
        )
    )
    extruder_story = bool(
        re.search(r"\bэкструдер\w*\b", t)
        and re.search(r"\b(?:разобр\w*|пришлось|первый\s+раз|нажрал\w*|трезв\w*)\b", t)
    )
    casual = bool(re.search(r"\b(?:другое\s+дело|рука\s+не\s+поднял\w*)\b", t))
    filament_ooze_story = bool(
        (other_brand or re.search(r"\b(?:есун|esun)\b", t))
        and re.search(r"\b(?:купил\w*|пришлось\s+купить)\b", t)
        and re.search(
            r"\b(?:"
            r"брак|течет|текёт|капл\w*|портит\s+печать|"
            r"не\s+хотел\s+печатать|техподдержк\w*|ориг\w*"
            r")\b",
            t,
        )
    )
    if other_brand and (extruder_story or casual):
        return True
    if extruder_story and casual and re.search(r"\bнажрал\w*\b", t):
        return True
    if filament_ooze_story:
        return True
    return False


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


def _is_multicolor_experience_opinion(text: str) -> bool:
    """«на иксе тише смена цвета, кобра 3 меняет цвета как калаш» — мнение/сравнение, не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\bкак\s+(?:настро|сделать|включ|поменять|менять|переключ|откалибр|задать)\b", t
    ):
        return False
    color_ctx = bool(
        re.search(
            r"\b(?:смен\w*\s+цвет\w*|мен\w*\s+цвет\w*|переключ\w*\s+цвет\w*|"
            r"многоцвет\w*|многоцветн\w*)\b",
            t,
        )
    )
    if not color_ctx:
        return False
    opinion = bool(
        re.search(
            r"\b(?:нрав\w*|удобн\w*|неудобн\w*|тих\w*|тише|громк\w*|громче|"
            r"бесит|раздража\w*|круто|класс\w*|норм\b|кайф\w*)\b",
            t,
        )
        or re.search(r"\b(?:как[\s-]?будто|какбудто|словно|типа\s+как)\b", t)
        or re.search(r"\bпротестир\w*\b", t)
    )
    if opinion:
        return True
    # «отхода меньше/скорость быстрей чем а1/bambu» — сравнение с конкурентом, не запрос к вики
    competitor_cmp = bool(
        re.search(r"\b(?:а1\b|a1\b|бамбу|bambu|p2s|п2с)\b", t)
        and re.search(r"\b(?:меньше|больше|быстрей|быстрее|медленней|медленнее)\b", t)
    )
    return competitor_cmp


def _is_joke_printer_model_clarify_reply(text: str | None) -> bool:
    """Шуточный ответ на «уточни модель» (фанфик Kobra X Max и т.п.) — не поиск в вики."""
    if not text or not text.strip():
        return False
    if _model_slug_hints(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:"
        r"kobra\s*x\s*max|"
        r"\d{1,3}[\s-]*color|"
        r"giga\s*blaster|brain\s*depilation|depilation|"
        r"\b5g\b|gt\s*neo|turbo\s*custom"
        r")\b",
        t,
    ):
        return True
    words = t.split()
    if len(words) >= 8 and re.search(r"\banycubic\b", t) and re.search(r"\bkobra\b", t):
        if re.search(r"\b(?:turbo|neo|custom|blaster|color|max)\b", t):
            return True
    return False


def _is_third_party_filament_brand_chat(text: str) -> bool:
    """Bambu/eSUN и т.п.: мнение о пластике, PETG HF — не оглавление Filament & Resin."""
    if not text or not text.strip():
        return False
    if _is_error_code_query(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    third_brand = bool(
        re.search(
            r"\b(?:"
            r"bambu\s*lab|бамбул\w*|бамбу\w*|"
            r"esun|e\s*sun|sunlu|eryone|polymaker|prusament"
            r")\b",
            t,
        )
    )
    if not third_brand:
        return False
    opinion = bool(
        re.search(r"\b(?:хорош\w*|плох\w*|качеств\w*|стоит\s+ли|бер[её]те)\w*\b", t)
        or re.search(r"\bведь\s+хорош", t)
    )
    hf_speed = bool(
        re.search(r"\bpetg\s*hf\b", t)
        and re.search(r"\b(?:скорост|speed|быстр|высок|надо\s+ли|нужно\s+ли)\w*\b", t)
    )
    return opinion or hf_speed or ("?" in text and re.search(r"\bпластик\w*\b", t))


def _is_filament_tolerance_banter(text: str) -> bool:
    """«Одному богу известно какой зазор» у втулки — реплика в треде, не filament-guide."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:настро|сделать|убрать|исправ|замен))\b",
        t,
    ):
        return False
    idiom = bool(
        re.search(
            r"\b(?:"
            r"одному\s+богу\s+известно|"
            r"бог\s+его\s+знает|"
            r"кто\s+его\s+знает|"
            r"хз\s+какой|"
            r"никто\s+не\s+знает"
            r")\b",
            t,
        )
    )
    clearance = bool(re.search(r"\b(?:зазор\w*|люфт\w*|backlash)\b", t))
    mech = bool(re.search(r"\b(?:втулк\w*|подшипник|bearing|bushing)\b", t))
    filament = bool(re.search(r"\b(?:пластик|филамент|filament|пруток|нит)\w*\b", t))
    return idiom and clearance and mech and filament


def _is_filament_brand_quality_opinion(text: str) -> bool:
    """Мнение о качестве стороннего пластика / возня с катушкой в ACE — не вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    if _is_error_code_query(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|не\s+печатает|не\s+работает|что\s+делать|"
        r"как\s+(?:настро|почин|исправ|сделать|замен|подключ))\b",
        t,
    ):
        return False
    about_quality = bool(
        re.search(r"\bкачеств\w*\b", t)
        and re.search(
            r"\b(?:пластик|филамент|filament|eryone|катушк|spool|brand|бренд)\w*\b",
            t,
        )
    )
    return about_quality


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
    # «куплю X, а на следующий день комбо выйдет» — шутка о тайминге покупки.
    timing_joke = bool(
        re.search(r"\bкупл\w*\b", t)
        and re.search(r"\b(?:выйдет|появится|выпустят|анонс)\w*\b", t)
        and re.search(r"\b(?:следующий\s+день|завтра|через\s+день|как\s+обычно|как\s+всегда|у\s+меня\s+всегда)\b", t)
    )
    if timing_joke:
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


def _is_price_hyperbole_banter(text: str) -> bool:
    """Шутка-гипербола о цене («аська как крыло от самолёта будет стоить») — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\bсколько\s+стоит\b", t):
        return False
    price = bool(
        re.search(r"\b(?:сто[ие](?:т|ть|л[аои]?)|стоить|цен[аеуы]|по\s+цене|обойд[её]тся)\b", t)
    )
    hyperbole_noun = bool(
        re.search(
            r"\bкак\s+(?:крыло|самол[её]т\w*|космолёт\w*|космолет\w*|вертол[её]т\w*|"
            r"чугунн\w*\s+мост\w*|квартир\w*)\b",
            t,
        )
    )
    speculative = bool(
        re.search(r"\bкак\b", t)
        and re.search(r"\b(?:наверное|наверно|поди|видимо|небось)\b", t)
    )
    return price and (hyperbole_noun or speculative)


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
    # «Я так понял кобра x у вас есть?» — вопрос о наличии принтера у собеседника
    owns_question = bool(
        re.search(r"\b(?:у\s+(?:вас|тебя))\s+(?:есть|имеется|нет|была|был|было)\b", t)
        and not re.search(r"\b(?:инструкц|гайд|ссылк|вики|проблем|ошибк)\b", t)
    )
    if owns_question and printer_ctx:
        return True
    # «Икса ещё одного возьмёшь с аськой?» — вопрос о покупке принтера к собеседнику
    buy_question = bool(
        re.search(r"\b(?:возьм[её]шь|возьм[её]те|берёшь|берешь|купишь|купите|закажешь|закажете)\b", t)
    )
    if buy_question and printer_ctx:
        return True
    # «и она теперь многоцветная?» — вопрос о состоянии принтера у собеседника
    state_change = bool(
        re.search(r"\b(?:и|а|ну)\s+(?:он[ао]?|их)\s+теперь\b", t)
        or (re.search(r"\bтеперь\b", t) and re.search(r"\b(?:многоцвет\w*|работает|пашет|включ\w*|стала)\b", t))
    )
    if state_change and printer_ctx:
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


def _is_peer_diagnostic_interrogation(text: str) -> bool:
    """«Температура какая была?» — допрос автора о его прошлых настройках, не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба к боту настроить/починить/объяснить — не отсекаем.
    if re.search(
        r"\b(?:как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|подключ|замен|выставить|задать|ставить|поставить)|"
        r"что\s+делать|почему|помогите|подскаж|какой\s+должн|должн\w*\s+быть|нужн\w*\s+(?:ставить|выставить))\b",
        t,
    ):
        return False
    return bool(_PEER_PAST_PARAM_NOUN_RE.search(t) and _PEER_PAST_QUERY_RE.search(t))


def _is_peer_action_experience_question(text: str) -> bool:
    """«А ты замерял резонанс?» / «Прошивку 2.7.2.7 ставили?» — спрашивают собеседников об их опыте, не бота."""
    if not text or not text.strip() or "?" not in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба о помощи / инструкции / собственная проблема — это вопрос к боту.
    if re.search(
        r"\b(?:"
        r"как\s+(?:настро|откалибр|калибр|почин|исправ|сделать|убрать|подключ|замен|поставить|ставить|выставить|задать|обнов|прошить|провер|измер)|"
        r"что\s+делать|почему|зачем|"
        r"нужн\w*\s+ли|стоит\s+ли|надо\s+ли|можно\s+ли|"
        r"как(?:ую|ой|ая|ие|ое)\s+(?:\w+\s+){0,2}(?:ставить|выбрать|брать|прошив)|"
        r"помогите|помоги|подскаж\w*|"
        r"у\s+меня|не\s+могу|не\s+получ\w*|не\s+работает|не\s+знаю|не\s+пойму|не\s+понимаю"
        r")\b",
        t,
    ):
        return False
    if not _PEER_ACTION_PAST_RE.search(t):
        return False
    # Явное обращение к собеседнику.
    second_person = bool(
        re.search(r"\b(?:а\s+ты|ты|вы|тебе|вам|у\s+тебя|у\s+вас|твой|тво[яёе]|ваш\w*)\b", t)
    )
    # Безличное короткое «X-ли?» — обращено к группе («ставили? пробовали?»).
    bare_group = len(t.split()) <= 5
    # «кто-нибудь ставил/пробовал/обновлял?» — вопрос к группе об опыте (любой длины).
    group_query = bool(
        re.search(r"\b(?:кто[\s-]?нибудь|ктонибудь|кто[\s-]?то|кто[\s-]?либо|никто)\b", t)
    )
    return second_person or bare_group or group_query


def _is_filament_feed_test_probe(text: str) -> bool:
    """«Если дать подачу филамента, пластик идёт ровно?» — диагностический вопрос соседу, не к вики."""
    if not text or not text.strip() or "?" not in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба к боту настроить/починить/объяснить — не отсекаем.
    if re.search(
        r"\b(?:как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|подключ|замен|выставить|задать)|"
        r"что\s+делать|почему|зачем|помогите|подскаж|где\s+(?:найти|взять))\b",
        t,
    ):
        return False
    cond = bool(
        re.search(r"\bесли\b", t)
        and re.search(
            r"(?:подач\w*|продав\w*|выдав\w*|прогна\w*|прокач\w*|"
            r"дать\b(?:\W+\w+){0,3}\W+(?:филамент|пластик)|"
            r"пода(?:ть|ю|ем|ёт)\b)",
            t,
        )
    )
    behavior = bool(re.search(r"\b(?:равномерн\w*|ровн\w*)", t))
    return cond and behavior


def _is_vague_filament_thread_reference(text: str) -> bool:
    """«а пластик такого план какой лучше» — ссылка на контекст треда, конкретного материала нет."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not re.search(r"\bтакого\s+(?:же\s+)?план\w*\b", t):
        return False
    if not re.search(r"\b(?:пластик|филамент|filament)\w*\b", t):
        return False
    # Конкретный тип материала или бренд — бот может дать содержательный ответ
    if re.search(
        r"\b(?:tpu|тпу|petg|петг|pla|пла|abs|абс|nylon|нейлон|"
        r"esun|есун|bambu|бамбу|eryone|polymaker|sunlu|"
        r"hips|хипс|flex|флекс|asa|аса)\b",
        t,
    ):
        return False
    return (
        bool(
            re.search(r"\b(?:какой|что|какие)\b", t)
            and re.search(r"\b(?:лучше|рекоменд\w*|посовет\w*|взять|брать|купить)\b", t)
        )
        or "?" in text
    )


def _is_bare_competitor_printer_question(text: str) -> bool:
    """«А1 комбо?» — короткий вопрос о принтере конкурента (≤4 слова), не вики-запрос к Кобре."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Только очень короткие сообщения (1–4 слова)
    if len(t.split()) > 4:
        return False
    # Явный запрос инструкции — не отсекаем
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:настро|исправ|почин|замен|подключ)|"
        r"что\s+делать|не\s+работает|ошибка|почему|где\s+(?:найти|взять))\b",
        t,
    ):
        return False
    # Bambu A1 / A1 Combo — Anycubic такой модели не выпускал
    if re.search(r"\b[аa]1\b", t) and re.search(r"\b(?:комбо|combo)\b", t):
        return True
    # Явный конкурент в очень коротком сообщении
    if re.search(
        r"\b(?:bambu|бамбу|бамбук|p2s|п2с|x1c|x1\s*c|prusa|пруса|ender|"
        r"creality|кр[еи]ал[иы]?т[иы]|qidi)\b",
        t,
    ):
        return True
    return False


def _is_competitor_showcase_request(text: str) -> bool:
    """«Можешь показать качество печати креалити?» — просьба показать конкурента, не вопрос к вики Anycubic."""
    if not text or not text.strip():
        return False
    if not _mentions_competitor_printer(text):
        return False
    # Если упомянут и наш принтер (миграция/сравнение с Kobra) — не отсекаем.
    if _printer_mentioned(text):
        return False
    if _is_error_code_query(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба настроить/починить/перейти — не отсекаем.
    if re.search(
        r"\bкак\s+(?:настро|откалибр|почин|исправ|сделать|убрать|подключ|замен|перейти|перенести)\b",
        t,
    ):
        return False
    # Просьба показать / продемонстрировать / сравнить конкурента.
    showcase = bool(
        re.search(
            r"\b(?:покажи\w*|показать|показал\w*|продемонстр\w*|"
            r"скинь\w*|скин\w*|можешь\s+показать|сравн\w*|что\s+скажешь\s+(?:о|про))\b",
            t,
        )
    )
    return showcase


def _is_product_news_announcement(text: str) -> bool:
    """Новостной пресс-релиз об анонсе продукта («Creality представила сушилку SpacePi X4S») — не вопрос к вики."""
    if not text or not text.strip():
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба что-то сделать с новинкой — не отсекаем.
    if re.search(
        r"\bкак\s+(?:настро|подключ|использ\w*|обнов|перейти|перенести|замен)\b",
        t,
    ):
        return False
    announce = bool(
        re.search(
            r"\b(?:представил\w*|анонсир\w*|презентов\w*|"
            r"выпустил\w*|выпустит|выпуска\w*|релизн\w*)\b",
            t,
        )
        or re.search(r"\bпредставл[её]н\w*\b", t)
        or re.search(r"\bновинк\w*\b", t)
    )
    pr_speak = bool(
        re.search(
            r"\b(?:по\s+заявлению\s+компании|ключевые\s+особенност\w*|"
            r"расширя\w*\s+линейк\w*|продолжает\s+расширя\w*|"
            r"анонсирова\w*|намекнул\w*)\b",
            t,
        )
    )
    novelty = bool(
        re.search(r"\b(?:новинк\w*|нов(?:ый|ую|ое|ые|ого|ой|ая))\b", t)
        or re.search(r"\b(?:линейк\w*|модул\w*|устройств\w*)\b", t)
    )
    return announce and (pr_speak or novelty)


def _is_thread_printing_tip(text: str) -> bool:
    """Советы в треде без вопроса — не запрос к боту."""
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    tl = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|что\s+делать|не\s+работает|"
        r"как\s+(?:настро|почин|исправ|сделать|убрать|решить|подключ|замен))\b",
        tl,
    ):
        return False
    if re.search(r"\b(?:ещё|также|тоже)\s+важно\b", tl):
        return True
    if re.search(r"\bя\s+бы\b", tl) and re.search(
        r"\b(?:дал|дала|добавил|добавила|закрыл|закрыла|поставил|поставила|"
        r"убрал|убрала|попробовал|попробовала|начал|начала|оставил|оставила|"
        r"советовал|рекомендовал)\w*\b",
        tl,
    ):
        return True
    if re.search(r"\bв\s+общем-то\b", tl):
        return True
    if re.search(r"\bладно\b", tl) and re.search(r"\bспасибо\b", tl):
        return True
    if re.search(r"\bу\s+меня\s+(?:есть|стоит|имеется|лежат|лежит)\b", tl):
        return True
    return False


def _is_problem_combo_banter(text: str) -> bool:
    """«+ кривая тенза/незатянутая тенза и т.д. вместе с плавающим столом ядрёная смесь».

    Перечисление проблем с выводом «ядрёная/гремучая смесь» — это реплика-согласие
    в треде, а не запрос к вики.
    """
    if not text or not text.strip() or "?" in text:
        return False
    if _message_has_help_intent(text):
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|что\s+делать|как\s+(?:настро|откалибр|почин|исправ|убрать|решить))\w*",
        t,
    ):
        return False
    combo_idiom = bool(
        re.search(r"\b(?:ядр[её]н\w*|гремуч\w*|адск\w*|весёл\w*|весел\w*|та\s+ещё)\s+смес\w*", t)
        or re.search(r"\bвместе\b.{0,40}\bсмес\w*", t)
    )
    enumeration_plus = bool(
        text.strip().startswith("+") and re.search(r"\bи\s*т\.?\s*д\.?", t)
    )
    return combo_idiom or enumeration_plus


def _is_purchase_deliberation_banter(text: str) -> bool:
    """«Думал про комбо-версию, но послушав Васю уже не уверен 😂» — раздумья о покупке.

    Обсуждение, какую версию/модель брать — это болтовня, а не запрос к вики
    (страницы сборки/инструкции тут отвечать не должны).
    """
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба о помощи/инструкции — не трогаем.
    if re.search(
        r"\bкак\s+(?:настро|откалибр|почин|исправ|собрать|подключ|замен|обнов|прошить)\w*",
        t,
    ):
        return False
    purchase_ctx = bool(
        re.search(
            r"\b(?:комбо|combo|верси\w*|версию|обычн\w*\s+верс|"
            r"брать|взять|куплю|купить|покупа\w*|заказ\w*|присматрива\w*)\b",
            t,
        )
    )
    deliberation = bool(
        re.search(
            r"\b(?:"
            r"думал\s+про|думаю\s+про|подумыва\w*|"
            r"не\s+увер\w*|сомнева\w*|склоня\w*|"
            r"решаю|выбираю\s+между|колебл\w*|раздумыва\w*"
            r")\b",
            t,
        )
    )
    return purchase_ctx and deliberation


def _is_hardware_vs_settings_dilemma(text: str) -> bool:
    """«Это техничка или всё-таки настройки?» — диагностический спор в треде.

    Пользователь уже сам провёл диагностику (обслужил, подкрутил, проверил) и
    спрашивает у людей, железо это или софт. Уточнять модель тут бессмысленно —
    вики-страница на такой вопрос «или/или» всё равно не ответит.
    """
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Явная просьба дать инструкцию — не отсекаем.
    if re.search(
        r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\w*",
        t,
    ):
        return False
    hardware = bool(
        re.search(r"\b(?:техничк\w*|желез\w*|механик\w*|аппаратн\w*|по\s+железу)\b", t)
    )
    settings = bool(
        re.search(r"\b(?:настройк\w*|настрой\w*|софт\w*|программн\w*)\b", t)
    )
    dilemma = bool(re.search(r"\b(?:или|либо)\b", t))
    return hardware and settings and dilemma


def _is_relay_to_peer_chatter(text: str) -> bool:
    """«Скинь ему видосы · пусть поймёт · так ему и напиши» — указание переслать кому-то, не вопрос боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # «скинь/дай ссылку» — это всё-таки обращение к боту.
    if re.search(r"\bссыл\w*", t):
        return False
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|замен))\b",
        t,
    ):
        return False
    pust_understand = bool(
        re.search(
            r"\bпусть\s+(?:он\s+|она\s+|они\s+)?(?:пойм[её]т|посмотр\w*|увид\w*|почита\w*|знает|поймут)\b",
            t,
        )
    )
    if pust_understand:
        return True
    relay = bool(
        re.search(r"\b(?:скинь\w*|кинь\w*|перешл\w*|покажи\w*|напиши\w*|отправь\w*)\b", t)
    )
    third_party = bool(re.search(r"\b(?:ему|ей|им)\b", t))
    media = bool(re.search(r"\b(?:видос\w*|видео|ролик\w*|скрин\w*)\b", t))
    return relay and third_party and media


def _is_money_worth_banter(text: str) -> bool:
    """«в моих деньгах это как 2 кобры, а в ваших и с скидками 3» — болтовня о ценности, не вопрос."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:купить|настро|замен|почин|собрать|подключ))\b", t
    ):
        return False
    if re.search(r"\bсколько\s+стоит\b", t):
        return False
    money_worth = bool(
        re.search(r"\bв\s+(?:моих|ваших|твоих|наших|его|её|ее|их)\s+деньг\w*\b", t)
        or re.search(r"\bв\s+пересч[её]те\s+на\b", t)
    )
    if not money_worth:
        return False
    compare = bool(
        re.search(r"\bкак\b", t)
        or re.search(r"\bскидк\w*\b", t)
        or re.search(r"\b(?:кобр\w*|kobra\w*|принтер\w*)\b", t)
    )
    return compare


def _is_design_feature_car_sarcasm(text: str) -> bool:
    """«а если у него дверь в машине кривая — тоже особенность конструкции?» — сарказм-аналогия, не вопрос."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж\w*|как\s+(?:настро|исправ|убрать|почин|замен))\b", t
    ):
        return False
    design = bool(
        re.search(r"\bособенност\w*\s+конструкци\w*\b", t)
        or re.search(r"\bконструктивн\w*\s+особенност\w*\b", t)
    )
    if not design:
        return False
    sarcasm_frame = bool(re.search(r"\bтоже\b", t) or re.search(r"\b(?:а\s+)?если\b", t))
    analogy = bool(
        re.search(r"\b(?:машин\w*|авто\w*|тачк\w*|телефон\w*|холодильник\w*|чайник\w*)\b", t)
    )
    return sarcasm_frame and analogy


def _is_pure_numeric_or_symbol_message(text: str) -> bool:
    """Сообщение без реальных слов — только цифры и символы (35?, 40%?).

    Такие «ответы» в треде — числа с вопросительным знаком, проценты — не вопросы к боту.
    """
    if not text or not text.strip():
        return False
    # Если в тексте нет ни одной последовательности из ≥2 букв — это не слово
    words = re.findall(r"[а-яёa-z]{2,}", text.lower())
    return not words


def _is_offbeat_social_banter(text: str) -> bool:
    """Болтовня без темы 3D-печати: сон, алкоголь, запрещённые вещества.

    «Кто хочет спать — тот спит», «Картофельную водку?», «Лсд эт вроде не печать» — не вопросы к боту.
    """
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж|как\s+(?:настро|исправ|почин|сделать))\b", t):
        return False
    has_print_ctx = bool(
        re.search(
            r"\b(?:принтер|печат|слайсер|сопло|экструдер|пластик|смол|кобра|kobra|"
            r"прошивк|калибр|слой|температур|сопл)\w*\b",
            t,
        )
        or _printer_mentioned(text)
    )
    # Алкоголь / спиртное
    alcohol = bool(
        re.search(
            r"\b(?:водк\w*|пив\w*|виск\w*|самогон\w*|алкоголь|коньяк\w*|бухло\w*|бухать|"
            r"ром\b|джин\b|вин[оа]\b|шампанск\w*)\w*\b",
            t,
        )
    )
    # Сон / засыпание (социальное)
    sleep_chat = bool(
        re.search(
            r"\b(?:кто\s+хочет\s+спать|хочет\s+спать|хочу\s+спать|пора\s+спать|"
            r"иду\s+спать|пошёл\s+спать|пошел\s+спать|ляг\w*\s+спать)\b",
            t,
        )
    )
    # Наркотики / запрещённые вещества без контекста принтера
    drugs = bool(
        re.search(r"\b(?:лсд|lsd|марихуан\w*|наркотик\w*)\b", t)
        and not has_print_ctx
    )
    if alcohol and not has_print_ctx:
        return True
    if sleep_chat:
        return True
    if drugs:
        return True
    return False


def _is_bare_rhetorical_context_question(text: str) -> bool:
    """Короткий анафорический/риторический вопрос без темы 3D-печати — реплика в треде, не вопрос к боту.

    Примеры: «А как это связано?», «А зачем он?», «А зачем продавать?».
    Такие фразы осмысленны только в контексте предыдущих реплик чата.
    """
    if not text or not text.strip():
        return False
    raw = text.strip()
    if "?" not in raw:
        return False
    t = re.sub(r"\s+", " ", raw.lower()).strip()
    word_count = len(t.split())
    if word_count > 7:
        return False
    if re.search(
        r"\b(?:помогите|подскаж|как\s+(?:настро|исправ|сделать|убрать|решить|починить|подключ|замен))\b",
        t,
    ):
        return False
    has_print_ctx = bool(
        re.search(
            r"\b(?:принтер|печат|слайсер|сопло|экструдер|пластик|смол|кобра|kobra|ace|аська|"
            r"прошивк|калибр|слой|температур|сопл|платформ|стол\b|филамент|катушк)\w*\b",
            t,
        )
        or _printer_mentioned(raw)
    )
    if has_print_ctx:
        return False
    # «А зачем X?» или «Зачем X?» — короткий вопрос без 3D-контекста
    if re.match(r"^(?:а\s+)?зачем\b", t) and word_count <= 5:
        return True
    # «А как это связано?», «А что это?» с анафорой
    anaphora = bool(
        re.search(r"\b(?:это|этот|эта|эти|оно|он|она|они|его|её|ее|им|их|тот|та|те|то|там|тут)\b", t)
    )
    if re.match(r"^(?:а\s+)?(?:как|что|куда|откуда)\b", t) and anaphora and word_count <= 6:
        return True
    # «По длинне оригинала?», «За сколько взял?» — короткий уточняющий фрагмент с предлога
    starts_with_prep = bool(
        re.match(r"^(?:по|из|за|с\b|в\b|на|при|от|до|для|у\b)\b", t)
    )
    if starts_with_prep and word_count <= 4:
        return True
    return False


def _is_personal_chat_action_reference(text: str) -> bool:
    """«Я тут где-то скидывал/спрашивал» — ссылка на своё прошлое действие в чате, не вопрос к боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if "?" in text and re.search(r"\b(?:как\s+найти|где\s+(?:найти|посмотреть))\b", t):
        return False
    personal = bool(re.search(r"\b(?:я|мы)\b", t))
    past_action = bool(
        re.search(
            r"\b(?:скидывал\w*|скидал\w*|поделил\w*|писал\w*|спрашивал\w*|слал\w*|"
            r"отправлял\w*|постил\w*|кидал\w*|кинул\w*)\b",
            t,
        )
    )
    place_ref = bool(re.search(r"\b(?:тут|здесь|там|где[\s-]?то|сюда|выше|раньше)\b", t))
    return personal and past_action and place_ref


def _is_unrelated_pc_hardware_banter(text: str) -> bool:
    """Болтовня о ПК-компонентах (проц, CPU, GPU) без контекста 3D-печати.

    «Андрюхе что проц впадлу менять» — разговор про компьютер, не про принтер.
    """
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж|что\s+делать)\b", t):
        return False
    has_print_ctx = bool(
        re.search(
            r"\b(?:принтер|печат|слайсер|кобра|kobra|прошивк|калибр|слой)\w*\b",
            t,
        )
        or _printer_mentioned(text)
    )
    if has_print_ctx:
        return False
    pc_hw = bool(
        re.search(
            r"\b(?:проц\w*|процессор\w*|cpu|gpu|видеокарт\w*|оперативк\w*|"
            r"ram\b|hdd\b|ssd\b|ноутбук\w*|laptop)\b",
            t,
        )
    )
    return pc_hw


def _is_casual_advice_in_thread(text: str) -> bool:
    """Бытовой совет/рекомендация в треде без запроса к боту (утверждение, не вопрос).

    Примеры: «Верхнюю крышку проклеить», «Можно же почистить», «тикет на сайте составить».
    """
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж|не\s+работает|что\s+делать)\b", t):
        return False
    # «Можно (же) <глагол обслуживания>» — пассивная рекомендация
    if re.search(
        r"\bможно\s+(?:же\s+)?(?:почистить|промыть|продуть|проклеить|зафиксировать|"
        r"поправить|заменить|смазать|прочистить|перепрошить|откалибровать|подтянуть)\b",
        t,
    ):
        return True
    # Тикет в поддержку — совет-наблюдение, не вопрос
    if re.search(r"\bтикет\b", t) and re.search(
        r"\b(?:на\s+сайте|составить|создать|отправить|заполнить|написать)\b", t
    ):
        return True
    # Глагол обслуживания в инфинитиве без вопросительного слова — совет
    if re.search(
        r"\b(?:проклеить|промыть|продуть|прочистить|протереть|смазать|накатить|перепрошить)\b",
        t,
    ):
        return True
    # Повелительное наклонение «поставьте/переставьте/загрузите X в Y» — совет в треде
    if re.search(
        r"\b(?:поставьте|переставьте|загрузите|переставь|поменяйте|поменяй)\b",
        t,
    ) and not re.search(r"\b(?:помогите|подскаж)\b", t):
        return True
    return False


def _is_print_task_planning_statement(text: str) -> bool:
    """«Надо напечатать X для К3 потому что лоточков не хватает» — объявление задачи в чате, не вопрос к боту."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж|как\s+(?:настро|сделать|убрать|печатать))\b", t):
        return False
    # «надо/нужно напечатать X» — объявление задачи (не «как напечатать?»)
    task = bool(
        re.search(r"\b(?:надо|нужно)\s+(?:\w+\s+){0,5}напечатать\b", t)
        or re.search(r"\bхочу\s+(?:\w+\s+){0,4}напечатать\b", t)
    )
    # С явным обоснованием или целью — точнее соответствует паттерну
    reason = bool(
        re.search(r"\bпотому\s+что\b", t)
        or re.search(r"\bдля\s+(?:многоцвет|к3|кобр|s1|принтер)\w*\b", t)
        or re.search(r"\bне\s+хватает\b", t)
    )
    return task and reason


def _is_multicolor_tower_rhetoric(text: str) -> bool:
    """«Без башни никак / без башни не печатается?» — риторика про нужность Prime Tower, не запрос к вики.

    Сюда же риторические подтверждения у соседей по чату:
    «многоцвет же без башни не печатается?» — на это в вики нет отдельной страницы-ответа.
    """
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(r"\b(?:помогите|подскаж\w*|как\s+(?:отключ|убрать|настро|включ|добав))\b", t):
        return False
    if re.search(r"\bбез\s+башн\w*\s+никак\b", t):
        return True
    # «без башни не печатается/не работает/не выйдет?» (с опечатками «чепятается»)
    return bool(
        re.search(
            r"\bбез\s+башн\w*\b.{0,20}\bне\s+\w*(?:печат|чепят|чипят|напечат|работ|выйд|получ|ид[её]т)\w*",
            t,
        )
    )


def _is_colloquial_printer_fragment(text: str) -> bool:
    """Обрывки «как кобра х», «как на кобре» — сравнение в треде, не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    raw = text.strip()
    if len(raw) > 40:
        return False
    t = re.sub(r"\s+", " ", raw.lower()).strip()
    if re.search(
        r"\b(?:помогите|подскаж|не\s+работает|что\s+делать|"
        r"как\s+(?:настро|откалибр|почин|исправ|сделать|убрать|решить|подключ|замен))\b",
        t,
    ):
        return False
    return bool(
        re.match(
            r"^как\s+(?:"
            r"(?:кобр\w*|kobra\w*|vyper\w*|вайпер\w*|фотон\w*|photon\w*)"
            r"(?:\s+\w{1,4})?|"
            r"на\s+(?:кобр\w*|kobra\w*|vyper\w*|вайпер\w*|фотон\w*)"
            r")\s*$",
            t,
            re.I | re.UNICODE,
        )
    )


def _is_expert_deferral_chatter(text: str) -> bool:
    """Делится догадкой и сам предлагает дождаться/спросить опытных — не вопрос боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return bool(_DEFER_TO_EXPERT_RE.search(t))


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
        or _is_print_quality_meta_curiosity(text)
        or _is_colloquial_printer_fragment(text)
        or _is_cross_chat_tip_sharing(text)
        or _is_ace_chitu_hardware_observation(text)
        or _is_multicolor_preset_banter(text)
        or _is_other_printer_maintenance_story(text)
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
            r"подскаж\w*|"
            r"скажите\s+как|"
            r"как\s+(?:\w+\s+){0,10}убрать"
            r")\b",
            t,
        )
    )


def _is_multicolor_flow_calibration_chat(text: str | None) -> bool:
    """Вопрос про работу авто-калибровки потока в многоцветной печати — в вики нет ответа.

    Например: «будет ли калибровать поток для каждого пластика при многоцветной печати?».
    Здесь «пластик» — обобщённо («для каждого пластика»), а не конкретный материал,
    поэтому это не настройки слайсинга под PETG/TPU и не выбор филамента.
    """
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    has_flow_calib = bool(
        (re.search(r"\bкалибр\w*", t) and re.search(r"\bпоток\w*", t))
        or re.search(r"flow\s+calibrat", t)
    )
    if not has_flow_calib:
        return False
    multicolor = bool(
        re.search(
            r"\b(?:многоцвет\w*|много\s+цвет\w*|мультиколор|multi[\s-]?color|multicolor|"
            r"разн\w*\s+цвет\w*|неск\w*\s+цвет\w*)\b",
            t,
        )
    )
    if not multicolor:
        return False
    specific_material = bool(
        re.search(r"\b(?:тпу|tpu|петг|petg|пла|pla|abs|абс|nylon|нейлон)\b", t)
    )
    return not specific_material



def _is_causal_continuation(text: str) -> bool:
    r"""«Потому что...» / «Ну потому...» — продолжение чужой реплики, не вопрос к боту.

    Такие сообщения объясняют что-то, сказанное выше в треде, и не адресованы боту.
    """
    if not text or not text.strip():
        return False
    t = re.sub(r'\s+', ' ', text.lower()).strip()
    if re.search(r'\b(?:помогите|подскаж|как\s+(?:настро|исправ|починить|сделать|убрать|решить))\b', t):
        return False
    return bool(re.match(r'^(?:ну\s+)?потому\s+что\b', t))


def _is_anaphoric_person_question(text: str) -> bool:
    r"""«А щас че он хочет?» — короткий вопрос о человеке без темы принтера."""
    if not text or not text.strip():
        return False
    raw = text.strip()
    if '?' not in raw:
        return False
    t = re.sub(r'\s+', ' ', raw.lower()).strip()
    word_count = len(t.split())
    if word_count > 8:
        return False
    if re.search(r'\b(?:помогите|подскаж|принтер|печат|экструдер|сопло|кобра|kobra)\w*\b', t):
        return False
    from app.bot.heuristics._base import _printer_mentioned
    if _printer_mentioned(raw):
        return False
    person_ref = bool(re.search(r'\b(?:он|она|они|его|её|ее|им|их)\b', t))
    want_verb = bool(re.search(r'\b(?:хочет|хотят|хотел|хотела|хотели|говорит|говорят|делает|делают)\b', t))
    if person_ref and want_verb:
        return True
    if re.match(r'^(?:а\s+)?(?:щас|сейчас|тут|там)\b', t) and word_count <= 6:
        return True
    return False


def _is_chat_social_moderation(text: str) -> bool:
    r"""«Можно не тут? Тут дети» — социальный/модерационный комментарий в чате."""
    if not text or not text.strip():
        return False
    t = re.sub(r'\s+', ' ', text.lower()).strip()
    if re.search(r'\b(?:принтер|печат|экструдер|сопло|кобра|kobra|ошибка|калибр)\w*\b', t):
        return False
    if re.search(r'\b(?:тут|здесь|при)\s+(?:дет\w+|ребёнк\w+|детьми)\b', t):
        return True
    if re.search(r'\b(?:можно|давайте|пожалуйста)\b.{0,20}\b(?:не\s+тут|не\s+здесь|в\s+лс|в\s+лич)\b', t):
        return True
    if re.search(r'\b(?:иди|идите|пиш\w+|перенес\w+|общайтесь)\b.{0,15}\b(?:в\s+лс|в\s+лич\w*|в\s+личку)\b', t):
        return True
    return False


# Мат с растянутыми буквами: «заеееебааал» сначала схлопываем до «заебал».
_PROFANITY_RE = re.compile(
    r"\b(?:"
    r"а?х+у+е|о+х+у+е|ху+[йёяе]|"
    r"за+[её]+б|вы+[её]+б|въ+[её]+б|до+[её]+б|"
    r"[её]+б+а+н|[её]+б+а+л|[её]+б+у+ч|на+х+у+й|на+х+е+р|"
    r"б+л+я+|бл[яэ]ть|"
    r"пи+зд|"
    r"му+да[кч]|долбо[её]б|пид[оа]р|"
    r"г[оа]ндон|"
    r"с+у+к+а+\b|сук[аи]\b"
    r")",
    re.IGNORECASE,
)

# Слова про принтер/печать — если есть, мат может сопровождать реальную проблему.
_PRINT_CTX_RE = re.compile(
    r"\b(?:принтер|печат|слайсер|сопл|экструдер|пластик|филамент|катушк|смол|"
    r"кобра|kobra|ace|аськ|прошивк|калибр|сло[йя]|температур|стол\b|платформ|"
    r"ошибк|подач|обдув|ремен|термистор|нагрев|адгез|сцеплен)\w*\b",
    re.IGNORECASE,
)

# Явная просьба о помощи/инструкции — такие реплики под фильтры болтовни не загоняем.
_HELP_GUARD_RE = re.compile(
    r"\b(?:помогите|помоги|подскаж\w*)\b|"
    r"\bкак\s+(?:настро|исправ|почин|сделать|убрать|решить|подключ|замен|откалибр)",
    re.IGNORECASE,
)


def _is_profanity_outburst_chatter(text: str) -> bool:
    """Эмоциональный мат без темы 3D-печати — «Ахуели совсем?», «как меня этот Николай заебал».

    Если в сообщении нет ни одного слова про принтер/печать и нет просьбы о помощи,
    а есть мат — это выброс эмоций в чате, а не вопрос к боту.
    """
    if not text or not text.strip():
        return False
    raw = text.strip()
    t = re.sub(r"\s+", " ", raw.lower()).strip()
    # схлопываем растянутые буквы: «заеееебааал» → «заебал»
    collapsed = re.sub(r"(.)\1{2,}", r"\1", t)
    if _HELP_GUARD_RE.search(collapsed):
        return False
    if _PRINT_CTX_RE.search(collapsed) or _printer_mentioned(raw):
        return False
    if not _PROFANITY_RE.search(collapsed):
        return False
    # короткие вопросы-выбросы («ахуели?») — до 10 слов; ранты-утверждения без «?» — длиннее
    wc = len(collapsed.split())
    if "?" in raw:
        return wc <= 10
    return wc <= 30


def _is_works_fine_reassurance(text: str) -> bool:
    """«У меня норм пашет», «всё нормально работает» — реплика-успокоение, не вопрос к боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    # «не работает / не пашет» — это уже проблема, а не успокоение
    if re.search(r"\bне\s+(?:пашет|работает|печатает|фурычит|пыхтит)\b", t):
        return False
    positive = bool(
        re.search(
            r"\b(?:норм|нормально|нормас|нормал|ок|окей|отлично|хорошо|збс|пучком|ч[её]тко)\b",
            t,
        )
    )
    works = bool(re.search(r"\b(?:пашет|работает|печатает|фурычит|пыхтит|крутит)\b", t))
    return positive and works


def _is_marketplace_search_chatter(text: str) -> bool:
    """«Нашёл, но не то что на Авито» — болтовня про поиск на барахолке/маркетплейсе, не вопрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    place = bool(
        re.search(
            r"\b(?:авито|avito|юла\b|барахолк\w*|алиэкспресс|алик\b|aliexpress|"
            r"озон|ozon|вайлдбер\w*|wildberries|маркетплейс)\b",
            t,
        )
    )
    if not place:
        return False
    return bool(
        re.search(
            r"\b(?:нашёл|нашел|нашл\w*|не\s+то|искал\w*|смотрел\w*|глянул\w*|"
            r"видел\w*|купил\w*|заказал\w*|брал\b)\b",
            t,
        )
    )


# Узлы/параметры для диагностического допроса соседа («вентилятор работает?»).
_DIAG_COMPONENT_RE = re.compile(
    r"\b(?:вентилятор\w*|кулер\w*|ремн\w*|ремень|сопл\w*|хотенд\w*|термистор\w*|"
    r"температур\w*|поток\w*|обдув\w*|ретракт\w*|концевик\w*|датчик\w*|"
    r"экструдер\w*|подач\w*|нагрев\w*|вал\w*|эксцентрик\w*|пластик\w*|филамент\w*)\b",
    re.IGNORECASE,
)


def _is_peer_diagnostic_checklist(text: str) -> bool:
    """«Боковой вентилятор работает?», «Температура, фирма пластика, хотенд?» —

    короткий диагностический вопрос/перечисление узлов соседу по чату, не запрос к вики.
    """
    if not text or "?" not in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:у\s+меня|не\s+работает|не\s+могу|не\s+получ\w*|"
        r"как\s+(?:настро|почин|исправ|сделать|убрать|подключ|замен)|"
        r"почему|что\s+делать|помогите|подскаж\w*|ошибк\w*)\b",
        t,
    ):
        return False
    if len(t.split()) > 7:
        return False
    comma_list = ("," in t) and (len(_DIAG_COMPONENT_RE.findall(t)) >= 2)
    state = bool(
        _DIAG_COMPONENT_RE.search(t)
        and re.search(
            r"\b(?:работает|работают|крутит\w*|натянут\w*|закручен\w*|"
            r"подключ\w*|включ[её]н\w*|цел\w*|стоит|стоят)\b",
            t,
        )
    )
    return comma_list or state


def _is_bare_combo_variant_fragment(text: str) -> bool:
    """«Комбо?», «гарантийный комбо?» — обрывок про вариант принтера без вопроса по сути."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return bool(
        re.match(r"^(?:а\s+|и\s+|про\s+|это\s+|гарантийн\w*\s+)?(?:комбо|combo)\s*\??$", t)
    )


def _is_social_location_question(text: str) -> bool:
    """«Вы территориально откуда?» — социальный вопрос о местоположении, не тема вики."""
    if not text or "?" not in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _PRINT_CTX_RE.search(t):
        return False
    if re.search(r"\bтерриториально\b", t):
        return True
    if re.search(r"\b(?:вы|ты)\b.{0,12}\bоткуда\b", t) or re.search(r"\bоткуда\b.{0,8}\b(?:вы|ты)\b", t):
        return True
    if re.search(r"\bв\s+как(?:ом|ой)\s+(?:городе|регионе|стране)\b", t):
        return True
    return False


def _is_content_post_request(text: str) -> bool:
    """«Видео нарезки будет?» — вопрос про публикацию контента в чате, не запрос к вики."""
    if not text or "?" not in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _PRINT_CTX_RE.search(t):
        return False
    return bool(
        re.search(r"\b(?:видео|ролик|стрим|запись|туториал|урок|обзор)\w*\b", t)
        and re.search(
            r"\b(?:будет|будут|выложи\w*|скинеш\w*|скинет\w*|запиш\w*|сдела\w*|планир\w*)\b",
            t,
        )
    )


def _is_thread_continuation_filler(text: str) -> bool:
    """«хотя ладно, не везде…», «это я понял, но…» — продолжение/реакция в треде, не вопрос к боту."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.match(r"^(?:да\s+|ну\s+)?хотя\b", t):
        return True
    if re.match(r"^(?:это\s+)?я\s+понял", t):
        return True
    if re.match(r"^понял[,\s]", t) or t in ("понял", "понятно"):
        return True
    return False


def _is_competitor_model_disambiguation(text: str) -> bool:
    """«а хот к2 это чё, кобра 2? или креалити к2?» — выяснение чужой модели/конкурента, не вопрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    has_comp = bool(
        re.search(r"\b(?:креалит\w*|creality|бамбу\w*|bambu|prusa|пруса|ender|qidi)\b", t)
    )
    disambig = bool(re.search(r"(?:\bэто\s+ч[ёе]\b|\bчто\s+за\b|\bили\b)", t))
    return has_comp and disambig
