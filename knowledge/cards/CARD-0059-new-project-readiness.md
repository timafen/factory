# CARD-0059 — Честная готовность нового проекта

## HEAD

Status: Specified — ожидает реализации.
Specification: `knowledge/specs/new-project-readiness.md`.
Decision: возможность воркера получить новый managed-репозиторий не считается
подтверждённой готовностью, пока готовый воркер не сообщает его как cached или
advertised.
Implementation commit: ещё не создан — эта карточка заведена на стадии
Specification, изменения продукта запрещены до Implement + Test.

## LOG

### 2026-08-10 — Specification

Проверены текущие `internal/controlplane/store.go`,
`internal/protocol/types.go`, `web/src/Repositories.tsx` и подготовка managed
репозитория, описанная в `docs/worker.md`. Серверный `routing_ready` сейчас честно
означает возможность маршрута, но UI называет готовым и uncached/unadvertised
воркера, для которого доступ к конкретному проекту проверит лишь первая попытка.
Спецификация сохраняет API и on-demand acquisition, но разделяет подтверждённое,
непроверенное, заблокированное и выключенное состояния в интерфейсе.
