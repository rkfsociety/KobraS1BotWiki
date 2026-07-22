# Task 2 — серверный API пользовательского чата

## Production/tests commit

`0bd3f8e70d0fcf333d1b2cdb1a98d93dbf20b866` — `Добавить API персонального чата Mini App`.

## Изменённые файлы

- `app/bot/miniapp_access.py`
- `app/web_miniapp.py`
- `app/web_panel.py`
- `tests/test_miniapp_access.py`
- `tests/test_web_miniapp.py`

## RED

До реализации целевой запуск завершился ожидаемым RED: 7 интеграционных проверок не прошли из-за отсутствия пользовательской роли Mini App и endpoint'ов `/api/app/chat/history` и `/api/app/chat/message`. Отдельный тест членства завершился ошибкой импорта отсутствующей `is_group_member`.

## GREEN и проверки

```text
python -m pytest tests/test_web_miniapp.py tests/test_miniapp_access.py -q --basetemp=C:\Temp\kobra-pytest
24 passed in 11.02s

ruff check app/bot/miniapp_access.py app/web_miniapp.py app/web_panel.py tests/test_web_miniapp.py tests/test_miniapp_access.py
All checks passed!
```

Также выполнен `git diff --check` без ошибок.
