# Спецификация: CPU-изоляция панели, мозга и тяжёлых прогонов

## Цель и влияние на владельца

Тяжёлые исполнения worker и release Gate не должны отбирать процессорное время у
панели Factory и её мозга. После внедрения владелец сохраняет отклик публичного
dashboard API во время одновременной нагрузки: за минуту все 60 запросов к
`https://factory.timafen.com/api/v1/dashboard` получают HTTP 200, а p95 полного
времени запроса не превышает одной секунды.

Политика утверждена владельцем и не требует дополнительного выбора: создаются
четыре соседних systemd slice. Панель получает приоритет без жёсткой квоты;
мозг — одну CPU; исполнители и Gate получают общую квоту именно на группу, а
не по квоте на каждый service unit.

## Технический подход и реальные файлы

В репозитории исходники systemd уже хранятся в `ops/systemd/`, а
`ops/fx-factory-release` извлекает это дерево из доверенной ревизии, добавляет
его в атомарный release inventory, вызывает `systemctl daemon-reload` и умеет
откатывать набор артефактов. Реализация расширит именно этот путь, а не будет
редактировать live-unit вручную.

- Добавить в `ops/systemd/` четыре peer-slice: `factory-panel.slice`,
  `factory-brain.slice`, `factory-workers.slice`, `factory-gate.slice`.
  У panel: `CPUWeight=10000`, без `CPUQuota`; у brain: `CPUWeight=3000`,
  `CPUQuota=100%`; у workers: `CPUWeight=300`; у Gate: `CPUWeight=100`.
  Все slices должны быть соседними (без вложения друг в друга) и ставиться в
  `/etc/systemd/system/`.
- В новом `ops/install-cpu-isolation.sh` вычислять `N` как число online logical
  CPU через `getconf _NPROCESSORS_ONLN` с fail-closed проверкой целого значения
  больше нуля. Генерировать атомарно drop-in’ы в
  `/etc/systemd/system/<unit>.service.d/`: `factory-server` -> panel и
  `Nice=-5`; `factory-pilot` и `factory-intake` -> brain и `Nice=0`; все unit’ы
  из уже существующего `FACTORY_WORKER_SERVICES` -> workers и `Nice=10`;
  `factory-release-broker` -> Gate и `Nice=15`. Скрипт задаёт group quota на
  slice: workers `CPUQuota=N*50%`, Gate `CPUQuota=N*25%`; он никогда не пишет
  `CPUQuota` в worker/Gate service drop-in.
- `ops/fx-factory-release` включит четыре slice и сгенерированные drop-in’ы в
  candidate inventory до первой мутации, применит их вместе с бинарями и при
  ошибке вернёт предыдущие файлы. После замены нужен `daemon-reload`; обычный
  порядок безопасного перезапуска server, workers, brain и broker сохраняется.
  В release-path передаётся единый список worker units в installer, поэтому
  дополнительные worker-service не остаются вне CPU-группы.
- Добавить `ops/test-install-cpu-isolation.sh`: изолированная фикстура с
  поддельными `getconf` и `systemctl` проверяет значения для N=например 8,
  расположение quota только в двух slice и отказ на некорректном N.
  `ops/test-fx-factory-release.sh` расширить проверками inclusion, rollback и
  `daemon-reload` для полного CPU-комплекта. Для внешнего SLO добавить
  `ops/test-dashboard-cpu-isolation.sh`: он одновременно запускает
  воспроизводимую CPU-нагрузку в workers- и Gate-slice и выполняет 60 запросов
  за 60 секунд, записывая коды, полные времена и p95; ненулевой результат
  означает любой не-200 или p95 > 1.0 s.

Публичные HTTP-API, Go-код scheduler/worker и UI не меняются. Dashboard является
наблюдаемой проверкой, а не новым endpoint.

## Последовательный план

1. Добавить четыре slice и installer, включая вычисление N, проверку CPUQuota
   на уровне групп и атомарную замену service drop-in’ов.
2. Подключить installer и все его артефакты к trusted extraction, inventory,
   установке, `daemon-reload` и rollback в release driver.
3. Расширить shell-фикстуры: проверить все mapping `unit -> Slice/Nice`,
   формулы квот, multi-worker случай, отсутствие per-unit quota, невалидный N
   и восстановление комплекта после отказа.
