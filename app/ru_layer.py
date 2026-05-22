from __future__ import annotations



import re





_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")





# Мини-словарь RU -> EN для поиска по англоязычной вики.

# Добавляй сюда по мере появления типовых вопросов.

_MAP: list[tuple[re.Pattern[str], str]] = [

    (re.compile(r"\bэкструдер\b", re.I), "extruder module print head replacement"),

    (re.compile(r"\bсопло\b|\bно(у)?зл\b", re.I), "nozzle"),

    (re.compile(r"\bхотэнд\b|\bхотэн(д)?\b", re.I), "hotend"),

    (re.compile(r"\bтерм(и)?стор\b", re.I), "thermistor"),

    (re.compile(r"\bнагревател(ь|я)\b", re.I), "heater cartridge"),

    (re.compile(r"\bстол\b|\bплатформ(а|ы)\b", re.I), "bed build plate"),

    (re.compile(r"\bкалибр(овк)?а\b|\bуровн(ять|ень)\b|\bлевел(инг)?\b", re.I), "leveling calibration"),

    (

        re.compile(r"\bкуб(ов|а|ы)?\b.*\b(стол|настрой|калибр|уровн)|\b(стол|настрой|калибр|уровн).*\bкуб(ов|а|ы)?\b", re.I),

        "nozzle scraping hot bed calibration flatness",

    ),

    (re.compile(r"\bцарапа(ет|ют|ет)?\b.*\bстол|\bстол.*\bцарапа", re.I), "nozzle scraping hot bed"),

    (re.compile(r"\bпрошивк(а|у)\b|\bфирмвар(е)?\b", re.I), "firmware update"),
    (re.compile(r"\bцветн\w*\s+печат\w*\b|\bмногоцвет\w*\b", re.I), "multi-color printing firmware"),

    (re.compile(r"\bошибк(а|у)\b|\berr\b", re.I), "error"),

    (re.compile(r"\bне печатает\b|\bне печата(ет|ю)\b", re.I), "not printing"),

    (re.compile(r"\bзастрял(а|о)?\b|\bзаклинил(о|а)?\b", re.I), "jam stuck"),

    (re.compile(r"\bфиламент\w*\b", re.I), "filament"),
    (re.compile(r"\bтпу\b|\btpu\b", re.I), "TPU flexible filament print settings"),
    (re.compile(r"\bпетг\b|\bpetg\b", re.I), "PETG filament print settings"),
    (re.compile(r"\bмост\w*\b", re.I), "bridge flow slicing"),
    (re.compile(r"\bпластик\w*\b", re.I), "filament plastic material"),

    (re.compile(r"\bпода(ет|ёт|ач|еки)\w*\b", re.I), "feeding feed extruder"),

    (re.compile(r"\bшестерн\w*\b", re.I), "extruder gear filament feed"),

    (re.compile(r"\bсрыв\w*\b", re.I), "slipping skipping extruder gear"),

    (re.compile(r"\bне\s+пода\w*\b", re.I), "not feeding filament"),

    (

        re.compile(

            r"\bмотор\w*\b.{0,40}\b(подач|филамент|экструдер)|\b(подач|филамент|экструдер)\b.{0,40}\bмотор",

            re.I,

        ),

        "extruder feed motor stepper",

    ),

    (re.compile(r"\bнить\b|\bсопл(и|я)\b", re.I), "stringing"),

    (re.compile(r"\bретракт\b", re.I), "retraction"),

    (re.compile(r"\bшумит\b|\bшум\b", re.I), "noise"),

    (re.compile(r"\bрем(е)?нь\b", re.I), "belt"),

    (re.compile(r"\bось x\b|\bx-ось\b|\bx axis\b", re.I), "x axis"),

    (re.compile(r"\bось y\b|\by-ось\b|\by axis\b", re.I), "y axis"),

    (re.compile(r"\bось z\b|\bz-ось\b|\bz axis\b", re.I), "z axis"),

    (re.compile(r"\bшаговик\b|\bшаговый двигатель\b", re.I), "stepper motor"),

    (re.compile(r"\bпоменять\b|\bзаменить\b|\bсменить\b|\bустановить\b", re.I), "replace install"),

    (re.compile(r"\bснять\b|\bразобрать\b", re.I), "remove disassemble"),

    (re.compile(r"\bкобра\b", re.I), "kobra"),

    (re.compile(r"\bкомбо\b", re.I), "combo"),

    (re.compile(r"\bаська\b|\bаска\b|\bаськ\w*\b|\bэйс\b", re.I), "ACE Pro filament station"),

    (re.compile(r"\bсушилк\w*\b|\bсуш[иао]т\w*\b", re.I), "filament drying moisture desiccant"),

    (re.compile(r"\bace\s*pro\b", re.I), "ACE Pro"),

    (re.compile(r"\bдвер(ь|и|ей|ью|ями)?\b", re.I), "glass door acrylic enclosure"),

    (re.compile(r"\bпередн(яя|ей|юю|ие|их)?\b", re.I), "front"),

    (re.compile(r"\bпетл(и|я|ей|ью)?\b", re.I), "hinge door"),

]





