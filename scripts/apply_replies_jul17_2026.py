"""Разбор recent_replies (2026-07-17): manual_qa + эвристики + очистка ленты."""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEXT_PATH = ROOT / "app" / "bot" / "text_heuristics.py"
TEST_PATH = ROOT / "tests" / "test_replies_jul17_chatter.py"
RECENT_PATH = ROOT / ".cache" / "recent_replies.json"

NEW_QA = [
    {
        "keys": [
            "вырез на модели под магниты",
            "вырез под магниты",
            "отверстие под магнит",
            "вырезать под магниты",
            "инструмент в слайсере под магниты",
            "вырез в слайсере под магнит",
        ],
        "title": "Вырез под магниты в слайсере",
        "answer": (
            "В слайсере это обычно делают отрицательным объёмом (Negative Part / Modifier):\n\n"
            "• Anycubic Slicer Next / Orca: добавьте цилиндр/куб → тип «Negative part» "
            "(вычитание) и поставьте на место магнита; диаметр чуть больше магнита "
            "(+0.2…0.4 мм на сторону).\n"
            "• Либо заранее сделайте отверстие в CAD (Fusion/FreeCAD/Blender) и уже "
            "готовую STL режьте в слайсере.\n"
            "• Для утопленных магнитов удобнее CAD; для быстрой правки готовой модели — "
            "negative part в слайсере.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/software-and-app/"
            "new-page-anycubic-slicer-beta(orca-version)/"
            "anycubic-slicer-next-slicing-software-quick-start-guide"
        ),
    },
    {
        "keys": [
            "много нитей при печати petg",
            "очень много нитей при печати",
            "нитей при печати petg",
            "паутина petg на стандартном",
            "стринги petg kobra",
        ],
        "title": "Много нитей (стринги) на PETG",
        "answer": (
            "На PETG «паутина» — часто влажность + температура + ретракт.\n\n"
            "• Просушите катушку (PETG обычно 55–60°C, несколько часов).\n"
            "• Снизьте температуру сопла на 5–10°C от профиля (у вас 210°C уже помогает — "
            "смотрите, чтобы слои ещё держались).\n"
            "• Увеличьте длину и скорость ретракта; на direct drive чаще 0.5–1.5 мм / 30–45 мм/с.\n"
            "• Поднимите travel speed; включите combing / avoid crossing walls.\n"
            "• Проверьте, что сопло не подтекает на idle.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/stringing-or-oozing"
        ),
    },
    {
        "keys": [
            "принтер подключается к сети а слайсер не видит",
            "слайсер не видит его",
            "слайсер не видит принтер",
            "принтер в сети слайсер не видит",
            "не видит принтер в слайсере",
            "слайсер не находит принтер",
        ],
        "title": "Принтер в Wi‑Fi, слайсер не видит",
        "answer": (
            "Если принтер в сети, а Anycubic Slicer Next его не находит:\n\n"
            "• ПК и принтер должны быть в одной подсети (не гостевая сеть, не VPN).\n"
            "• На принтере: Settings → Network → LAN Mode — включите LAN и посмотрите WiFi IP.\n"
            "• В слайсере: Workbench → Add Printer → введите IP вручную, если автоскан пустой.\n"
            "• Проверьте firewall Windows; на раздаче с телефона/hotspot discovery часто ломается.\n"
            "• Принтер только на 2.4 GHz Wi‑Fi.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/lan-connection-guide"
        ),
    },
    {
        "keys": [
            "зарезервировать ip",
            "зарезервировать ip kobra",
            "статический ip принтера",
            "постоянный ip принтера",
            "один и тот же ip",
            "принтер каждый раз получает разный ip",
        ],
        "title": "Постоянный IP для Kobra S1",
        "answer": (
            "На самом принтере «зарезервировать IP» обычно нельзя — адрес выдаёт роутер/хост.\n\n"
            "• Нормальный путь: DHCP reservation на роутере по MAC принтера "
            "(привязка MAC → фиксированный IP).\n"
            "• Раздача интернета с ПК (Windows hotspot/ICS) часто не умеет reservation — "
            "IP будет плавать; надёжнее обычный роутер или ручной IP в LAN Mode, "
            "если интерфейс это позволяет.\n"
            "• IP смотрите: Settings → Network → LAN Mode → WiFi IP; в слайсере можно "
            "добавить принтер по IP.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/lan-connection-guide"
        ),
    },
    {
        "keys": [
            "максимальную скорость так",
            "максимальная скорость sla",
            "скорость sla печати",
            "максимальную скорость смолы",
            "осваивать так печать",
            "скорость смоляной печати",
        ],
        "title": "Скорость SLA/смоляной печати",
        "answer": (
            "У смоляных (LCD/MSLA) принтеров «максимальная скорость» — это не мм/с как у FDM, "
            "а время слоя (exposure) + подъём платформы.\n\n"
            "• Смотрите профиль смолы в ChiTu/Anycubic Photon Workshop: exposure time, "
            "lift distance/speed, bottom layers.\n"
            "• Гнать быстрее = короче экспозиция и быстрее подъём — риск недосвета, "
            "отрыва от платформы, «пустого» стола.\n"
            "• Берите официальный профиль под вашу смолу и модель принтера; "
            "ускоряйте по одному параметру и печатайте тест-модель.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/resin-3d-printer/Common/the-print-platform-is-empty-after-printing"
        ),
    },
    {
        "keys": [
            "температуру внутри аськи",
            "аська показывает что держит",
            "китайский датчик показывает",
            "температура аськи и датчик",
            "аська держит 47",
            "расхождение температуры ace",
        ],
        "title": "ACE: расхождение температуры с внешним датчиком",
        "answer": (
            "Разница 2–5°C между экраном ACE и китайским термометром — обычное дело:\n\n"
            "• Датчик ACE меряет воздух в своей точке; внешний датчик в другом месте камеры "
            "часто показывает ниже.\n"
            "• Ориентируйтесь на показания ACE: для PLA обычно 45–50°C, PETG ~55–60°C "
            "(смотрите лимит прошивки).\n"
            "• Если ACE «держивает» около уставки (±2–3°C) — это нормальная гистерезисная "
            "работа нагревателя, не поломка.\n"
            "• Подозрение на брак датчика — только если ACE сильно врёт (десятки градусов) "
            "или ошибка сенсора в логе.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/ace-pro/ace-pro-dryerguide"
        ),
    },
]

