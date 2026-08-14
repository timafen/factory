# Спецификация: актуализация доказательств browser suite в CARD-0126

## Цель и влияние на владельца

Убрать из CARD-0126 и этой спецификации неподтверждённое утверждение, что
`no new privileges` блокирует браузер. Для владельца результат должен ясно
разделять проверенную работоспособность launcher и текущую отсутствующую
зависимость web: browser suite не объявляется пройденным.

## Технический подход и реальные файлы

1. В `knowledge/cards/CARD-0126-staticcheck-attempt-lifecycle.md` заменить
   stale claim о NNP актуальным наблюдением: `/usr/local/libexec/factory/factory-browser-sandbox --version`
   успешно запускает Chrome 151 с exit 0.
2. Зафиксировать текущий блокер `just test-browser`: отсутствует
   `web/node_modules/.bin/tsc`, поэтому Playwright и browser suite не стартуют.
3. Не устанавливать зависимости и не менять product code, launcher, lifecycle
   или E2E-тесты; перечисленные файлы реализации остаются областью будущей работы.

## Последовательный план

1. Проверить наличие launcher и выполнить его `--version` с ограничением времени.
2. Проверить отсутствие `web/node_modules/.bin/tsc` и зафиксировать фактический
   ранний отказ `just test-browser`.
3. Обновить только эту спецификацию и карточку; dependency installation и
   повторный browser suite оставить следующему этапу.

## Критерии приёмки

- Устаревшее утверждение о `no new privileges` удалено из карточки и спецификации.
- Launcher подтверждён командой `factory-browser-sandbox --version`, exit 0.
- Текущий blocker назван явно: отсутствует `web/node_modules/.bin/tsc`.
- Browser suite не объявлен успешным; установка зависимостей не выполнена.
- Diff содержит только спецификацию и карточку CARD-0126.

## Тест-план

- `test -x /usr/local/libexec/factory/factory-browser-sandbox`.
- `timeout 30s /usr/local/libexec/factory/factory-browser-sandbox --version`.
- Проверить blocker: `test ! -x web/node_modules/.bin/tsc`.
- После установки зависимостей следующий этап выполняет ровно один
  `just test-browser`; здесь suite намеренно не заявляется пройденным.

## Риски и решения

- Риск снова принять инфраструктурное наблюдение за причиной: хранить вывод
  launcher и exit code отдельно от browser suite.
- Риск преждевременно объявить E2E зелёным: считать отсутствие `tsc` блокером
  до установки web-зависимостей и фактического запуска Playwright.
- Риск расширить область: запретить dependency installation и любые изменения
  исходников, launcher, lifecycle и тестов на этом этапе.

## Карточка работы

Карточка: `knowledge/cards/CARD-0126-staticcheck-attempt-lifecycle.md`.
Текущая работа — документационная коррекция; реализация отсутствует.

Файлы реализации для следующего этапа: нет изменений в репозитории; область
проверки — `/usr/local/libexec/factory/factory-browser-sandbox` и web-зависимости.

ГОТОВО-КОГДА: файл knowledge/specs/staticcheck-attempt-lifecycle.md
ГОТОВО-КОГДА: файл knowledge/cards/CARD-0126-staticcheck-attempt-lifecycle.md
ГОТОВО-КОГДА: команда timeout 30s /usr/local/libexec/factory/factory-browser-sandbox --version

Implementation commit: 4707a6de747a52c01e5db914f905b4378b3159fe — исправлено самосравнение в lifecycle-тесте worker
