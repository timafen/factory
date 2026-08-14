# CARD-0127 — Выпуск перезапускает обновлённый broker

Implementation commit: не создан — этап Specification не вносит код; SHA появится в карточке после отдельного коммита реализации.

## HEAD

- Статус: Specified — ожидает Implement.
- Ветка: `factory/db9587c1-e97-d4a01507-a47`.
- Что должно измениться: после durable terminal-результата выпуск перезапускает
  активный broker ровно один раз, только если заменил его executable.
- Доказательство реализации: unit-тест порядка commit/restart и shell-fixture
  двух последовательных выпусков без `deleted-inode`.
- Следующее действие: реализовать границу restart в broker и расширить fixture.

## LOG

### 2026-08-13 — Specification

Определена поздняя граница перезапуска: release-driver не останавливает
родительский broker, поскольку работает в его cgroup; broker отправляет restart
только после durable terminal commit. Покрыты success, rollback после замены,
no-change и два последовательных выпуска. Product code на этапе спецификации
не изменялся, поэтому implementation commit отсутствует намеренно.
