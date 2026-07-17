"""Разбор missed_questions (2026-07-17): manual_qa + эвристики + очистка очереди."""
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
TEXT_PATH = ROOT / "app" / "bot" / "text_heuristics.py"
TEST_PATH = ROOT / "tests" / "test_missed_jul17_chatter.py"

NEW_QA = [
    {
        "keys": [
            "чем можно отмыть пластик со стола",
            "отмыть пластик со стола",
            "чем отмыть стол",
            "отмыть пластик со стола",
            "почистить стол от пластика",
            "чем протирать стол",
        ],
        "title": "Чем отмыть пластик/клей со стола",
        "answer": (
            "Стол (PEI/текстура): остудите, снимите пластину.\n\n"
            "• Остатки PLA/PETG — изопропиловый спирт (ИПС) 90%+, мягкая салфетка, без абразива.\n"
            "• Сильный нагар/клей — тёплая вода + немного средства для посуды, затем снова ИПС.\n"
            "• Не скребите металлическим ножом по покрытию; пластиковый шпатель — ок.\n"
            "• После мойки полностью высушите пластину перед печатью.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/maintenance-recommendations"
        ),
    },
    {
        "keys": [
            "к чему мне стоит подготовится после покупки",
            "подготовится после покупки кубика",
            "проблемами могу столкнуться в первые дни",
            "первый принтер с какими проблемами",
            "первые дни эксплуатации",
            "после покупки кубика 1с",
        ],
        "title": "Первые дни с Kobra S1 — к чему готовиться",
        "answer": (
            "После покупки Kobra S1 / Combo чаще всего упираются в:\n\n"
            "• Сеть/слайсер: 2.4 GHz Wi‑Fi, LAN Mode, IP вручную если автоскан пустой.\n"
            "• Первый слой: прогрев, ИПС на столе, автокалибровка, Z-offset.\n"
            "• Филамент: сушка (особенно PETG/TPU), правильный профиль в слайсере.\n"
            "• ACE (если Combo): Unload/Load, PTFE без перегибов, привыкание к смене цвета.\n"
            "• Шум/люфты: проверка натяжения ремней X/Y по инструкции.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/quick-start-guide"
        ),
    },
    {
        "keys": [
            "сперва внешняя стенка печаталась",
            "внешняя стенка печаталась а потом внутренняя",
            "наплывы вылазят",
            "outer wall first",
            "сначала внешняя стенка",
            "порядок стенок в слайсере",
        ],
        "title": "Наплывы: печатать внешнюю стенку первой?",
        "answer": (
            "Да, в Orca / Anycubic Slicer Next можно включить «Outer wall first» / "
            "«Сначала внешняя стенка» — иногда убирает наплывы на стыке периметров.\n\n"
            "Также проверьте:\n"
            "• температуру (−5…10°C), поток, давление Advance/PA;\n"
            "• скорость внешней стенки ниже внутренней;\n"
            "• ширину линии ≈ диаметру сопла;\n"
            "• сухой филамент.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/printing-effect-is-not-good"
        ),
    },
    {
        "keys": [
            "чем склеить пла пластик",
            "склеить pla",
            "склеить пла",
            "клей для pla большой площади",
            "цианакрилат pla",
            "чем склеить детали pla",
        ],
        "title": "Чем склеить PLA на большой площади",
        "answer": (
            "Для PLA на большой площади:\n\n"
            "• Лучше всего — дихлорметан / специальные PLA-клеи (химическая сварка) "
            "тонким слоем, в проветривании.\n"
            "• Цианакрилат (суперклей) — для маленьких стыков; на большой площади "
            "действительно не успевает: наносите по зонам или используйте гель + активатор.\n"
            "• Эпоксидка 2к — если нужна прочность и зазор, но шов толще.\n"
            "• Перед склейкой обезжирьте, подгоните плоскости, зафиксируйте струбцинами.\n\n"
            "Это общие приёмы склейки — не специфика Anycubic."
        ),
    },
    {
        "keys": [
            "кастом что на него есть",
            "оставаться на стоковой прошивке",
            "кастом или сток",
            "ставить кастом на этот принтер",
            "кастом прошивка s1 плюсы минусы",
            "стоковая прошивка или кастом",
        ],
        "title": "Кастомная прошивка vs сток на Kobra S1",
        "answer": (
            "Сток Anycubic: поддержка ACE/облака/приложения, обновления с wiki, гарантийные "
            "разборки проще.\n\n"
            "Кастом (Klipper-сборки сообщества и т.п.): больше тюнинга (input shaper, макросы), "
            "но сами обновления, риск «кирпича», ACE/мультицвет могут работать иначе или не работать, "
            "гарантия/поддержка Anycubic на кастом обычно не распространяется.\n\n"
            "Если принтер устраивает «из коробки» — разумнее сток. Кастом имеет смысл, "
            "если осознанно нужна гибкость и готовы обслуживать сами.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"
        ),
    },
    {
        "keys": [
            "чищу печатает и всё равно забивается",
            "печатает и всё равно забивается",
            "всё равно забивается как это должно",
            "чищу забивается снова",
            "постоянно забивается хотэнд",
        ],
        "title": "Чистил — снова забивается",
        "answer": (
            "Если после прочистки снова клинит:\n\n"
            "• Heat creep / высокая температура + долгий простой — снизьте °C, проверьте обдув радиатора.\n"
            "• Частичный засор в горле — cold pull, игла, при необходимости замена quick-release сопла.\n"
            "• Влажный/мягкий филамент или неверный диаметр — сушка, другая катушка.\n"
            "• Плохая посадка hotend / PTFE — переустановите по гайду.\n"
            "• Слишком большой ретракт — уменьшите.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/troubleshooting-abnormal-print-head-clogging"
        ),
    },
    {
        "keys": [
            "малый диаметр прутка",
            "ошибку падает малый диаметр",
            "диаметр прутка вики",
            "подаю пластик из аси ошибку",
            "filament diameter too thin",
            "тонкий пруток ace",
        ],
        "title": "ACE/ошибка: малый диаметр прутка",
        "answer": (
            "В вики Anycubic прямо сказано: если диаметр нити слишком тонкий, шестерни "
            "не захватывают филамент — сыпятся ошибки подачи/ретракта (в т.ч. 11511/11512 и рядом).\n\n"
            "Что делать:\n"
            "• Отмотайте метр–два, откусите ровно, заново Load (часто помогает на «тонком» конце).\n"
            "• Измерьте микрометром несколько точек — норма ~1.75±0.05 мм; брак катушки — замена.\n"
            "• Проверьте прижим в ACE, PTFE без сильных перегибов, нет ли обломка в хотэнде.\n"
            "• Попробуйте другую катушку того же типа.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/error-codes/11511-code/s1"
        ),
    },
    {
        "keys": [
            "инструкции нет по полному разбору головы",
            "полный разбор головы",
            "разобрать голову kobra s1",
            "разбор головы s1",
            "как разобрать хотэнд s1",
        ],
        "title": "Полный разбор головы Kobra S1",
        "answer": (
            "Пошаговые разборы узла головы разнесены по гайдам Anycubic (не один «полный мануал»):\n\n"
            "• Чистка/засор хотэнда: cleaning-hotend-clogging / troubleshooting clogging.\n"
            "• Замена hotend: hotend-replacement-guide.\n"
            "• Экструдер/нож/детекторы — отдельные страницы в разделе Combo.\n\n"
            "Снимайте питание, фотографируйте шлейфы, не потеряйте клипсы PTFE.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/hotend-replacement-guide"
        ),
    },
    {
        "keys": [
            "как проверить кривизну стола",
            "проверить кривизну стола",
            "кривой стол как проверить",
            "карта стола кривизна",
            "насколько кривой стол",
        ],
        "title": "Как проверить кривизну стола",
        "answer": (
            "На Kobra S1:\n\n"
            "1. Прогрейте стол и сопло, протрите пластину ИПС.\n"
            "2. Запустите автокалибровку / bed mesh в меню принтера или в слайсере (если доступно).\n"
            "3. Смотрите карту высот: перепад больше ~0.3–0.5 мм по площади — стол/пластина кривые "
            "или крепление ослаблено.\n"
            "4. Для печати больших деталей ровность критична; при сильном перекосе — замена пластины/стола "
            "или сервис.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/first-layer"
        ),
    },
    {
        "keys": [
            "что может так щелкать при печати",
            "щелкать при печати",
            "щелкает при печати s1",
            "щелчки при печати",
            "щёлкает при печати",
        ],
        "title": "Щелчки при печати (не экструдер)",
        "answer": (
            "Если щёлкает не экструдер (не проскальзывание шестерён):\n\n"
            "• Ремни X/Y — слабое/неравномерное натяжение, ролики, натяжители сзади по бокам.\n"
            "• Кабель-цепь / шлейф задевает корпус при движении головы.\n"
            "• Вентилятор/кожух дребезжит — проверьте крепёж.\n"
            "• Стол/рама — ослабленные винты.\n"
            "• Запись видео + локализация по оси помогают отличить ремень от вентилятора.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/x-axis-belt-replacement-guide"
        ),
    },
    {
        "keys": [
            "принтер на неотапливаемый балкон",
            "поставить принтер на балкон",
            "балкон где зимой будет холодно",
            "принтер на холодном балконе",
            "печатать на балконе зимой",
        ],
        "title": "Принтер на холодном балконе",
        "answer": (
            "Неотапливаемый балкон зимой — обычно плохая идея:\n\n"
            "• PLA/PETG плохо печатаются на сильном холоде и сквозняке (отлип, слои).\n"
            "• Электроника и смазка не любят конденсат и минус.\n"
            "• Влажность губит катушки.\n\n"
            "Если очень надо — закрытый корпус, обогрев помещения хотя бы до +15…18°C, "
            "без сквозняка, сухой филамент. Иначе лучше комната.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/filament-guide"
        ),
    },
    {
        "keys": [
            "через амс пускать тпу нельзя",
            "тпу через ace",
            "tpu через ace",
            "тпу в ace нельзя",
            "можно ли тпу через ace",
            "tpu в амс",
        ],
        "title": "TPU через ACE / AMS",
        "answer": (
            "Мягкий TPU через ACE Pro часто проблемный: высокое сопротивление в PTFE, "
            "риск застревания и ошибок подачи. Жёсткий TPU (Shore ~95A) иногда тянет, "
            "но Anycubic для TPU рекомендует прямую подачу и низкие скорости.\n\n"
            "Практика: мягкий TPU — мимо ACE, напрямую в экструдер; сушить обязательно.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu"
        ),
    },
    {
        "keys": [
            "максимальный объемный расход",
            "объемный расход для тпу",
            "volumetric speed tpu",
            "max volumetric speed тпу",
            "объёмный расход тпу",
        ],
        "title": "Max volumetric speed для TPU",
        "answer": (
            "Для TPU ставьте консервативно: часто 2–6 mm³/s в начале (зависит от Shore и сопла), "
            "скорость печати 15–40 мм/с, минимальный ретракт.\n\n"
            "Если появляются недоэкструзия/пропуски — снизьте volumetric limit ещё. "
            "Точное число подбирается тестом на вашей катушке и сопле.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu"
        ),
    },
    {
        "keys": [
            "нейлон па6 или па12",
            "рискнуть взять нейлон па6",
            "па6 или па12",
            "nylon pa6 или pa12",
            "какой нейлон брать па",
        ],
        "title": "Нейлон PA6 vs PA12",
        "answer": (
            "PA6 обычно жёстче/дешевле, сильнее тянет влагу, выше усадка — нужен закрытый корпус, "
            "сушка, осторожный первый слой.\n\n"
            "PA12 часто стабильнее по влаге и чуть проще в печати, дороже.\n\n"
            "На стоковом S1 без доработок оба капризны; начинающим проще PETG/ASA для «инженерки». "
            "Если берёте нейлон — сушилка обязательна, смотрите температуры на катушке.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/filament-guide"
        ),
    },
]