STRINGING_EXTRA_KEYS = [
    "много нитей при печати",
    "очень много нитей",
    "нитей при печати",
]

NEW_BANTER_FN = r'''

def _is_parcel_arrival_banter(text: str) -> bool:
    """«Вот оно как раз и пришло» — реплика про посылку/доставку, не вопрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(r"\b(?:помогите|подскаж|не\s+работает|ошибк\w*|как\s+(?:настро|почин))\b", t):
        return False
    return bool(
        re.search(r"\bкак\s+раз\s+и\s+пришл", t)
        or re.search(r"\bвот\s+оно\s+как\s+раз\b", t)
        or (re.search(r"\bпришл[оа]\b", t) and re.search(r"\bкак\s+раз\b", t) and len(t.split()) <= 10)
    )


def _is_filament_shopping_poll(text: str) -> bool:
    """«Посоветуйте пластик … и где брали» — опрос чата про покупку, не гайд вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:как\s+(?:настро|печат|сушить|хранить)|температур\w*\s+для|профиль\s+для)\b",
        t,
    ):
        return False
    ask = bool(re.search(r"\b(?:посоветуйте|порекомендуйте|подскажите\s+пластик)\b", t))
    where = bool(re.search(r"\bгде\s+(?:брал|брали|покупал|покупали|взять|взяли)\b", t))
    filament = bool(
        re.search(
            r"\b(?:пластик|филамент|petg|pla|abs|asa|тпу|tpu|флуоресцентн|светящ)\w*\b",
            t,
        )
    )
    return ask and filament and (where or re.search(r"\bпроверенн\w*\b", t))


def _is_warranty_service_sidebar(text: str) -> bool:
    """Гарантия/суд/ДНС/акт замены — спор с сервисом, не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if re.search(
        r"\b(?:как\s+(?:замен|настро|откалибр|почин)|помогите\s+настро|ошибк\w*\s+\d+)\b",
        t,
    ):
        return False
    service = bool(
        re.search(
            r"\b(?:"
            r"гарант\w*|днс|dns|суд\w*|слушани\w*|акт\w*|"
            r"запчаст\w*|официальн\w*\s+не\s+представ|"
            r"кривой\s+стол\s+выслал|в\s+замен\s+родного|"
            r"письмо\s+от\s+кубик"
            r")\b",
            t,
        )
    )
    dispute = bool(
        re.search(
            r"\b(?:"
            r"проиграл|выигран|не\s+хотели|не\s+покажут|"
            r"выдадут\s+акт|мало\s+что\s+решает|"
            r"та\s+нафиг|на\s+скорость\s+не\s+влия"
            r")\b",
            t,
        )
    )
    return service and (dispute or re.search(r"\b(?:креалити|creality|ремн\w*)\b", t))


def _is_peer_bed_mesh_lecture(text: str) -> bool:
    """«Когда снимите карту стола… закреп технички» — совет людям в треде, не вопрос боту."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    mesh = bool(re.search(r"\b(?:карт\w*\s+стол|bed\s*mesh|mesh)\b", t))
    lecture = bool(
        re.search(r"\b(?:снимите|поймете|поймёте|закреп|техничк)\b", t)
        or re.search(r"\bдля\s+печати\s+больших\s+деталей\b", t)
    )
    return mesh and lecture
'''

