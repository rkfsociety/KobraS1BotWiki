"""Разбор missed_questions.json (2026-06-30): manual_qa + эвристики + очистка очереди."""
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
TEST_PATH = ROOT / "tests" / "test_missed_jun30_chatter.py"

NEW_QA = [
    {
        "keys": [
            "закончился один цвет",
            "сохранить печать",
            "многоцвет петг закончился",
            "цвет будет только завтра",
            "пауза многоцвет ночь",
            "филамент закончился завтра",
        ],
        "title": "Многоцвет: закончился цвет, продолжить завтра",
        "answer": (
            "Если в многоцветной печати закончился один цвет и докупите только на следующий день:\n\n"
            "• Не выключайте принтер из розетки — при обрыве питания на печати с ACE сработает "
            "возобновление после включения (Power Loss Resume).\n"
            "• Датчик окончания нити обычно ставит паузу; стол остаётся подогретым — это главное для PETG.\n"
            "• Уберите сквозняки, закройте камеру, чтобы деталь не остыла.\n"
            "• На следующий день: просушите филамент, загрузите в тот же слот ACE, возобновите печать с экрана.\n\n"
            "Отдельно «выставлять температуру в камере» на ночь не нужно — в паузе держится подогрев стола. "
            "Не двигайте стол и не трогайте Z.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/quick-start-guide"
        ),
    },
    {
        "keys": [
            "что такое откаты",
            "не понимаю что такое откаты",
            "ретракт что это",
            "откаты по умолчанию",
            "значения откатов норм",
        ],
        "title": "Что такое откаты (ретракт)",
        "answer": (
            "Откаты (ретракт, retraction) — насколько экструдер оттягивает филамент назад, когда сопло "
            "перемещается по пустому ходу. Нужно, чтобы не тянуть нитку по модели и не оставлять «сопли».\n\n"
            "В стоковых профилях Anycubic/Orca для Kobra S1 обычно нормальные стартовые значения — "
            "менять без причины не нужно. Подкручивайте, если видите нити между деталями или подтёки на стенках.\n\n"
            "Тест откатов в слайсере — для подбора под ваш пластик и скорость; новичку не обязателен.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/software-and-app/anycubicslicer"
        ),
    },
    {
        "keys": [
            "везде для бамбулаб",
            "найти для аникубика",
            "профиль для anycubic",
            "настройки для кобры в слайсере",
            "где профиль kobra s1",
        ],
        "title": "Профили Anycubic в слайсере (не Bambu Lab)",
        "answer": (
            "В Orca / Anycubic Slicer Next при добавлении принтера выберите Kobra S1 или S1 Combo "
            "(не Bambu Lab). Профили материалов — в списке филаментов с префиксом Anycubic или Generic; "
            "можно импортировать официальный bundle с wiki.\n\n"
            "Профили Bambu к Kobra не подходят один в один: другая кинематика, ACE, температуры и обдув.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/software-and-app/anycubicslicer"
        ),
    },
    {
        "keys": [
            "где наработку смотреть",
            "наработку смотреть kobra s1",
            "сколько часов печатал принтер",
            "часов показывает облако",
            "подсчёт в принтере",
            "наработка печати по часам",
        ],
        "title": "Где смотреть наработку (часы печати) Kobra S1",
        "answer": (
            "На экране принтера: Настройки (Settings) → Устройство (Device) → Информация о принтере "
            "(Printer information). Там же версия прошивки; на части прошивок есть счётчик наработки.\n\n"
            "В приложении Anycubic / облаке после привязки аккаунта показываются часы печати через облако — "
            "они часто меньше реальных: локальная печать с USB и LAN без облака в статистику приложения "
            "может не попадать. Через VPN видите тот же облачный счётчик, не полную наработку с принтера.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"
        ),
    },
]

NEW_BANTER_FN = '''

def _is_offtopic_work_life_sidebar(text: str) -> bool:
    """Работа, сварка, заводы, карьера — без запроса по принтеру."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(
        r"\\b(?:"
        r"как\\s+(?:настро|откалибр|почин|сделать|подключ|обнов|прошить)|"
        r"где\\s+(?:найти|смотреть|взять|скачать)|"
        r"помогите|подскаж|не\\s+работает|ошибк\\w*|"
        r"наработк\\w*|часов\\s+печат|подсч[её]т"
        r")\\b",
        t,
    ):
        return False
    work_ctx = bool(
        re.search(
            r"\\b(?:"
            r"завод\\w*|сварщик\\w*|сварк\\w*|литейщик\\w*|айтишник\\w*|токарник\\w*|"
            r"слесар\\w*|цех\\w*|аргоном|электрод\\w*|корефан\\w*|кореш\\w*|удалёнк\\w*|"
            r"проектн\\w*\\s+институт|сокращен\\w*\\s+штата|первая\\s+работа|"
            r"разочарован\\w*|патриот\\w*|львов\\w*|спб\\b|санкт[\\s-]?петербург|"
            r"ликеро[\\s-]?марочн\\w*|маск\\w*\\s+панорамн\\w*|краг\\w*|"
            r"станки\\s+японск\\w*|школьн\\w*\\s+токарник"
            r")\\b",
            t,
        )
    )
    if not work_ctx:
        return False
    if _PRINT_CTX_RE.search(t) or _printer_mentioned(text):
        return False
    return True
'''