# Distinctive chatter phrases (≥6 chars) from the missed queue — sidebar dump.
SIDEBAR_EXTRA = [
    r"\bпроклинашки\b",
    r"\bкак\s+будто\s+вмазало\b",
    r"\bунифицированное\s+самому\b",
    r"\bпридумал\s+дьявол\b",
    r"\bстыковочный\s+рейс\b",
    r"\bалипэй\b",
    r"\bаэропорт\w*\s+китая\b",
    r"\bв\s+вичат\b",
    r"\bплита\s+вон\s+как\s+нагрела\b",
    r"\bспекаймость\b",
    r"\bгреть\s+зажигалкой\b",
    r"\bсжег\s+родное\b",
    r"\b3\s+сопла\b.*\b2700\b",
    r"\bна\s+луне\s+у\s+тебя\s+пвз\b",
    r"\bприлет\s+12\s+августа\b",
    r"\bпридет\s+12\s+августа\b",
    r"\bспасибо\s+что\s+проверил\b",
    r"\bгорло\s+подтекает\b",
    r"\bзапущу\s+на\s+220\b",
    r"\bчей\s+силк\b",
    r"\bнужда\s+в\s+баблишк\b",
    r"\bтолько\s+с\s+одной\s+стороны\s+вылезло\b",
    r"\bяндекс\s+маркет\s*\??\b",
    r"\bвнешку\s+бы\s+победить\b",
    r"\bитог\s+подвести\s+что\s+сделано\b",
    r"\bчто\s+это\s+за\s+полоска\s+такая\b",
    r"\bотключено\s+замедление\s+на\s+нависаниях\b",
    r"\bкак\s+будто\s+бы\s+идеально\b",
    r"\bсилки\s+более\s+текучие\b",
    r"\bвс[её]\s+что\s+выше\s+10\b",
    r"\bяб\s+поставил\s+от\s+50\b",
    r"\bпеременную\s+высоту\s+слоев\b",
    r"\bвремя\s+охлаждения\s+слоев\b",
    r"\bширину\s+внешки\s+до\s+0\.6\b",
    r"\bактивировать\s+флэшбэки\b",
    r"\bчто-то\s+не\s+то\s+делаете\b",
    r"\bломается\s+втулка\b",
    r"\bфлюрик\s+или\s+люмик\b",
    r"\bдрыг\s+стол\b",
    r"\bдруг\s+стол\s+на\s+другой\b",
    r"\bvpn\s+колхозить\b",
    r"\bфиксатор\s+резьбы\b",
    r"\bзначит\s+замена\s*\??\b",
    r"\bза\s+тебя\s+не\s+очень\s+то\s+рады\b",
    r"\bбросил\s+в\s+2015\b",
    r"\bс\s+асе\s+никогда\s+не\s+было\s+проблем\b",
    r"\bфункционала\s+некста\s+вполне\b",
    r"\bчиди\s+студио\s+супер\s+кривой\b",
    r"\bкастраты\b",
    r"\bпроклинаю\s+каждого\s+китайца\b",
    r"\bпроблема\s+с\s+бабками\b",
    r"\bкурилке\s+аэропорта\b",
    r"\bпионер\s+лагерь\b",
    r"\bноги\s+ставьте\s+туда\b",
    r"\bесли\s+что\s+осуждаю\b",
    r"\bс\s+жопкой\s+понятно\b",
    r"\bтарахтело\s+об\s+стенку\b",
    r"\bнету\s+бабок\b",
    r"\bнужда\s+в\s+бабле\b",
    r"\bпогулять\s+с\s+собакой\b",
    r"\bво\s+как\s+называется\b",
    r"\bстол\s+и\s+так\s+паршивый\b",
    r"\bс\s+песком\s+пластик\s+жрать\b",
    r"\bне\s+показатель\s+что\s+он\s+не\s+сырой\b",
    r"\bчто\s+что\s+из\s+вакуума\b",
    r"\bчто\s+за\s+фирма\s+пластика\b",
    r"\bчей\s+тпу\s+стоит\s+брать\b",
    r"\bтечет\s+хот\b",
    r"\bхот\s+не\s+течет\b",
    r"\bкак\s+с\s+работы\s+приеду\b",
    r"\bв\s+карманах\s+пусто\b",
    r"\bподготовкой\s+заказов\s+к\s+отправке\b",
    r"\bмоноцает\b",
    r"\bкак\s+и\s+на\s+кобре\s+3\b",
    r"\b80-90\s+где-то\b",
    r"\bсколько\s+км\s+ехать\b",
    r"\bдо\s+тольятти\b",
    r"\bкак\s+угодно\b",
    r"\bзачем\s+покупать\s*$",
    r"\bкоммерческая\s+версия\s+доступна\b",
    r"\b0\.16\s+хайквол\b",
    r"\bоркой\s+чистой\b",
    r"\bкорпус\s+яхты\b",
    r"\bгде\s+трубку\s+то\b",
    r"\bвсю\s+голову,?\s+все\s+что\s+откруч\b",
    r"\bмонтажное\s+сидение\b",
    r"\bскан\s+корпуса\s+головы\b",
    r"\bхз\s+что\s+за\s+она\b",
    r"\bфольгированный\s+скотч\b",
    r"\bкак\s+она\s+его\s+взорвёт\b",
    r"\bпять\s+лет\s+как\s+ни\s+как\b",
    r"\bбрал\s+в\s+днс\s+уценке\b",
    r"\bвины\s+поджимные\b",
    r"\bкубик\s+пла,?\s+тот\s+что\s+прислали\b",
    r"\bпруток\s+доходил\b",
    r"\bхуже\s+абс\b",
    r"\bнатуральный\s+па\b",
    r"\bотматываем\s+с\s+метр\s+пластика\b",
    r"\bне\s+забывай\s+фоткать\b",
    r"\bкак\s+приваренная\b",
    r"\bголова\s+вообще\s+не\s+люфтит\b",
    r"\bдолжен\s+сидеть\s+мертво\b",
    r"\bищите\s+заусенцы\s+на\s+столе\b",
    r"\bотскочу\s+на\s+пару\s+часиков\b",
    r"\bарахна\s+не\s+включена\b",
    r"\bнастройки\s+печати\s+мои\s+не\s+пробовал\b",
    r"\bвот\s+и\s+думайте\s+что\s+это\b",
    r"\bоптические\s+валы\b",
    r"\bне\s+сфоткал\s+что\s+приехало\b",
    r"\bкарбон\s+валы\b",
    r"\bвот\s+этих\s*\??\s*$",
    r"\bне\s+хочу\s+сдавать\s+его\b",
    r"\bпринтер\s+на\s+гарантии\s*\??\s*$",
    r"\bбык\s+нассал\b",
    r"\bна\s+петг\s+так\s+же\s+было\b",
    r"\bполосит\s+по\s+той\s+стороне\b",
    r"\bцарапины\s+на\s+самой\s+пластине\b",
    r"\bгде\s+голова\s+ездит\b",
    r"\bголова\s+путешествует\b",
    r"\bоба\s+тянуть\s*\??\s*$",
    r"\bгде\s+гладить\s+и\s+чего\s+крутить\b",
    r"\bпошёл\s+ломать\b",
    r"\bнатяжители\s+снаружи\s+или\s+внутри\b",
    r"\bпочесать,?\s+там\s+попинать\b",
    r"\bядерный\s+реактор\s+запускать\b",
    r"\bсистеме\s+с\s+хранением\s+товара\b",
    r"\bослабить\s+натяжители,?\s+пошатать\s+голову\b",
    r"\bпр.?бл.?мы\s+c\s+б.?б.?с.?ми\b",
    r"\bпересобрал\s+в\s+каком\s+плане\b",
    r"\bупаковали\s+как\s+repaired\b",
    r"\bа\s+ты\s+как\s+думал\s*$",
    r"\bкак\s+включить\s+принтер\s*$",
    r"\bвот\s+зачем\s*$",
    r"\bво\s+все\s+тяжкие\b",
    r"\bс\s+иваново\b",
    r"\bмелкие\s+катушки\s+не\s+взять\b",
    r"\bкак\s+вариант\s*$",
    r"\bв\s+чём\s+создаются\s+такие\s+модели\b",
    r"\bпроблемы\s+с\s+бабосами\b",
    r"\bтебя\s+смыло\b",
    r"\bкак\s+у\s+волги\s+старой\b",
    r"\bчто\s+за\s+пессимизм\b",
    r"\bинструкция\s+как\s+ей\s+пользоваться\s*$",
    r"\bя\s+один\s+страдаю\s+вот\s+этим\b",
    r"\bсудебная\s+практика\s+в\s+сторону\s+продавцов\b",
    r"\bдонорского\s+принтера\b",
    r"\bхоч.?шь\s+з.?р.?б.?тыв.?ть\b",
    r"\bтитаново\s+обожженный\b",
    r"\bили\s+али\s+или\s+у\s+нас\b",
    r"\bпрозрачного\s+тпу\b",
    r"\bсредней\s+гибкости\b",
    r"\bлады\s+гранты\b",
    r"\bянтарная\s+амфибия\b",
    r"\bаська\s+когда\s+сосет\s+пластик\b",
    r"\bкатушкодержатель\s+на\s+с1макс\b",
    r"\bмазать\s+колесико\b",
    r"\bкак\s+его\s+упереть\b",
    r"\bбудешь\s+18\+\s+печатать\b",
    r"\bпойду\s+забирать\s+данное\s+чудо\b",
    r"\bпокрасочный\s+бокс\s+приехал\b",
    r"\bот\s+стола\s+оторвать\s+и\s+в\s+воздухе\b",
    r"\bрублей\s+за\s+400\b",
    r"\bкак\s+макака\s+наклеил\b",
    r"\bстолика\s+для\s+сканирования\b",
    r"\bсожгет\s+из\s+них\b",
    r"\bкак\s+он\s+бедный\s+живет\b",
    r"\bобновленную\s+ревизию\s+cobra\s+s1\s+с\s+ace\s+pro2\b",
]