# --- patches to existing functions ---

TIP_OLD = '''    if re.search(r"\\bу\\s+меня\\s+(?:есть|стоит|имеется|лежат|лежит)\\b", tl):
        return True
    return False


def _is_problem_combo_banter(text: str) -> bool:'''

TIP_NEW = '''    if re.search(r"\\bу\\s+меня\\s+(?:есть|стоит|имеется|лежат|лежит)\\b", tl):
        return True
    if re.search(r"\\bпод\\s+\\d+\\s+градус", tl) and re.search(r"\\bпостав\\w*\\s+печат", tl):
        return True
    if re.search(r"\\bменьше\\s+шансов\\s+что\\s+слома", tl):
        return True
    return False


def _is_problem_combo_banter(text: str) -> bool:'''

PURCHASE_OLD = '''    deliberation = bool(
        re.search(
            r"\\b(?:"
            r"думал\\s+про|думаю\\s+про|подумыва\\w*|"
            r"не\\s+увер\\w*|сомнева\\w*|склоня\\w*|"
            r"решаю|выбираю\\s+между|колебл\\w*|раздумыва\\w*"
            r")\\b",
            t,
        )
    )
    return purchase_ctx and deliberation'''

PURCHASE_NEW = '''    deliberation = bool(
        re.search(
            r"\\b(?:"
            r"думал\\s+про|думаю\\s+про|думаю\\s+(?:о\\s+)?смен|"
            r"думаю\\s+брать|долго\\s+думаю|подумыва\\w*|"
            r"не\\s+увер\\w*|сомнева\\w*|склоня\\w*|"
            r"решаю|выбираю\\s+между|колебл\\w*|раздумыва\\w*"
            r")\\b",
            t,
        )
        or re.search(r"\\bстоит\\s+ли\\b", t)
        or re.search(r"брать\\s+ли\\s+(?:s1|кобр|kobra)", t)
    )
    return purchase_ctx and deliberation'''

CMP_OLD = '''    # «кобра 3 стоит как Х» — сравнение в треде, не «как настроить».
    if re.search(r"\\bстоит\\s+как\\b", t) and _printer_mentioned(text):
        return True
    return False'''

CMP_NEW = '''    # «кобра 3 стоит как Х» — сравнение в треде, не «как настроить».
    if re.search(r"\\bстоит\\s+как\\b", t) and _printer_mentioned(text):
        return True
    # Выбор между моделями по эстетике/подаче («дрыгостолы», «поэстетичнее»).
    if re.search(r"\\b(?:дрыгостол|поэстетичн|нет\\s+в\\s+жизни\\s+совершенств)\\w*", t):
        return True
    if (
        re.search(r"\\bкогда\\s+выбирал\\b", t)
        and re.search(r"\\b(?:смотрели|смотрел|подача\\s+филамент)\\w*", t)
    ):
        return True
    return False'''

