Implementation commit: 670a284140a2db4b130606516fe375029143d18e — Plan, epic, бюджеты и ветки истории изолированы по work_id

## HEAD

Status: Implemented
Branch: factory/d6262485-d88-f2b729ce-4fa
Implementation commit: 670a284140a2db4b130606516fe375029143d18e
What changed: одноимённые работы больше не делят состояние Plan, epic, бюджетов и history branch; fallback по title оставлен только для legacy-записей без provenance.
Evidence: `python3 -m unittest -v pilot.test_pilot` → 218 OK, 13 skipped; `just check` → инфраструктурный timeout в неизменённых `internal/controlplane` и `internal/worker`.
One next action: выполнить Verify после слияния изменений в main.

## LOG

### 2026-08-11 — Implement

Перенесена изоляция по `work_id` на свежий `origin/main` с сохранением новой логики Pilot. Все 218 Pilot-тестов прошли; общий `just check` дошёл до независимых Go-тестов и остановился по их пятиминутному timeout вне области изменения.
