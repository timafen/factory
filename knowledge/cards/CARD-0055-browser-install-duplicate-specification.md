# CARD-0055 — Установка браузера сохраняет работу воркеров

## HEAD

Status: Specification ready — уточнить доказательство непрерывной работы
воркера при установке браузера.

## Спецификация

### Цель и влияние на пользователя

Администратор может обновить серверный Chromium, не обрывая работу уже
зарегистрированного воркера. Установка системных зависимостей остаётся
неинтерактивной и не запускает `needrestart` в режиме перезапуска. До успешного
завершения установщик обязан действительно запустить Chromium в Linux sandbox,
открыть разрешённые страницы и удостовериться, что тот же воркер не был
остановлен или заменён.

CARD-0052 уже ввела `NEEDRESTART_MODE=l`, sandbox launcher и навигационный
smoke. Эта работа не расширяет сеть или API: она делает узкий оставшийся
контракт проверяемым — непрерывность работающего воркера во время установки.

### Технический подход

В `ops/install-server-browser.sh` сохранить существующие
`DEBIAN_FRONTEND=noninteractive` и `NEEDRESTART_MODE=l`, но до первой мутации
снять снимок активного `factory-worker.service` (состояние и MainPID). После
установки зависимостей и после live smoke сравнить снимок: если активный до
установки воркер исчез, стал неактивным или получил другой PID, завершить
установку ошибкой и запустить существующий откат browser-комплекта. Неактивный
до начала воркер не должен быть запущен этим установщиком.

Существующий inline Playwright smoke остаётся единственным живым критерием:
`chromium.launch` использует доставленный launcher и `chromiumSandbox: true`,
загружает DOM loopback и staging, сохраняет screenshot и отклоняет production и
произвольный internet. Не менять allowlist, AppArmor, launcher, API, форматы
данных или порядок штатного release: это scope creep.

`ops/test-install-server-browser.sh` получит управляемый активный worker mock с
неизменным PID/heartbeat во время реального запуска test Chromium, а также
отрицательный сценарий замены PID. `ops/test-fx-factory-release.sh` закрепит,
что browser installer вызывается только после штатной healthy-registration
воркера и не вызывает дополнительного worker lifecycle на успешном пути.

### План

1. В installer добавить снимок только уже активного worker unit и fail-closed
   проверку его состояния и PID вокруг dependency install и Playwright smoke.
2. Расширить installer regression: подтвердить list-only `needrestart`, живой
   запуск Chromium, непрерывный worker и откат при смене PID.
3. Расширить release regression: подтвердить порядок healthy-registration →
   browser installer и отсутствие дополнительного stop/start/restart worker на
   успешном browser-шаге.
4. Запустить две целевые shell-регрессии; root/systemd/AppArmor smoke выполнить
   на разрешённом host, когда доступен парольless root.

### Критерии приёмки

1. Если `factory-worker.service` был активен перед browser install, после
   установки зависимостей и после успешного smoke он остаётся активным с тем же
   MainPID; installer не вызывает для него `stop`, `start` или `restart`.
2. Live smoke реально запускает Chromium через sandbox launcher, подтверждает
   DOM loopback и staging, сохраняет непустой screenshot и при этом показывает
   непрерывность ранее активного воркера. Ошибка smoke или смена worker PID
   завершают установку неуспешно и откатывают browser-комплект.

### План проверок

- Добавить к `ops/test-install-server-browser.sh` позитивную проверку PID и
  heartbeat активного воркера до/после всех installer gates и негативную
  проверку смены PID с rollback.
- Добавить к `ops/test-fx-factory-release.sh` проверку отсутствия lifecycle
  действий с воркером после успешного browser gate.
- Обязательные команды с кодом 0: `bash ops/test-install-server-browser.sh` и
  `bash ops/test-fx-factory-release.sh`.

### Риски и решения

`MainPID` — практический признак отсутствия restart для systemd service; он не
доказывает обработку конкретной задачи внутри процесса, поэтому проверка не
обещает exactly-once выполнение задач. Альтернатива — всегда останавливать
browser install при неактивном воркере — отклонена: browser provisioning не
должен менять lifecycle отключённого сервиса.

Настоящий root/systemd/AppArmor/Chromium smoke в текущем окружении недоступен,
поскольку `sudo -n` требует пароль. Эмуляция остаётся регрессией, а не заменой
host smoke; запрещено ради неё ослаблять sandbox или сетевой allowlist.

### Card

`knowledge/cards/CARD-0055-browser-install-duplicate-specification.md` —
карточка этой работы. Связанная исходная реализация:
`knowledge/cards/CARD-0052-browser-install-live-smoke.md`.

ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда bash ops/test-install-server-browser.sh
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