CONT_OLD = '''    if re.match(r"^вряд-?ли\\s*,\\s*а\\s+с\\s+какой\\s+целью", t):
        return True
    return False


def _is_slicer_preview_chatter(text: str) -> bool:'''

CONT_NEW = '''    if re.match(r"^вряд-?ли\\s*,\\s*а\\s+с\\s+какой\\s+целью", t):
        return True
    if re.match(r"^пробовал,\\s*все\\s+равно", t):
        return True
    if re.search(r"\\bиз-за\\s+этого\\s+могло\\b", t) and re.search(r"\\bрябь\\b", t):
        return True
    if re.search(r"\\bсобери\\s+масло\\s+салфетк", t):
        return True
    if re.search(r"\\bразве\\s+что\\s+монослой\\b", t):
        return True
    return False


def _is_slicer_preview_chatter(text: str) -> bool:'''

SIDEBAR_OLD = '''        r"\\bпод\\s+тяжел\\w*\\s+котик\\w*\\s*\\??\\s*$",
    )
    return any(re.search(p, t) for p in patterns)'''

# After pull the sidebar patterns may differ - find a stable anchor near end of patterns list
SIDEBAR_ANCHOR_OLD = None  # filled at runtime

AUTO_OLD = '''            r"чудо\\s+инженерии|мирового\\s+дизайна|одноклассник\\w*.*париж\\w*"
            r")\\b",
            t,
        )'''

AUTO_NEW = '''            r"чудо\\s+инженерии|мирового\\s+дизайна|одноклассник\\w*.*париж\\w*|"
            r"салон\\s+убит|укурыш|ее\\s+продает"
            r")\\b",
            t,
        )'''

OBS_PATCH_FN = r'''

def _is_sensor_thread_banter(text: str) -> bool:
    """Болтовня про датчик филамента/ACE в треде без запроса помощи."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(r"\b(?:помогите|подскаж|как\s+(?:настро|почин|замен)|не\s+работает|ошибк\w*)\b", t):
        return False
    sensor = bool(re.search(r"\bдатчик\w*\b", t) and re.search(r"\b(?:филамент|конца\s+нити|runout)\w*\b", t))
    ace_spool = bool(
        re.search(r"\b(?:катушк\w*|аськ\w*|ace)\b", t)
        and re.search(r"\b(?:поперепихал|проблем\s+небыл|дефект\s+на\s+прутк)\w*", t)
    )
    s1_shrug = bool(
        re.search(r"\bс1\b", t)
        and re.search(r"\bдатчик\b", t)
        and re.search(r"\b(?:пофигу|как\s+работал\s+так\s+и\s+работает)\b", t)
    )
    slang = bool(re.search(r"\bдатчик\s+филамента\b", t) and re.search(r"\bстранно\s+что\b", t))
    airflow = bool(
        re.search(r"\bпоток\s+определить\b", t)
        and re.search(r"\b(?:щелей|рисунок|переливает)\w*", t)
    )
    market_scan = bool(
        re.search(r"\bискал\s+через\s+слайсер\s+в\s+маркете\b", t)
        or re.search(r"\bотсканировать\s+на\s+благо\b", t)
    )
    return sensor or ace_spool or s1_shrug or slang or airflow or market_scan
'''

NEW_FUNCS = (
    "_is_parcel_arrival_banter",
    "_is_filament_shopping_poll",
    "_is_warranty_service_sidebar",
    "_is_peer_bed_mesh_lecture",
    "_is_sensor_thread_banter",
)

