"""Патч: _is_thread_printing_tip + стекл -> стеклянн."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "app" / "bot" / "text_heuristics.py"

FUNC_BODY = (
    "\n"
    "def _is_thread_printing_tip(text: str) -> bool:\n"
    "    \"\"\"Советы в треде без вопроса — не запрос к боту.\"\"\"\n"
    "    if not text or not text.strip() or \"?\" in text:\n"
    "        return False\n"
    "    if _message_has_help_intent(text):\n"
    "        return False\n"
    "    tl = re.sub(r\"\\s+\", \" \", text.lower()).strip()\n"
    "    if re.search(\n"
    "        r\"\\b(?:помогите|подскаж|что\\s+делать|не\\s+работает|\"\n"
    "        r\"как\\s+(?:настро|почин|исправ|сделать|убрать|решить|подключ|замен))\\b\",\n"
    "        tl,\n"
    "    ):\n"
    "        return False\n"
    "    if re.search(r\"\\b(?:ещё|также|тоже)\\s+важно\\b\", tl):\n"
    "        return True\n"
    "    if re.search(r\"\\bя\\s+бы\\b\", tl) and re.search(\n"
    "        r\"\\b(?:дал|дала|добавил|добавила|закрыл|закрыла|поставил|поставила|\"\n"
    "        r\"убрал|убрала|попробовал|попробовала|начал|начала|оставил|оставила|\"\n"
    "        r\"советовал|рекомендовал)\\w*\\b\",\n"
    "        tl,\n"
    "    ):\n"
    "        return True\n"
    "    if re.search(r\"\\bв\\s+общем-то\\b\", tl):\n"
    "        return True\n"
    "    if re.search(r\"\\bладно\\b\", tl) and re.search(r\"\\bспасибо\\b\", tl):\n"
    "        return True\n"
    "    if re.search(r\"\\bу\\s+меня\\s+(?:есть|стоит|имеется|лежат|лежит)\\b\", tl):\n"
    "        return True\n"
    "    return False\n"
    "\n"
)

OLD_SIG = "def _is_non_wiki_chatter_message(text: str) -> bool:"
OLD_KW = "\"стекл\","
NEW_KW = "\"стеклянн\","
OLD_TAIL = "        or _is_chat_past_incident_recollection(text)\n    )"
NEW_TAIL = "        or _is_chat_past_incident_recollection(text)\n        or _is_thread_printing_tip(text)\n    )"


def patch() -> None:
    t = P.read_text(encoding="utf-8")
    changed = False

    if OLD_KW in t:
        t = t.replace(OLD_KW, NEW_KW, 1)
        print("стекл -> стеклянн: OK")
        changed = True
    else:
        print("стекл keyword: already fixed or not found")

    if "_is_thread_printing_tip" not in t:
        if OLD_SIG in t:
            t = t.replace(OLD_SIG, FUNC_BODY + OLD_SIG, 1)
            print("_is_thread_printing_tip: added")
            changed = True
        else:
            print("ERROR: anchor _is_non_wiki_chatter_message not found")
    else:
        print("_is_thread_printing_tip: already present")

    if "_is_thread_printing_tip(text)" not in t:
        if OLD_TAIL in t:
            t = t.replace(OLD_TAIL, NEW_TAIL, 1)
            print("return clause: updated")
            changed = True
        else:
            print("ERROR: return clause anchor not found")
    else:
        print("return clause: already present")

    if changed:
        P.write_text(t, encoding="utf-8")
        print("Written.")
    else:
        print("Nothing to do.")


if __name__ == "__main__":
    patch()
