# Приёмка: судьба ветки после повторной попытки слияния

## Цель и влияние на владельца

После повторного AUTO-MERGE-конфликта владелец получает однозначный исход:
если та же работа уже доказанно влита другим PR, устаревший PR закрывается и
помечается `superseded`; если закрытие через GitHub не удалось, работа не
теряется и возвращается в correction flow. Повторный запуск не должен повторно
сливать или закрывать уже обработанную работу.

## Технический подход и реальные файлы

Источником идентичности является сохранённый `merge_intent.work_id`, а не
название или имя ветки. В `pilot/pilot.py` функция `_supersede_conflicted_pr`
должна разрешать ровно один открытый PR с тем же marker и base и ровно один
другой merged PR с тем же marker и base; только затем вызывается `gh_close_pr`.
Фаза `superseded` и terminal-переход фиксируются после успешного закрытия.
Любой неуспешный или неоднозначный ответ оставляет фазу `conflict`, чтобы
`resume_merge_conflicts` создал единственную задачу `merge_conflict_return`.
Идемпотентность обеспечивается сохранённой фазой, `work_id`, parent provenance
и проверкой существующей correction-задачи.

Реальные файлы реализации и проверки:

- `pilot/pilot.py` — merge intent, проверка PR, close/supersede и correction flow;
- `pilot/test_pilot.py` — `MergeConflictRecoveryTests` для успеха, отказа,
  restart и отсутствия повторного действия.

## Последовательный план

1. Воспроизвести второй конфликт с одним открытым stale PR и одним merged PR
   того же `work_id` и base; проверить ровно один close и `superseded`.
2. Воспроизвести отказ `gh_close_pr`; проверить сохранение `conflict` и создание
   correction-задачи с прежней веткой и work identity.
3. Перезапустить recovery после каждого исхода и убедиться, что повторных
   close, merge и correction нет.
4. Выполнить целевой тест и затем полный `just check` ровно на Verify-этапе.
5. Провести чистый pipeline Triage → Specification → Implement + Test → Review
   → Verify → release и live acceptance с проверкой GitHub PR.

## Критерии приёмки

- При втором конфликте закрывается ровно один устаревший открытый PR, только при
  единственном подтверждённом merged PR с теми же marker и base; фаза — `superseded`.
- Ошибка или неоднозначность GitHub не переводит работу в terminal; создаётся
  ровно одна correction-задача `merge_conflict_return`.
- Restart не вызывает повторное закрытие, повторное слияние или duplicate correction.
- Correction сохраняет исходный `work_id` и branch, проходит Review и Verify,
  после чего pipeline доходит до release и live acceptance.
- После успешного сценария не остаётся незакрытых candidate-веток.

## Тест-план

- `python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests` — 10
  локальных регрессий, включая close failure и restart.
- `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — синтаксис.
- `just check` — полный проектный набор один раз на Verify-этапе.
- Чистый приёмочный прогон штатного pipeline с GitHub PR, release и live
  acceptance; зафиксировать URL PR и факт отсутствия candidate-веток.

## Риски и решения

- Неполный/неоднозначный ответ GitHub может привести к опасному close: при
  любом несоответствии close запрещён, остаётся correction flow.
- Сбой после внешнего close может повторить действие: durable phase и поиск
  существующего состояния делают restart идемпотентным.
- Удалённый release/live acceptance не покрыт локальными тестами: обязательным
  является отдельный чистый прогон перед Verify PASS.

## Карточка работы

Используется выданная карточка
`knowledge/cards/CARD-0168-auto-close-stale-pr-after-repeated-auto-merge-conflict.md`.
Она описывает реализацию, её локальные доказательства и следующий переход на
независимую приёмку; новая карточка и общие журналы не создаются.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл knowledge/cards/CARD-0168-auto-close-stale-pr-after-repeated-auto-merge-conflict.md
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests
