"""Патч: вопрос про прошивку — не error-codes, уточнение без «кода ошибки»."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIRMWARE_INTENT_FN = '''
def _topic_is_firmware_update_intent(text: str | None) -> bool:
    """Установка/обновление прошивки — не страницы /error-codes/."""
    if not text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _is_error_code_query(text):
        return False
    if not re.search(r"\\b(?:прошив|фирмвар|firmware)\\w*\\b", t):
        return False
    return bool(
        re.search(
            r"\\b(?:"
            r"став|обнов|установ|залив|прошив|апдейт|update|flash|"
            r"прилетел|вышл|вышла|новая|новую|верси|version|"
            r"можно\\s+ли|стоит\\s+ли|надо\\s+ли|нужно\\s+ли"
            r")\\w*\\b",
            t,
        )
    )


'''


def patch_text_heuristics(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_topic_is_firmware_update_intent" in text:
        print("text_heuristics: already patched")
        return
    anchor = "def _topic_is_filament_material_choice_intent(text: str | None) -> bool:"
    if anchor not in text:
        raise RuntimeError(f"anchor not found in {path}")
    text = text.replace(anchor, FIRMWARE_INTENT_FN + anchor, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("text_heuristics: patched")


def patch_wiki_ranking(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_firmware_guide_url_plausible" in text:
        print("wiki_ranking: already patched")
        return

    imp_old = "    _topic_is_filament_slicing_settings_intent,\n\n    _user_already_replaced_motherboard,"
    imp_new = (
        "    _topic_is_filament_slicing_settings_intent,\n\n"
        "    _topic_is_firmware_update_intent,\n\n"
        "    _user_already_replaced_motherboard,"
    )
    if imp_old not in text:
        raise RuntimeError("import anchor not found")
    text = text.replace(imp_old, imp_new, 1)

    helper = '''
def _firmware_guide_url_plausible(url: str) -> bool:
    """Гайды по обновлению прошивки, не коды ошибок."""
    u = url.lower().replace("_", "-")
    if "/error-codes" in u:
        return False
    if "firmware-update" in u or "firmware-update-guide" in u:
        return True
    if "check-or-updating-printer-firmware" in u:
        return True
    if "firmware-version-update" in u or "firmware-upgrade-log" in u:
        return True
    if "upload-firmware" in u:
        return True
    if "firmware" in u and "update" in u:
        return True
    if "general-knowledge" in u and "firmware" in u:
        return True
    return False




'''
    anchor = "def _topic_is_nozzle_intent(topic: str | None) -> bool:"
    text = text.replace(anchor, helper + anchor, 1)

    bonus_anchor = '    if "хотэнд" in tl or "hotend" in tl or "hot end" in tl:\n\n        if "hotend" in u or "hot-end" in u:\n\n            b += 20\n'
    bonus_new = (
        bonus_anchor
        + "\n    if _topic_is_firmware_update_intent(topic) and not _is_error_code_query(topic):\n\n"
        + '        if "/error-codes/" in u:\n\n            b -= 85\n\n'
        + '        elif _firmware_guide_url_plausible(url):\n\n            b += 68\n\n'
        + '        elif "firmware" in u:\n\n            b += 22\n'
    )
    if bonus_anchor not in text:
        raise RuntimeError("bonus anchor not found")
    text = text.replace(bonus_anchor, bonus_new, 1)

    pen_anchor = (
        'def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:\n\n'
        '    """Тема «дверь» или «подача филамента», а URL про другое узло — сильный штраф."""\n\n'
        '    if _topic_is_filament_material_choice_intent(topic) or _topic_is_filament_slicing_settings_intent(topic):'
    )
    pen_new = (
        'def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:\n\n'
        '    """Тема «дверь» или «подача филамента», а URL про другое узло — сильный штраф."""\n\n'
        '    if _topic_is_firmware_update_intent(topic):\n\n'
        '        if _firmware_guide_url_plausible(url):\n\n'
        '            return 0\n\n'
        '        if "/error-codes/" in url.lower():\n\n'
        '            return 90\n\n'
        '        return 42\n\n'
        '    if _topic_is_filament_material_choice_intent(topic) or _topic_is_filament_slicing_settings_intent(topic):'
    )
    if pen_anchor not in text:
        raise RuntimeError("penalty anchor not found")
    text = text.replace(pen_anchor, pen_new, 1)

    resp_anchor = "    if _topic_is_filament_feed_intent(question) and not _filament_feed_guide_url_plausible(url):\n\n        return False\n\n    return True"
    resp_new = (
        "    if _topic_is_firmware_update_intent(question) and not _firmware_guide_url_plausible(url):\n\n"
        "        return False\n\n"
        "    if _topic_is_filament_feed_intent(question) and not _filament_feed_guide_url_plausible(url):\n\n"
        "        return False\n\n    return True"
    )
    if resp_anchor not in text:
        raise RuntimeError("response anchor not found")
    text = text.replace(resp_anchor, resp_new, 1)

    path.write_text(text, encoding="utf-8", newline="\n")
    print("wiki_ranking: patched")


def patch_i18n(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "clarify_prompt_no_error_code" in text:
        print("i18n: already patched")
        return
    ru_old = (
        '        "clarify_prompt": (\n'
        '            "Похоже, ответ есть в вики, но мне не хватает данных.\\n"\n'
        '            "Уточни, пожалуйста, <b>модель принтера</b> {hint} (например: <b>Kobra S1</b>) и/или <b>код ошибки</b>.\\n"\n'
        '            "Ответь на это сообщение."\n'
        '        ),\n'
    )
    ru_new = (
        '        "clarify_prompt": (\n'
        '            "Похоже, ответ есть в вики, но мне не хватает данных.\\n"\n'
        '            "Уточни, пожалуйста, <b>модель принтера</b> {hint} (например: <b>Kobra S1</b>) и/или <b>код ошибки</b>.\\n"\n'
        '            "Ответь на это сообщение."\n'
        '        ),\n'
        '        "clarify_prompt_no_error_code": (\n'
        '            "Похоже, ответ есть в вики, но мне не хватает данных.\\n"\n'
        '            "Уточни, пожалуйста, <b>модель принтера</b> {hint} (например: <b>Kobra S1</b>).\\n"\n'
        '            "Ответь на это сообщение."\n'
        '        ),\n'
    )
    if ru_old not in text:
        raise RuntimeError("i18n ru anchor not found")
    text = text.replace(ru_old, ru_new, 1)

    en_old = (
        '        "clarify_prompt": (\n'
        '            "It looks like the answer is in the wiki, but I need more details.\\n"\n'
        '            "Please specify your <b>printer model</b> {hint} (e.g. <b>Kobra S1</b>) and/or an <b>error code</b>.\\n"\n'
        '            "Reply to this message."\n'
        '        ),\n'
    )
    en_new = (
        '        "clarify_prompt": (\n'
        '            "It looks like the answer is in the wiki, but I need more details.\\n"\n'
        '            "Please specify your <b>printer model</b> {hint} (e.g. <b>Kobra S1</b>) and/or an <b>error code</b>.\\n"\n'
        '            "Reply to this message."\n'
        '        ),\n'
        '        "clarify_prompt_no_error_code": (\n'
        '            "It looks like the answer is in the wiki, but I need more details.\\n"\n'
        '            "Please specify your <b>printer model</b> {hint} (e.g. <b>Kobra S1</b>).\\n"\n'
        '            "Reply to this message."\n'
        '        ),\n'
    )
    if en_old not in text:
        raise RuntimeError("i18n en anchor not found")
    text = text.replace(en_old, en_new, 1)

    path.write_text(text, encoding="utf-8", newline="\n")
    print("i18n: patched")


def patch_clarify(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "_topic_is_firmware_update_intent" in text:
        print("clarify: already patched")
        return
    imp_old = "    _needs_model_clarification,\n"
    imp_new = "    _needs_model_clarification,\n    _topic_is_firmware_update_intent,\n"
    if imp_old not in text:
        raise RuntimeError("clarify import anchor not found")
    text = text.replace(imp_old, imp_new, 1)

    old = '    clarify_body = _t(lang, "clarify_prompt").format(hint=hint)\n'
    new = (
        '    # Про прошивку — только модель, без «кода ошибки».\n'
        '    clarify_key = (\n'
        '        "clarify_prompt_no_error_code"\n'
        '        if _topic_is_firmware_update_intent(text)\n'
        '        else "clarify_prompt"\n'
        '    )\n'
        '    clarify_body = _t(lang, clarify_key).format(hint=hint)\n'
    )
    if old not in text:
        raise RuntimeError("clarify body anchor not found")
    text = text.replace(old, new, 1)

    old2 = '        out = _t(lang, "clarify_prompt").format(hint=hint)\n'
    new2 = '        out = _t(lang, clarify_key).format(hint=hint)\n'
    if old2 not in text:
        raise RuntimeError("clarify slash anchor not found")
    text = text.replace(old2, new2, 1)

    hint_old = '        "enclosure",\n\n    )\n'
    hint_new = (
        '        "enclosure",\n\n'
        '        "прошив",\n\n'
        '        "firmware",\n\n'
        '    )\n'
    )
    if hint_old not in text:
        raise RuntimeError("clarify hint anchor not found")
    text = text.replace(hint_old, hint_new, 1)

    path.write_text(text, encoding="utf-8", newline="\n")
    print("clarify: patched")


def main() -> None:
    patch_text_heuristics(ROOT / "app" / "bot" / "text_heuristics.py")
    patch_wiki_ranking(ROOT / "app" / "bot" / "wiki_ranking.py")
    patch_i18n(ROOT / "app" / "bot" / "i18n.py")
    patch_clarify(ROOT / "app" / "bot" / "clarify.py")


if __name__ == "__main__":
    main()
