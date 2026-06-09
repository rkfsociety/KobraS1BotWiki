"""Topic-интенты: функции определения тематики вопросов."""
from __future__ import annotations

import re

from app.bot.heuristics._base import (
    _is_error_code_query,
    _printer_mentioned,
)
from app.bot.heuristics._ace import (
    _is_ace_unit_trade_banter,
    _topic_is_ace_filament_slot_intent,
    _topic_is_ace_not_detected_intent,
)
from app.bot.heuristics._banter import (
    _is_colloquial_printer_fragment,
    _is_filament_tolerance_banter,
    _is_multicolor_flow_calibration_chat,
    _is_other_printer_maintenance_story,
    _is_sarcastic_thread_banter,
    _is_third_party_filament_brand_chat,
    _message_has_help_intent,
)


def _topic_is_marketplace_commerce_intent(text: str | None) -> bool:
    """Продажа на WB/Ozon, ТН ВЭД готовых моделей — не тема вики Anycubic."""
    from app.bot.heuristics._ace import _is_combo_ace_marketplace_chat
    if not text:
        return False
    if _is_combo_ace_marketplace_chat(text):
        return True
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
    # «что ещё докинуть к заказу кроме филамента» — совет по комплектации, не вики.
    order_advice = bool(
        re.search(r"\bк\s+заказ\w*\b", t)
        and re.search(r"\b(?:докин\w*|добав\w*|положить|нужно\s+ещё|ещё\s+взять)\b", t)
    )
    if order_advice:
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


def _topic_is_filament_bed_removal_intent(text: str | None) -> bool:
    """Как оторвать TPU/деталь от стола — не гайд print-tpu чужой модели."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    has_material = bool(
        re.search(
            r"\b(?:тпу|tpu|петг|petg|пла|pla|abs|абс|нейлон|nylon|пластик|филамент|filament|гибк)\w*\b",
            t,
        )
    )
    has_bed = bool(
        re.search(
            r"\b(?:пластин\w*|стол\w*|платформ\w*|build\s*plate|bed|pei|build\s*surface)\b",
            t,
        )
    )
    has_remove = bool(
        re.search(
            r"\b(?:"
            r"отрыв\w*|оторв\w*|снять|снима\w*|отдел\w*|"
            r"peel|detach|remove\s+from|"
            r"отлип\w*|откле\w*"
            r")\b",
            t,
        )
    )
    if not (has_material and has_bed and has_remove):
        return False
    return bool(
        "?" in text
        or re.search(
            r"\b(?:совет\w*|проще|подскаж\w*|помогите|как\s+лучше|как\s+проще|есть\s+ли)\b",
            t,
        )
    )


def _topic_is_filament_material_choice_intent(text: str | None) -> bool:
    """Какой пластик/TPU/фирму взять — не замена сопла и не подача филамента."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _topic_is_filament_bed_removal_intent(text):
        return False
    if _is_filament_tolerance_banter(text):
        return False
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
            r"\b(?:какой|какая|какое|что\s+взять|что\s+лучше|посовет|подскаж|рекоменд|"
            r"какую\s+фирм|бренд|марк[ау]|which|what\s+filament|brand)\w*\b",
            t,
        )
    ) or bool(
        re.search(r"\bкакие\b", t)
        and re.search(
            r"\b(?:фирм\w*|бренд\w*|марк\w*|пластик\w*|филамент\w*|тпу|tpu)\b",
            t,
        )
    )
    stock_nozzle_ctx = bool(re.search(r"\bродн\w*\s+сопл|\bstock\s+nozzle\b", t))
    return wants_choice or stock_nozzle_ctx


def _topic_is_filament_slicing_settings_intent(text: str | None) -> bool:
    """Параметры нарезки/печати под материал (PETG, TPU) — не уточнение модели принтера."""
    if not text:
        return False
    if _is_third_party_filament_brand_chat(text):
        return False
    if _is_multicolor_flow_calibration_chat(text):
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
    hole_ctx = bool(re.search(r"\b(?:отверст\w*|дыр\w*|hole)\b", t))
    if not (slicer_ctx and hole_ctx):
        return False
    # Дырки «в месте шва» после замены хотенда — это под-экструзия/шов, не вертикальная стенка.
    if re.search(r"\b(?:шв[ае]|шов\w*|в\s+месте\s+шва|пропуск\w*|недоэкструз\w*)\b", t):
        return False
    # Тема узкая: круглое отверстие в вертикальной стенке, которое деформируется/моделят каплей.
    deform_ctx = bool(re.search(r"\b(?:сплющ\w*|деформ\w*|овал\w*|капл\w*|dogbone|teardrop)\b", t))
    vertical_ctx = bool(re.search(r"\bвертикальн\w*\b", t) and re.search(r"\b(?:стенк\w*|стен\w*|wall)\b", t))
    return deform_ctx or vertical_ctx