TEST_CONTENT = '''"""Регрессии по разбору recent_replies 2026-07-17."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_filament_shopping_poll,
    _is_non_wiki_chatter_message,
    _is_parcel_arrival_banter,
    _is_peer_bed_mesh_lecture,
    _is_purchase_deliberation_banter,
    _is_sensor_thread_banter,
    _is_thread_continuation_filler,
    _is_thread_printing_tip,
    _is_warranty_service_sidebar,
)


def test_magnets_cutout_manual_qa():
    msg = (
        "всем привет, кто знает как сделать вырез на модели под магниты? "
        "какой инструмент в слайсере и как"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_petg_stringing_manual_qa():
    msg = (
        "Очень много нитей при печати petg на стандартном профиле kobra X , "
        "уже увеличивал и скорость отката и сам откат , помогает лишь установка температуры в 210°С"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_slicer_not_seeing_printer_manual_qa():
    msg = (
        "Приветствую всех. Чет принтер подключается к сети, а слайсер не видит его . "
        "Поможете разобраться , что случилось?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_static_ip_manual_qa():
    msg = (
        "всем привет, подскажите пожалуйста "
        "есть ли возможность  для kobra s1 зарезервировать ip что бы он всегда получал один и тот же"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_sla_speed_manual_qa():
    msg = "Приветствую. Недавно начал осваивать так печать. Не подскажите максимальную скорость так?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_temp_sensor_manual_qa():
    msg = (
        "температуру внутри аськи выставил 45, аська показывает что держит 47. "
        "китайский датчик показывает 42.5"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_parcel_arrival_is_chatter():
    msg = "Вот оно как раз и пришло"
    assert _is_parcel_arrival_banter(msg)
    assert _is_conversational_chatter(msg)


def test_angle_print_tip_is_chatter():
    msg = "Под 45 градусов поставить печать, меньше шансов что сломается"
    assert _is_thread_printing_tip(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_fluorescent_shopping_is_chatter():
    msg = "Всем привет. Посоветуйте пластик флуоресцентный проверенный и где брали."
    assert _is_filament_shopping_poll(msg)
    assert _is_conversational_chatter(msg)


def test_buy_s1_deliberation_is_chatter():
    msg = (
        "Добрый вечер дамы и господа :) "
        "Я тут давненько думаю о смене принтера. "
        "У меня сейчас кубик кобра 2 про. Но долго думаю брать ли S1 "
        "Ведь кроме Petg и PLA врятли буду ещё чем-то печатать. Стоит ли?)"
    )
    assert _is_purchase_deliberation_banter(msg)
    assert _is_conversational_chatter(msg)


def test_warranty_sidebar_is_chatter():
    msg = (
        "Три недели назад ДНС проиграл слушание по гарантии принтера Креалити, "
        "не хотели кривой стол ремонтировать."
    )
    assert _is_warranty_service_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_crooked_bed_service_is_chatter():
    msg = "Та нафиг? На скорость не влияет. И вообще они мне кривой стол выслали. В замен родного кривого"
    assert _is_warranty_service_sidebar(msg)
    assert _is_conversational_chatter(msg)


def test_bed_mesh_lecture_is_chatter():
    msg = (
        "Когда снимите карту стола в программе - закреп технички. "
        "Поймете насколько у вас кривой стол. Для печати больших деталей - это важно"
    )
    assert _is_peer_bed_mesh_lecture(msg)
    assert _is_conversational_chatter(msg)


def test_sensor_banter_is_chatter():
    msg = "Ну да)) датчик филамента.. Странно что он у вас голову и без асе не еп))"
    assert _is_sensor_thread_banter(msg)
    assert _is_conversational_chatter(msg)


def test_monolayer_fragment_is_chatter():
    msg = "Разве что монослой"
    assert _is_thread_continuation_filler(msg)
    assert _is_conversational_chatter(msg)


def test_real_network_question_not_shopping():
    assert not _is_filament_shopping_poll(
        "Подскажите температуру для флуоресцентного PLA на kobra s1"
    )


def test_real_bed_calibration_not_warranty():
    assert not _is_warranty_service_sidebar(
        "Подскажите как откалибровать стол на kobra s1, первый слой не липнет"
    )


def test_error_10409_not_chatter():
    assert not _is_conversational_chatter("Ошибка 10409")
'''


