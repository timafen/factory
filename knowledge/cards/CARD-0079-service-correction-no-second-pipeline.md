# CARD-0079 — Служебная коррекция не запускает второй конвейер

Implementation commit: 2edcd9b1890c3419952297b4eadc4b5d300f46dd — возврат этапа учитывается только после создания повторной задачи.

## HEAD

- Status: Specification ready — awaiting implementation.
- Specification: `knowledge/specs/service-correction-does-not-start-second-pipeline.md`.
- What will change: Control Plane явно сохранит родителя и вид служебной
  коррекции, а Пилот перестанет считать её самостоятельной работой.
- Acceptance evidence: целевой Python-тест докажет отсутствие нового
  конвейера для маркированной дочерней задачи; Go-тесты подтвердят миграцию,
  API и оконную метрику предотвращённых дублей.
- Next action: Implement по спецификации, затем Verify.

## LOG

### 2026-08-11 — Specification

Владелец утвердил first-class контракт `parent_task_id` + `correction_kind`.
Зафиксированы nullable-миграция, API, ограниченный набор видов cap-return,
пропуск маркированной задачи в Пилоте и метрика
`duplicate_pipeline_starts_prevented`. Старые задачи с пустыми полями остаются
обычными; `request_key` не становится главным контрактом служебности.