def _topic_is_resonance_pa_tuning_intent(text: str | None) -> bool:
    """Резонанс, PA, затухающие колебания / вибрации — не clarify вместо ответа."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # Сильные сигналы — речь действительно про резонанс/затухающие колебания/шейпер.
    strong = bool(
        re.search(
            r"\b(?:"
            r"резонанс|resonance|ringing|"
            r"колебан\w*|затуха\w*|"
            r"input\s*shap|шейпер|shaper|виброкомпенс\w*|"
            r"layer\s*shift|сдвиг\s+сл\w*"
            r")\b",
            t,
        )
    )
    # Слабые: голое упоминание PA / вибраций / jerk без слов резонанса.
    weak = bool(re.search(r"\bpa\b|pressure\s*advance|\bвибрац\w*|\bjerk\b|\baccel\w*", t))
    if not (strong or weak):
        return False
    explicit_ask = bool(
        re.search(
            r"\b(?:"
            r"как\s+(?:настро|откалибр|калибр)\w*|настро\w*|калибр\w*|автокалибр\w*|"
            r"не\s+влия\w*|почему|связан\w*|подскаж\w*|помогите|что\s+это\s+(?:такое|за)"
            r")\b",
            t,
        )
    )
    if strong:
        return bool("?" in text or explicit_ask)
    # Болтовня-наблюдение к чужому фото («плохо видно, как-будто… тоже PA шалит?») —
    # для голого PA одного «?» мало, нужен явный запрос настройки/калибровки.
    observation = bool(
        re.search(
            r"\b(?:плохо\s+видно|как[\s-]?будто|какбудто|похоже\s+(?:на\s+то|что)|тоже\b)\b",
            t,
        )
    )
    if observation and not explicit_ask:
        return False
    return explicit_ask


def _topic_is_slicer_feature_help_intent(text: str | None) -> bool:
    """Убрать «ушко»/brim в слайсере — не quick start вики."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not re.search(r"\b(?:слайсер\w*|slicer|нарезк\w*|слайс\w*|orca)\b", t):
        return False
    remove_act = bool(
        re.search(r"\b(?:убрать|удалить|отключить|выключить|убери|скрыть|remove|disable)\w*\b", t)
    )
    feature = bool(
        re.search(
            r"\b(?:"
            r"ушк\w*|уши\b|mouse\s*ear|"
            r"brim|брим|"
            r"таб\w*|pointing"
            r")\b",
            t,
        )
    )
    struggle = bool(re.search(r"\b(?:не\s+получается|никак\s+не|не\s+могу)\b", t))
    help_ctx = bool(
        re.search(r"\b(?:подскаж\w*|помогите|помоги)\b", t)
        or re.search(r"\bкак\s+(?:\w+\s+){0,10}убрать\b", t)
    )
    if remove_act and (feature or struggle):
        return True
    return help_ctx and remove_act


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


def _topic_is_slicer_choice_opinion_intent(text: str | None) -> bool:
    """Мнение про Orca vs слайсер для Kobra — не quick start вики."""
    from app.bot.heuristics._banter import _is_slicer_app_disambiguation
    if not text:
        return False
    return _is_slicer_app_disambiguation(text)


def _topic_needs_printer_model(text: str) -> bool:
    """Тема вопроса обычно специфична для модели (без модели ответ легко промахнется)."""
    t = text.lower()

    # Отрыв TPU/пластика со стола — не уточнение модели вместо совета.
    if _topic_is_filament_bed_removal_intent(text):
        return False

    # Выбор марки/типа пластика (TPU и т.п.) — не путать с сервисом сопла.
    if _topic_is_filament_material_choice_intent(text):
        return False

    # Настройки слайсера под PETG/TPU (мост, поток, поддержки) — не привязка к модели Kobra.
    if _topic_is_filament_slicing_settings_intent(text):
        return False

    # Отверстия в вертикальных стенках / «капля» в CAD — не привязка к модели.
    if _topic_is_slicer_vertical_hole_intent(text):
        return False

    # Убрать ушко/brim в слайсере — не привязка к модели принтера.
    if _topic_is_slicer_feature_help_intent(text):
        return False

    # Резонанс / PA / затухающие колебания — общая калибровка, не уточнение модели вместо ответа.
    if _topic_is_resonance_pa_tuning_intent(text):
        return False

    # ACE Pro: слот/чип запомнил материал — не уточнение модели принтера.
    if _topic_is_ace_filament_slot_intent(text):
        return False

    # P2S/Bambu + eSUN/ориг. пластик, подтёки — личная история, не модель Kobra.
    if _is_other_printer_maintenance_story(text):
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
        "подогрев",
        "сопл",
        "двер",
        "петл",
        "стеклянн",
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

    # «на столе» (мебель) ≠ heated bed; стол принтера — только с калибровкой/печатью.
    if re.search(r"\bстол\w*\b", t) and re.search(
        r"\b(?:"
        r"калибр|уровн|level|скрейп|царап|сопл|подогрев|hotbed|heated|"
        r"настрой\w*|печат\w*|куб"
        r")\w*\b",
        t,
    ):
        return True

    # «кубы» / leveling cubes при настройке стола — разная инструкция по моделям
    if "куб" in t and any(
        k in t for k in ("стол", "калибр", "уровн", "настрой", "level", "bed", "скрейп", "царап", "сопл")
    ):
        return True

    # «говорит не печатает, зачем ему аськи» — пересказ, не поломка принтера пользователя.
    if _is_sarcastic_thread_banter(text):
        return False

    if _is_other_printer_maintenance_story(text):
        return False

    return False
