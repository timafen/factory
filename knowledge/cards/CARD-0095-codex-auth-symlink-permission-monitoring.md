# CARD-0095 — Мониторинг Codex проверяет конечный auth.json

Implementation commit: 709a717c7ddf8e9ac20863046e7e49aefb67f3eb — Существующая Automation переключается на checker на месте с проверкой сохранности расписания и истории.

## HEAD

- Status: Implemented — замечание Review об аудите Automation закрыто.
- Branch: `factory/a95b3ad4-282-c73cedf2-52c`.
- Specification:
  `knowledge/specs/codex-auth-symlink-permission-monitoring.md`.
- Scope: устранить ложную тревогу о режиме `777` у auth-симлинка и сохранить
  обнаружение небезопасных прав конечного OAuth-файла.
- Relation: исходная находка закрывается как дубликат
  `CARD-0047-codex-auth-provisioning-ownership`; CARD-0095 не переделывает
  provisioning и описывает только отдельное исправление мониторинга.
- What changed: checker использует `stat -Lc`; новая идемпотентная команда обновляет именно
  существующую Automation и проверяет прежние ID, cron/timezone, enabled и все Occurrence.
- Evidence: `just test-tooling` и изолированный `just build` — PASS; live update сохранил
  Automation, расписание и 70 Occurrence; 11 фактических целей безопасны; Run now не создал
  новой находки. До выпуска ветки production checkout ещё не содержит checker. Снимок:
  `knowledge/evidence/CARD-0095-automation-update.json`.
- Next action: повторный Review сверяет поставленный операторский путь и evidence со свежим `main`.


## LOG

### 2026-08-12 — Specification

Владелец подтвердил разделение работ: сообщение о доступных OAuth-токенах не
подтвердилось и является дубликатом CARD-0047, а ложноположительная проверка
получает отдельную техническую карточку.

Изучены `ops/provision-codex-auth.sh`, его тест, интеграция `test-tooling` и
документы CARD-0047. Provisioner уже fail-closed проверяет обычный общий файл с
режимом `600` и владельцем `factory:factory`; отдельного read-only мониторинга
прав в репозитории нет.

Спецификация требует проверять метаданные конечной цели через `stat -Lc` либо
эквивалентную явную обработку симлинка. Ключевая регрессия создаёт ссылку с
обычным для Linux режимом `777`: безопасная цель проходит, а небезопасный режим
целевого `auth.json` обнаруживается. Содержимое OAuth-файла не читается.

Номер `CARD-0095` выбран после проверки свежего `origin/main` и деревьев 773
опубликованных веток: `CARD-0093` и `CARD-0094` заняты, `CARD-0095` и выбранный
путь свободны.

### Передача в реализацию

- Реализовать только отдельный checker, его shell-тест, включение в
  `test-tooling` и операторскую документацию.
- Не менять модель auth-ссылок и защищённую общую цель из CARD-0047.
- В карточке Implement заменить строку `Implementation commit` полным SHA
  отдельного кодового коммита, существующего в ветке до документационного
  коммита карточки.
- Обновить контекст существующей Automation без смены schedule и без удаления
  исторических Occurrence; Run now не должен создавать повторную finding о 777.


### 2026-08-12 — Implement

Добавлен `ops/check-codex-auth-permissions.sh`: он проверяет только конечную цель `auth.json` через
`stat -Lc`, поэтому безопасная цель за симлинком с отображаемым режимом 777 проходит, а неверный режим,
тип, владелец, группа и dangling-ссылка дают ненулевой код. Проверка read-only и не выводит секрет.

Регрессия `bash ops/test-check-codex-auth-permissions.sh` покрывает безопасную цель, режимы 644/660/777,
каталог, неверные метаданные, отсутствие воркеров и отсутствие изменения цели; `just test-tooling` и
`just build` завершились PASS. Полный `just check` прошёл format/vet/vuln/staticcheck и все пакеты
до внеобластного flaky `internal/worker.TestIdleWorkerMakesOneClaimPerPollingInterval`, завершившегося
таймаутом ожидания.

Через штатный API обновлён context Automation «Патруль Factory»: версия 2, расписание `17 * * * *`
сохранено, 68 исторических Occurrence сохранены, Automation снова enabled; live checker вернул 0,
подтвердил 11 целей `regular file 600 factory factory` и не вывел содержимое токена. После этого
Run now task завершился успешно с результатом «новых подтверждённых нерешённых находок нет»;
matching run-now occurrence сохранился, повторная карточка о режиме 777 не создана.

### 2026-08-12 — Implement

После замечания Review добавлена идемпотентная операторская команда обновления текущей
Automation через штатный API. Перед `PUT` она запоминает идентификатор, расписание,
enabled-состояние и полный набор Occurrence, а после обновления проверяет их сохранность;
регрессия покрывает обновление на месте и повторный запуск без новой версии.

Команда применена к живой Automation «Патруль Factory»: версия изменилась с 2 на 3,
ID и расписание `17 * * * *` / `America/Chicago` остались прежними, все 70 исторических
Occurrence сохранились. Live checker вернул 0 для 11 целей с метаданными
`regular file 600 factory factory`; проверяемый обезличенный снимок сохранён в
`knowledge/evidence/CARD-0095-automation-update.json`.

Run now версии 3 завершился успешно и не создал новых находок. Он ожидаемо сообщил,
что checker отсутствует в production checkout до слияния этой ветки; это остаётся
единственной границей живой проверки и устраняется обычным выпуском поставленного кода.

`just test-tooling` — PASS, включая две новые регрессии; `FACTORY_BUILD_DIR=/tmp/card0095-build
just build` — PASS; `git diff --check` — PASS.
