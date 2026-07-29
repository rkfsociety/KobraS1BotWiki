# Разбор вопросов без ответа 2026-07-29 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Полностью разобрать 201 запись из боевой очереди, дать ответы на самостоятельные технические вопросы и не отвечать на контекстную болтовню.

**Architecture:** Новая узкая функция `_is_missed_jul29_thread_noise` отсекает только распознанные типы реплик текущих веток и защищает самостоятельные технические вопросы. Существующие записи `manual_qa` получают недостающие ключи; новые ответы добавляются лишь для тем, которых ещё нет. После проверки покрытия очередь очищается.

**Tech Stack:** Python 3.12, pytest, JSON-хранилища `data/*.json`, существующий пакет `app.bot.heuristics`.

## Global Constraints

- Работать в текущем `master`; ветку не создавать.
- Для реальных вопросов отдавать приоритет `data/manual_qa.json`.
- Не добавлять непроверенные или неточные ссылки.
- Для chatter-фильтра обязательны негативные тесты на реальные вопросы.
- После полного разбора записать `[]` в `data/missed_questions.json`.
- Создать коммит только с относящимися к задаче файлами; push не выполнять.

---

### Task 1: Зафиксировать ожидаемую классификацию

**Files:**
- Create: `tests/test_missed_jul29_chatter.py`

**Interfaces:**
- Consumes: `app.bot.text_heuristics._is_missed_jul29_thread_noise`
- Produces: регрессии для чатовых веток и защита самостоятельных вопросов

- [ ] **Step 1: Write the failing tests**

Добавить параметризованные примеры для модераторского спора, кратких ответов, советов собеседнику, обсуждения влажности, разборки головы и последовательной печати. Отдельно добавить негативные примеры для недоэкструзии, повторных засоров, очистки сопла, PETG, подключения проводов, пружин стола и неисправной сушки.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_missed_jul29_chatter.py -q`

Expected: FAIL при импорте отсутствующей `_is_missed_jul29_thread_noise`.

### Task 2: Добавить узкий chatter-фильтр

**Files:**
- Modify: `app/bot/heuristics/_banter.py`
- Modify: `app/bot/heuristics/_filter.py`
- Modify: `app/bot/heuristics/__init__.py`
- Modify: `app/bot/text_heuristics.py`

**Interfaces:**
- Produces: `_is_missed_jul29_thread_noise(text: str) -> bool`

- [ ] **Step 1: Implement the minimal classifier**

Добавить защиту самостоятельных технических вопросов, затем узкие признаки обсуждений текущих веток: модерация/спор, спам, обещания и ссылки, короткие контекстные реплики, личный опыт и советы без запроса, дискуссии о последовательной печати, влажности, разборке головы и калибровке.

- [ ] **Step 2: Register and export the classifier**

Подключить функцию в `_is_non_wiki_chatter_message`, `heuristics.__init__` и совместимый `text_heuristics.py`.

- [ ] **Step 3: Run focused tests**

Run: `python -m pytest tests/test_missed_jul29_chatter.py tests/test_bad_answers_chatter.py -q`

Expected: PASS.

### Task 3: Закрыть реальные вопросы через manual_qa

**Files:**
- Modify: `data/manual_qa.json`
- Modify: `tests/test_missed_jul29_chatter.py`

**Interfaces:**
- Consumes: `find_manual_qa_answer(load_manual_qa_store(), text)`
- Produces: краткие ответы и устойчивые ключи длиной не менее 6 символов

- [ ] **Step 1: Add failing matching tests**

Проверить матчинг повторного засора, очистки сопла/cold pull, серой полосы после смены цвета, температуры и скорости PETG, очистки клея, скрипа PETG, безопасного подключения, неисправной сушки и обращения в поддержку.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_missed_jul29_chatter.py -q`

Expected: FAIL для отсутствующих ключей/ответов и ложного совпадения длинного вопроса с ответом про стальное сопло.

- [ ] **Step 3: Update manual answers**

Удалить неоднозначный ключ `тройках принтера`, расширить подходящие существующие записи и добавить только отсутствующие ответы. Официальные ссылки использовать лишь для уже проверенных страниц Anycubic и формы поддержки.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_missed_jul29_chatter.py tests/test_manual_qa_faq.py -q`

Expected: PASS.

### Task 4: Проверить покрытие и очистить очередь

**Files:**
- Modify: `data/missed_questions.json`

- [ ] **Step 1: Audit every queue entry**

Для каждой из 201 записей проверить, что она либо отсекается `_is_non_wiki_chatter_message`, либо получает ответ `find_manual_qa_answer`.

- [ ] **Step 2: Clear the queue**

Заменить содержимое `data/missed_questions.json` на `[]`.

- [ ] **Step 3: Run complete verification**

Run:

```powershell
python -m pytest tests/ -q
python C:\Users\USSR\.codex\skills\repairing-text-encoding\scripts\scan_mojibake.py .
git diff --check
```

Expected: все тесты проходят, сканер не находит повреждённой кодировки, `git diff --check` не сообщает ошибок.

- [ ] **Step 4: Review and commit**

Проверить `git diff`, отсутствие посторонних файлов и пустую очередь; создать один итоговый коммит без push.
