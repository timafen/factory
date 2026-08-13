# CARD-0097 — Самопроверка команд перед Review

Implementation commit: 310cca91f993d7000e1f0825d535a814288004fc — Pilot запускает обещанные команды в обязательной изоляции до Review.

## HEAD

- Status: Implement завершён, целевые проверки зелёные.
- Branch: `factory/d9b02617-91c-0338d669-4dd`.
- Implementation commit: `310cca91f993d7000e1f0825d535a814288004fc`.
- What changed: сохранённые команды выполняются по порядку один раз на pinned
  detached checkout; дубли удаляются.
- What changed: systemd sandbox закрывает сеть, привилегии, секреты и Factory,
  делает candidate read-only и ограничивает набор 2 CPU, 4 ГБ и 20 минутами.
- Evidence: `python3 -m unittest pilot.test_pilot.PreReviewSelfCheckTests` →
  7 tests, OK; смежные DeliveryArea/FreshDefaultBranch/PreReview → 21 tests, OK.
- Next action: Review проверяет implementation-коммит и карточку этой ветки.

## LOG

### 2026-08-12 — Specification

Владелец утвердил автоматический запуск только `ГОТОВО-КОГДА: команда` во
временной копии кандидата: без сети, секретов, привилегий и доступа к Factory,
с лимитами 2 CPU, 4 ГБ и 20 минут на весь набор. Ошибка, лимит или тайм-аут
возвращают работу в Разработку с полным санитизированным журналом.

Планируемые файлы: `pilot/pilot.py`, `pilot/test_pilot.py`. Не входят UI, API,
схема обещаний, общие тесты и исполнение произвольных команд из отчёта.
Обязательная проверка: `python3 -m unittest
pilot.test_pilot.PreReviewSelfCheckTests`.

Pilot использует уже существующие saved promises и свежий pinned Git snapshot.
Preflight должен запускать точный список обещанных команд только в обязательной
OS-песочнице; отсутствие безопасной изоляции — fail-closed возврат, а не запуск
на хосте. Успешный summary передаётся Review, а Verify сохраняет отдельную
проверку свежего кандидата перед merge.

Риск: недоверенный код тестов и зависимостей может попытаться использовать сеть,
секреты либо инфраструктуру. Защита — detached временный checkout, чистое
окружение, read-only исходники, network/capability isolation и ресурсные лимиты;
журнал очищается от секретов до возврата задачи.

### 2026-08-12 — Implement

Pilot получил preflight между pinned scope gate и созданием Review. Команды
берутся только из сохранённых promises, выполняются последовательно в detached
checkout и не запускаются повторно после успешного summary.

Обязательная transient systemd-unit использует read-only bind исходников,
чистое окружение, PrivateNetwork/RestrictAddressFamilies, dropped capabilities,
2 CPU, 4 ГБ и общий monotonic deadline 20 минут. Недоступная изоляция закрывает
переход; ошибка, сигнал, OOM или timeout возвращают полный ограниченный журнал,
включая предыдущие команды, после маскировки секретов.

Evidence: `python3 -W error::ResourceWarning -m unittest
pilot.test_pilot.DeliveryAreaTests pilot.test_pilot.FreshDefaultBranchSnapshotTests
pilot.test_pilot.PreReviewSelfCheckTests` → 21 tests, OK; `python3 -m py_compile
pilot/pilot.py pilot/test_pilot.py` → OK; `git diff --check` → OK.
