# Сервер создаёт снимок базы без домашней папки

Implementation commit: 1e4f7316513c7c8b329dfe01c8c43a41e5ee38cc — явный CLI backup выполняется до поиска домашней папки и bootstrap-конфигурации.

## HEAD

Status: Implemented and verified.

Branch: `factory/aaac33cd-686-712a01d8-21f`.

Implementation commit: `1e4f7316513c7c8b329dfe01c8c43a41e5ee38cc`.

What changed: `factory-server -database SOURCE -backup DEST` создаёт
автономный снимок без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`.
Остальные режимы сохраняют прежнюю инициализацию.

Evidence: subprocess-регрессия — PASS; `go test ./...` — PASS;
`go build ./...` — PASS.

One next action: провести review и влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

- Перенесён проверенный кандидат CARD-0124 без альтернативной реализации.
- Ранний recovery-путь включается только для непустого `-backup` и явно
  посещённого `-database`; грамматику разбирает стандартный `flag.FlagSet`.
- Subprocess-тест собрал настоящий сервер и подтвердил четыре формы флагов без
  домашних переменных, автономность снимка и неизменность файлов источника.
- `go test -count=1 ./cmd/factory-server -run
  '^TestBackupCLICreatesSnapshotWithoutHome$'`, `go test ./...` и
  `go build ./...` завершились успешно.
