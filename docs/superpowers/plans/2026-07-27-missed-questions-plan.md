# Обработка вопросов без ответа Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разобрать серверную очередь вопросов без ответа и предотвратить повторное накопление реплик этой ветки.

**Architecture:** Существующие `manual_qa` покрывают уже известные темы; новые технические ответы добавляются в JSON. Для болтовни добавляется одна узкая функция в `_banter.py`, её регистрация в `_filter.py` и регрессионные тесты.

**Tech Stack:** Python 3, JSON, pytest, git, SSH к production-хосту.

## Global Constraints

- Не коммитить `.env`, токены и посторонний `scripts/analyze_jul24_missed.py`.
- Не пушить без прямого запроса.
- `data/missed_questions.json` после полного разбора должен содержать `[]`.
- Новые ключи `manual_qa` должны быть длиной не менее 6 символов.

### Task 1: Регрессионные тесты

**Files:**
- Modify: `tests/test_missed_jul23_chatter.py`

- [ ] Добавить тесты на реплики ветки и негативные тесты на подробный технический вопрос.
- [ ] Запустить выбранные тесты и зафиксировать ожидаемый RED до реализации.

### Task 2: Фильтр и ручные ответы

**Files:**
- Modify: `app/bot/heuristics/_banter.py`
- Modify: `app/bot/heuristics/_filter.py`
- Modify: `app/bot/heuristics/__init__.py`
- Modify: `app/bot/text_heuristics.py`
- Modify: `data/manual_qa.json`

- [ ] Реализовать минимальную узкую эвристику с защитой явных просьб о помощи.
- [ ] Зарегистрировать и реэкспортировать функцию.
- [ ] Добавить три кратких ручных ответа с проверенными ссылками или без ссылки при отсутствии точной страницы.
- [ ] Повторно запустить тесты и проверить матчинг.

### Task 3: Очистка и финальная проверка

**Files:**
- Modify: `data/missed_questions.json`

- [ ] Записать локальную очередь как `[]`.
- [ ] Закоммитить относящиеся изменения.
- [ ] На сервере сбросить очередь в `[]` и проверить содержимое.
- [ ] Выполнить полный `pytest` и проверить рабочее дерево.
