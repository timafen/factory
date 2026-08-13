# CARD-0126: staticcheck для attempt lifecycle

## HEAD

Status: implemented
Branch: factory/92da7e03-e26-8114028f-ae3
Implementation commit: 4707a6de747a52c01e5db914f905b4378b3159fe — исправлена проверка стабильной задержки lifecycle-теста
What changed: самосравнение заменено на сравнение двух вычисленных значений `want` и `got`; поведение worker не менялось.
Evidence: целевой тест, worker staticcheck, полный `just staticcheck`, `just test` и `just build` — PASS; browser suite — заблокирован политикой контейнера.
One next action: повторить browser suite в среде, где разрешён `factory-browser-sandbox`.

## LOG

### 2026-08-13 — Implement

В `internal/worker/attempt_lifecycle_test.go` устранено `SA4000` без изменения product code.
Целевые и полные Go-проверки, staticcheck и сборка прошли; browser suite дошёл до запуска и остановлен контейнерной политикой `no new privileges`.
