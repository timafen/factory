# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: 48b044c4e401080039da3d386208e16ba0bc7000 — перезапуск привязан к фактическому production-пути посредника

## HEAD

- Status: Ready for repeat review
- Branch: `factory/9bcbf482-22b-eda5089d-eeb`
- Implementation commit: `48b044c4e401080039da3d386208e16ba0bc7000`
- What changed: после durable terminal commit посредник определяет замену бинарника по фактическому пути `/opt/factory-data/bin/factory-release-broker` и перезапускает systemd unit; тест сверяет этот путь с production unit.
- Evidence: целевые restart и production-config тесты → PASS; все Go- и UI-тесты, tooling и launcher → PASS; `just build` → PASS.
- One next action: повторить Review исправленного production-пути.

## LOG

### 2026-08-13 — Implement

Добавлен restart после committed marker и освобождения active operation для успешного и откатившегося выпуска, который заменил broker. Неизменённый или неопределимый executable, ошибка persistence и повторный POST restart не вызывают. Целевые Go-тесты, race-проверка, release fixture, installer-тест и синтаксическая проверка прошли.

### 2026-08-13 — Implement

Исправлен блокер Review: restart теперь сравнивает запущенный процесс с бинарником по фактическому production-пути. Регрессионный тест фиксирует соответствие кода рабочему systemd unit; целевые restart/release/installer проверки, полный локальный набор и сборка прошли.
