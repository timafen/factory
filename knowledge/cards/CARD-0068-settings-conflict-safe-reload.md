Implementation commit: c72f68486e6f2ad95ddeca88a01fe8444685bbf1 — экран настроек предлагает загрузить свежую версию после конфликта, а тесты подтверждают безопасную запись файла

# CARD-0068 — Безопасное восстановление настроек после конфликта

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/c2f32131-2b9-14f6a6dd-fff`.
- Implementation commit: `c72f68486e6f2ad95ddeca88a01fe8444685bbf1` — локализовано действие после конфликта и закреплены гарантии хранения.
- What changed: после `409` владелец может загрузить свежие настройки; тесты проверяют порядок моделей, атомарную замену и неизменность файла при ошибке.
- Evidence: целевые control-plane и Settings-тесты, web typecheck/lint/build и `go build ./...` прошли.
- One next action: проверить `/settings` и передать ветку на Review.

## LOG

### 2026-08-11 — Implement

Основной экран и API уже находились в `main`. Узкая поставка добавила русское
действие восстановления после конфликта версии и недостающие проверки обещаний:
перестановка `brain_chain` сохраняет notes, запись атомарно заменяет inode, а
missing/oversized/invalid файл и сбой записи не повреждают прежние данные.

Доказательства: целевой `go test ./internal/controlplane` — PASS; `Settings.test.tsx`
— 9/9 PASS; TypeScript, focused ESLint, production build и `go build ./...` — PASS.
