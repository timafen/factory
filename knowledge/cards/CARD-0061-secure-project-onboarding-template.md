# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

- Status: SPECIFIED — ожидает реализации.
- Branch: `factory/a78d60aa-96f-0281b277-4d5`.
- Implementation commit: pending — реализация не начата на стадии Specification.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changes: новый проект получает обязательный staging, fail-closed readiness,
  именованные release/rollback-адаптеры и секреты вне репозитория и БД Factory.
- One next action: реализовать утверждённый шаблон v1 по спецификации.

## LOG

### 2026-08-10 — Specification

Владелец утвердил v1: человекочитаемое имя, репозиторий, основная ветка, тип,
среды с URL и health-check, проверки, идентификаторы операций, имена секретов и
точный allowlist хостов. Staging обязателен; production блокирован до отдельного
подтверждения владельца. Работа допускается лишь после готовности доступа/worker/
секретов и secret-scan, static/typecheck, tests, build на одном SHA. Секреты
остаются в `/etc/factory/projects/<project>/<environment>.env` с `root`, группой
исполнителя и режимом `0640`; значения не выходят из разрешённой операции.
