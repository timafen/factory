# Реальная session регистрируется до запуска gate

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: factory/41133b78-0b9-493dcc4b-322
Implementation commit: 6d877feb05a19a23cb13644a432a7dd2f07b28c1 — release сохраняет точный итог forked gate.
What changed: актуальная release/rollback-логика main сохранена; supervisor ждёт authoritative status настоящей команды.
What changed: пропавший или повреждённый результат ограниченно завершается fail-closed, без установки.
Evidence: pinned base `2a6eb6046f5a595e5156a4ec0300e0a1aa2f6e11` and candidate `cab3bc96123dc2426bf3aec564695d2197c89102`; target shell suite and syntax check PASS. Full `just check` reached all Go tests, vet, vulnerability scan and staticcheck; UI check is blocked by missing local `eslint` (exit 127), outside this change.
One next action: human merge candidate branch after reviewing the UI dependency finding.

## LOG

### 2026-08-12 — Implement

На свежем `main` вручную совмещены gate-supervision и новая release/rollback-логика;
forking launcher больше не скрывает ошибку настоящего gate, а отсутствие результата
запрещает установку. Проверки подтвердили точный отказ, успешный forked gate, bounded
cleanup, сигналы, race, сборку и воспроизводимые release-артефакты.

### 2026-08-12 — Verify

| Acceptance criterion | Check | Result |
| --- | --- | --- |
| Forked launcher не скрывает успех или ошибку настоящего gate | `ops/test-fx-factory-release.sh` | PASS: success, failure, no-result and signal scenarios |
| Нет результата gate не запускает установку | Тот же adversarial shell suite | PASS: fail-closed |
| Shell-код синтаксически корректен | `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` | PASS |
| Регрессии проекта | `just check` | Go tests, vet, vulnerability scan and staticcheck PASS; `ui-check` stopped at missing `eslint` (exit 127), outside scope |

Pinned comparison: base `2a6eb6046f5a595e5156a4ec0300e0a1aa2f6e11` ... candidate `cab3bc96123dc2426bf3aec564695d2197c89102`; changed files are exactly the launcher, its test, and this card.
