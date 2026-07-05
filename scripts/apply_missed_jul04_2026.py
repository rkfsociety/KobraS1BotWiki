"""Разбор missed_questions.json (2026-07-04): manual_qa + эвристики + очистка очереди."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
MISSED_PATH = ROOT / "data" / "missed_questions.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEST_PATH = ROOT / "tests" / "test_missed_jul04_chatter.py"

NEW_QA = [
    {
        "keys": [
            "ключ нужен для сопла",
            "какой ключ для сопла",
            "размер ключа сопла",
            "ключ для смены сопла",
            "какой ключ нужен для сопла",
        ],
        "title": "Ключ для сопла Kobra S1",
        "answer": (
            "В комплекте с Kobra S1 идёт ключ для сопла (под гайку нагревательного блока, "
            "обычно 7 мм — уточните по вашей ревизии).\n\n"
            "Замена: прогрейте сопло до рабочей температуры материала, выключите питание, "
            "придерживайте блок ключом из комплекта и открутите сопло против часовой. "
            "Не тяните «на холодную» — можно сорвать резьбу.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/nozzle-silicone-replacement-guide"
        ),
    },
    {
        "keys": [
            "замедления отключены",
            "замедление при охлаждении",
            "slow down охлажден",
            "охлаждении прутка замедлен",
            "галочка стоит охлажден",
        ],
        "title": "Замедление при охлаждении (Slow Down)",
        "answer": (
            "В Orca / Anycubic Slicer в настройках охлаждения есть «Замедление для слоя» "
            "(Slow Down for layer cooling): принтер снижает скорость, если слою не хватает "
            "времени на обдув.\n\n"
            "• Галочка «отключить замедление» — печать быстрее, но мелкие детали и мосты "
            "могут плавиться.\n"
            "• Для тонких деталей и PETG обычно лучше оставить замедление включённым.\n"
            "• Минимальное время слоя (Minimum layer time) работает вместе с этой опцией.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/software-and-app/anycubicslicer"
        ),
    },
]

KEY_UPDATES: dict[str, list[str]] = {
    "Компенсация резонанса": [
        "резонанс",
        "борьба с резонансом",
        "гудит и волны",
        "секрет борьбы с резонансом",
        "борьбы с резонансом",
    ],
    "Обновление прошивки": [
        "где скачать прошивку",
        "есть где скачать 2.6",
        "скачать 2.6.0.0",
        "скачать прошивку 2.6",
    ],
    "Температуры PETG": [
        "50 градусов на petg",
        "всм 50 градусов на petg",
    ],
}

NEW_BANTER_FN = '''

def _is_offtopic_auto_sidebar(text: str) -> bool:
    """Автомобильный оффтоп: марки, двигатели, цены машин — без запроса по принтеру."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(
        r"\\b(?:"
        r"как\\s+(?:настро|откалибр|почин|сделать|подключ|обнов|прошить)|"
        r"где\\s+(?:найти|смотреть|взять|скачать)|"
        r"помогите|подскаж|не\\s+работает|ошибк\\w*"
        r")\\b",
        t,
    ):
        return False
    auto_ctx = bool(
        re.search(
            r"\\b(?:"
            r"ваг\\w*|volkswagen|бмв|bmw|логан|sandero|рено|renault|пасат|passat|"
            r"арт[eé]on|arteon|фокус\\s*3|ford|ф4р|dci|атмо|капиталк|"
            r"бензин|кобыл\\w*|ньютon|двигател\\w*|тачк\\w*|миллионник|"
            r"восьмиклоп|дорест|сандero|шкода|skoda|octavia|октави|"
            r"джил\\w*|geely|dongfeng|донгфенг|voyah|войя|деpal|епай|"
            r"лada|лада\\s+[,]|самокат\\s+свой\\s+купить|"
            r"китайц\\w*\\s+делают\\s+тач|обслуживан\\w*\\s+как\\s+.*\\bваг\\w*|"
            r"ездил\\w*|\\bезж\\w*|артеон|пассат|"
            r"азс\\b|заправк\\w*|"
            r"машин\\w*\\s+(?:убив|цен|скин)|"
            r"авно\\s+рено|левосторонн\\w*\\s+сверл"
            r")\\b",
            t,
        )
        or (
            re.search(r"\\bмашин\\w*\\b", t)
            and re.search(r"\\b(?:убив|цен|скин|плох|хорош|нов\\w+|купить|дорог)\\w*\\b", t)
        )
    )
    if not auto_ctx:
        return False
    if _PRINT_CTX_RE.search(t) or _printer_mentioned(text):
        return False
    return True
