Implementation commit: d4075ad5fc96ab614e8d06294303aa8d32fc8415 — переименования, копии и пути с управляющими символами переводят документный выпуск на полный Gate.

# CARD-0105 — Документные изменения проходят лёгкие ворота

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/4a7494a6-9bb-2d050abd-5b7`.
- Implementation commit: `d4075ad5fc96ab614e8d06294303aa8d32fc8415`.
- What changed: `diff-tree` распознаёт rename/copy; статусы `R`/`C` и пути с
  управляющими символами fail-closed запускают полный UI+Go+release Gate.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и
  `bash ops/test-fx-factory-release.sh` → PASS.
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

### 2026-08-12 — Implement

Включены `-M -C --find-copies-harder` в raw diff; rename и copy распознаются и
не могут пройти лёгкие ворота. Пути с управляющими символами также отклоняются;
добавлена copy fixture, а rename и newline fixture подтверждают полный Gate.
`bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и
`bash ops/test-fx-factory-release.sh` — PASS.