NEW_BANTER_FN = '''

def _is_money_lend_spam(text: str) -> bool:
    """«Нужда в баблишке?», «Проблемы с бабосами?» — спам про деньги, не вопрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if re.search(r"\\b(?:как\\s+(?:настро|почин|печат)|ошибк\\w*|сопл|экструдер)\\b", t):
        return False
    return bool(
        re.search(r"\\b(?:бабл|бабок|бабк|бабос|баблишк|финанс|деньг)\\w*", t)
        and re.search(
            r"\\b(?:нужда|проблем|черкани|обращай|пиши|выруч|помог|пусто|не\\s+хвата)\\w*",
            t,
        )
    )


def _is_travel_airport_sidebar(text: str) -> bool:
    """Аэропорт/алипэй/стыковочный рейс/Тольятти — тревел-оффтоп."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t) and re.search(r"\\b(?:принтер|печат|сопл|кобра)\\b", t):
        return False
    return bool(
        re.search(
            r"\\b(?:"
            r"аэропорт|алипэй|alipay|стыковочн\\w*\\s+рейс|вичат|wechat|"
            r"тольятти|иваново|калининград|литовск\\w*\\s+вал|"
            r"янтарн\\w*\\s+амфиби|хаммер\\s+решил\\s+искупа"
            r")\\b",
            t,
        )
    )


def _is_missed_jul17_thread_noise(text: str) -> bool:
    """Остатки missed_questions 2026-07-17: короткие реплики треда без запроса к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t) and re.search(
        r"\\b(?:как\\s+(?:настро|откалибр|почин|сделать|подключ|замен)|ошибк\\w*|не\\s+работает)\\b",
        t,
    ):
        return False
    patterns = (
PLACEHOLDER_PATTERNS
    )
    return any(re.search(p, t) for p in patterns)
'''