def expand_queries(text: str) -> list[str]:

    """

    Возвращает список вариантов запроса:

    - исходный текст

    - если есть кириллица: отдельный "английский" запрос по словарю

    - плюс комбинированный (исходный + англ. слова)

    """

    base = text.strip()

    if not base:

        return []



    out = [base]

    if not _CYRILLIC_RE.search(base):

        return out



    extra: list[str] = []

    # На WB/ТН ВЭД «пластик» — про готовые модели, не про филамент в принтере
    from app.bot.text_heuristics import _topic_is_marketplace_commerce_intent

    commerce = _topic_is_marketplace_commerce_intent(base)

    for pat, repl in _MAP:

        if commerce and repl == "filament plastic material":

            continue

        if pat.search(base):

            extra.append(repl)



    extra_txt = " ".join(sorted(set(extra))).strip()

    if extra_txt:

        # EN-only вариант часто матчится лучше с англоязычной вики

        out.append(extra_txt)

        # комбинированный оставляем на случай, если в базе есть и латиница (модель/код ошибки)

        out.append(base + " " + extra_txt)

        if "extruder" in extra_txt and any(x in extra_txt for x in ("replace", "install", "remov")):

            out.append("extruder replacement module guide")

        if "door" in extra_txt and any(x in extra_txt for x in ("replace", "install", "remov", "glass")):

            out.append("glass door replacement install guide")

        if "scraping" in extra_txt or "flatness" in extra_txt:

            out.append("nozzle scraping hot bed troubleshooting guide")

        if re.search(r"(аська|аска|аськ\w*|ace\s*pro|\bace\b)", base, re.I) and re.search(

            r"не\s+вид|not\s+(see|detect)|doesn.?t\s+see|подключен|подключени|ошибк|выбрасыв|connection|binding",

            base,

            re.I,

        ):

            out.append("printer binding ACE Pro network connection troubleshooting")

        if re.search(r"(аська|аска|аськ\w*|ace\s*pro|\bace\b)", base, re.I) and re.search(

            r"сушилк|суш[иао]т|dryer|drying|влажн|moisture", base, re.I

        ):

            out.append("ACE Pro filament drying moisture storage ace-pro-notes")

        if re.search(r"филамент|подач|шестерн|экструдер|feeding|extruder", base, re.I) and re.search(

            r"не\s+пода|срыв|крутит|застрял|jam|clog|block|feeding", base, re.I

        ):

            out.append(

                "filament feeding timeout print head clogging extruder abnormal blocking troubleshooting"

            )



    seen: set[str] = set()

    uniq: list[str] = []

    for item in out:

        if item not in seen:

            seen.add(item)

            uniq.append(item)

    return uniq



