"""Разбор missed_questions.json (2026-07-03): manual_qa + эвристики + очистка очереди."""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
MISSED_PATH = ROOT / "data" / "missed_questions.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEST_PATH = ROOT / "tests" / "test_missed_jul03_chatter.py"

NEW_QA = [
    {
        "keys": [
            "ключ нужен для сопла s1",
            "какой ключ для сопла",
            "ключ для сопла s1",
            "ключ на сопло kobra s1",
            "размер ключа сопло",
            "ключ сопла kobra",
        ],
        "title": "Ключ для сопла Kobra S1",
        "answer": (
            "На Kobra S1 / S1 Combo стоит быстросъёмное (quick-release) сопло — его не откручивают "
            "накидным ключом. Снимают защёлки на радиаторе и меняют сопло в перчатках (сопло горячее).\n\n"
            "Для обслуживания хотэнда в инструкциях указаны шестигранники: S1.5 (прочистка залпа в горле), "
            "S2.0 / S2.5 — для крышек и модулей головы. Отдельного «ключа на сопло» как у Ender/MK3 нет.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/cleaning-hotend-clogging"
        ),
    },
    {
        "keys": [
            "термодатчик не мог умереть",
            "термодатчик умер",
            "термодатчик сгорел",
            "понижу температуру и ничего не изменится",
            "снижаю температуру ничего не меняется",
            "температура не меняется при настройке",
        ],
        "title": "Температура не меняется — термодатчик?",
        "answer": (
            "Если снижаете температуру в слайсере/на экране, а качество или подтёки не меняются — "
            "это не всегда «умерший» термодатчик.\n\n"
            "• Сбойный термодатчик: показания скачут, температура «замирает» при нагреве, принтер не доходит "
            "до цели или перегревается с ошибкой — проверьте разъём датчика и при необходимости замените узел хотэнда.\n"
            "• Чаще причина не в датчике: засор/частичный клин, неверный тип пластика в профиле, слишком высокий "
            "поток, плохая адгезия — симптомы похожи, но мало меняются от ±5°C.\n"
            "• Проверьте реальный нагрев: после preheat сопло должно плавить тестовый PLA; при 200°C нить идёт ровно.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/printing-effect-is-not-good"
        ),
    },
    {
        "keys": [
            "50 градусов на петг",
            "50 град на petg",
            "петг стол 50",
            "низкая температура стола petg",
            "petg стол 50",
        ],
        "title": "PETG: температура стола 50°C — норма?",
        "answer": (
            "Для PETG стол 50°C обычно низковат — типичный диапазон 70–85°C (смотрите катушку). "
            "На 50°C чаще отрывы углов и слабая адгезия.\n\n"
            "Исключение: некоторые бренды/профили PETG печатают с 60°C и ниже на текстурированной PEI — "
            "но стабильнее начать с 75–80°C.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/filament-guide"
        ),
    },
    {
        "keys": [
            "на каких скоростях печатает на кубике",
            "скорости печати на кобре",
            "скорость печати kobra s1",
            "на каких скоростях на s1",
            "какие скорости на кобре s1",
        ],
        "title": "Скорости печати на Kobra S1",
        "answer": (
            "Стартовые скорости — из профиля Anycubic/Orca для вашей модели (Kobra S1 Combo):\n\n"
            "• Черновые слои / стенки: 150–250 мм/с в «спорт»-профиле; для качества снизьте внешнюю стенку до 80–120 мм/с.\n"
            "• PETG/TPU — медленнее PLA на 20–40%.\n"
            "• Первый слой: 20–40 мм/с.\n\n"
            "Ориентируйтесь на стоковый профиль материала и уменьшайте скорость, если появляются артефакты. "
            "Сохраните копию профиля перед правками.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/filament-guide"
        ),
    },
    {
        "keys": [
            "где скачать прошивку s1",
            "скачать 2.6.0.0",
            "прошивка 2.6 kobra",
            "где скачать прошивку kobra",
            "обновление прошивки скачать",
        ],
        "title": "Где скачать прошивку Kobra S1",
        "answer": (
            "Актуальные прошивки для Kobra S1 / S1 Combo (принтер и ACE) — на официальной странице обновлений Anycubic.\n\n"
            "• Берите сборку именно для вашей модели (S1 Combo ≠ Kobra 3).\n"
            "• Флешка FAT32, не выключайте питание до завершения.\n"
            "• Версию на экране сравните с файлом на wiki перед установкой.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"
        ),
    },
]

