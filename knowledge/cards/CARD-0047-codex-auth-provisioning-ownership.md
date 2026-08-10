# CARD-0047 — Provisioning Codex создаёт auth-файлы от пользователя factory

## HEAD

- Status: Implemented — готово к проверке и выкладке.
- Branch: `factory/ae2c3cee-02e-75b9c303-11f`.
- Head commit: `d3c9243` — «Защитить общую авторизацию Codex при выпуске».
- Specification: `knowledge/specs/codex-auth-provisioning-ownership.md`.
- What changed: релиз до установки проверяет общую цель как обычный файл
  `600 factory:factory` и атомарно обновляет существующие auth-ссылки от имени
  `factory`; явный `CODEX_HOME` поддерживает provisioning нового воркера.
- Evidence: `bash ops/test-provision-codex-auth.sh` — PASS для корректной цели и
  fail-closed матрицы; `bash ops/test-fx-factory-release.sh` — PASS для порядка
  релиза и отказа до изменения работающей установки.
- One next action: выложить ветку и подтвердить владельца ссылок обязательной
  командой проверки метаданных на целевой машине.

## LOG

### 2026-08-10 — Specification

Владелец подтвердил: симлинки заменять не надо. Нужен внешний provisioning,
который создаёт их от `factory` и проверяет владельца и режим целевого auth-файла.
В репозитории Factory отсутствует соответствующий механизм, поэтому кодовая
поставка здесь не требуется; отдельная карточка фиксирует инфраструктурную работу.

### 2026-08-10 — Implement

Добавлен `ops/provision-codex-auth.sh`: он не читает секрет, отклоняет отсутствие,
неверный тип, режим, владельца или группу общей цели и только после проверки
создаёт ссылки от `factory`. `fx-factory-release` запускает его до установки и
перезапусков. Целевой тест, интеграционный тест релиза и `just test-tooling`
завершились PASS.
