# CARD-0095 — Мониторинг Codex проверяет конечный auth.json

Implementation commit: cea86c67ad856d13b05e44cd936e7314cd58710b — Добавлен read-only checker прав конечных целей Codex и регрессии на симлинк с отображаемым режимом 777.

## HEAD

- Status: Implemented — целевые проверки PASS; полный check выявил только внеобластной flaky-тест worker.
- Branch: `factory/4feea8b9-05a-942a7a20-8d1`.
- Specification:
  `knowledge/specs/codex-auth-symlink-permission-monitoring.md`.
- Scope: устранить ложную тревогу о режиме `777` у auth-симлинка и сохранить
  обнаружение небезопасных прав конечного OAuth-файла.
- Relation: исходная находка закрывается как дубликат
  `CARD-0047-codex-auth-provisioning-ownership`; CARD-0095 не переделывает
  provisioning и описывает только отдельное исправление мониторинга.
- What changed: checker использует `stat -Lc`, принимает только `regular file 600 factory factory`,
  не меняет ссылки и не читает содержимое токена; Automation «Патруль Factory» переведена на него.
- Evidence: `bash ops/test-check-codex-auth-permissions.sh`, `bash ops/test-provision-codex-auth.sh`,
  `just test-tooling` и `just build` — PASS; live checker подтвердил 11 безопасных целей; Run now
  завершился без новых подтверждённых находок.
- Next action: Verify проверяет поставленный коммит относительно свежего `main`; известный риск —
  внеобластной `internal/worker.TestIdleWorkerMakesOneClaimPerPollingInterval`.


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
