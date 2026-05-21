"""Одноразовый скрипт: вставить фильтры бытового чата в исходники."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HELPERS = '''
def _is_slicer_app_disambiguation(text: str) -> bool:
    """«Это в ChiTu или Orca?» — уточнение в треде, не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if re.search(r"\\bкак\\s+(?:настро|установ|использов|скачать|сделать|выбрать)\\b", t):
        return False
    if _is_error_code_query(text) or _printer_mentioned(text):
        return False
    has_slicer = bool(re.search(r"\\b(?:слайсер\\w*|slicer)\\b", t))
    has_app = bool(
        re.search(
            r"\\b(?:чиди|чити|chitu|chitubox|orca|орка|anycubic|cura|prusaslicer|bambu\\s*studio)\\b",
            t,
        )
    )
    if not (has_slicer or has_app):
        return False
    choice = bool(re.search(r"\\bили\\b", t) or t.count("?") >= 2)
    demonstrative = bool(re.search(r"^\\s*это\\s+", t))
    if (has_slicer and has_app and (choice or demonstrative)) or (has_app and choice and len(t) <= 100):
        return True
    return False


def _is_filament_testing_plan_sharing(text: str) -> bool:
    """Планы по катушке/тестам — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if re.search(r"\\bкатушк", t) and re.search(r"\\bтест", t):
        return True
    if re.search(r"\\b(?:буду|будем)\\s+(?:всякое\\s+)?тест", t):
        return True
    if re.search(r"\\b(?:определил|выбрал|отвёл|отвел)\\b.{0,30}\\bтест", t):
        return True
    return False


def _is_sarcastic_printer_banter(text: str) -> bool:
    """Шутки про А4/бумагу или тред с люфтом — не запрос к вики."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if re.search(r"\\bкак\\s+(?:убрать|устранить|уменьшить|настро)\\b", t):
        return False
    if re.search(r"\\b(?:а4|a4)\\b", t) and re.search(r"\\b(?:принтер|вставля|бумаг)\\b", t):
        return True
    if re.search(r"\\bбумаг\\w*\\b", t) and re.search(r"\\bпечата", t):
        if re.search(r"\\bэто\\s+же\\s+принтер\\b", t) or "?" in text:
            return True
    if (t.count("·") >= 2 or t.count("?") >= 2) and re.search(r"\\bлюфт\\b", t):
        if not re.search(r"\\b(?:помогите|подскаж)\\b", t):
            return True
    return False