4. Реализовать параметризуемый стендовый CPU/SLO сценарий; перед запуском он
   проверяет права systemd и наличие всех четырёх slice, а затем возвращает
   результат p95 и список плохих ответов.
5. На staging выполнить одну минуту смешанной нагрузки и 60 dashboard
   запросов; приложить измерение только если стендовые полномочия доступны.

## Критерии приёмки

1. Существуют ровно четыре соседних Factory slice с утверждёнными CPUWeight;
   только brain имеет фиксированную `CPUQuota=100%`, panel не имеет CPUQuota.
2. На хосте с N online logical CPU workers-slice имеет `CPUQuota=N*50%`,
   Gate-slice — `N*25%`; ни один worker/Gate service drop-in не содержит
   CPUQuota.
3. Server находится в panel slice с `Nice=-5`; pilot/intake — в brain с
   `Nice=0`; все configured worker units — в workers с `Nice=10`; release
   broker — в Gate с `Nice=15`.
4. Release атомарно устанавливает и откатывает slices/drop-in’ы вместе с
   остальными артефактами и делает `systemctl daemon-reload` до рестарта.
5. При одновременной тяжёлой нагрузке workers и Gate 60 запросов за минуту к
   публичному dashboard endpoint все отвечают 200, а p95 полного времени <= 1 s.

## Тест-план

- Локально: `bash ops/test-install-cpu-isolation.sh` — формулы N, placement
  свойств, unit mapping, multi-worker и fail-closed N без реального systemd.
- Локально: `bash ops/test-fx-factory-release.sh` — release inventory,
  daemon-reload и rollback CPU-политики в существующей изолированной фикстуре.
- На staging: `bash ops/test-dashboard-cpu-isolation.sh
  https://factory.timafen.com/api/v1/dashboard` — 60 запросов/60 секунд при
  одновременной нагрузке обеих тяжёлых групп; команда завершается 0 только при
  всех HTTP 200 и p95 <= 1 s.
- Проверка свойств на сервере: `systemctl show factory-{panel,brain,workers,gate}.slice
  -p CPUWeight -p CPUQuotaPerSecUSec` и `systemctl show` для каждого mapping
  unit с `-p Slice -p Nice`; это подтверждает применённую, а не только
  сгенерированную конфигурацию.

## Риски и решения

- `CPUQuota` systemd выражается в процентах одной CPU; installer вычисляет
  итоговую строку после определения online CPU, а не оставляет неоднозначный
  символ N в unit-файле. Изменение online CPU требует повторного release/install
  для пересчёта; hotplug-демон намеренно не добавляется.
- Неверный список worker units оставит процесс вне workers slice. Используется
  существующий `FACTORY_WORKER_SERVICES` как единственный источник, а тест
  включает второй worker unit.
- CPUWeight работает при конкуренции и не гарантирует абсолютную задержку.
  Поэтому SLA закреплён отдельным смешанным нагрузочным измерением и hard quota
  для двух тяжёлых групп.
- Нагрузка на production недопустима без разрешения владельца: обязательный SLO
  запускается на staging; публичный URL указан владельцем как точка измерения.
- Сторонние systemd drop-in’ы могут конфликтовать. Installer использует свой
  префикс, проверяет итог через `systemctl show`, а release rollback возвращает
  его прежнее содержимое; чужие файлы не удаляет.

## Карточка работы

`knowledge/cards/CARD-0097-cpu-isolation-panel-brain-and-heavy-runs.md`

## Проверяемые обещания

ГОТОВО-КОГДА: файл ops/systemd/factory-panel.slice
ГОТОВО-КОГДА: файл ops/systemd/factory-brain.slice
ГОТОВО-КОГДА: файл ops/systemd/factory-workers.slice
ГОТОВО-КОГДА: файл ops/systemd/factory-gate.slice
ГОТОВО-КОГДА: файл ops/install-cpu-isolation.sh
ГОТОВО-КОГДА: файл ops/test-install-cpu-isolation.sh
ГОТОВО-КОГДА: файл ops/test-dashboard-cpu-isolation.sh
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда bash ops/test-install-cpu-isolation.sh
