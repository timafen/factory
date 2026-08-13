Implementation commit: 3301907af829ddc23ecb391ba0f6e52adc0ef243 — определена проверяемая реализация доступа Pilot, прямого broker driver, видимого отказа и адресной сверки 28 waits.

# CARD-0112 — Восстановить автопоезд выпуска и видимость отказа

## HEAD

- Status: Specification — готово к Implement + Test.
- Branch: `factory/bcb45ab3-31d-a8de1e3a-3d2`.
- Specification: `knowledge/specs/auto-release-broker-access-and-failure-visibility.md`.
- Scope: доступ Pilot к broker socket, passwordless fixed-path Factory adapter,
  дедуплицированная видимость terminal failure и доказательная адресная сверка
  ровно 28 осиротевших waits.
- Out of scope: SQLite/API protocol, `NoNewPrivileges`, adapters других
  проектов, эвристическое массовое завершение и изменение live state этой
  поставкой.
- Evidence: спецификация сверена с фактическими installer, release generation,
  broker executor, Pilot V2 delivery/outbox и Overview projection; обязательная
  проверка реализации — `python3 ops/test-reconcile-factory-delivery-waits.py`.
- Next action: реализовать перечисленные файлы и сформировать манифест 28 waits
  только из подтверждённого production snapshot и успешного ручного выпуска.

## LOG

### 2026-08-13 — Specification

Зафиксированы четыре независимые границы исправления. Group drop-in переносится
с `factory-server.service` на реального клиента сокета `factory-pilot.service`
с обязательным restart. Factory adapters broker запускают root-owned
`/usr/local/lib/fx-factory-release` напрямую и сохраняют code-owned allowlist,
тогда как другие adapters не меняются.

Terminal failure получает deterministic failure outbox/journal event и остаётся
`failed`: receipts, `mark_final(true)` и закрытие waits запрещены. Overview
показывает текущую либо последнюю ошибку человеческим текстом без SHA, PID и
внутренних идентификаторов.

Одноразовая сверка принимает только явный набор из 28 уникальных waits,
совпавший с зафиксированным state preimage. Для каждого wait требуется точный
verified merge SHA, доказанное ancestry в SHA установленного ручного выпуска,
совпадающие release-info/current manifest и завершённый release journal. Tool
создаёт отдельный output и не пишет live state; операторское применение остаётся
за пределами автоматической поставки.

### 2026-08-13 — Проверяемая передача

Спецификация дополнена отдельными строками `ГОТОВО-КОГДА` для каждого файла
реализации и одной обязательной команды целевого reconciliation-теста. Это
фиксирует измеримый контракт передачи разработке; продуктовый код в этой работе
не изменяется.
