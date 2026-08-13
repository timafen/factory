Implementation commit: 32f901785a5c70f3a448292b6bd96423f1da35aa — Markdown-only кандидаты после доверенного checkout проходят `git diff --check`, а все сомнительные изменения сохраняют полный Gate.

# CARD-0105 — Документные изменения проходят лёгкие ворота

## HEAD

- Status: Implemented — ready for verification.
- Branch: `factory/6cde39c6-851-9e21a67b-306`.
- Implementation commit: `32f901785a5c70f3a448292b6bd96423f1da35aa`.
- What changed: raw NUL-delimited diff допускает только непустые обычные `.md`
  и запускает `git diff --check`; mode, symlink, rename, смешанные и кодовые
  изменения продолжают идти через полный UI+Go+release Gate.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` →
  PASS; `bash ops/test-fx-factory-release.sh` → PASS.
- Next action: проверить изменения независимым review перед слиянием.

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
