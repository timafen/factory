# CARD-0091: Безопасный journal и восстанавливаемый откат выпуска

Implementation commit: 5d0f278 — journal выпуска разбирается безопасно, остановка служб обязательна, DB restore связан с ожидающим поколением

## HEAD

Status: Implemented; production release не выполнялся.

Branch: factory/08ec33ed-9b5-56e7cd06-80a

Implementation commit: 5d0f278 — безопасный journal, fail-closed остановка служб и проверка DB restore до мутации.

What changed: root-процесс больше не исполняет содержимое journal как shell; восстановление БД принимает только snapshot из связанного ожидающего journal и отвергает sidecar-файлы.

Evidence: `bash -n ops/fx-factory-release` → PASS; `bash ops/test-fx-factory-release.sh` → PASS; `git diff --check` → PASS.

One next action: повторить проверку в root-enabled systemd fixture.

## LOG

### 2026-08-11 — Implement

Устранены замечания Review по trusted release-state, остановке служб и порядку DB restore; обычный rollback не меняет live DB, а отдельное восстановление проверяет journal до переключения файлов. Целевой fixture и shell syntax проходят; systemd fixture в текущем окружении требует root.