def _is_conversational_skepticism(text: str) -> bool:
    """Скепсис в треде — не запрос к вики."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if re.search(r"\\b(?:сомневаюсь|сомневаемся|не\\s+думаю|вряд\\s+ли|сомнев)\\b", t) and re.search(r"\\bчто\\b", t):
        return True
    if re.search(r"\\b(?:пустят|напечатают|запустят|заморачив)\\b", t) and re.search(
        r"\\b(?:кубик|куб|печат)\\b", t
    ):
        return True
    if re.search(r"\\bвс[её]\\s+на\\s+этом\\b", t) and re.search(r"\\bпечат", t):
        return True
    return False


def _is_non_wiki_chatter_message(text: str) -> bool:
    """Сообщения чата, на которые бот не отвечает из вики."""
    return (
        _is_conversational_skepticism(text)
        or _is_sarcastic_printer_banter(text)
        or _is_slicer_app_disambiguation(text)
        or _is_filament_testing_plan_sharing(text)
        or _is_technical_opinion_sharing(text)
        or _is_technical_observation_sharing(text)
        or _is_partial_manual_find_observation(text)
        or _is_chat_meta_discussion(text)
    )


'''


def patch_text_heuristics() -> None:
    p = ROOT / "app" / "bot" / "text_heuristics.py"
    t = p.read_text(encoding="utf-8")
    old_needs = """    # Наблюдения и бытовой чат — модель не уточняем.
    if (
        _is_technical_opinion_sharing(text)
        or _is_technical_observation_sharing(text)
        or _is_partial_manual_find_observation(text)
        or _is_chat_meta_discussion(text)
    ):
        return False"""
    new_needs = """    # Наблюдения и бытовой чат — модель не уточняем.
    if _is_non_wiki_chatter_message(text):
        return False"""
    if old_needs in t:
        t = t.replace(old_needs, new_needs)
    marker = "# Сравнительное «как на кобре», разговорное «ужас как» в конце — не вопрос к боту."
    if "def _is_non_wiki_chatter_message" not in t and marker in t:
        t = t.replace(marker, HELPERS + marker)
    old_help = """def _message_has_help_intent(text: str) -> bool:
    \"\"\"Пользователь ищет помощь / инструкцию, а не просто комментирует чат.\"\"\"
    if not text or not text.strip():
        return False
    raw = text.strip()"""
    new_help = """def _message_has_help_intent(text: str) -> bool:
    \"\"\"Пользователь ищет помощь / инструкцию, а не просто комментирует чат.\"\"\"
    if not text or not text.strip():
        return False
    if (
        _is_conversational_skepticism(text)
        or _is_sarcastic_printer_banter(text)
        or _is_slicer_app_disambiguation(text)
        or _is_filament_testing_plan_sharing(text)
    ):
        return False
    raw = text.strip()"""
    if old_help in t:
        t = t.replace(old_help, new_help)
    old_chatter = """    if _is_partial_manual_find_observation(text):
        return True
    if _is_chat_meta_discussion(text):
        return True
    if _is_technical_observation_sharing(text):
        return True
    if _is_technical_opinion_sharing(text):
        return True
    if _message_has_help_intent(text):"""
    new_chatter = """    if _is_non_wiki_chatter_message(text):
        return True
    if _message_has_help_intent(text):"""
    if old_chatter in t:
        t = t.replace(old_chatter, new_chatter)
    p.write_text(t, encoding="utf-8")


def patch_layer_model_gate() -> None:
    p = ROOT / "app" / "bot" / "layer_model_gate.py"
    t = p.read_text(encoding="utf-8")
    old_topic = '''def topic_is_layer_slicing_intent(text: str | None) -> bool:
    if not text:
        return False
    tl = text.lower()
    if re.search(r"\\b0\\.\\d{1,3}\\b", tl) and re.search(r"слой|слоя|слое|слою|layer", tl):
        return True
    return any(
        k in tl
        for k in (
            "слой",
            "слоя",
            "слое",
            "слою",
            "печать",
            "в печать",
            "тест",
            "слайс",
            "layer",
            "slic",
            "test print",
            "benchy",
            "профил",
        )
    )'''
    new_topic = '''def topic_is_layer_slicing_intent(text: str | None) -> bool:
    if not text:
        return False
    from app.bot.text_heuristics import _is_non_wiki_chatter_message

    if _is_non_wiki_chatter_message(text):
        return False
    tl = text.lower()
    if re.search(r"\\b0\\.\\d{1,3}\\b", tl) and re.search(r"слой|слоя|слое|слою|layer", tl):
        return True
    if re.search(r"\\bслайс(?!er\\w*)\\b", tl) or re.search(r"\\bslic(?!er\\w*)\\b", tl):
        return True
    if re.search(r"\\b(?:тестов(?:ую|ый|ая)|тест)\\s*(?:печат|принт|print)\\b", tl):
        return True
    if re.search(r"\\btest\\s*print\\b|\\bbenchy\\b", tl):
        return True
    if re.search(r"\\bтест\\b", tl) and re.search(r"\\b(?:слой|слоя|слое|layer|0\\.\\d|калибр|level)\\b", tl):
        return True
    return any(k in tl for k in ("слой", "слоя", "слое", "слою", "печать", "в печать", "layer", "профил"))'''
    if old_topic in t:
        t = t.replace(old_topic, new_topic)
    old_clarify = """    # Бытовой чат: наблюдения, мнения, цитаты — модель не уточняем.
    from app.bot.text_heuristics import (
        _is_chat_meta_discussion,
        _is_partial_manual_find_observation,
        _is_technical_observation_sharing,
        _is_technical_opinion_sharing,
    )

    if (
        _is_technical_opinion_sharing(text)
        or _is_technical_observation_sharing(text)
        or _is_partial_manual_find_observation(text)
        or _is_chat_meta_discussion(text)
    ):
        return False"""
    new_clarify = """    from app.bot.text_heuristics import _is_non_wiki_chatter_message

    if _is_non_wiki_chatter_message(text):
        return False"""
    if old_clarify in t:
        t = t.replace(old_clarify, new_clarify)
    p.write_text(t, encoding="utf-8")


def patch_web_wiki_index() -> None:
    p = ROOT / "app" / "web_wiki_index.py"
    t = p.read_text(encoding="utf-8")
    old_import = """from app.bot.text_heuristics import (
    _is_chat_meta_discussion,
    _is_marketplace_promo_message,
    _is_partial_manual_find_observation,
    _is_technical_observation_sharing,
    _is_technical_opinion_sharing,
)"""
    new_import = """from app.bot.text_heuristics import (
    _is_marketplace_promo_message,
    _is_non_wiki_chatter_message,
)"""
    if old_import in t:
        t = t.replace(old_import, new_import)
    old_checks = """    # «Нашёл только инструкцию как…» — в тексте есть «как», но это не вопрос к боту.
    if _is_partial_manual_find_observation(text):

        return False

    # Цитата «помогите…» при обсуждении истории чата — не вопрос к боту.
    if _is_chat_meta_discussion(text):

        return False

    # «Заметил, что параметр X — не тот» — наблюдение, не вопрос (в тексте есть «что»).
    if _is_technical_observation_sharing(text):

        return False

    # «Как по мне люфт не страшен» — мнение, не вопрос «как сделать».
    if _is_technical_opinion_sharing(text):

        return False

    t = _normalize(text)"""
    new_checks = """    if _is_non_wiki_chatter_message(text):

        return False

    t = _normalize(text)"""
    if old_checks in t:
        t = t.replace(old_checks, new_checks)
    old_tail = """    if "ссыл" in t and any(w in t for w in ("вики", "wiki", "настрой", "калибр", "уровн", "стол", "куб")):

        return True

    return bool(
        re.search(
            r"\\b(как|почему|зачем|что|где|когда|кто|можно ли|помогите|не работает)\\b",
            t,
        )
    )"""
    new_tail = """    if "ссыл" in t and any(w in t for w in ("вики", "wiki", "настрой", "калибр", "уровн", "стол", "куб")):

        return True

    if re.search(r"\\bтак\\s+что\\b", t) and "?" not in text:
        if not re.search(r"\\bтак\\s+что\\s+(?:делать|значит|не\\s+так|не\\s+работает)\\b", t):
            return False

    if re.search(r"\\b(?:сомневаюсь|сомневаемся)\\b", t) and re.search(r"\\bчто\\b", t) and "?" not in text:
        return False

    return bool(
        re.search(
            r"\\b(как|почему|зачем|что|где|когда|кто|можно ли|помогите|не работает)\\b",
            t,
        )
    )"""
    if old_tail in t:
        t = t.replace(old_tail, new_tail)
    p.write_text(t, encoding="utf-8")


def main() -> None:
    patch_text_heuristics()
    patch_layer_model_gate()
    patch_web_wiki_index()
    print("done")


if __name__ == "__main__":
    main()
