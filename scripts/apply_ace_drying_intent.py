"""Патч: «аськи как сушилки» не должны тянуть ace-pro-filament-replacement-guide."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRYING_INTENT_FN = '''
def _topic_is_ace_filament_drying_intent(text: str | None) -> bool:
    """ACE Pro как сушилка / сушка филамента в станции — не замена катушки в ACE."""
    if not text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if not (_ace_mentioned(text) or re.search(r"\\bаськ\\w*\\b", t)):
        return False
    if re.search(r"\\b(?:замен|поменя|смени|установ|replace|remov|disassembl)\\w*\\b", t):
        return False
    has_dry = bool(
        re.search(
            r"\\b(?:сушилк\\w*|суш[иао]т|высуш|просуш|dryer|drying|dry\\s*box|"
            r"влажн\\w*|увлаж|moisture|desiccant|гигро)\\w*\\b",
            t,
        )
    )
    return has_dry


'''


def patch_text_heuristics(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_topic_is_ace_filament_drying_intent" in text:
        print("text_heuristics: already patched")
        return
    anchor = "def _user_already_replaced_motherboard(text: str) -> bool:"
    if anchor not in text:
        raise RuntimeError(f"anchor not found in {path}")
    text = text.replace(anchor, DRYING_INTENT_FN + anchor, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("text_heuristics: patched")


def patch_wiki_ranking(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_ace_drying_guide_url_plausible" in text:
        print("wiki_ranking: already patched")
        return

    imp_old = "    _topic_is_ace_connection_intent,\n\n    _topic_is_ace_not_detected_intent,"
    imp_new = (
        "    _topic_is_ace_connection_intent,\n\n"
        "    _topic_is_ace_filament_drying_intent,\n\n"
        "    _topic_is_ace_not_detected_intent,"
    )
    if imp_old not in text:
        raise RuntimeError("import anchor not found")
    text = text.replace(imp_old, imp_new, 1)

    helper = '''
def _ace_drying_guide_url_plausible(url: str) -> bool:
    """Сушка в ACE: заметки/FAQ, не replacement-guide по катушке."""
    u = url.lower().replace("_", "-")
    if "ace-pro-notes" in u:
        return True
    if "ace-pro" in u and u.rstrip("/").endswith("/faq"):
        return True
    return False


'''
    anchor = "def _door_guide_url_plausible(url: str) -> bool:"
    if anchor not in text:
        raise RuntimeError("door anchor not found")
    text = text.replace(anchor, helper + anchor, 1)

    bonus_anchor = "    if _topic_is_filament_feed_intent(topic):"
    bonus_new = (
        "    if _topic_is_ace_filament_drying_intent(topic):\n\n"
        "        if \"ace-pro-notes\" in u:\n\n"
        "            b += 48\n\n"
        "        elif \"ace-pro\" in u and u.rstrip(\"/\").endswith(\"/faq\"):\n\n"
        "            b += 28\n\n"
        "        if \"filament-replacement\" in u or (\"replacement\" in u and \"filament\" in u):\n\n"
        "            b -= 85\n\n"
        "        elif \"ace-pro\" in u and \"replacement\" in u:\n\n"
        "            b -= 65\n\n"
        "\n"
        "    if _topic_is_filament_feed_intent(topic):"
    )
    if bonus_anchor not in text:
        raise RuntimeError("bonus anchor not found")
    text = text.replace(bonus_anchor, bonus_new, 1)

    accept_anchor = "    if _topic_is_marketplace_commerce_intent(question):\n\n        return False"
    accept_new = (
        "    if _topic_is_ace_filament_drying_intent(question) and not _ace_drying_guide_url_plausible(url):\n\n"
        "        return False\n\n"
        "    if _topic_is_marketplace_commerce_intent(question):\n\n        return False"
    )
    if accept_anchor not in text:
        raise RuntimeError("accept anchor not found")
    text = text.replace(accept_anchor, accept_new, 1)

    path.write_text(text, encoding="utf-8", newline="\n")
    print("wiki_ranking: patched")


def patch_ru_layer(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "filament drying moisture" in text:
        print("ru_layer: already patched")
        return
    old = (
        '    (re.compile(r"\\bаська\\b|\\bаска\\b|\\bаськ\\w*\\b|\\bэйс\\b", re.I), "ACE Pro filament station"),\n\n'
        '    (re.compile(r"\\bace\\s*pro\\b", re.I), "ACE Pro"),'
    )
    new = (
        '    (re.compile(r"\\bаська\\b|\\bаска\\b|\\bаськ\\w*\\b|\\bэйс\\b", re.I), "ACE Pro filament station"),\n\n'
        '    (re.compile(r"\\bсушилк\\w*\\b|\\bсуш[иао]т\\w*\\b", re.I), "filament drying moisture desiccant"),\n\n'
        '    (re.compile(r"\\bace\\s*pro\\b", re.I), "ACE Pro"),'
    )
    if old not in text:
        raise RuntimeError("ru_layer map anchor not found")
    text = text.replace(old, new, 1)

    expand_anchor = '            out.append("printer binding ACE Pro network connection troubleshooting")\n\n        if re.search(r"филамент|подач|шестерн|экструдер|feeding|extruder", base, re.I)'
    expand_new = (
        '            out.append("printer binding ACE Pro network connection troubleshooting")\n\n'
        '        if re.search(r"(аська|аска|аськ\\w*|ace\\s*pro|\\bace\\b)", base, re.I) and re.search(\n\n'
        '            r"сушилк|суш[иао]т|dryer|drying|влажн|moisture", base, re.I\n\n'
        '        ):\n\n'
        '            out.append("ACE Pro filament drying moisture storage ace-pro-notes")\n\n'
        '        if re.search(r"филамент|подач|шестерн|экструдер|feeding|extruder", base, re.I)'
    )
    if expand_anchor not in text:
        raise RuntimeError("ru_layer expand anchor not found")
    text = text.replace(expand_anchor, expand_new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("ru_layer: patched")


def main() -> None:
    patch_text_heuristics(ROOT / "app" / "bot" / "text_heuristics.py")
    patch_wiki_ranking(ROOT / "app" / "bot" / "wiki_ranking.py")
    patch_ru_layer(ROOT / "app" / "ru_layer.py")


if __name__ == "__main__":
    main()