NEW_BANTER_FN = '''

def _is_klipper_offtopic_sidebar(text: str) -> bool:
    """Klipper/BTT/хост/Raspberry — обсуждение вне стоковой прошивки Anycubic, не вопрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t) and re.search(
        r"\\b(?:помогите|подскаж|как\\s+(?:настро|прошить|обнов|подключ)|где\\s+скачать)\\b", t
    ):
        if not re.search(r"\\b(?:клиппер|klipper|бтт|btt|мцу|mcu)\\b", t):
            return False
    klipper_ctx = bool(
        re.search(
            r"\\b(?:"
            r"клиппер|klipper|"
            r"бтт|btt|"
            r"мцу|mcu|"
            r"картограф|cartograph|"
            r"распбер|raspberry|оранж\\s*пи|orange\\s*pi|"
            r"плата\\s+головы|хост\\s+один"
            r")\\b",
            t,
        )
    )
    if not klipper_ctx:
        return False
    if re.search(
        r"\\b(?:"
        r"как\\s+(?:настро|прошить|обнов|подключ)|"
        r"где\\s+(?:скачать|взять)|"
        r"помогите|подскаж|не\\s+работает|ошибк\\w*"
        r")\\b",
        t,
    ) and _printer_mentioned(text) and not re.search(r"\\b(?:бтт|btt|клиппер|klipper)\\s+какая\\b", t):
        return False
    return True


def _is_offtopic_gas_station_joke(text: str) -> bool:
    """Шутка про АЗС/бензин 95 — оффтоп, не 3D-печать."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    return bool(
        re.search(r"\\b(?:азс|бензин|заправк)\\w*\\b", t)
        and re.search(r"\\b(?:фильтр|95|бензин)\\b", t)
    )
'''

TEST_CONTENT = '''"""Регрессии по разбору missed_questions 2026-07-03."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_community_experience_poll,
    _is_conversational_chatter,
    _is_klipper_offtopic_sidebar,
    _is_non_wiki_chatter_message,
    _is_offtopic_gas_station_joke,
    _is_vague_fix_without_symptom,
)


def test_nozzle_key_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "Какой ключ нужен для сопла s1?")


def test_thermistor_manual_qa():
    msg = (
        "Хорошо, допустим понижу температуру и ничего не изменится "
        "то в чем может быть проблема, термодатчик не мог умереть?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_petg_bed_50_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "Всм 50 градусов на петг?")


def test_print_speeds_manual_qa():
    msg = "всем привет А кто на каких скоростях печатает на кубике?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_firmware_download_manual_qa():
    msg = "у меня не было такой.была какая то 2.5дальше не помню цифры.есть где скачать 2.6.0.0?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_thanks_meta_is_chatter():
    msg = "спасибо, что обяснил, а то все перелазил и не нашел ясного ответа, почему оно так делало"
    assert _is_conversational_chatter(msg)


def test_klipper_btt_sidebar_is_chatter():
    msg = (
        "Бтт какая плата? У них свои сборки оси с клиппером, у распбери свои, "
        "у мелков вообще ось перелопачена, у орандж пи тоже свои особенности"
    )
    assert _is_klipper_offtopic_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_klipper_host_question_is_chatter():
    msg = "Хост один на два принтера? Возможно прошивки на том, где работает, не конфликтуют с версией клиппера"
    assert _is_klipper_offtopic_sidebar(msg)


def test_gas_station_joke_is_chatter():
    msg = "В фильтрах выбираешь 95, далее жмешь слева вверху азс и выбирает только заправки где есть бензин"
    assert _is_offtopic_gas_station_joke(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_vague_fix_without_symptom():
    assert _is_vague_fix_without_symptom("Подскажите как это исправить?")


def test_speed_poll_is_chatter():
    msg = "А есть тут шаришие в клипере?"
    assert _is_community_experience_poll(msg)


def test_real_nozzle_key_not_klipper():
    assert not _is_klipper_offtopic_sidebar("Какой ключ нужен для сопла s1?")


def test_real_thermistor_not_gas_joke():
    assert not _is_offtopic_gas_station_joke(
        "термодатчик не мог умереть при печати petg?"
    )
'''


