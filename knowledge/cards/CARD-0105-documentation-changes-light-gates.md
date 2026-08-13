Implementation commit: 947e0c782d225e478b48d51fdd64e1873f125239 — все шесть неоднозначных Git-сценариев подтверждают fail-closed переход к полному Gate.

# CARD-0105 — Документные изменения проходят лёгкие ворота

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/671ab15f-e72-da47c992-9c0d-4a26-8762-e874f7a0f097`.
- Implementation commit: `947e0c782d225e478b48d51fdd64e1873f125239`.
- What changed: добавлены fail-closed испытания merge-коммита, коммита без
  родителя, пустого коммита, submodule, ошибки `git diff-tree` и имени файла
  с переводом строки; каждое подтверждает полный UI+Go+release Gate.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` →
  PASS; `bash ops/test-fx-factory-release.sh`, `cd web && npm test`,
  `cd web && npm run build`, `go test ./...` → PASS.
- Next action: выполнить независимый review перед слиянием.

## Контракт реализации

- Классифицировать документационный commit после доверенного checkout по raw
  NUL-delimited diff с его единственным родителем.
- Разрешить лёгкую проверку только непустому набору обычных `.md` без смены mode,
  rename/copy, symlink или submodule.
- На лёгком пути выполнить `git diff --check`; на любом неясном результате
  сохранить полный UI+Go+release Gate.
- Не менять build, snapshot, manifest, rollback, live-check и результат брокера.

## Проверка

Главное доказательство — `bash ops/test-fx-factory-release.sh`: suite должен
различать Markdown-only commit и отрицательные fixtures по журналу реально
вызванных команд, а также подтверждать остановку до мутаций при плохом Markdown.

## Файлы реализации

- `ops/fx-factory-release`
- `ops/test-fx-factory-release.sh`

Спецификация: `knowledge/specs/documentation-changes-light-gates.md`.

## LOG

### 2026-08-12 — Implement

Добавлен fail-closed классификатор raw NUL-delimited diff после доверенного
checkout. Markdown-only fixture подтверждает лёгкие ворота и поставку; fixtures
для Go, mixed, mode, symlink и rename подтверждают полный Gate, а whitespace
останавливает выпуск до сборки и мутаций. `bash ops/test-fx-factory-release.sh` — PASS.

### 2026-08-12 — Implement

Добавлены шесть обязательных fail-closed fixtures: merge, root, empty,
submodule, ошибка `git diff-tree` и имя с переводом строки. Каждая fixture
подтверждает запуск полного UI+Go+release Gate; `bash -n` и
`bash ops/test-fx-factory-release.sh` — PASS.
