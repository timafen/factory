# Реальная session регистрируется до запуска gate

Implementation commit: b9eea4a711cb6255a2daf70ea5139e239dd71cee — release gate требует атомарный успешный результат реальной session до установки.

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/b305a0cc-eef-73c7d64b-40c.
Implementation commit: b9eea4a711cb6255a2daf70ea5139e239dd71cee — release gate требует атомарный успешный результат реальной session до установки.
What changed: session wrapper атомарно публикует код завершения; выпуск ждёт process group и принимает только корректный `status=0`.
What changed: ненулевой, отсутствующий или повреждённый result-файл запрещает сборку и установку даже при раннем успешном выходе forked launcher.
Evidence: `bash ops/test-fx-factory-release.sh` (forked failure и invalid result) → PASS; Go tests/build и web typecheck/lint/tests/build → PASS.
One next action: merge the implementation branch.

## LOG

### 2026-08-11 — Implement

Forked launcher больше не считается session gate: готовность подтверждается только
из wrapper, уже запущенного через `setsid`, до старта проверок. Shell-фикстура
принудительно форкает launcher и подтверждает успешный выпуск без потери реальной
группы; signal-cleanup и отказавшие gate-сценарии сохранены.

### 2026-08-12 — Implement

Реальная session теперь атомарно публикует код завершения после gate, а release
продолжает работу только после завершения process group и при `status=0`.
Регрессии подтверждают остановку до сборки и установки при ненулевом коде внутри
forked session, а также при отсутствующем или повреждённом result-файле.
