"""Патч: выбор TPU/пластика не должен тянуть «замена сопла» и уточнение модели."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MATERIAL_INTENT_FN = '''
def _topic_is_filament_material_choice_intent(text: str | None) -> bool:
    """Какой пластик/TPU/фирму взять — не замена сопла и не подача филамента."""
    if not text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _topic_is_filament_feed_intent(text):
        return False
    if re.search(r"\\b(?:замен|поменя|смени|установ|replace|remov|disassembl)\\w*\\b", t):
        return False
    has_material = bool(
        re.search(
            r"\\b(?:тпу|tpu|пластик|филамент|filament|petg|pla|abs|nylon|нейлон|гибк)\\w*\\b",
            t,
        )
    )
    if not has_material:
        return False
    wants_choice = bool(
        re.search(
            r"\\b(?:какой|какая|какое|какие|что\\s+взять|что\\s+лучше|посовет|подскаж|рекоменд|"
            r"какую\\s+фирм|бренд|марк[ау]|which|what\\s+filament|brand)\\w*\\b",
            t,
        )
    )
    stock_nozzle_ctx = bool(re.search(r"\\bродн\\w*\\s+сопл|\\bstock\\s+nozzle\\b", t))
    return wants_choice or stock_nozzle_ctx


'''


def patch_text_heuristics(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_topic_is_filament_material_choice_intent" in text:
        print("text_heuristics: already patched")
        return
    anchor = "def _topic_is_filament_feed_intent(text: str | None) -> bool:"
    if anchor not in text:
        raise RuntimeError(f"anchor not found in {path}")
    text = text.replace(anchor, MATERIAL_INTENT_FN + anchor, 1)

    old = '    t = text.lower()\n\n\n\n    ru = ('
    new = (
        '    t = text.lower()\n\n\n\n'
        '    # Выбор марки/типа пластика (TPU и т.п.) — не путать с сервисом сопла.\n'
        '    if _topic_is_filament_material_choice_intent(text):\n\n\n\n'
        '        return False\n\n\n\n'
        '    ru = ('
    )
    if old not in text:
        raise RuntimeError("_topic_needs_printer_model anchor not found")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("text_heuristics: patched")


def patch_wiki_ranking(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_filament_material_guide_url_plausible" in text:
        print("wiki_ranking: already patched")
        return

    imp_old = "    _topic_is_filament_feed_intent,\n\n    _user_already_replaced_motherboard,"
    imp_new = (
        "    _topic_is_filament_feed_intent,\n\n"
        "    _topic_is_filament_material_choice_intent,\n\n"
        "    _user_already_replaced_motherboard,"
    )
    if imp_old not in text:
        raise RuntimeError("import anchor not found")
    text = text.replace(imp_old, imp_new, 1)

    helper = '''
def _filament_material_guide_url_plausible(url: str) -> bool:
    """Страницы про выбор/печать материала, не замена сопла."""
    u = url.lower().replace("_", "-")
    if "print-tpu" in u or "filament-guide" in u:
        return True
    if "filament-and-resin" in u and "guide" in u:
        return True
    if "parameters-selection" in u:
        return True
    if "flexible" in u and "filament" in u:
        return True
    if re.search(r"(?:^|/)tpu(?:/|$|-)", u):
        return True
    if "extra-material" in u and "printing" in u:
        return True
    return False




'''
    anchor = "def _topic_is_nozzle_intent(topic: str | None) -> bool:"
    text = text.replace(anchor, helper + anchor, 1)

    bonus_anchor = '    if "сопло" in tl or "nozzle" in tl:\n\n        if "nozzle" in u:\n\n            b += 20\n'
    bonus_new = (
        bonus_anchor
        + "\n    if _topic_is_filament_material_choice_intent(topic):\n\n"
        + '        if "print-tpu" in u:\n\n            b += 72\n\n'
        + '        elif "filament-guide" in u:\n\n            b += 58\n\n'
        + '        elif "parameters-selection" in u:\n\n            b += 45\n\n'
        + '        elif "extra-material" in u and "printing" in u:\n\n            b += 38\n\n'
        + '        if "replace" in u and "nozzle" in u:\n\n            b -= 70\n'
    )
    if bonus_anchor not in text:
        raise RuntimeError("bonus anchor not found")
    text = text.replace(bonus_anchor, bonus_new, 1)

    pen_anchor = 'def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:\n\n    """Тема «дверь» или «подача филамента», а URL про другое узло — сильный штраф."""\n\n    if _topic_is_filament_feed_intent(topic):'
    pen_new = (
        'def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:\n\n'
        '    """Тема «дверь» или «подача филамента», а URL про другое узло — сильный штраф."""\n\n'
        '    if _topic_is_filament_material_choice_intent(topic):\n\n'
        '        u = url.lower().replace("_", "-")\n\n'
        '        if _filament_material_guide_url_plausible(url):\n\n'
        '            return 0\n\n'
        '        if "replace" in u and "nozzle" in u:\n\n'
        '            return 85\n\n'
        '        if "nozzle" in u and any(k in u for k in ("scraping", "silicone", "cleaning")):\n\n'
        '            return 72\n\n'
        '        return 35\n\n'
        '    if _topic_is_filament_feed_intent(topic):'
    )
    if pen_anchor not in text:
        raise RuntimeError("penalty anchor not found")
    text = text.replace(pen_anchor, pen_new, 1)

    nozzle_check = (
        '    if _topic_is_nozzle_intent(question) and not _nozzle_guide_url_plausible(\n\n'
        '        url, allow_silicone=_topic_is_nozzle_silicone_intent(question)\n\n'
        '    ):\n\n'
        '        return False\n'
    )
    nozzle_new = (
        '    if (\n\n'
        '        _topic_is_nozzle_intent(question)\n\n'
        '        and not _topic_is_filament_material_choice_intent(question)\n\n'
        '        and not _nozzle_guide_url_plausible(\n\n'
        '            url, allow_silicone=_topic_is_nozzle_silicone_intent(question)\n\n'
        '        )\n\n'
        '    ):\n\n'
        '        return False\n\n'
        '    if _topic_is_filament_material_choice_intent(question) and not _filament_material_guide_url_plausible(url):\n\n'
        '        return False\n'
    )
    if nozzle_check not in text:
        raise RuntimeError("nozzle check anchor not found")
    text = text.replace(nozzle_check, nozzle_new, 1)

    path.write_text(text, encoding="utf-8", newline="\n")
    print("wiki_ranking: patched")


def patch_ru_layer(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "print TPU flexible filament" in text:
        print("ru_layer: already patched")
        return
    old = '    (re.compile(r"\\bфиламент\\w*\\b", re.I), "filament"),\n'
    new = (
        old
        + '    (re.compile(r"\\bтпу\\b|\\btpu\\b", re.I), "TPU flexible filament print settings"),\n'
        + '    (re.compile(r"\\bпластик\\w*\\b", re.I), "filament plastic material"),\n'
    )
    if old not in text:
        raise RuntimeError("ru_layer anchor not found")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("ru_layer: patched")


def main() -> None:
    patch_text_heuristics(ROOT / "app" / "bot" / "text_heuristics.py")
    patch_wiki_ranking(ROOT / "app" / "bot" / "wiki_ranking.py")
    patch_ru_layer(ROOT / "app" / "ru_layer.py")


if __name__ == "__main__":
    main()
