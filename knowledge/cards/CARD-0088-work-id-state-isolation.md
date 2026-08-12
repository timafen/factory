# Изоляция состояния одноимённых работ

Implementation commit: c5fd6a9c3b3d2cf284e5da0e5a080e4e65f2c929 — бюджеты, диагностика и корневые metadata изолированы по work_id

## HEAD

Status: Implemented
Branch: factory/6de3d20b-c7a-5eeb114c-ad5
Implementation commit: c5fd6a9c3b3d2cf284e5da0e5a080e4e65f2c929 — бюджеты, диагностика и корневые metadata изолированы по work_id
What changed: budget, diagnostic history/repair state, branch lookup and stop state now use durable work_id; Epic and Plan provenance is recorded after task creation.
Evidence: targeted same-title provenance and diagnostic isolation tests → PASS; pilot.py compilation → PASS.
One next action: run the full repository verification before merge.

## LOG

### 2026-08-11 — Implement

Изоляция бюджетов, диагностики и корневых записей перенесена на durable `work_id`; title fallback оставлен для legacy без provenance. Целевые проверки двух одноимённых работ и диагностики прошли; полный прогон ранее остановлен внешним зависанием тестового окружения.
