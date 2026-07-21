"""Разбор missed_questions (2026-07-21): manual_qa + эвристики + очистка очереди."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
MISSED_PATH = ROOT / "data" / "missed_questions.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEXT_PATH = ROOT / "app" / "bot" / "text_heuristics.py"
TEST_PATH = ROOT / "tests" / "test_missed_jul21_chatter.py"
BANTER_SNIPPET_PATH = ROOT / "scripts" / "jul21_banter_functions.py"

NEW_QA = [
    {
        "keys": [
            "крайнее положение по оси",
            "концевик как работает",
            "как определяет положение оси",
            "как он определяет крайнее положение",
            "определяет крайнее положение по оси",
        ],
        "title": "Хоминг X/Y: как принтер находит ноль",
        "answer": (
            "Kobra S1 / Combo при хоминге едет головой/столом до концевика (limit switch) "
            "на краю оси. Срабатывание концевика — сигнал «ноль». Это не «датчик в голове» "
            "и не чисто программный предел: нужен физический концевик на каждой оси.\n\n"
            "Если «долбится» в край — проверьте концевик, крышку/колпак (не мешает ли), "
            "шлейфы, затем Home и тест нажатием на концевик вручную.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/limit-switch"
        ),
    },
    {
        "keys": [
            "крепление щётки s1",
            "щетка валик kobra s1",
            "крепление у с1 для щётки",
            "крепление щетки валика",
            "замену этой щетки",
            "замену этой зетки",
        ],
        "title": "Крепление щётки/валика на Kobra S1",
        "answer": (
            "На S1 штатная щётка/валик для очистки сопла — отдельный узел; крепление своё, "
            "с Max/другими моделями 1:1 обычно не совпадает.\n\n"
            "• Замена/сервис — по гайдам purge wiper (близкий узел на линейке Combo).\n"
            "• «Нормальную» щётку часто печатают из STL сообщества или берут аналог под размер посадки.\n"
            "• Силиконовая подложка под сопло — расходник, сопло быстро портит мягкую подложку.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/purge-wiper-replace-guide"
        ),
    },
    {
        "keys": [
            "скачиваю презагружается",
            "перезагружается при скачивании",
            "когда скачиваю он презагружается",
            "презагружается при скачивании",
            "перезагружается когда скачиваю",
        ],
        "title": "Перезагрузка при скачивании прошивки/обновления",
        "answer": (
            "Если принтер перезагружается во время скачивания прошивки по Wi‑Fi/облаку:\n\n"
            "• Проверьте стабильность сети (2.4 GHz, роутер рядом, без VPN на телефоне/ПК).\n"
            "• Попробуйте обновление с USB-флешки по официальной инструкции — надёжнее OTA.\n"
            "• Не прерывайте питание; если цикл повторяется — скачайте .swu/.bin с wiki и прошейте локально.\n"
            "• После неудачного OTA иногда помогает перезагрузка роутера и повтор.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"
        ),
    },
    {
        "keys": [
            "вики не открывает vpn",
            "wiki.anycubic vpn",
            "вики эникубовское",
            "wiki anycubic vpn",
            "не открывает через vpn",
            "не открывает у всех",
        ],
        "title": "Wiki Anycubic не открывается через VPN",
        "answer": (
            "Официальная wiki.anycubic.com иногда недоступна через часть VPN/провайдеров "
            "(CDN, блокировки, маршрут).\n\n"
            "• Попробуйте без VPN или другой VPN/сервер/страну.\n"
            "• Другой браузер, мобильный интернет, DNS 8.8.8.8 / 1.1.1.1.\n"
            "• Зеркало: скачайте PDF/прошивку с app.anycubic.com или поддержки, если сайт лежит.\n\n"
            "Это сетевая проблема доступа, не неисправность принтера."
        ),
    },
    {
        "keys": [
            "aux fan chamber fan",
            "вент модели aux",
            "aux fan или chamber",
            "chamber fan или вент",
            "вент модели или aux",
        ],
        "title": "Aux / chamber / model fan на S1",
        "answer": (
            "На Kobra S1 Combo обычно:\n\n"
            "• Model fan — обдув модели/детали (на голове).\n"
            "• Auxiliary (aux) fan — дополнительный обдув камеры/слоя.\n"
            "• Chamber/box filter fan — вентилятор фильтра/камеры (не путать с обдувом модели).\n\n"
            "В слайсере и на экране названия могут отличаться; смотрите, какой вентилятор "
            "крутится при печати ABS/PLA и при автообдуве.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/auxiliary-cooling-fan-replacement-guide\n"
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/model-cooling-fan-replacement-guide"
        ),
    },
    {
        "keys": [
            "ремни потянул ничего не поменялось",
            "подтяжки ремней xy",
            "ремни на xy я по мануалу потянул",
            "после подтяжки ничего не поменялось",
            "потянул ремни xy",
        ],
        "title": "Подтянул ремни XY — качество не изменилось",
        "answer": (
            "Если после подтяжки ремней X/Y дефект печати тот же:\n\n"
            "• Ремни — не единственная причина: проверьте Z-offset, первый слой, влажный филамент, "
            "температуры, калибровку PA/flow.\n"
            "• Смотрите, что именно не так (ghosting, слои, размер) — ремни чаще дают полосы/потери шагов.\n"
            "• Равномерность натяжения с обеих сторон, ролики, крепёж каретки.\n"
            "• При сильном артефакте — тестовый куб/бенч и фото для сравнения.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/x-axis-belt-replacement-guide\n"
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/printing-effect-is-not-good"
        ),
    },
    {
        "keys": [
            "разъем в камере",
            "для чего разъем в камере",
            "разъём в камере",
            "разъем в камере s1",
        ],
        "title": "Разъём в камере Kobra S1",
        "answer": (
            "На Kobra S1 Combo разъём(ы) в корпусе камеры — сервисные/заготовки под опции "
            "(фильтр, доп. модули). Это не «лазер из коробки»: лазерные комплекты — отдельная "
            "линейка и прошивка.\n\n"
            "Если разъём пустой — заглушка нормальна. Не подключайте неизвестные модули без "
            "инструкции Anycubic."
        ),
    },
]

SIDEBAR_EXTRA = [
    r"\bгде-то\s+тут\s+в\s+флудилке\b",
    r"\bтемпературах\s+баръера\b",
    r"\blm317\b",
    r"\bразмера\s+2515\b",
    r"\bготов\s+с\s+ней\s+поиграться\b",
    r"\bкстати,?\s+почему\s+бы\s+и\s+да\b",
    r"\bтенза\s+должна\s+отрабатывать\b",
    r"\bвы\s+где\s+шастаете\s+админ\b",
    r"\bсиликоновую\s+подложку\s+аля\s+бамбулаб\b",
    r"\bскинуть\s+профили\s+для\s+печати\b",
    r"\bне\s+заметил\s+поменял\s+походу\s+в\s+профиле\b",
    r"\bна\s+стандартном\s+норм\s+нарезается\b",
    r"\bкрасное\s+было\s+как\s+ч[её]рное\b",
    r"\bтреснуло\s+на\s+раме\s+держател\b",
    r"\bкакбудто\s+он\s+скрывает\b",
    r"\bхотите\s+ржаку\b",
    r"\bсами\s+себе\s*\??\s*$",
    r"\bметалл\s+мог\s+поломаться\b",
    r"\bинвалиды\s+сборщики\b",
    r"\bне\s+присобачить\b",
    r"\bможно\s+присобачить\b",
    r"\bчего\s+запаса\s+нету\b",
    r"\bдихлорэтан\s+сможет\b",
    r"\b700\s*часов\b",
    r"\bваленки\s+собирали\b",
    r"\bпереверни\s+как\s+было\b",
    r"\bотверстия\s+заклеены\s+по\s+бокам\b",
    r"\bне\s+критичн\w*\(\(\(\b",
    r"\bголова\s+разваливается\b",
    r"\bhueforge\b",
    r"\bарахна\s+вообще\s+не\s+хочет\b",
    r"\bоткат\s+у\s+тебя\s+какой\b",
    r"\bна\s+1\.2\s+как\s+будто\b",
    r"\bна\s+15%\s+нарезки\s+зависает\b",
    r"\bмебель\s+из\s+катушек\b",
    r"\bактивную\s+камеру\s+подвезут\b",
    r"\bхай\s+будет\b",
    r"\bсерый\s+закончится\b",
    r"\bне\s+высоко\s+ли\s*\??\s*$",
    r"\bчто\s+не\s+совет\s*-\s*сушите\s+пластик\b",
    r"\bканал\s+бамбуков\b",
    r"\bполе\s+250\b",
    r"\bh2d\s+нужно\s+брать\b",
    r"\bчто\s+бы\s+я\s+делал\s+без\s+вас\b",
    r"\bp2s\s+не\s+купил\b",
    r"\bзавтра\s+не\s+сломается\b",
    r"\bпочти\s+нет\s+отличий\s+с\s+низовой\b",
    r"\bну\s+раз\s+почти\s+никаких\b",
    r"\bпластик\s+дерьмо\s+ебаное\b",
    r"\bкачество\s+абс\s+прям\s+не\s+очень\b",
    r"\bдругой\s+есть\s*\??\s*$",
    r"\bтолько\s+что\s+перед\s+началом\b",
    r"\bчей\s+абс\s*\??\s*$",
    r"\bна\s+с1\s+тоже\s+все\s+четко\b",
    r"\bкакой\s+принтер\s*\??\s*$",
    r"\bпромышленных\s+масштабах\b",
    r"\bближе\s+фотограф\w*\s+дефекта\b",
    r"\bклей\s+наносили\s*\??\s*$",
    r"\bдефекты\s+с\s+250\s+вплоть\b",
    r"\bну,?\s+как\s+знаете\s*:?\)?\s*$",
    r"\bуровень\s+стола\s+неверно\s+определил\b",
    r"\bна\s+первом\s+слое\s+проблема\b",
    r"\bпараметры\s+пластика\s*\??\s*$",
    r"\bпараметры\s+какие\s*\??\s*$",
    r"\bбошку\s+напечатать\b",
    r"\bполтора\s+цилиндр\b",
    r"\bприняли\s+без\s+проблем\b",
    r"\bв\s+воздухе\s+печатал\b",
    r"\bцилиндр\s+с\s+отверстием\s+посередине\b",
    r"\bнадрачивал\s+каналы\b",
    r"\bпортал\s+на\s+с1\s+снимать\b",
    r"\bвидосы\s+башки\b",
    r"\bвы\s+дразнитесь\b",
    r"\bпаять\s+будешь\b",
    r"\bпринтер\s+разломал\b",
    r"\bлишь\s+черный\s+и\s+белый\b",
    r"\bтакой\s+пластик\s+видел\b",
    r"\bгугл[о-]?ии\b",
    r"\bтеплопроводящий\s+герметик\b",
    r"\bпод\s+плюс\s+сделано\b",
    r"\bот\s+куда\s+если\s+был\s+закрыт\b",
    r"\bот\s+куда\s+угодно\b",
    r"\bоберег\s+от\s+нестоямбы\b",
    r"\bчемодан\s+на\s+сканер\b",
    r"\bтурецком\s+магазине\b",
    r"\bкак\s+эсть\b",
    r"\bбумага\s+первая\s+линия\s+техподдержки\b",
    r"\bвыслали\s+ось\s+z\b",
    r"\bпри\s+заказе\s+он\s+на\s+почту\b",
    r"\bместо\s+покупки\s+озер\b",
    r"\bгде\s+был\s+куплен\s+принтер\b",
    r"\bна\s+макса\s+новый\s+стол\b",
    r"\bдемоническом\s+языке\b",
    r"\bпечата.*\bsbs\b",
    r"\bстол\s+зачем\s+новый\b"
]

NEW_FUNCS = (
    "_is_vpn_bot_spam",
    "_is_homing_endstop_thread_sidebar",
    "_is_missed_jul21_thread_noise",
)
TEST_CONTENT = '''"""Регрессии по разбору missed_questions 2026-07-21."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_homing_endstop_thread_sidebar,
    _is_missed_jul21_thread_noise,
    _is_non_wiki_chatter_message,
    _is_vpn_bot_spam,
)