def patch_manual_qa() -> None:
    entries = json.loads(QA_PATH.read_text(encoding="utf-8"))
    # Extra keys on existing stringing entry
    for e in entries:
        if isinstance(e, dict) and e.get("title") == "Паутина/нити (стринги)":
            keys = list(e.get("keys") or [])
            for k in STRINGING_EXTRA_KEYS:
                if k not in keys:
                    keys.append(k)
            e["keys"] = keys
            break
    now = time.time()
    for i, e in enumerate(NEW_QA):
        entries.insert(
            0,
            {
                "keys": e["keys"],
                "title": e["title"],
                "answer": e["answer"],
                "ts": now - i * 0.001,
            },
        )
    QA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_banter() -> None:
    t = BANTER_PATH.read_text(encoding="utf-8")
    for old, new in (
        (TIP_OLD, TIP_NEW),
        (PURCHASE_OLD, PURCHASE_NEW),
        (CMP_OLD, CMP_NEW),
        (CONT_OLD, CONT_NEW),
        (AUTO_OLD, AUTO_NEW),
    ):
        if old in t:
            t = t.replace(old, new)
        else:
            print(f"WARN: patch block not found: {old[:60]!r}...")

    # Add patterns to general_thread_sidebar near end of tuple
    extra_patterns = (
        '        r"\\bнет\\s+в\\s+жизни\\s+совершенств",\n'
        '        r"\\bсалон\\s+убит",\n'
        '        r"\\bукурыш\\b",\n'
    )
    marker = '        r"\\bпод\\s+тяжел\\w*\\s+котик\\w*\\s*\\??\\s*$",\n'
    if marker in t and "укурыш" not in t:
        t = t.replace(marker, extra_patterns + marker)

    if "_is_parcel_arrival_banter" not in t:
        # Insert new funcs before _is_vague_fix_without_symptom (near end)
        # Prefer before _is_klipper if present, else before vague
        anchor = "def _is_vague_opinion_without_symptom(text: str) -> bool:"
        block = NEW_BANTER_FN.lstrip("\n") + OBS_PATCH_FN.lstrip("\n")
        if anchor in t:
            t = t.replace(anchor, block + anchor)
        else:
            t += "\n" + block

    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    # Imports: after last banter import before closing paren of from _banter
    for name in NEW_FUNCS:
        if name in t:
            continue
        # Add to import list before closing of _banter import
        needle = "    _is_offtopic_gas_station_joke,\n)"
        if needle in t:
            t = t.replace(needle, f"    _is_offtopic_gas_station_joke,\n    {name},\n)")
        else:
            needle2 = "    _is_personal_upholstery_project_sidebar,\n)"
            if needle2 in t:
                t = t.replace(needle2, f"    _is_personal_upholstery_project_sidebar,\n    {name},\n)")

    # Chain
    chain_end = "        or _is_offtopic_gas_station_joke(text)\n    )"
    if chain_end in t and "_is_parcel_arrival_banter(text)" not in t:
        extra = "".join(f"        or {name}(text)\n" for name in NEW_FUNCS)
        t = t.replace(
            chain_end,
            "        or _is_offtopic_gas_station_joke(text)\n" + extra + "    )",
        )
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    for name in NEW_FUNCS:
        if name in t:
            continue
        needle = "    _is_offtopic_gas_station_joke,\n"
        if needle in t:
            t = t.replace(needle, f"    _is_offtopic_gas_station_joke,\n    {name},\n")
    INIT_PATH.write_text(t, encoding="utf-8")


def patch_text_heuristics() -> None:
    t = TEXT_PATH.read_text(encoding="utf-8")
    for name in NEW_FUNCS:
        if name in t:
            continue
        needle = "    _is_offtopic_gas_station_joke,\n"
        if needle in t:
            t = t.replace(needle, f"    _is_offtopic_gas_station_joke,\n    {name},\n")
    TEXT_PATH.write_text(t, encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def clear_recent_replies() -> None:
    RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_PATH.write_text("[]\n", encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    patch_text_heuristics()
    write_tests()
    clear_recent_replies()
    print(f"OK: {len(NEW_QA)} manual_qa + {len(NEW_FUNCS)} banter filters + recent_replies cleared")


if __name__ == "__main__":
    main()