# Inject patterns into function body
_patterns_literal = ",\n        ".join(f'r"{p}"' for p in SIDEBAR_EXTRA)
NEW_BANTER_FN = NEW_BANTER_FN.replace("PLACEHOLDER_PATTERNS", _patterns_literal)

NEW_FUNCS = (
    "_is_money_lend_spam",
    "_is_travel_airport_sidebar",
    "_is_missed_jul17_thread_noise",
)

TEST_CONTENT = '''"""Регрессии по разбору missed_questions 2026-07-17."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_missed_jul17_thread_noise,
    _is_money_lend_spam,
    _is_non_wiki_chatter_message,
    _is_travel_airport_sidebar,
)


def test_clean_bed_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "Привет, чем можно отмыть пластик со стола ?"
    )


def test_first_days_manual_qa():
    msg = (
        "Первый принтер. Сравнил с аналогами этот больше заинтересовал по цене и характеристикам. "
        "С какими проблемами могу столкнуться в первые дни эксплуатации?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_thin_filament_manual_qa():
    msg = (
        "Подаю пластик из аси, причём это единственный в аси пластик от кубиков, это ПЛА "
        "который достался мне бесплатно за предзаказ макса, и вот его подаю, а он мне в ошибку "
        "падает, и хз что делать, по вики кубиков тип малый диаметр прутка..."
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_balcony_manual_qa():
    msg = (
        "подскажите пожалуйста, поставить принтер на неотапливаемый балкон"
        "(где зимой будет холодно) - плохая идея?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_tpu_ace_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "Но известно же , что через амс пускать тпу нельзя?"
    )


def test_click_noise_manual_qa():
    msg = (
        "Подскажите, что может так щелкать при печати? Не могу понять, в чем причина. "
        "С экструдером это никак не связано. S1"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_money_spam_is_chatter():
    assert _is_money_lend_spam("Нужда в баблишке ? Обращайся.)")
    assert _is_conversational_chatter("Проблемы с бабосами? Пиши помогу")


def test_airport_sidebar_is_chatter():
    msg = (
        "Я только алипэй себе делал когда 5 часов торчал в аэропорту Китая "
        "и хотел купить пожрать в вендинге"
    )
    assert _is_travel_airport_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_thread_noise_is_chatter():
    assert _is_missed_jul17_thread_noise("Ну чо проклинашки?😁😁😁😁")
    assert _is_conversational_chatter("Как будто вмазало")


def test_real_bed_clean_not_noise():
    assert not _is_missed_jul17_thread_noise(
        "Подскажите чем отмыть пластик со стола на kobra s1"
    )


def test_real_clog_not_money():
    assert not _is_money_lend_spam(
        "Хотэнд забивается, подскажите что делать на kobra s1"
    )
'''


