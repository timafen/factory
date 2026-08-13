# Сервер создаёт снимок базы без домашней папки

Implementation commit: 7cf0368f7d2a0daf855a357f167d6f5fc67eedd3 — явный CLI backup выполняется до поиска домашней папки и bootstrap-конфигурации.

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/2900277a-169-836b7302-c15`.

Implementation commit: `7cf0368f7d2a0daf855a357f167d6f5fc67eedd3`.

What changed: `factory-server -database SOURCE -backup DEST` создаёт автономный снимок без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`; остальные режимы сохраняют прежнюю инициализацию.

Evidence: целевая subprocess-проверка четырёх форм CLI — PASS; полный `go test -count=1 ./...` и `go build ./...` — PASS.

One next action: выполнить Review и слияние после проверки владельцем.

## LOG

### 2026-08-13 — Implement

- Реализация и тесты перенесены с предыдущей ветки на свежий `origin/main`.
- Subprocess-тест запускает настоящий сервер без домашних переменных, проверяет четыре формы флагов, автономность снимка и неизменность источника.
- Целевая проверка, полный `go test -count=1 ./...`, `go build ./...`, `gofmt -l` и `git diff --check` завершились успешно.
