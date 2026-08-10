# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented + automated tests PASS; live root check blocked by managed container.
- Branch: `factory/0c92756c-894-2d86eb27-28e`.
- Head commit: `ee9c892` (`Дать агентам безопасный снимок стенда через Chromium`).
- What changed: агенты и «Диалог» получают PNG утверждённого стенда через Chromium
  с обязательным network namespace и allowlist-прокси.
- What changed: штатный выпуск обновляет системные `fx`/release-helper и выполняет
  идемпотентные `browser-sandbox install/check`; отмена убирает process group/netns.
- Evidence: `go test ./...` — PASS; UI — 123/123; typecheck, lint, UI/Go build — PASS;
  release и fx browser-sandbox shell tests — PASS; cancellation test 3/3 — PASS.
- Live evidence: отсутствует — `sudo` заблокирован флагом `no new privileges`,
  user namespace также запрещён политикой managed-контейнера.
- One next action: на Factory-host выпустить эту ветку с root и сохранить PASS
  `fx factory browser-sandbox check`, затем открыть `/dialog` и получить снимок.

## LOG

### 2026-08-09 — Implement

Функция заново собрана от свежего `origin/main` без файлов прежней ветки вне
области. Закрыты замечания Review: выпуск ставит системные команды и sandbox,
Go-runner и launcher ограниченно завершают всё дерево Chromium, а сетевой check
доказывает блокировку TCP/UDP/DNS по firewall counter вместо таймаута ответа.
Полные Go/UI тесты, сборки и целевые shell-проверки прошли; живая root-проверка
невозможна внутри worker-контейнера из-за обязательного `no new privileges`.
