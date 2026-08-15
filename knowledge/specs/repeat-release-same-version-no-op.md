# Повторный выпуск той же версии не создаёт ложные current и previous

## Цель и влияние на владельца

Сейчас повторный `fx-factory-release main`, когда `main` разрешается в уже
установленный commit, проходит весь выпуск заново. Driver формирует новый
`release_id` из времени/PID, собирает новый snapshot и manifest, а после
переключения служб публикует новый `current`, прежний `current` делает
`previous`. В результате владелец видит две роли для одного кода и теряет
реальную предыдущую точку отката.

После реализации такой повтор станет успешным безопасным no-op: уже
опубликованные `current` и `previous`, их целые поколения, manifest-хеши,
пути и `factory-current.json` останутся байт-в-байт прежними. Не будут
запускаться build/gates, online snapshot, остановка или запуск служб, не
появится journal и новое поколение. Владелец получит понятное сообщение,
что запрошенная версия уже установлена. Выпуск первого поколения без
истории и выпуск другого commit SHA сохраняют существующую семантику.

В этой работе «та же версия» означает точное совпадение полного SHA,
полученного из `git rev-parse HEAD` после разрешения `ref`, с SHA уже
установленного `current`. Заголовок commit, короткий SHA, `release_id`, дата
или совпадающее имя ветки не являются идентичностью версии.

## Технический подход и реальные файлы

- `ops/fx-factory-release` — сохранить текущие lock и fail-closed проверки
  `validate_release_history` и `validate_live_rollback_kit`. Для непустой
  проверенной истории дополнительно закрепить инвариант: `candidate_sha` в
  manifest текущего поколения совпадает с SHA в валидной живой metadata. При
  расхождении отказать до любых изменений, а не выбирать no-op на основании
  одного из источников.
- В том же driver разрешить исходный `ref` и получить полный `sha` через
  существующий доверенный clone/checkout. Сразу после этого, до извлечения
  trusted gate, запуска gate, `npm ci`, `vite build`, `go build`, snapshot,
  создания `release_id` и остановки служб, проверить только для
  `bootstrap_release=0`: `sha == current manifest candidate_sha ==
  current_sha`. При точном равенстве напечатать человекочитаемый успешный
  no-op, закрыть временный work directory штатным cleanup и выйти с кодом 0.
  Guard не должен писать metadata, ссылки, journal, manifest или новый
  каталог поколения.
- Если SHA отличается, либо история bootstrap-пустая, guard не срабатывает:
  существующий путь создаёт snapshot/manifest, применяет уникальный
  `release_id`, проходит gates и services, затем атомарно публикует current и
  previous как сейчас. Формат manifest, retention, rollback и правила
  production-выпуска этой работой не меняются.
- `ops/test-fx-factory-release.sh` — добавить отдельный наблюдаемый fixture
  сценария: выполнить успешный выпуск SHA A, зафиксировать resolved targets
  `current`/`previous`, хеши обоих manifest, хеш и содержимое metadata, список
  поколений; повторить тот же repo/HEAD SHA A после очистки event/gate
  журналов; затем добавить в fixture repo новый commit SHA B и выполнить
  обычный выпуск. Вспомогательные wrappers должны позволять доказать, что
  второй запуск не заходил в gates/build/services.

## Последовательный план

1. Уточнить preflight-инвариант согласованности живой metadata и manifest
   текущего поколения; несовпадение оставить fail-closed.
2. Разместить сравнение после получения полного candidate SHA и до первой
   тяжёлой операции или мутации, с отдельным успешным no-op сообщением и
   штатным cleanup.
3. Расширить fixture последовательностью A → A → B. Для A → A проверить
   код возврата, отсутствие новых поколений, journal, gate/build/service
   событий и неизменность ссылок, manifest и metadata.
4. Для A → B подтвердить обычную ротацию: новый current содержит B, previous
   указывает ровно на прежний current A, оба поколения проходят существующую
   проверку целостности.
5. Выполнить обязательный release-тест и проверку whitespace; не трогать
   product/UI-файлы за пределами двух перечисленных shell-файлов.

## Критерии приёмки

1. В валидной non-bootstrap истории повторный выпуск того же полного
   resolved Git SHA завершается кодом 0 с явным no-op сообщением.
2. Такой no-op не запускает `npm ci`, UI/Go gates, `vite build`, `go build`,
   backup/snapshot, `systemctl stop/start`, установку payload или запись
   journal; после cleanup нет нового build/generation артефакта.
3. До и после no-op совпадают resolved targets `current` и `previous`,
   байты `factory-current.json`, SHA manifest обоих поколений, имена/пути
   поколений и rollback-точка; в `current` и `previous` не появляется новая
   роль с тем же SHA.
4. Сравнение использует полный resolved SHA и не считает одинаковый subject,
   ref или `release_id` достаточным основанием для no-op. Несогласованная
   metadata/manifest блокирует выпуск безопасным отказом.
5. Первый выпуск, когда истории current/previous ещё нет, не пропускается
   как no-op и сохраняет bootstrap-поведение.
6. После выпуска другого полного SHA существующая ротация не ломается:
   новый candidate становится `current`, прежний current остаётся
   `previous`, metadata и manifest описывают новый SHA, а обычные gates и
   service-переход выполняются один раз.
7. Форматы manifest, retention, `fx factory rollback`, live production
   deployment и UI в рамках этой работы не изменяются.

## Тест-план

- Новый последовательный сценарий в `ops/test-fx-factory-release.sh`: A → A
  → B в одном fixture. Второй запуск должен иметь статус 0, но нулевые новые
  строки в gate/build и service event журналах; сравнения делаются до/после
  по symlink targets, generation names, `factory-current.json` и manifest
  hashes.
- Для третьего запуска assert `manifest.candidate_sha` нового current равен
  B, предыдущий target равен сохранённому current A, а оба поколения проходят
  существующий `verify_immutable_generation`. Отдельно assert, что второй
  no-op не создаёт `release_id`/journal и не сдвигает bootstrap previous.
- Проверить, что subject/ref с одинаковым текстом при реально новом SHA не
  обходят обычный выпуск; это исключает слишком широкое сравнение.
- Обязательная команда: `bash ops/test-fx-factory-release.sh`.
- Документарная проверка: `git diff --check`.

## Риски и решения

- Сравнение только с `factory-current.json` может скрыть рассинхрон с
  опубликованным manifest. Решение: перед no-op сопоставлять оба источника и
  отказывать при расхождении.
- Сравнение короткого SHA или subject даёт ложное совпадение. Решение:
  использовать полный вывод `rev-parse HEAD` и явно проверить новый SHA в
  A → B сценарии.
- Guard, поставленный после build или stop, уже не идемпотентен. Решение:
  зафиксировать его сразу после resolved SHA, до trusted gate/build,
  snapshot, `release_id` и systemd-мутаций; lock остаётся действующим.
- Первый выпуск имеет metadata старого установленного кода, но ещё не имеет
  поколения current. Решение: no-op разрешён только при
  `bootstrap_release=0`; bootstrap всегда строится по существующему пути.
- В текущем Factory-контейнере release fixture может остановиться на
  проверке владельца `/usr/bin/stat` (UID окружения `nobody`, тогда как
  fixture ожидает root). Решение: не расширять продуктовую область из-за
  этого ограничения; прогонять обязательный тест в доверенном runner и
  отдельно отмечать инфраструктурный блок, если он воспроизводится.

## Карточка работы

`knowledge/cards/CARD-0302-repeat-release-same-version.md`

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
