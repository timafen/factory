# CARD-0048 — Регрессионная проверка идемпотентности Verify

## HEAD

- Status: Verified PASS.
- Branch: `factory/39f26cd9-cb9-14766b8b-b57`.
- Head commit: `1fc8cb1` (`Кириллица в заголовках задач и в тексте коммита превращается в "?"`).
- What changed: код не менялся: защита из основной ветки хранит ID Verify-задачи
  в журнале мёржей и повторно не завершает её.
- Evidence: `python3 -m unittest pilot.test_pilot.PipelineWatchTests.test_verify_pass_is_processed_once -v` — 1/1 OK; два цикла дают один мёрж и одну запись.
- One next action: изменений для вливания нет; продолжать наблюдение только при новом воспроизведении сбоя.

## LOG

### 2026-08-10 — Implement

Проверена защита, уже находящаяся в свежем `main`, для повторной обработки
одного Verify PASS. Первый цикл выполняет мёрж и сохраняет ID задачи; второй
цикл пропускает финализацию, поэтому не создаёт повторный мёрж или запись.

Проверка: `python3 -m unittest pilot.test_pilot.PipelineWatchTests.test_verify_pass_is_processed_once -v` — 1/1 OK.
