# CARD-0062 — Безопасный шаблон подключения проекта

## HEAD

Implementation commit: 2763341fdb3cc84698c0d54745bcc073567c8050 — новый проект подключается только через строгий шаблон, а claim защищён credential конкретного worker.
- Status: READY FOR REVIEW — критерии реализации и новая граница claim подтверждены.
- Branch: `factory/97679252-1e5-ee3063c7-e8e`.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: добавлены проектный контракт, readiness, безопасные секреты,
  именованные release/rollback-адаптеры и экран `/projects`.
- Security: регистрация, аттестация и claim требуют server-issued credential,
  привязанный к `worker_id`; отсутствующий или чужой credential получает `401`.
- Evidence: `go test ./... -count=1` → PASS; `npm --prefix web test -- --run` →
  14 файлов, 142 теста PASS; vet, typecheck, lint и Go/Web build → PASS.
- One next action: провести Review итогового трёхточечного diff и claim-границы.

## LOG

### 2026-08-11 — Implement

Реализация пофайлово собрана на свежем `origin/main` без карточки и истории
старой ветки. Новый HTTP-контракт claim проверен тремя исходами: `401` без
credential, `401` с credential другого worker и успешное назначение только со
своим. Полные Go/Web-тесты, vet, typecheck, lint и обе сборки прошли.