TEST_CONTENT = '''"""Регрессии по разбору missed_questions 2026-06-30."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_non_wiki_chatter_message,
    _is_offtopic_work_life_sidebar,
)


def test_multicolor_pause_overnight_manual_qa():
    msg = (
        "Сейчас печатал многоцвет петг и закончился один цвет. Будет только завтра. "
        "Как максимально сохранить печать?"
    )
    assert find_manual_qa_answer(msg)


def test_retraction_manual_qa():
    assert find_manual_qa_answer("я чайник и не понимаю что такое откаты")


def test_anycubic_profile_manual_qa():
    assert find_manual_qa_answer("тут везде для бамбулаб. А как найти для аникубика?")


def test_print_hours_manual_qa():
    assert find_manual_qa_answer("где у Кобры S1 наработку смотреть")
    assert find_manual_qa_answer("Ну через ВПН подключил но чёт там 47 часов показывает")


def test_money_spam_is_chatter():
    assert _is_non_wiki_chatter_message("НУЖНЫ БАБКИ ?? ПИШИ МНЕ")


def test_long_anecdote_is_chatter():
    snippet = "В проектный институт спустили сверху разнарядку провести сокращение штата"
    assert _is_conversational_chatter(snippet + " " + "ЖОРы" * 20)


def test_ssh_community_poll_is_chatter():
    msg = "есть у кого-то ssh сервер для 2.7.2.7? чот у меня старый не работает"
    assert _is_non_wiki_chatter_message(msg)


def test_welding_factory_chat_is_chatter():
    msg = "У меня кореш учился на сварщика и там препод говорил про аргон"
    assert _is_offtopic_work_life_sidebar(msg)
    assert _is_conversational_chatter(msg)


def test_retraction_opinion_is_chatter():
    msg = "А вообще зачем трогать ретракты ? Они в стоке норм стоят"
    assert _is_non_wiki_chatter_message(msg)


def test_fragment_clog_is_chatter():
    assert _is_non_wiki_chatter_message("если чуть забито то из-за этого может быть?")


def test_real_retraction_help_not_chatter():
    assert not _is_non_wiki_chatter_message("как настроить откаты на kobra s1?")
    assert not _is_non_wiki_chatter_message("подскажите что такое откаты в слайсере")
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

    if "_is_offtopic_work_life_sidebar" not in t:
        anchor = "def _is_vague_fix_without_symptom(text: str) -> bool:"
        t = t.replace(anchor, NEW_BANTER_FN.lstrip("\n") + anchor)

    # money spam
    old = '        or re.search(r"\\bне\\s+хватает\\s+бабла\\b", t)\n    )'
    new = (
        '        or re.search(r"\\bне\\s+хватает\\s+бабла\\b", t)\n'
        '        or re.search(r"\\bнужн\\w*\\s+бабк", t)\n'
        '        or (re.search(r"\\bпиши\\s+мне\\b", t) and "?" in text)\n'
        "    )"
    )
    if old in t:
        t = t.replace(old, new)

    # thread humor — long anecdote
    old = '    if re.search(r"\\bзаберу\\s+кобр\\w*\\s+за\\s+\\d+\\s+как\\s+надоест", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bзаберу\\s+кобр\\w*\\s+за\\s+\\d+\\s+как\\s+надоест", t):\n'
        "        return True\n"
        '    if len(t) > 200 and re.search(r"\\b(?:проектн\\w*\\s+институт|сокращен\\w*\\s+штата|жор\\w*|лор\\w*|чижик)\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bанекдот\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # community poll
    old = '        r"вопрос\\s+не\\s+по\\s+тебе"\n        r")\\b",'
    new = (
        '        r"вопрос\\s+не\\s+по\\s+тебе|"\n'
        '        r"есть\\s+у\\s+кого[\\s-]?(?:то|нибудь)?|"\n'
        '        r"ssh\\s+сервер|"\n'
        '        r"печатал\\s+кто|"\n'
        '        r"воском\\s+на\\s+фдм"\n'
        '        r")\\b",'
    )
    if old in t:
        t = t.replace(old, new)

    # general sidebar patterns
    old = '        r"\\bбиметалл\\s+как\\s+выглядит\\b",\n    )'
    new = (
        '        r"\\bбиметалл\\s+как\\s+выглядит\\b",\n'
        '        r"\\bзасран\\w*\\b",\n'
        '        r"\\bмы\\s+и\\s+так\\s+знали\\b",\n'
        '        r"\\bкингрун\\w*\\s+топ\\b",\n'
        '        r"\\bнит\\b.*\\bговно\\b",\n'
        '        r"\\bчто\\s+то\\s+на\\s+безумном\\b",\n'
        '        r"\\bзачем\\s+это\\s+посредничество\\b",\n'
        '        r"\\bшпатель\\s+с\\s+чиди\\b",\n'
        '        r"\\bноу\\s+нейм\\b",\n'
        '        r"\\bкак\\s+у\\s+вас\\s*\\??\\s*$",\n'
        '        r"\\bвот\\s+и\\s+ответ\\s+почему\\b",\n'
        '        r"\\bскажите\\s+где\\s+я\\s+не\\s+прав\\b",\n'
        '        r"\\bневажно\\s+где\\s+покупать\\b",\n'
        '        r"\\bна\\s+озоне\\s+эта\\s+же\\s+цена\\b",\n'
        '        r"\\bлитейщик\\w*\\b",\n'
        '        r"\\bфрезернуть\\s+к\\s+приемной\\b",\n'
        '        r"\\bпродавливаемая\\s+потоком\\b",\n'
        '        r"\\bхз\\s+почему\\b",\n'
        '        r"\\bно\\s+знаю\\s+что\\s+такое\\s+есть\\b",\n'
        '        r"\\bэто\\s+с\\s+чего\\s+бы\\b",\n'
        '        r"\\bв\\s+итоге\\s+все\\s+сломал\\b",\n'
        '        r"\\bщас\\s+вася\\s+придет\\b",\n'
        '        r"\\bда\\s+чего\\s+его\\s+смотреть\\b",\n'
        '        r"\\bмакита\\s+с\\s+озона\\b",\n'
        '        r"\\bпригласишь\\s+посмотреть\\b",\n'
        "    )"
    )
    if old in t:
        t = t.replace(old, new)

    # continuation filler
    old = '    if re.search(r"\\bтот\\s+кто\\s+писал\\b", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bтот\\s+кто\\s+писал\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bпросто\\s+из-за\\s+того\\s+что\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bразве\\s+нет\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # technical opinion — retraction stock
    old = "        if modeling_ctx and opinion_marker:\n            return True\n    return False\n\n\ndef _is_technical_observation_sharing"
    new = (
        "        if modeling_ctx and opinion_marker:\n"
        "            return True\n"
        '    if re.search(r"\\b(?:ретракт|откат)\\w*\\b", t) and re.search(\n'
        '        r"\\b(?:сток|по\\s+умолчан|зачем\\s+трогать|норм\\s+стоят)\\w*\\b", t\n'
        "    ):\n"
        "        return True\n"
        "    return False\n\n\ndef _is_technical_observation_sharing"
    )
    if old in t:
        t = t.replace(old, new)

    # bare fragments
    old = '    if wc <= 4 and re.match(r"^как\\s+и\\b", t):\n        return True\n    return False'
    new = (
        '    if wc <= 4 and re.match(r"^как\\s+и\\b", t):\n'
        "        return True\n"
        '    if re.match(r"^если\\s+чуть\\s+забит", t):\n'
        "        return True\n"
        '    if re.match(r"^тест\\s+откатов\\s+для\\s+кого", t):\n'
        "        return True\n"
        '    if re.match(r"^у\\s+меня\\s+как\\s+слева", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # social location
    old = '    if re.search(r"\\bв\\s+как(?:ом|ой)\\s+(?:городе|регионе|стране)\\b", t):\n        return True\n    return False'
    new = (
        '    if re.search(r"\\bв\\s+как(?:ом|ой)\\s+(?:городе|регионе|стране)\\b", t):\n'
        "        return True\n"
        '    if re.search(r"\\bточно\\s+из\\s+(?:спб|мск|москв|питер|санкт)\\b", t):\n'
        "        return True\n"
        "    return False"
    )
    if old in t:
        t = t.replace(old, new)

    # third party brands — kingrun, nite
    old = (
        '            r"bambu\\s*lab|бамбул\\w*|бамбу\\w*|"\n'
        '            r"esun|e\\s*sun|sunlu|eryone|polymaker|prusament"\n'
        '            r")\\b",'
    )
    new = (
        '            r"bambu\\s*lab|бамбул\\w*|бамбу\\w*|"\n'
        '            r"esun|e\\s*sun|sunlu|eryone|polymaker|prusament|"\n'
        '            r"kingrun|кингрун|\\bnit\\b|нит\\b"\n'
        '            r")\\b",'
    )
    if old in t:
        t = t.replace(old, new)

    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    old = "        or _is_vague_fix_without_symptom(text)\n    )"
    new = "        or _is_vague_fix_without_symptom(text)\n        or _is_offtopic_work_life_sidebar(text)\n    )"
    if "_is_offtopic_work_life_sidebar" not in t and old in t:
        t = t.replace(old, new)
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    old = "    _is_offbeat_social_banter,\n"
    new = "    _is_offbeat_social_banter,\n    _is_offtopic_work_life_sidebar,\n"
    if "_is_offtopic_work_life_sidebar" not in t and old in t:
        t = t.replace(old, new)
    INIT_PATH.write_text(t, encoding="utf-8")


def clear_missed() -> None:
    MISSED_PATH.write_text("[]\n", encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    write_tests()
    clear_missed()
    print("manual_qa:", len(NEW_QA), "entries; missed_questions cleared")


if __name__ == "__main__":
    main()