'''

TEST_CONTENT = '''"""Регрессии по разбору missed_questions 2026-07-04."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer
from app.bot.text_heuristics import (
    _is_non_wiki_chatter_message,
    _is_offtopic_auto_sidebar,
)


def test_resonance_manual_qa():
    msg = (
        "Люди, у меня странный вопрос. Есть на s1 какой-то секретный секрет борьбы с резонансом? "
        "Я уже ремни перетянул, и калибровку калибровал, и смазал всё, а всё равно на скоростях "
        "60-100 гудит и волны пускает"
    )
    assert find_manual_qa_answer(msg)


def test_nozzle_wrench_manual_qa():
    assert find_manual_qa_answer("Какой ключ нужен для сопла s1?")


def test_cooling_slowdown_manual_qa():
    msg = "В охлаждении прутка - замедления отключены ? ( галочка стоит?)"
    assert find_manual_qa_answer(msg)


def test_firmware_download_manual_qa():
    assert find_manual_qa_answer("есть где скачать 2.6.0.0?")


def test_logan_car_chat_is_chatter():
    assert _is_offtopic_auto_sidebar("Логан и Сандero плохие машины?)")


def test_vw_engine_chat_is_chatter():
    assert _is_offtopic_auto_sidebar("Восьмиклоп это как 1.6 атмо у вага. Никуда не разгоняется")


def test_benzin_nostalgia_is_chatter():
    assert _is_offtopic_auto_sidebar("Я еще помню времена до короны когда бензин стоил 53 рубля")


def test_speed_poll_is_chatter():
    assert _is_non_wiki_chatter_message("всем привет А кто на каких скоростях печатает на кубике?")


def test_real_nozzle_help_not_chatter():
    assert not _is_non_wiki_chatter_message("Какой ключ нужен для сопла s1?")
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
    for e in entries:
        title = e.get("title") or ""
        for substr, keys in KEY_UPDATES.items():
            if substr in title:
                existing = {k.lower() for k in e.get("keys", []) if isinstance(k, str)}
                for k in keys:
                    if k.lower() not in existing:
                        e.setdefault("keys", []).append(k)
                        existing.add(k.lower())
    QA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_banter() -> None:
    t = BANTER_PATH.read_text(encoding="utf-8")

    if "_is_offtopic_auto_sidebar" not in t:
        anchor = "def _is_offtopic_work_life_sidebar(text: str) -> bool:"
        t = t.replace(anchor, NEW_BANTER_FN.lstrip("\n") + anchor)

    # community polls
    old = '        r"воском\\s+на\\s+фдм"\n        r")\\b",'
    new = (
        '        r"воском\\s+на\\s+фдм|"\n'
        '        r"на\\s+каких\\s+скорост\\w*\\s+печата|"\n'
        '        r"шариш\\w*\\s+в\\s+клипер|"\n'
        '        r"устанавливал\\w*\\s+.*\\bfunssor\\b|"\n'
        '        r"кто\\s+нибудь\\s+объясните\\s+человеку"\n'
        '        r")\\b",'
    )
    if old in t:
        t = t.replace(old, new)

    # general sidebar — append before closing paren of patterns tuple
    old = '        r"\\bпригласишь\\s+посмотреть\\b",\n    )'
    new = (
        '        r"\\bпригласишь\\s+посмотреть\\b",\n'
        '        r"\\bзачем\\s+мне\\s+читать\\b",\n'
        '        r"\\bна\\s+этом\\s+достижения\\s+всё\\b",\n'
        '        r"\\bочень\\s+мало\\s+кто\\s+знает\\b",\n'
        '        r"\\bкак\\s+максимум\\b",\n'
        '        r"\\bэто\\s+дешевле\\s*\\??\\s*$",\n'
        '        r"\\b959\\s+это\\s+за\\b",\n'
        '        r"\\bмало\\s+ли\\s+кто\\s+то\\s+хотел\\b",\n'
        '        r"\\bсижу\\s+думаю\\s+че\\s+отсканировать\\b",\n'
        '        r"\\bили\\s+я\\s+спал\\s+как\\s+сурок\\b",\n'
        '        r"\\bтебя\\s+не\\s+выгонят\\b",\n'
        '        r"\\bнадо\\s+что\\s+то\\s+придумать\\b",\n'
        '        r"\\bпо\\s+одному\\s+[-—]\\s+не\\s+работает\\b",\n'
        '        r"\\bспасибо,\\s+что\\s+об[ъь]яснил\\b",\n'
        '        r"\\bв\\s+продолжении\\s+флуда\\b",\n'
        '        r"\\bвряд[-\\s]?ли,\\s+а\\s+с\\s+какой\\s+целью\\b",\n'
        '        r"\\bчто\\s+было\\s+в\\s+том\\s+и\\s+рисовал\\b",\n'
        '        r"\\bкосмического\\s+аппарата\\b",\n'
        '        r"\\bне\\s+наш\\s+метод\\b",\n'
        '        r"\\bгде[-\\s]?то\\s+ссылка\\s+есть\\b",\n'
        '        r"\\bполучается\\s+цену\\s+доставки\\b",\n'
        '        r"\\bглавное\\s+правильно\\s+инженера\\b",\n'
        '        r"\\bпосмотрим\\s+че\\s+получится\\b",\n'
        '        r"\\bпещерный\\s+принтер\\b",\n'
        '        r"\\bчто\\s+то\\s+как\\s+то\\s+не\\s+очень\\b",\n'
        '        r"\\bчто\\s+за\\s+клей\\s+использовали\\b",\n'
        '        r"\\bчто\\s+за\\s+модель,\\s+можно\\s+фото\\b",\n'
        '        r"\\bэто\\s+тебя\\s+вася\\s+на\\s+клей\\b",\n'
        '        r"\\bа\\s+где\\s+такой\\s+нашел\\b",\n'
        '        r"\\bнах\\s+ты\\s+вобще\\s+с\\s+ними\\s+споришь\\b",\n'
        '        r"\\bтакую\\s+пластину\\s+как\\s+будто\\s+выкинуть\\b",\n'
        '        r"\\bк\\s+пластине\\s+не\\s+липнет\\b",\n'
        '        r"\\bфильтрах\\s+выбираешь\\s+95\\b",\n'
        '        r"\\b1300[-\\s]?1500\\s+как\\s+в\\s+клубе\\b",\n'
        '        r"\\bвидал\\s+как\\s+быстро\\b",\n'
        '        r"\\bбрал\\s+самые\\s+дешевые\\s+на\\s+озоне\\b",\n'
        '        r"\\bлегенькие\\s+как\\s+картонные\\b",\n'
        '        r"\\bиспользовано\\s+полтора\\s+предмета\\b",\n'
        '        r"\\bпотёк\\s+второй\\s+хот\\b",\n'
        '        r"\\bу\\s+бамбумодов\\s+какой\\s+размер\\b",\n'
        '        r"\\bкитайцы\\s+делают\\s+тачки\\b",\n'
        '        r"\\bрули\\s+перешив\\w*\\b",\n'
        '        r"\\bруки\\s+перешив\\w*\\b",\n'
    )'
    )
    if old in t:
        t = t.replace(old, new)

    # bare fragments
    old = '    if re.match(r"^у\\s+меня\\s+как\\s+слева", t):\n        return True\n    return False'
    new = (
        '    if re.match(r"^у\\s+меня\\s+как\\s+слева", t):\n'
        "        return True\n"
        '    if re.match(r"^а\\s+фото\\s+где\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^а\\s+аа\\s+да\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^так,\\s+а\\s+что\\s+это\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^чтобы\\s+что\\s*\\??$", t):\n'
        "        return True\n"
        '    if re.match(r"^это\\s+дешевле\\s*\\??$", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # vague fix — «как это исправить» без симптома
    old = '    return not symptom\n\n\ndef _is_bare_fragment_question'
    new = (
        "    if re.search(r\"\\bкак\\s+это\\s+исправ\\w*\\b\", t) and not symptom:\n"
        "        return True\n"
        "    return not symptom\n\n\ndef _is_bare_fragment_question"
    )
    if old in t:
        t = t.replace(old, new)

    # technical opinion — PLA brand rants
    old = "        if modeling_ctx and opinion_marker:\n            return True\n    if re.search(r\"\\b(?:ретракт|откат)\\w*\\b\", t)"
    new = (
        "        if modeling_ctx and opinion_marker:\n"
        "            return True\n"
        '    if re.search(r"\\b(?:пла|филамент)\\b", t) and re.search(\n'
        '        r"\\b(?:не\\s+ест|в\\s+помойку|фирменн\\w*|кормить)\\w*\\b", t\n'
        "    ):\n"
        "        return True\n"
        '    if re.search(r"\\b(?:ретракт|откат)\\w*\\b", t)'
    )
    if old in t:
        t = t.replace(old, new)

    # maintenance story — hotend leak, glass slip
    old = "    casual = bool(re.search(r\"\\b(?:другое\\s+дело|рука\\s+не\\s+поднял\\w*)\\b\", t))\n"
    new = (
        "    casual = bool(re.search(r\"\\b(?:другое\\s+дело|рука\\s+не\\s+поднял\\w*)\\b\", t))\n"
        "    kobra_story = bool(\n"
        '        re.search(r"\\b(?:хот\\w*|стекл\\w*)\\b", t)\n'
        '        and re.search(r"\\b(?:потек|съезж\\w*|опытом\\s+установил)\\w*\\b", t)\n'
        "    )\n"
    )
    if "kobra_story" not in t and old in t:
        t = t.replace(old, new)
        t = t.replace(
            "    return extruder_story or casual or filament_ooze_story",
            "    return extruder_story or casual or filament_ooze_story or kobra_story",
        )

    # casual advice — clipper update nag
    old = '    if re.search(\n        r"\\b(?:проклеить|промыть|продуть|прочистить|протереть|смазать|накатить|перепрошить)\\b",\n        t,\n    ):\n        return True'
    new = (
        '    if re.search(\n'
        '        r"\\b(?:проклеить|промыть|продуть|прочистить|протереть|смазать|накатить|перепрошить)\\b",\n'
        "        t,\n"
        "    ):\n"
        "        return True\n"
        '    if re.search(r"\\bклиппер\\s+обновил\\b", t) and re.search(r"\\b(?:мцу|картографер|плат\\w*\\s+голов)\\b", t):\n'
        "        return True"
    )
    if "клиппер\\s+обновил" not in t and old in t:
        t = t.replace(old, new)

    # chat meta — neighbor noise
    old = '    chat_ref = bool(re.search(r"\\bв\\s+чат\\w*\\b", t))'
    new = (
        '    chat_ref = bool(re.search(r"\\bв\\s+чат\\w*\\b", t))\n'
        '    if re.search(r"\\b(?:грохот\\w*|шум\\w*)\\b", t) and re.search(r"\\b(?:вчера|у\\s+вас\\s+там)\\b", t):\n'
        "        return True"
    )
    if "грохот" not in t.split("def _is_chat_past_incident_recollection")[1].split("def ")[0]:
        t = t.replace(old, new, 1)

    # filament brand social — price opinion
    old = '        or re.search(r"\\bцвет\\s+прям\\s+\\w+.*что\\s+за\\s+пластик", t)\n    )'
    new = (
        '        or re.search(r"\\bцвет\\s+прям\\s+\\w+.*что\\s+за\\s+пластик", t)\n'
        '        or re.search(r"\\b\\d+\\s+рубл\\w*\\s+за\\s+катушк", t)\n'
        '        or re.search(r"\\bфантастическ\\w*\\s+низк\\w*\\s+цен", t)\n'
        "    )"
    )
    if "фантастическ" not in t:
        t = t.replace(old, new)

    # firmware gossip — version ask without help (experience share)
    old = '    if re.search(r"\\bоткатывать\\s+до\\s+стабильн", t):\n        return True\n    return False\n\n\ndef _is_offtopic_news_or_shop_meta'
    new = (
        '    if re.search(r"\\bоткатывать\\s+до\\s+стабильн", t):\n'
        "        return True\n"
        '    if re.search(r"\\b2\\.\\d+\\.\\d+\\.\\d+\\b", t) and re.search(r"\\b(?:балуюсь|проблем\\s+не\\s+было|не\\s+утверждаю)\\b", t):\n'
        "        return True\n"
        "    return False\n\n\ndef _is_offtopic_news_or_shop_meta"
    )
    if "балуюсь" not in t:
        t = t.replace(old, new)

    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    old = "        or _is_offtopic_work_life_sidebar(text)\n        or _is_figurative_mood_remark(text)\n    )"
    new = (
        "        or _is_offtopic_work_life_sidebar(text)\n"
        "        or _is_offtopic_auto_sidebar(text)\n"
        "        or _is_figurative_mood_remark(text)\n"
        "    )"
    )
    if "_is_offtopic_auto_sidebar" not in t and old in t:
        t = t.replace(old, new)
    # import in filter from banter
    old_imp = "    _is_offtopic_work_life_sidebar,\n"
    new_imp = "    _is_offtopic_work_life_sidebar,\n    _is_offtopic_auto_sidebar,\n"
    if "_is_offtopic_auto_sidebar" not in t and old_imp in t:
        t = t.replace(old_imp, new_imp)
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    old = "    _is_offtopic_work_life_sidebar,\n"
    new = "    _is_offtopic_work_life_sidebar,\n    _is_offtopic_auto_sidebar,\n"
    if "_is_offtopic_auto_sidebar" not in t and old in t:
        t = t.replace(old, new)
    INIT_PATH.write_text(t, encoding="utf-8")


def patch_text_heuristics() -> None:
    th = ROOT / "app" / "bot" / "text_heuristics.py"
    t = th.read_text(encoding="utf-8")
    old = "    _is_offtopic_work_life_sidebar,\n"
    new = "    _is_offtopic_work_life_sidebar,\n    _is_offtopic_auto_sidebar,\n"
    if "_is_offtopic_auto_sidebar" not in t and old in t:
        t = t.replace(old, new)
    th.write_text(t, encoding="utf-8")


def clear_missed() -> None:
    MISSED_PATH.write_text("[]\n", encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    patch_text_heuristics()
    write_tests()
    clear_missed()
    print("manual_qa:", len(NEW_QA), "new; missed_questions cleared")


if __name__ == "__main__":
    main()
