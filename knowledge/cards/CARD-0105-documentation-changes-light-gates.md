Implementation commit: e8ce86a94978f3e5a7d39475f346ad52bc4937cd — безопасные Markdown-only коммиты проходят лёгкие ворота, а неоднозначные изменения сохраняют полный Gate.

# CARD-0105 — Документные изменения проходят лёгкие ворота

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/a2b5f25d-270-33378f2b-28f`.
- Implementation commit: `e8ce86a94978f3e5a7d39475f346ad52bc4937cd`.
- What changed: обычные Markdown-only коммиты проходят `git diff --check`
  без UI/Go/release Gate; неоднозначные diff остаются на полном Gate.
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

### 2026-08-12 — Implement

Реализация пересобрана от свежего `origin/main`. Rename-fixture больше не
добавляет отсутствующий старый путь, а ошибка `diff-tree` воспроизводится
детерминированно после успешных clone и checkout. `bash -n` и полный целевой
`bash ops/test-fx-factory-release.sh` → PASS.
