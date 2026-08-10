# Сетевая изоляция серверного браузера

## Контракт

Серверный Chromium может устанавливать TCP/UDP-соединения только с адресами,
которые в момент запуска принадлежат `factory.timafen.com` и
`staging-automation.tarser.net`. Loopback разрешён как техническое исключение.
`automation.tarser.net`, DNS из браузера и весь остальной интернет запрещены.

Граница обеспечивается transient systemd scope: `IPAddressDeny=any`,
`IPAddressAllow=localhost` и точечные `IPAddressAllow` для предварительно
разрешённых root-процессом адресов. Chromium получает фиксированные resolver
rules для двух имён, поэтому ему не требуется сетевой DNS. Аргументы, способные
подменить resolver/proxy или отключить Chromium sandbox, launcher отвергает.
Подстановка переменных и specifier в аргументах `systemd-run` отключена, поэтому
после проверки аргументы не могут превратиться в запрещённые switches.

На Ubuntu с запретом unprivileged user namespaces установщик добавляет
AppArmor-профиль для точного пути закреплённого full Chromium. Профиль разрешает
только необходимый Chromium sandbox `userns`; `--no-new-privs` и запрет всех
аргументов отключения sandbox сохраняются.

## Установка и выпуск

До изменения живых файлов root-installer запускает локальный listener и
проверяет, что та же systemd BPF-политика разрешает loopback, но блокирует
заведомо доступный non-loopback адрес хоста. Любая ошибка означает fail-closed:
контроль без BPF-свойств обязан достичь того же адреса и опровергнуть изоляцию,
иначе launcher не устанавливается. Launcher, root helper, конфигурация, sudoers
и AppArmor-профиль заменяются как один комплект и целиком возвращаются при
неуспешном smoke.

Штатный release обязательно запускает installer. Ошибка BPF-пробы, установки
или smoke прерывает выпуск и возвращает прежние server/worker binaries.
Системные зависимости ставятся с `NEEDRESTART_MODE=l` и
`DEBIAN_FRONTEND=noninteractive`, поэтому needrestart только перечисляет
затронутые службы и не перезапускает активные worker units.

## Smoke-критерии

- Chromium запускается с включённым Linux sandbox через установленный launcher.
- Каждая разрешённая и запрещённая навигация выполняется в отдельной Playwright
  page, которая закрывается сразу после проверки. Поздняя внутренняя навигация
  Basic Auth в `chrome-error://chromewebdata/` не может перебить staging.
- Локальный Factory на `http://127.0.0.1:7337` и staging загружают DOM; staging
  сохраняется в screenshot.
- Публичный `https://factory.timafen.com` либо загружает DOM, либо возвращает
  ровно `net::ERR_INVALID_AUTH_CREDENTIALS`: Basic Auth доказывает достижимость
  защищённого FQDN. Любая другая ошибка прерывает установку.
- `automation.tarser.net` и `example.com` не открываются.
- Screenshot существует и не пуст.

## Fail-closed альтернатива

Если systemd BPF firewall на целевом хосте не проходит живую пробу, установка
не продолжается. Равноценная следующая реализация — отдельный network namespace
для Chromium с deny-by-default nftables и тем же динамическим набором адресов;
переключаться на неё автоматически или разрешать обычную сеть запрещено.

## Вне области

Не разрешаются дополнительные домены, production, произвольный DNS, proxy или
отключение Chromium sandbox. Общий egress Factory server/worker не меняется.