def test_homing_manual_qa():
    msg = (
        "Но я не знаю как он определяет крайнее положение по оси . "
        "Программно ли, датчиком в голове"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_brush_mount_manual_qa():
    msg = "А какое крепление у с1 для щётки/валика штатное? Мб от мах подойдёт?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_firmware_reboot_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "когда скачиваю он презагружается")


def test_wiki_vpn_manual_qa():
    msg = "Вики эникубовское чет даже через КВН у меня не открывает у всех так?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_fan_types_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "это aux fan или chamber fan? или вент модели?"
    )


def test_belt_tension_manual_qa():
    msg = (
        "Добрый! А это сильно плохо? Ремни на XY я по мануалу потянул. "
        "Первая картинка до, вторая после подтяжки. Ничего не поменялось"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_chamber_connector_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "А для чего разъем в камере ? Или это для лазера ?"
    )


def test_vpn_spam_is_chatter():
    msg = "Ребят, кто здесь спрашивал про норм впн? ищите в телеграме lotvpnbot, проверено."
    assert _is_vpn_bot_spam(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_homing_sidebar_is_chatter():
    assert _is_homing_endstop_thread_sidebar("У меня когда без крышки запускал он тупо в угол долбился")
    assert _is_conversational_chatter("На ноль нажать не может?")


def test_thread_noise_is_chatter():
    assert _is_missed_jul21_thread_noise("Хотите ржаку?")
    assert _is_conversational_chatter("Гугло-ИИ пишет, что мол вообще ппц, так жить нельзя =)")


def test_real_homing_not_sidebar():
    assert not _is_homing_endstop_thread_sidebar(
        "Я просто хз как он определяет крайнее положение по оси Х"
    )


def test_real_wiki_vpn_not_spam():
    assert not _is_vpn_bot_spam(
        "Вики эникубовское чет даже через КВН у меня не открывает у всех так?"
    )
'''


def patch_manual_qa() -> None:
    entries = json.loads(QA_PATH.read_text(encoding="utf-8"))
    existing_titles = {e.get("title") for e in entries if isinstance(e, dict)}
    now = time.time()
    added = 0
    for i, e in enumerate(NEW_QA):
        if e["title"] in existing_titles:
            continue
        entries.insert(
            0,
            {"keys": e["keys"], "title": e["title"], "answer": e["answer"], "ts": now - added * 0.001},
        )
        existing_titles.add(e["title"])
        added += 1
    QA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_banter() -> None:
    t = BANTER_PATH.read_text(encoding="utf-8")
    if "_is_missed_jul21_thread_noise" in t:
        print("banter already patched (jul21)")
        return
    raw = BANTER_SNIPPET_PATH.read_text(encoding="utf-8")
    start = raw.find("def _is_vpn_bot_spam")
    if start == -1:
        raise RuntimeError("jul21 banter snippet missing functions")
    chunk = raw[start:].strip() + "\n"
    t = t.rstrip() + "\n\n" + chunk
    BANTER_PATH.write_text(t, encoding="utf-8")


def _add_imports(path: Path, names: tuple[str, ...]) -> None:
    t = path.read_text(encoding="utf-8")
    for name in names:
        if name in t:
            continue
        for needle in (
            "    _is_missed_jul17_thread_noise,\n",
            "    _is_travel_airport_sidebar,\n",
            "    _is_money_lend_spam,\n",
        ):
            if needle in t:
                t = t.replace(needle, needle + f"    {name},\n", 1)
                break
    path.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    for name in NEW_FUNCS:
        if f"{name}," not in t:
            for needle in (
                "    _is_missed_jul17_thread_noise,\n",
                "    _is_travel_airport_sidebar,\n",
                "    _is_money_lend_spam,\n",
            ):
                if needle in t:
                    t = t.replace(needle, needle + f"    {name},\n", 1)
                    break
    anchor = "        or _is_missed_jul17_thread_noise(text)\n    )"
    if anchor in t and "_is_missed_jul21_thread_noise(text)" not in t:
        extra = "".join(f"        or {n}(text)\n" for n in NEW_FUNCS)
        t = t.replace(anchor, anchor.replace("    )", extra + "    )"))
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    _add_imports(INIT_PATH, NEW_FUNCS)


def patch_text() -> None:
    _add_imports(TEXT_PATH, NEW_FUNCS)


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def clear_missed() -> None:
    MISSED_PATH.write_text("[]\n", encoding="utf-8")


def verify() -> None:
    sys.path.insert(0, str(ROOT))
    from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
    from app.bot.text_heuristics import _is_non_wiki_chatter_message

    store = load_manual_qa_store()
    missed = json.loads(MISSED_PATH.read_text(encoding="utf-8"))
    uncovered: list[str] = []
    for x in missed:
        t = (x.get("text") or "").strip()
        if not t:
            continue
        if find_manual_qa_answer(store, t) or _is_non_wiki_chatter_message(t):
            continue
        uncovered.append(t)
    if uncovered:
        print(f"VERIFY FAIL: {len(uncovered)} uncovered:")
        for t in uncovered:
            safe = t[:120].encode("utf-8", errors="backslashreplace").decode("utf-8")
            print(f"  - {safe}")
        sys.exit(1)


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    patch_text()
    write_tests()
    verify()
    clear_missed()
    print(
        f"OK: {len(NEW_QA)} QA + {len(NEW_FUNCS)} filters + "
        f"{len(SIDEBAR_EXTRA)} noise patterns; missed cleared"
    )


if __name__ == "__main__":
    main()
