# CARD-0302 — Полная инвентаризация каталога выпусков до очистки

## HEAD

- Status: Specification ready.
- Branch: `factory/dc9e4d3b-cd6-79d0f1b6-990`.
- Specification: `knowledge/specs/release-directory-inventory-safe-cleanup.md`.
- Owner decision: обследовать все 55 каталогов вне `generations/`, включая
  `build-*` пользователя `factory` и другие временные префиксы; пока ничего
  не удалять и не изменять.
- Implementation scope: `ops/fx-factory-release`,
  `ops/test-fx-factory-release.sh`.
- Required check: `bash ops/test-fx-factory-release.sh`.
- Next action: получить production-снимок 55 каталогов, классифицировать
  каждую запись и согласовать точные approved candidates по `scan_id`.

## LOG

### 2026-08-15 — Specification

Драйвер создаёт рабочую папку как `$REL/build-XXXXXX`, а его retention
рассматривает только `$REL/generations`; вне этой истории реестр каталогов не
ведётся. Предыдущая узкая политика была основана на снимке 41 каталога и на
префиксе `build-*`; текущий подтверждённый объём — 55, поэтому она не годится
как доказательство безопасности. В данной среде production-путь
`/opt/factory-data/releases/factory` отсутствует, поэтому недостающие имена,
владельцы и активность не вымышлялись.

Спецификация требует сначала создать полный воспроизводимый снимок и относит
неопределённые записи к fail-closed классу `unknown`. `build-*` владельца
`factory` не удаляется только по имени, uid или возрасту; столь же строго
защищены другие временные префиксы, указатели release и активные процессы.
Никакое удаление, перемещение, production release или изменение исходников
на этапе Specification не выполнялось.

Номер и путь карточки проверены по свежему `origin/main` и опубликованным
веткам: CARD-0301 занят, а CARD-0302 и этот путь свободны.