def patch_manual_qa() -> None:
    entries = json.loads(QA_PATH.read_text(encoding="utf-8"))
    now = time.time()
    for i, e in enumerate(NEW_QA):
        entries.insert(
            0,
            {"keys": e["keys"], "title": e["title"], "answer": e["answer"], "ts": now - i * 0.001},
        )
    QA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_banter() -> None:
    t = BANTER_PATH.read_text(encoding="utf-8")
    if "_is_missed_jul17_thread_noise" in t:
        print("banter already patched")
        return
    # Append before end of file
    t = t.rstrip() + "\n" + NEW_BANTER_FN.lstrip("\n")
    # Expand private money spam lightly
    old_money = '''        or re.search(r"\\bне\\s+хватает\\s+бабла\\b", t)
        or (re.search(r"\\bпиши\\s+мне\\b", t) and "?" in text)
    )'''
    new_money = '''        or re.search(r"\\bне\\s+хватает\\s+бабла\\b", t)
        or (re.search(r"\\bпиши\\s+мне\\b", t) and "?" in text)
        or re.search(r"\\bнужда\\s+в\\s+бабл", t)
        or re.search(r"\\bпроблем\\w*\\s+с\\s+баб", t)
    )'''
    if old_money in t:
        t = t.replace(old_money, new_money)
    BANTER_PATH.write_text(t, encoding="utf-8")


