# Автовыпуск подтверждает перезапуск сервера и воркеров после замены бинарей

## Цель и влияние на владельца

После инцидента в 19:03:40 CDT владелец должен получать либо подтверждённый
выпуск, в котором `factory-server` и каждая настроенная служба воркера уже
исполняют бинарь нового поколения, либо безопасный откат с понятной причиной.
Одной успешной замены файлов недостаточно: процесс с прежним inode продолжает
исполнять удалённый старый бинарь. Выпуск не должен объявляться успешным, пока
для всех служб, которые были активны до обновления, не доказана смена процесса
и совпадение его executable с payload выбранного поколения.

Неактивная до выпуска служба не запускается только ради этой проверки:
её сохранённое состояние остаётся частью контракта rollback. Изменение не
авторизует ручной выпуск, restart production-служб или изменение Pilot/БД.

## Технический подход и реальные файлы

Текущий `ops/fx-factory-release` уже останавливает все единицы из
`FACTORY_WORKER_SERVICES`, затем `factory-server`, устанавливает generation,
запускает server и воркеры и сверяет путь и SHA executable с manifest. Однако
проверка после запуска не сравнивает процесс с тем, который был до остановки;
`ops/test-fx-factory-release.sh` пока проверяет порядок вызовов fake
`systemctl`, а не доказуемую замену процесса. Отдельный
`ops/test-factory-release-systemd.sh` уже воспроизводит риск deleted inode,
но не связывает его с lifecycle выпуска.

Реализация должна дополнить release-driver краткоживущим снимком активных
unit до `stop_factory_units`: unit, MainPID и устойчивую process identity
(PID вместе со start-time из `/proc`, чтобы PID reuse не дал ложный успех),
а также digest `/proc/<pid>/exe`. После `install_generation`, start и
регистрации воркера driver обязан для каждой исходно активной единицы
проверить: unit active, процесс существует, identity отличается от снимка,
его `/proc/.../exe` указывает на штатный путь и digest равен соответствующему
artifact текущего manifest. Для server это `payload/factory-server`; для
каждой worker unit — `payload/factory-worker`.

Ошибка любой из этих проверок идёт в существующий `rollback`: старый полный
комплект и его состояния служб восстанавливаются, journal не помечается
`committed`, а текст ошибки называет unit и отсутствие нового процесса или
несовпадение binary. Существующие границы остаются: остановка воркеров до
server, server health до запуска воркеров, fresh healthy registration и
`restore_service_state`.

Файлы реализации:

- `ops/fx-factory-release`
- `ops/test-fx-factory-release.sh`
- `ops/test-factory-release-systemd.sh`

## Последовательный план

1. В `ops/fx-factory-release` выделить helper для безопасного чтения MainPID,
   process identity и digest executable только у active unit; собрать снимок
   server и всех значений `FACTORY_WORKER_SERVICES` до их остановки.
2. Сохранить существующую установку согласованного generation и порядок
   запуска, но после запуска/registration сопоставить каждую исходно active
   единицу со снимком и artifact manifest; inactive единицы исключить из
   требования о новом PID.
3. На несменившемся, отсутствующем или неверном executable вызвать имеющийся
   rollback с диагностикой конкретной службы; не публиковать release-info и
   не удалять transaction journal как успешный.
4. Расширить fake `systemctl` в `ops/test-fx-factory-release.sh`, чтобы он
   моделировал исходный MainPID и создание нового процесса на start; добавить
   зелёный сценарий для server и двух worker-служб и отрицательные сценарии,
   где одна служба остаётся на старом процессе или старом digest.
5. Расширить `ops/test-factory-release-systemd.sh` реальным transient unit:
   замена файла без restart должна наблюдаться как deleted/несовпадающий
   executable, а stop/start должен дать новый process identity и digest нового
   файла. В окружениях без PID 1 systemd сохранить явный SKIP вне CI.

## Критерии приёмки

1. Успешный выпуск доказывает для `factory-server` и каждой исходно active
   worker-службы, что процесс после замены не совпадает с предрелизным и
   исполняет digest payload текущего generation.
2. Любая активная служба, оставшаяся на старом PID/start-time, deleted inode,
   неверном пути или digest, отменяет выпуск до публикации metadata и запускает
   полный существующий rollback.
3. Все worker-службы берутся только из `FACTORY_WORKER_SERVICES`; значение по
   умолчанию с одной `factory-worker.service` сохраняет совместимость.
4. Служба, которая была inactive до выпуска, после успеха и rollback остаётся
   inactive и не создаёт ложного требования о restart.
5. Сохраняются existing health server, fresh healthy registration worker,
   journal/crash recovery, lock, snapshot и rollback без восстановления БД.

## Тест-план

- В `ops/test-fx-factory-release.sh` добавить fixture-процессы/identity,
  проверяющие успешную смену server и двух worker-служб после установки.
- Там же добавить отдельные отказные сценарии для несменившегося процесса и
  неправильного digest: команда завершается не нулём, старый generation и
  состояния служб восстановлены, release-info не выдаёт новый выпуск.
- В `ops/test-factory-release-systemd.sh` проверить на реальном systemd
  contrast «замена файла без restart» против «stop/start нового binary»;
  в developer-окружении без systemd допустим SKIP, в CI это обязательный PASS.
- Запустить `bash ops/test-fx-factory-release.sh`; дополнительно выполнить
  `bash ops/test-factory-release-systemd.sh`, `bash -n ops/fx-factory-release
  ops/test-fx-factory-release.sh ops/test-factory-release-systemd.sh` и
  `git diff --check`.

## Риски и решения

- MainPID может быть переиспользован ОС. Решение: сравнивать PID вместе с
  start-time, а не PID отдельно.
- У service manager возможна задержка между start и появлением process. Решение:
  применять ограниченный polling, согласованный с текущими bounded retry
  health/registration, и rollback по истечении.
- Проверка только SHA установленного файла пропускает старый живой процесс.
  Решение: digest читать из `/proc/<pid>/exe` и требовать новую identity.
- Расширение теста настоящего systemd недоступно на обычном runner. Решение:
  сохранить текущий честный SKIP вне CI и не подменять его успешной shell
  fixture; обязательная регрессия release-driver остаётся детерминированной.

## Карточка работы

`knowledge/cards/CARD-0090-auto-release-restarts-server-workers.md`

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-factory-release-systemd.sh
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
