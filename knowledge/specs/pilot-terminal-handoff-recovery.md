# Спецификация: Pilot доигрывает пропущенную передачу после рестарта

## Цель и влияние на владельца

Если Pilot перезапустился между фиксацией успешного terminal-этапа и созданием
следующего, работа больше не останется молча на полпути. После старта Pilot
сверит недавние успешные завершения с фактическим хвостом конвейера и создаст
только действительно отсутствующий следующий этап. Владелец не должен вручную
перезапускать такую работу и не увидит дублей уже продолжающегося конвейера.

## Технический подход и реальные файлы

- В `pilot/pilot.py` добавить startup-reconciliation перед обычным пропуском
  `state["processed"]`. Он рассматривает только ID, уже находившиеся в
  `processed` при старте процесса: обычный цикл продолжает владеть новыми
  terminal-задачами.
- Watermark хранить в `state.json` как время последнего успешно завершённого и
  сохранённого цикла Pilot. `run_loop()` обновляет его только после успешного
  `cycle()` и до атомарного `save(STATE_PATH, state)`; ошибка цикла не двигает
  границу. При старте recovery фиксирует прежнее значение как нижнюю границу и
  не расширяет выборку во время работы процесса.
- «Свежая» задача для recovery — видимая в текущем `/tasks?limit=100`, уже
  находившаяся в startup-снимке `processed`, со `state == "succeeded"`, чья
  terminal-метка (`finished_at`, иначе `updated_at`) строго новее watermark.
  Запись без обеих terminal-меток не восстанавливается автоматически. При
  первом запуске без watermark recovery только инициализирует границу текущим
  временем и не переигрывает историю.
- Для кандидата сначала применить `work_lifecycle_block()` и `is_stopped()`,
  определить известный нефинальный workflow и затем вызвать
  `live_or_done_at(tasks, task, next_stage_no, since=task.created_at)`. Наличие
  следующего или более позднего этапа в `created`, `queued`, `preparing`,
  `running` либо `succeeded` означает, что передача уже состоялась.
- Отсутствующий хвост передать существующему обработчику успешного этапа, а не
  отдельному упрощённому create-пути: сохраняются `decide`, выбор worker,
  capacity/host/area guards, ветка и handoff, а финальная защита
  `live_or_done_at()` непосредственно перед `create_child_task()` обеспечивает
  «ровно один раз» при повторном цикле.
- Recovery никогда не запускает `failed`/`cancelled`, неизвестный или финальный
  этап; не снимает owner-stop, архив/закрытие, завершённую plan-card или другую
  причину `work_lifecycle_block()`. При временной нехватке capacity/worker он не
  удаляет ID из `processed`: кандидат остаётся в ограниченном startup-наборе и
  повторяется следующим циклом того же процесса до появления хвоста либо
  безопасного lifecycle-блока.
- В `pilot/test_pilot.py` добавить restart-regression на потерянный Triage →
  Specification и табличные отрицательные случаи. API/schema, UI, release,
  merge/delivery и cursors Automation/Epics не меняются.

## Последовательный план

1. Зафиксировать в `run_loop()` durable watermark только после успешного цикла
   и получить неизменяемый startup-снимок recovery-кандидатов.
2. Вынести безопасную проверку уже обработанного успешного terminal-этапа до
   раннего `if tid in state["processed"]: continue`.
3. Переиспользовать обычный successful-handoff со всеми lifecycle-проверками и
   двумя проверками `live_or_done_at()` — при сверке и перед созданием.
4. Добавить регрессию реального restart-state и отрицательные сценарии дубля,
   старой истории, закрытия, stop, ошибок и финального этапа.
5. Выполнить целевой тест, соседние terminal/restart-тесты и проверку diff.

## Критерии приёмки

1. При startup-state с `processed=["triage-done"]`, свежим успешным Triage и
   без Specification следующий этап создаётся ровно один раз; повторный цикл
   или повторный restart его не дублирует.
2. Существующий live (`created`, `queued`, `preparing`, `running`) или
   `succeeded` этап того же либо большего номера подавляет восстановление через
   `live_or_done_at()`.
3. Recovery рассматривает только завершения строго новее сохранённого
   watermark; отсутствие watermark или terminal timestamp не оживляет старую
   историю.
4. Закрытая/архивированная работа, owner-stop, завершённая карточка, а также
   `failed`, `cancelled`, неизвестный и последний этап не создают задач и не
   вызывают решение мозга.
5. Временная невозможность передачи допускает безопасный повтор, но успешное
   создание становится видимым в том же task snapshot и исключает второй
   create.

## Тест-план

- Новый тест в `pilot/test_pilot.py` записывает state с watermark и уже
  processed свежим successful Triage, имитирует новый процесс и доказывает
  один Specification после двух циклов/restart.
- В той же группе проверить подавление при live/succeeded хвосте, строгую
  границу watermark, отсутствие timestamp, lifecycle block/stop,
  failed/cancelled и финальный Verify.
- Обязательная целевая команда:
  `python3 -m unittest -q pilot.test_pilot.AdaptivePollingTests.test_restart_recovers_processed_success_with_missing_next_stage`.
- Соседние проверки: terminal backlog/cursor, закрытая работа после restart и
  `live_or_done_at`; затем `git diff --check`.
- Полный `python3 -m unittest -q pilot.test_pilot` оставить этапу Verify. Его
  текущая baseline-краснота (2 failures CARD-0086 и 2 errors adaptive polling)
  не относится к этой реализации и не должна маскировать результат нового
  целевого теста.

## Риски и решения

- `created_at` не является временем завершения, поэтому для свежести он не
  используется; отсутствие terminal timestamp закрывается fail-safe отказом
  от автоматического replay.
- Watermark нельзя двигать при упавшем цикле: иначе пропущенное завершение
  окажется старше границы. Граница меняется только вместе с успешным durable
  сохранением состояния.
- Один API snapshot может устареть между сверкой и create. Существующий
  request/create-путь и повторная `live_or_done_at()` с добавлением созданной
  задачи в `_active_work_tasks` оставляют окно идемпотентным внутри Pilot; новая
  внешняя база или схема ради этого не вводится.
- Неограниченное проигрывание истории опасно для закрытых работ. Startup-набор,
  watermark, видимое окно API и lifecycle guards совместно ограничивают replay.

## Карточка работы

`knowledge/cards/CARD-0155-pilot-terminal-handoff-recovery.md`

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.AdaptivePollingTests.test_restart_recovers_processed_success_with_missing_next_stage
