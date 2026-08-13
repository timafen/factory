Implementation commit: 76d16c5191dcc8c44a001ffb71dbbaebf183f573 — текущий защищённый выпуск фиксирует Gate в доверенных Git-объектах и всегда запускает полный набор проверок; облегчение документного пути ещё не реализовано.

# CARD-0105 — Документные изменения проходят лёгкие ворота

## HEAD

- Status: Specification ready — implementation not started.
- Branch: `factory/582fc43b-7d6-1deacb08-914`.
- Owner outcome: изменения только обычных Markdown-файлов не ждут неизменившиеся
  UI/Go тесты, а любой сомнительный diff автоматически получает полный Gate.

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
