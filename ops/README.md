# Мозг фабрики

Здесь живёт всё, что делает фабрику самостоятельной, кроме секретов.

- `pilot/pilot.py` — пилот: смотрит на задачи, двигает конвейер, отвечает
  на технические вопросы сам, зовёт хозяина только по делу.
- `pilot/context.md` — инструкции всем агентам: как сдавать работу,
  за что нельзя возвращать, куда писать находки.
- `pilot/config.example.json` — пример конфигурации. Живой `config.json`
  лежит только на сервере: в нём личные темы уведомлений.
- `intake/app.py` — приёмник: голос в задачу, план, озвучка.
- `intake/plan.py` — экран «План»: предложения и находки по проектам.
- `ops/fx` — справочная копия брокера fx (живёт в /usr/local/bin, root).
- `ops/install-factory-control.sh` — атомарно обновляет сам брокер `fx` и
  драйвер выпуска из одной проверенной ревизии; частичная замена откатывается.
  На чистом хосте первый запуск — осознанное ручное действие root, а не часть
  конвейера. Root клонирует репозиторий, сверяет глазами нужный коммит `main`,
  затем из root-owned checkout запускает установщик: он ставит `fx`, release
  driver, cgroup helper и bootstrap без обращения к уже установленному `fx`.
  Обычный release helper не переустанавливает их.
- `ops/factory-cgroup-bootstrap.sh` — одноразово ставит cgroup helper с откатом,
  выполняет живой cgroup v2 probe и оставляет защищённый marker; до marker Gate
  закрыт. Запуск без root явно отмечается тестом как `SKIP`.
- `ops/install-brain.sh` — установка мозга при выкате: проверка, замена,
  перезапуск, откат при беде. Вызывается из fx-factory-release.
- `ops/provision-codex-auth.sh` — fail-closed проверка общего `auth.json` и
  создание ссылок рабочих `CODEX_HOME` от имени `factory`; вызывается релизом
  до запуска воркера и может использоваться provisioner-ом напрямую.
- `ops/systemd/` — справочные копии служб.

Секреты — токен GitHub, ключи, temы ntfy, пароли — в репозиторий не идут
никогда. Они живут на сервере: /etc/factory-access/, /etc/nginx/.

## Первая установка cgroup helper на чистом хосте

Это единственная точка начального доверия: её выполняет root руками, до первого
выпуска и не через `fx`. На сервере root должен сам получить исходники и сверить,
что выбран именно ожидаемый коммит из `main`:

```bash
sudo -i
git clone https://github.com/timafen/factory.git /root/factory-bootstrap
cd /root/factory-bootstrap
git fetch origin main
git checkout --detach origin/main
git log -1 --decorate
env FACTORY_CONTROL_BOOTSTRAP=1 bash ops/install-factory-control.sh "$PWD"
```

Перед последней командой root сравнивает показанный `HEAD` с согласованным
коммитом `main` и читает изменяемые `ops/`-файлы. Установщик проверяет
root-владение и права всей цепочки checkout, а также закреплённый SHA-256 helper;
он не запускает `fx`. После этого первый `fx factory cgroup-helper-bootstrap`
в доверенном каталоге выпуска выполняет живую cgroup v2-проверку и создаёт
marker. До marker Gate намеренно остаётся закрытым; последующие выпуски сверяют
owner, mode, hash и marker перед запуском Gate.