def _add_imports(path: Path, names: tuple[str, ...]) -> None:
    t = path.read_text(encoding="utf-8")
    for name in names:
        if name in t:
            continue
        # Prefer after last jul17 replies import if present
        for needle in (
            "    _is_sensor_thread_banter,\n",
            "    _is_parcel_arrival_banter,\n",
            "    _is_offtopic_gas_station_joke,\n",
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
                "    _is_sensor_thread_banter,\n",
                "    _is_parcel_arrival_banter,\n",
                "    _is_vague_fix_without_symptom,\n",
            ):
                if needle in t:
                    t = t.replace(needle, needle + f"    {name},\n", 1)
                    break
    if "_is_missed_jul17_thread_noise(text)" not in t:
        chain_end = "        or _is_sensor_thread_banter(text)\n    )"
        if chain_end not in t:
            chain_end = "        or _is_offtopic_gas_station_joke(text)\n    )"
        extra = "".join(f"        or {n}(text)\n" for n in NEW_FUNCS)
        if chain_end in t:
            t = t.replace(chain_end, chain_end.replace("    )", extra + "    )"))
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    _add_imports(INIT_PATH, NEW_FUNCS)


def patch_text() -> None:
    _add_imports(TEXT_PATH, NEW_FUNCS)


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def clear_missed() -> None:
    MISSED_PATH.write_text("[]\n", encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    patch_text()
    write_tests()
    clear_missed()
    print(f"OK: {len(NEW_QA)} QA + {len(NEW_FUNCS)} filters + {len(SIDEBAR_EXTRA)} noise patterns; missed cleared")


if __name__ == "__main__":
    main()