def patch_manual_qa() -> None:
    entries = json.loads(QA_PATH.read_text(encoding="utf-8"))
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

    if "_is_klipper_offtopic_sidebar" not in t:
        anchor = "def _is_vague_fix_without_symptom(text: str) -> bool:"
        t = t.replace(anchor, NEW_BANTER_FN.lstrip("\n") + anchor)

    # gratitude / thanks meta
    old = (
        '    helps = bool(re.search(r"\\b(?:помогает|выручает|спасает)\\b", t))\n'
        "    meta = bool(\n"
        '        re.search(r"\\b(?:админ\\w*|бот\\w*|когда\\s+админ|свободн\\w*\\s+доступ)\\b", t)\n'
        '        or re.search(r"\\bон\\s+очень\\s+часто\\b", t)\n'
        "    )\n"
        "    return helps and meta"
    )
    new = (
        '    helps = bool(re.search(r"\\b(?:помогает|выручает|спасает)\\b", t))\n'
        "    thanks = bool(\n"
        '        re.search(r"\\bспасибо\\b", t)\n'
        '        and re.search(r"\\b(?:объяснил|объясн|ясн\\w*\\s+ответ|помог)\\w*\\b", t)\n'
        "    )\n"
        "    meta = bool(\n"
        '        re.search(r"\\b(?:админ\\w*|бот\\w*|когда\\s+админ|свободн\\w*\\s+доступ)\\b", t)\n'
        '        or re.search(r"\\bон\\s+очень\\s+часто\\b", t)\n'
        "    )\n"
        "    return (helps and meta) or thanks"
    )
    if old in t:
        t = t.replace(old, new)

    # vague fix
    old = '    if not re.search(r"\\bкак\\s+такое\\s+чин\\w*\\b", t):\n        return False'
    new = (
        '    if not re.search(r"\\bкак\\s+(?:такое\\s+)?чин\\w*\\b", t) and not re.search(\n'
        '        r"\\bкак\\s+это\\s+исправ\\w*\\b", t\n'
        "    ):\n"
        "        return False"
    )
    if old in t:
        t = t.replace(old, new)

    # community poll
    old = '        r"воском\\s+на\\s+фдм"\n        r")\\b",'
    new = (
        '        r"воском\\s+на\\s+фдм|"\n'
        '        r"на\\s+каких\\s+скорост\\w*\\s+печата|"\n'
        '        r"шариш\\w*\\s+в\\s+клиппер|"\n'
        '        r"есть\\s+тут\\s+шариш"\n'
        '        r")\\b",'
    )
    if old in t:
        t = t.replace(old, new)

    # general sidebar
    old = '        r"\\bпригласишь\\s+посмотреть\\b",\n    )'
    new = (
        '        r"\\bпригласишь\\s+посмотреть\\b",\n'
        '        r"\\bбрал\\s+самые\\s+дешев\\w*\\s+на\\s+озон\\b",\n'
        '        r"\\bлегенькие\\s+как\\s+картонн\\w*\\b",\n'
        '        r"\\bне\\s+нашел\\s+подобн\\w*\\s+набор\\b",\n'
        '        r"\\bполтора\\s+предмета\\b",\n'
        '        r"\\bпот[её]к\\s+второй\\s+хот\\b",\n'
        '        r"\\bвидал\\s+как\\s+быстро\\b",\n'
        '        r"\\bкак\\s+в\\s+клубе\\s+на\\s+озон\\b",\n'
        '        r"\\bцену\\s+доставки\\s+в\\s+стоимость\\b",\n'
        '        r"\\bфантастически\\s+низк\\w*\\s+цен\\b",\n'
        '        r"\\bправильно\\s+инженер\\b",\n'
        '        r"\\bпосмотрим\\s+че\\s+получится\\b",\n'
        '        r"\\bсчет\\s+отредактирован\\b",\n'
        '        r"\\bпещерн\\w*\\s+принтер\\b",\n'
        '        r"\\bпластик\\s+авно\\b",\n'
        '        r"\\bкосмическ\\w*\\s+аппарат\\b",\n'
        '        r"\\bне\\s+наш\\s+метод\\b",\n'
        '        r"\\bгде-то\\s+ссылка\\s+есть\\b",\n'
        '        r"\\bвыкинуть\\s+пора\\b",\n'
        '        r"\\bк\\s+пластине\\s+не\\s+липнет\\b",\n'
        '        r"\\bчто\\s+то\\s+как\\s+то\\s+не\\s+очень\\b",\n'
        '        r"\\bчто\\s+за\\s+клей\\s+использовал\\b",\n'
        '        r"\\bчто\\s+за\\s+модель\\s*,\\s*можно\\s+фото\\b",\n'
        '        r"\\bвася\\s+на\\s+клей\\b",\n'
        '        r"\\bа\\s+где\\s+такой\\s+нашел\\b",\n'
        '        r"\\bа\\s+фото\\s+где\\b",\n'
        '        r"\\bстолкнулся\\s+с\\s+приколом\\b",\n'
        '        r"\\bспоришь\\s+с\\s+ними\\b",\n'
        '        r"\\bобъясните\\s+человеку\\s+в\\s+техничк\\b",\n'
        '        r"\\bперешив\\w*\\b",\n'
        "    )"
    )
    if old in t:
        t = t.replace(old, new)

    # thread humor
    old = '    if re.search(r"\\bанекдот\\b", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bанекдот\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bпещерн\\w*\\s+принтер\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bрули\\s+перешив\\b", t) or re.search(r"\\bруки\\s+перешив\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # continuation filler
    old = '    if re.search(r"\\bпечатат\\w*\\s+прям\\s+или\\s+как\\b", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bпечатат\\w*\\s+прям\\s+или\\s+как\\b", t):\n'
        "        return True\n"
        '    if re.match(r"^ааа\\s*да\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^чтобы\\s+что\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^вряд-?ли\\s*,\\s*а\\s+с\\s+какой\\s+целью", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # bare fragment
    old = '    if re.match(r"^у\\s+меня\\s+как\\s+слева", t):\n        return True\n    return False'
    new = (
        '    if re.match(r"^у\\s+меня\\s+как\\s+слева", t):\n'
        "        return True\n"
        '    if re.match(r"^так\\s*,\\s*а\\s+что\\s+это\\s*\\??$", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # firmware gossip
    old = '    if re.search(r"\\bоткатывать\\s+до\\s+стабильн", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bоткатывать\\s+до\\s+стабильн", t):\n'
        "        return True\n"
        '    if re.search(r"\\b2\\.\\d+\\.\\d+\\.\\d+\\b", t) and re.search(\n'
        '        r"\\b(?:балуюсь|проблем\\s+не\\s+было|не\\s+натыкал|скачать)\\w*\\b", t\n'
        "    ):\n"
        "        return True\n"
        '    if re.search(r"\\bклиппер\\s+обновил\\b", t) and re.search(r"\\b(?:мцу|mcu|картограф)\\w*\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # casual advice — klipper MCU
    old = (
        '    if re.search(\n'
        '        r"\\b(?:поставьте|переставьте|загрузите|переставь|поменяйте|поменяй)\\b",\n'
        "        t,\n"
        '    ) and not re.search(r"\\b(?:помогите|подскаж)\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    new = (
        '    if re.search(\n'
        '        r"\\b(?:поставьте|переставьте|загрузите|переставь|поменяйте|поменяй)\\b",\n'
        "        t,\n"
        '    ) and not re.search(r"\\b(?:помогите|подскаж)\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bклиппер\\s+обновил\\b", t) and re.search(r"\\b(?:мцу|mcu|собирай)\\w*\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # print task planning
    old = (
        '    if re.search(r"\\b(?:надо|нужно)\\s+напечатать\\b", t) and not re.search(\n'
        '        r"\\bкак\\s+напечатать\\b", t\n'
        "    ):\n"
        "        return True"
    )
    new = (
        '    if re.search(r"\\b(?:надо|нужно)\\s+напечатать\\b", t) and not re.search(\n'
        '        r"\\bкак\\s+напечатать\\b", t\n'
        "    ):\n"
        "        return True\n"
        '    if re.search(r"\\bзаказал\\b", t) and re.search(r"\\b(?:едет|замоделир|тпу|впервые)\\w*\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bвремязатрат\\w*\\s+на\\s+проектирован\\w*\\b", t):\n'
        "        return True"
    )
    if old in t:
        t = t.replace(old, new)

    # competitor — bambu key question
    old = '    if len(t.split()) > 4:\n        return False'
    new = '    if len(t.split()) > 8:\n        return False'
    if "_is_bare_competitor_printer_question" in t:
        # only replace inside that function — use more context
        old2 = (
            '    # Только очень короткие сообщения (1–4 слова)\n'
            "    if len(t.split()) > 4:\n"
            "        return False"
        )
        new2 = (
            "    # Короткие сообщения о конкурентах (до 8 слов)\n"
            "    if len(t.split()) > 8:\n"
            "        return False"
        )
        if old2 in t:
            t = t.replace(old2, new2)

    # thread printing tip — experience share
    old = '    if re.search(r"\\bу\\s+меня\\s+(?:есть|стоит|имеется|лежат|лежит)\\b", tl):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bу\\s+меня\\s+(?:есть|стоит|имеется|лежат|лежит)\\b", tl):\n'
        "        return True\n"
        '    if re.search(r"\\b(?:пластик\\s+дорогой|перекрут\\w*\\s+прутк|лидер-3d)\\b", tl):\n'
        "        return True\n"
        '    if re.search(r"\\b(?:хот\\s+не\\s+так|регулировк\\w*\\s+лап)\\b", tl):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # technical opinion — TPU shore / nozzle width sidebar
    old = (
        "        if modeling_ctx and opinion_marker:\n"
        "            return True\n"
        '    if re.search(r"\\b(?:ретракт|откат)\\w*\\b", t) and re.search(\n'
        '        r"\\b(?:сток|по\\s+умолчан|зачем\\s+трогать|норм\\s+стоят)\\w*\\b", t\n'
        "    ):\n"
        "        return True\n"
        "    return False\n\n\ndef _is_technical_observation_sharing"
    )
    new = (
        "        if modeling_ctx and opinion_marker:\n"
        "            return True\n"
        '    if re.search(r"\\b(?:ретракт|откат)\\w*\\b", t) and re.search(\n'
        '        r"\\b(?:сток|по\\s+умолчан|зачем\\s+трогать|норм\\s+стоят)\\w*\\b", t\n'
        "    ):\n"
        "        return True\n"
        '    if re.search(r"\\b95а\\b", t) and re.search(r"\\b(?:мягк|эластичн|желей)\\w*\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\b0\\.8\\s+сопл", t) and re.search(r"\\b(?:периметр|монолит)\\w*\\b", t):\n'
        "        return True\n"
        "    return False\n\n\ndef _is_technical_observation_sharing"
    )
    if old in t:
        t = t.replace(old, new)

    # profanity outburst — extend for "я хуй знает"
    old = '    if re.search(r"\\bнахуй\\b", t) and not _HELP_GUARD_RE.search(t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bнахуй\\b", t) and not _HELP_GUARD_RE.search(t):\n'
        "        return True\n"
        '    if re.search(r"\\bхуй\\s+знает\\b", t) and not re.search(r"\\b(?:помогите|подскаж)\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    for name in ("_is_klipper_offtopic_sidebar", "_is_offtopic_gas_station_joke"):
        old_import = "    _is_personal_upholstery_project_sidebar,\n)"
        new_import = f"    _is_personal_upholstery_project_sidebar,\n    {name},\n)"
        if name not in t and old_import in t:
            t = t.replace(old_import, new_import, 1)
            old_import = f"    _is_personal_upholstery_project_sidebar,\n    {name},\n)"
    old_chain = "        or _is_personal_upholstery_project_sidebar(text)\n    )"
    new_chain = (
        "        or _is_personal_upholstery_project_sidebar(text)\n"
        "        or _is_klipper_offtopic_sidebar(text)\n"
        "        or _is_offtopic_gas_station_joke(text)\n"
        "    )"
    )
    if "_is_klipper_offtopic_sidebar(text)" not in t and old_chain in t:
        t = t.replace(old_chain, new_chain)
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    additions = (
        "    _is_klipper_offtopic_sidebar,\n"
        "    _is_offtopic_gas_station_joke,\n"
    )
    old = "    _is_personal_upholstery_project_sidebar,\n    _is_vague_fix_without_symptom,\n"
    new = "    _is_personal_upholstery_project_sidebar,\n" + additions + "    _is_vague_fix_without_symptom,\n"
    if "_is_klipper_offtopic_sidebar" not in t and old in t:
        t = t.replace(old, new)
    INIT_PATH.write_text(t, encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def clear_missed() -> None:
    MISSED_PATH.write_text("[]\n", encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    write_tests()
    clear_missed()
    print(f"Added {len(NEW_QA)} manual_qa + banter patches; missed_questions cleared")


if __name__ == "__main__":
    main()
