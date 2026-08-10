# CARD-0055 — Дубликат: браузер ставится без рестарта воркеров

## HEAD

Status: Specification complete — закрыть как дубликат CARD-0052; продуктовых
изменений и выката не требуется.

## Спецификация

### Цель и влияние на пользователя

Установка серверного Chromium не перезапускает активные worker units: системные
зависимости вызываются с list-only `needrestart`. Установка также обязана
подтвердить работающий Linux sandbox и сетевой allowlist живым smoke; при любой
ошибке browser-комплект и release возвращаются к прежнему состоянию. Это уже
реализовано в `main` по CARD-0052, поэтому данная задача не добавляет поведения.

### Технический подход

Новая реализация не нужна. Подтверждённый минимальный состав уже находится в
`ops/install-server-browser.sh`: `DEBIAN_FRONTEND=noninteractive` и
`NEEDRESTART_MODE=l` предотвращают рестарты, затем installer выполняет BPF-probe,
установку Chromium и sandbox smoke; trap откатывает launcher, helper, config,
sudoers и AppArmor profile. `ops/test-install-server-browser.sh` проверяет эти
контракты через изолированные подмены, включая отсутствие `systemctl restart`.
`ops/test-fx-factory-release.sh` проверяет обязательный запуск installer,
код ошибки 7 и откат server/worker binaries при browser failure. Сеть и smoke
контрактированы в `knowledge/specs/server-browser-network-isolation.md`.

Затронутые реализацией файлы уже в `main`: `ops/install-server-browser.sh`,
`ops/test-install-server-browser.sh`, `ops/test-fx-factory-release.sh`,
`knowledge/specs/server-browser-network-isolation.md`, а также browser launcher,
Pilot/release интеграция из CARD-0052. Новых API, данных или файлов реализации
для этой задачи нет.

### План

1. Не менять продуктовый код: закрыть задачу как дубликат CARD-0052.
2. Перед закрытием выполнить installer и release регрессии с актуального `main`.
3. Зафиксировать недоступность настоящего root/systemd smoke как остаточный риск,
   не подменяя его эмуляцией.

### Критерии приёмки

- Installer передаёт `NEEDRESTART_MODE=l` и не вызывает `systemctl restart` во
  время установки системных зависимостей.
- До установки launcher проходит BPF firewall probe; smoke запускает Chromium
  только через sandbox launcher и проверяет разрешённые/запрещённые направления.
- Ошибка browser installer прерывает release с ожидаемым кодом и возвращает
  прежние server/worker binaries и browser-комплект.
- Целевые installer и release тесты завершаются с кодом 0 на текущем `main`.

### План проверок

- `bash ops/test-install-server-browser.sh`
- `bash ops/test-fx-factory-release.sh`

### Риски и решения

Настоящий root/systemd/AppArmor/Chromium smoke в этом окружении не выполнен:
`sudo -n` требует пароль. Это не причина менять реализацию или ослаблять
изоляцию; живой host smoke должен выполняться только на разрешённом целевом
хосте. Альтернатива — считать изолированные shell-тесты заменой root smoke —
отклонена. Scope creep: повторная реализация или выкат уже находящегося в `main`
исправления не допускаются.

### Card

`knowledge/cards/CARD-0052-browser-install-live-smoke.md` — карточка исходной
реализации; эта карточка документирует решение о дубликате.

ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда bash ops/test-install-server-browser.sh
