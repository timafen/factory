#!/usr/bin/env python3
"""factory-pilot: automatic pipeline orchestrator for Factory.

Watches tasks titled '[auto] ...'. When a stage task finishes, a decision
model (Claude) reads the result and decides: advance to the next stage,
or stop for a human. Manual tasks (without the [auto] prefix) are ignored,
so humans can always run stages by hand or skip ahead by creating an
'[auto]' task at any later stage themselves.

Planner layer (epics):
- A task titled '[epic-plan] <goal>' (or run through the 'Epic Planning'
  workflow) is a spoken/typed goal. Its worker reads the repo and emits a
  JSON block of subtasks. When it succeeds, the pilot decomposes it into an
  epic file under pilot/epics/ with status 'planned' - it does NOT start work.
- To approve, a human creates a task titled '[epic-start] <name substring>'.
  The pilot matches the most recent planned epic (by name substring, or the
  latest planned epic if no substring) and fans out one '[auto]' first-stage
  task per subtask, then marks the epic 'running'. A UI Start button can call
  the same mechanism later.
"""
import argparse
import base64
import calendar
import datetime
import io
import glob
import hashlib
import json, re, shlex, subprocess, time, urllib.request, urllib.error, urllib.parse, uuid, sys, os, tempfile

API = "http://127.0.0.1:7337/api/v1"
# Production keeps the fixed data root.  Tests and isolated tools may opt into
# a disposable root before importing this module, so they can never overwrite
# the live Pilot state while exercising cycle().
HOME = os.environ.get("FACTORY_DATA_HOME", "/opt/factory-data")
CONF_PATH = f"{HOME}/pilot/config.json"
STATE_PATH = f"{HOME}/pilot/state.json"
EPIC_DIR = f"{HOME}/pilot/epics"
QUESTION_DIR = f"{HOME}/pilot/questions"
CONTEXT_PATH = f"{HOME}/pilot/context.md"
VERDICT_DIR = f"{HOME}/pilot/verdicts"
PREFIX = "[auto]"
STAGE_TITLE_RE = re.compile(r"^\[auto\]\s*\[\d+/\d+\s+([^\]]+)\]\s*(.*)$")
EPIC_PLAN_WF = "Epic Planning"       # workflow title that produces a plan
EPIC_PLAN_PREFIX = "[epic-plan]"     # or any task titled like this
EPIC_START_PREFIX = "[epic-start]"   # human approval to fan out

HOST_LOAD_ACTIVE_STATES = {"running", "queued", "pending", "created", "starting"}
HOST_LOAD_LIGHT_STAGES = {"Triage", "Specification", "Review"}
HOST_LOAD_MINIMUM_ACTIVE = 1
MAX_RETAINED_PER_REPOSITORY = 10
PROCESSED_RETENTION = 10000
RESTART_RECOVERY_RETENTION = 500
FAST_POLL_SECONDS = 2
ACTIVE_POLL_SECONDS = 10
ERROR_BACKOFF_MAX_SECONDS = 300
MAX_PARALLEL_WORKS = 4
# A busy four-slot Factory must be able to refill all slots from completed
# handoffs in one bounded pass.  The history window below still prevents the
# old failure mode where every archival task was replayed in one cycle.
MAX_TERMINAL_TASKS_PER_CYCLE = 4
TERMINAL_HANDOFF_HISTORY_LIMIT = 200
MERGE_CONFLICT_RE = re.compile(
    r"merge conflict|has merge conflicts|not mergeable|cannot be cleanly created",
    re.I,
)


class ParallelWorkLimit(RuntimeError):
    """A pipeline handoff must wait until another work slot is free."""


def api(path, body=None):
    req = urllib.request.Request(API + path)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def all_tasks():
    """Read every task page so old real work is not displaced by service runs."""
    tasks, cursor = [], ""
    for _ in range(500):
        path = "/tasks?limit=200" + ("&cursor=" + urllib.parse.quote(cursor) if cursor else "")
        page = api(path)
        tasks.extend(page.get("tasks") or [])
        cursor = page.get("next_cursor") or ""
        if not cursor:
            break
    if cursor:
        raise RuntimeError("task pagination did not finish")
    return tasks


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def log(*a):
    print(*a, flush=True)


def base_title(title):
    return re.sub(r"^\[auto\]\s*(\[\d+/\d+[^\]]*\]\s*)?", "", title).strip()


PIPELINE_TITLE = re.compile(r"^\[auto\]\s*\[(\d+)/(\d+)\s+([^\]]+)\]\s*(.*)$")
SERVICE_WORK_TITLE = re.compile(r"(?:smoke|helper|debug|idempoten|идемпотен)", re.I)


def pipeline_title(task):
    """Owner-facing identity of a pipeline task, without its stage wrapper."""
    match = PIPELINE_TITLE.match(task.get("title") or "")
    if not match:
        return None
    return match.group(4).strip(), match.group(3).strip()


def has_task_provenance(task):
    """Whether control-plane provenance, rather than a legacy title, exists."""
    return any((task or {}).get(field) for field in (
        "work_id", "parent_task_id", "correction_kind"))


def task_work_id(task):
    """Durable work identity for new rows, title identity only for legacy rows."""
    task = task or {}
    return task.get("work_id") or base_title(task.get("title") or "")


def task_is_root(task):
    task = task or {}
    return bool(task.get("work_id") and task.get("work_id") == task.get("id")
                and not task.get("parent_task_id")
                and not task.get("correction_kind"))


def same_task_work(task, reference):
    """Compare durable work IDs when present; use titles only for legacy rows."""
    if isinstance(reference, dict):
        if (task or {}).get("work_id") or reference.get("work_id"):
            return bool((task or {}).get("work_id")
                        and (task or {}).get("work_id") == reference.get("work_id"))
        reference = base_title(reference.get("title") or "")
    if (task or {}).get("work_id"):
        return (task or {}).get("work_id") == reference
    return base_title((task or {}).get("title") or "").strip() == str(
        reference or "").strip()


def is_service_work(title):
    """Service runs are useful diagnostics, but are not owner work delivered."""
    return bool(SERVICE_WORK_TITLE.search(title or ""))


def verify_passed(result):
    """The last stage prints a PASS / BLOCKED verdict. First verdict word wins."""
    m = re.search(r"\b(PASS|BLOCKED)\b", result or "")
    return bool(m) and m.group(1) == "PASS"


def run_shell(cmd, timeout=1800):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           env=dict(os.environ, HOME=HOME), timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, f"shell error: {e}"


UI_BASE = "https://factory.timafen.com"


# Уведомления разложены по группам: владелец сам решает, что доходит до
# телефона. Событие, чья группа выключена, всё равно пишется в журнал и видно
# в интерфейсе — молчит только push, чтобы в потоке было видно настоящую тревогу.
NOTIFY_GROUPS = {
    "questions": ("Нужен твой ответ", "План эпика готов", "Кодекс закончил — твой ход"),
    "stuck": ("Кручусь по кругу", "Зациклилось", "Не могу продолжить",
              "Проверка не прошла", "Verify PASS, но мёрж", "Эпик НЕ запустился"),
    "money": ("Не влезло в деньги", "Остановил работу", "Дневной потолок",
              "Упёрлись в лимит", "Продлил бюджет"),
    "done": ("Задача выполнена", "Задача завершена", "Эпик завершён", "Задача заведена",
             "Голосовая задача", "Эпик запущен"),
    "escalate": ("Исполнитель повышен",),
    "diag": ("Разобрался в застрявшей", "Застряла — нужен ты"),
    "plan": ("Новое в Плане",),
    "routine": ("Повторяю этап", "Вернул сам:", "Вернул без Ревью", "Мёрж-конфликт", "Сдвинул застрявшую",
                "Взял из Плана",
                "Ответ принят", "Решил сам", "Разорвал круг сам", "Сменил подход",
                "Перезапускаю дешевле", "Эпик: пошла подзадача"),
}
NOTIFY_DEFAULTS = {"questions": True, "stuck": True, "money": True,
                   "done": True, "escalate": True, "routine": False}


def notify_group(title):
    """К какой группе относится уведомление. Незнакомое — к «работа встала»:
    лучше лишний раз позвать, чем промолчать о том, чего мы не предусмотрели."""
    t = str(title or "")
    for group, prefixes in NOTIFY_GROUPS.items():
        if any(t.startswith(p) for p in prefixes):
            return group
    return "stuck"


def notify_allowed(conf, title):
    group = notify_group(title)
    on = (conf.get("notify_groups") or {})
    return bool(on.get(group, NOTIFY_DEFAULTS.get(group, True)))


WORK_BRANCH_TOKEN = re.compile(r"`?factory/[0-9a-f][0-9a-f-]{15,}`?", re.IGNORECASE)
UUID_TOKEN = re.compile(
    r"`?[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}`?",
    re.IGNORECASE,
)
HEX_TOKEN = re.compile(r"`?(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])`?")


def no_bare_hashes(text):
    """Хозяин читает пуши на телефоне. Голый хеш ему не говорит ничего,
    поэтому в уведомления он не проходит никогда — это правило кода,
    а не пожелание агентам."""
    value = WORK_BRANCH_TOKEN.sub("рабочая ветка", str(text or ""))
    value = UUID_TOKEN.sub("внутренняя задача", value)
    return HEX_TOKEN.sub("проверенная версия", value)


NOTIFY_LOG_PATH = f"{HOME}/pilot/notifications.jsonl"


def _notify_journal(title, message, group, delivered, click, journal_id=""):
    """Каждое уведомление остаётся в журнале — экран «Уведомления» читает его.
    Тихие (выключенная группа) тоже пишутся, с пометкой."""
    try:
        if journal_id and os.path.exists(NOTIFY_LOG_PATH):
            with open(NOTIFY_LOG_PATH, encoding="utf-8") as stream:
                if any(json.loads(line).get("id") == journal_id
                       for line in stream if line.strip()):
                    return False
        rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "title": title, "message": message[:1500],
               "group": group, "delivered": bool(delivered), "click": click}
        if journal_id:
            rec["id"] = journal_id
        with open(NOTIFY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if os.path.getsize(NOTIFY_LOG_PATH) > 1_500_000:
            lines = io.open(NOTIFY_LOG_PATH, encoding="utf-8").readlines()[-800:]
            io.open(NOTIFY_LOG_PATH, "w", encoding="utf-8").writelines(lines)
        return True
    except Exception as e:
        log("notify_journal_error", repr(e))
        return False


def notify(conf, title, message, priority="default", tags="", click="", journal_id=""):
    title = no_bare_hashes(title)
    message = no_bare_hashes(message)
    _notify_journal(title, message, notify_group(title),
                    notify_allowed(conf, title), click, journal_id)
    if not notify_allowed(conf, title):
        log("QUIET[" + notify_group(title) + "] " + str(title)
            + " :: " + str(message)[:80].replace("\n", " "))
        return
    """Phone push via ntfy (if ntfy_topic set in config). Never raises."""
    topic = (conf or {}).get("ntfy_topic", "")
    if not topic:
        return
    server = (conf or {}).get("ntfy_server", "https://ntfy.sh")
    try:
        prio = {"low": 2, "default": 3, "high": 4, "max": 5}.get(priority, 3)
        body = {"topic": topic, "title": title[:120], "message": message[:1500],
                "priority": prio,
                # a button, not `click`: tapping the notification just opens it
                # for reading; the link is followed deliberately.
                "actions": [{"action": "view", "label": "Открыть в Factory",
                             "url": click or (UI_BASE + "/work"), "clear": False}]}
        if tags:
            body["tags"] = tags.split(",")
        req = urllib.request.Request(server, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        log("notify_error", repr(e))


def best_workers(worker_list):
    """Name -> worker, preferring online+healthy entries (re-registered workers
    can leave stale duplicates behind)."""
    out = {}
    for w in worker_list:
        cur = out.get(w["name"])
        score = (bool(w.get("online")), w.get("health") == "healthy")
        if cur is None or score > (bool(cur.get("online")), cur.get("health") == "healthy"):
            out[w["name"]] = w
    return out


def _http_err(e):
    try:
        return e.read().decode()[:300]
    except Exception:
        return str(e)


# ------------------------------------------------- денежный предохранитель ---
# 8 августа кодекс сжёг НЕДЕЛЬНЫЙ лимит подписки за один день: ~200 задач за
# сутки, из них 42 на одну работу. Счётчик долларов не видит кодекс, поэтому
# защита считает то, что видит всегда: сколько задач создано за 24 часа.
DAYFLAG_PATH = f"{HOME}/pilot/day_cap_flag.json"


def _recent_tasks():
    try:
        ts = api("/tasks?limit=200").get("tasks") or []
    except Exception:
        return []
    seen, out, now = set(), [], time.time()
    for t in ts:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        c = (t.get("created_at") or "")[:19]
        try:
            age = now - calendar.timegm(time.strptime(c, "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            continue
        if 0 <= age < 86400:
            out.append(t)
    return out


def money_guard(conf, title):
    """Бросает исключение, если создание задачи прожжёт лимиты подписок.
    Работает по числу задач, а не по долларам: доллары кодекса мы пока
    не видим, а число задач видим всегда и для всех провайдеров."""
    base = base_title(title)
    rec = _recent_tasks()
    wcap = int(conf.get("work_day_cap", 12))
    dcap = int(conf.get("day_task_cap", 120))
    # Живой темп важнее цифры из настроек: если фабрика уже сутки работает
    # быстрее потолка, значит потолок занижен — иначе она душит сама себя.
    try:
        pace = int(load(f"{HOME}/pilot/day_pace.json", {}).get("tasks") or 0)
        if pace > dcap:
            dcap = pace + 50
    except Exception:
        pass
    mine = sum(1 for t in rec if base_title(t.get("title", "")) == base)
    if mine >= wcap:
        if not is_stopped(conf, base):
            pause_pipeline(conf, base)
            notify(conf, "Остановил работу: сожгла дневной запас",
                   base + "\n" + str(mine) + " задач за сутки при потолке "
                   + str(wcap) + ". Это горящие деньги, а не прогресс. "
                   "Продолжить можно, сняв работу с паузы в настройках.",
                   priority="high", tags="money_with_wings")
        raise RuntimeError("work_day_cap: %r %d/%d" % (base[:40], mine, wcap))
    if len(rec) >= dcap:
        flag = load(DAYFLAG_PATH, {}) or {}
        day = time.strftime("%Y-%m-%d")
        if flag.get("day") != day:
            save(DAYFLAG_PATH, {"day": day})
            notify(conf, "Дневной потолок задач исчерпан",
                   str(len(rec)) + " задач за сутки при потолке " + str(dcap) +
                   ". Новые этапы не создаю, пока окно не освободится. "
                   "Потолок правится в настройках: day_task_cap.",
                   priority="high", tags="money_with_wings")
        raise RuntimeError("day_task_cap: %d/%d" % (len(rec), dcap))


# ------------------------------------------------- правила в каждую задачу ---
# context.md читает мозг пилота, а НЕ агенты. Всё, что обязаны знать агенты,
# доставляется сюда — пилот вшивает этот блок в контекст каждой [auto]-задачи.
AGENT_RULES = """
=== ПРАВИЛА ДЛЯ АГЕНТА (обязательны, проверяются машиной) ===
1. Ветка: режь от свежего origin/main (git fetch origin). НИКОГДА не делай
   checkout другой ветки в рабочей копии — это ломает воркера. Чужую работу
   забирай так: git fetch origin <ветка> && git reset --hard FETCH_HEAD.
2. Review и Verify: ДО ЛЮБОГО diff, log, merge-base или решения о пустой
   поставке получи default branch именно remote (`git ls-remote --symref origin
   HEAD`), fetch-ни только этот ref и рабочую ветку в отдельный read-only
   каталог, зафиксируй полные `base_sha` и `candidate_sha`. Все сравнения
   делай только как `<base_sha>...<candidate_sha>`; cached `origin/main`
   запрещён. Ошибка resolution/fetch — это `BLOCKED: review infrastructure`,
   никогда не REQUEST CHANGES. В финальном отчёте укажи обе SHA и причину,
   если инфраструктура заблокировала проверку.
3. Сдача: сначала перебазируй на свежий main (git fetch origin main,
   затем git rebase origin/main), потом проверь список файлов командой
   git diff --name-only origin/main...HEAD — именно ТРИ точки, сравнение от
   точки ветвления. В списке ТОЛЬКО твои файлы. Запушь:
   git push --force-with-lease -u origin HEAD. Непушенная работа не существует.
4. Отчёт заканчивай строками:
   ОБЛАСТЬ: <файлы через запятую, ровно как в git>
   TRY: <ссылка на экран, где человек ГЛАЗАМИ видит результат. Служебные
   страницы (health, login, «ok») — НЕ результат. Если работа невидимая
   (чистка кода, конфиги), пиши: TRY: нет>
   ДОКАЗАТЕЛЬСТВО: <обязательно, если TRY: нет. Пиши ПРО СУТЬ ЗАДАЧИ,
   для человека, который код не читает: СНАЧАЛА что теперь умеет продукт
   или что изменилось, ПОТОМ в скобках чем подтверждено. Пример:
   «песочница заводит политики продавца — оплату, доставку, возвраты —
   одной командой (проверено 25 целевыми проверками)». Голые «тесты
   зелёные», «diff чистый», «коммит запушен» доказательством НЕ считаются
   и будут возвращены>
5. Пиши для человека: первая строка коммита — по-русски, что и зачем.
   Голые хеши/ID на экранах и в текстах для владельца запрещены — только
   со словесной подписью. Ревью возвращает работу за голый хеш на экране.
6. Знания: заводи ОТДЕЛЬНУЮ карточку. Если в контексте выдана строка `Card: CARD-…`, заводи карточку
   только как `knowledge/cards/<выданный Card>-<slug>.md`. Не ищи следующий
   номер в файлах и не выбирай его самостоятельно. В общие файлы-журналы
   (CARD-0030 и подобные) НЕ дописывай ни строки: общий файл — магнит для
   конфликтов слияния, когда работы идут параллельно. Всё побочное — строками
   ПРЕДЛОЖЕНИЕ/НАХОДКА в отчёте, карточка заведётся сама.
   В начале карточки обязательно напиши строку `Implementation commit: <полный
   SHA> — <что реализовано>`: это коммит с кодом, сделанный ДО финального
   коммита самой карточки. Хеш обязан существовать в этой ветке и содержать
   изменения вне `knowledge/cards/`. Не пиши `Head commit` и не сверяй это
   поле с текущим `git HEAD`: запись карточки закономерно создаёт следующий
   документационный коммит.
7. Скорость: НЕ гоняй полный набор тестов на каждом шаге. Разработка гоняет
   только целевые тесты своей области (и новые). Ревью тесты не запускает —
   читает дифф, максимум целевые при сомнении. Полный набор — ровно ОДИН раз,
   на Проверке, перед вливанием. Итерации должны быть минутами, не десятками.
   Если общий набор проекта красный ИЗ-ЗА файлов вне твоей области — это долг
   проекта, а не твой дефект: прогони целевые тесты своей области, запиши
   строкой НАХОДКА, что именно красное, и ставь PASS. Работу за чужую
   красноту не возвращают.
7. Живая проверка на стенде РАЗРЕШЕНА и желательна (торговый проект):
   sudo -n /usr/local/bin/fx staging sandbox bootstrap-accounts | seller-policies
   | listings   (можно с флагами вида --tenant-id=... --account-id=...).
   Порядок: сначала аккаунты, потом политики, потом объявления. Если живая
   проверка прошла — в TRY: дай ссылку на экран стенда с результатом. Если
   чего-то из разрешённого не хватает — напиши строкой НАХОДКА, но остальное
   проверь живьём, а не пропускай.
=== КОНЕЦ ПРАВИЛ ===
"""


TRIAGE_AGENT_RULES = """
=== ПРАВИЛА ДЛЯ АГЕНТА (обязательны, проверяются машиной) ===
1. Это этап Разбора: здесь ещё нет поставки кода и удалённой ветки-кандидата.
   Не требуй имени ветки, коммита, перебазирования или отправки изменений.
2. Изучай задачу и свежий основной код без изменений файлов. Не создавай
   коммиты и не переключай рабочую копию на другую ветку.
3. Заверши ровно одним честным решением этапа: READY TO SPECIFY,
   NEEDS INFORMATION, WAIT или CLOSE / DUPLICATE. Отсутствующая ветка
   кандидата не является причиной WAIT на Разборе.
4. Если базовые инструкции workflow требуют строки сдачи ветки или коммита,
   на Разборе это требование не применяется: вместо них дай факты, границы,
   проверки и следующий шаг для Спецификации.
5. Пиши для человека. Поставленное человеком называй ПРЕДЛОЖЕНИЕМ,
   обнаруженное исполнителем по ходу работы — НАХОДКОЙ.
=== КОНЕЦ ПРАВИЛ ===
"""


VERIFY_AGENT_OVERRIDE = """
ФИНАЛЬНАЯ ПРОВЕРКА — ТОЛЬКО ЧТЕНИЕ.
Этот этап проверяет ровно тот снимок ветки, который уже прошёл Review. Поэтому
здесь запрещено изменять любые файлы, обновлять карточку знаний, создавать
коммиты, перебазировать или отправлять ветку. Это правило имеет приоритет над
инструкциями workflow и общими пунктами 3 и 6 о сдаче и карточке. Доказательства
Verify оставь только в отчёте; BRANCH и HEAD должны указывать на проверенный
неизменённый снимок. Тесты и сборку запускать можно, но их побочные файлы не
коммить. Иначе Verify сам меняет поставку после Review и создаёт бесконечный круг.
"""


def notification_channel(conf):
    """Return the configured owner notification URL for local workers."""
    server = str((conf or {}).get("ntfy_server") or "").strip().rstrip("/")
    topic = str((conf or {}).get("ntfy_owner_topic") or "").strip().strip("/")
    if not server or not topic:
        return ""
    return server + "/" + urllib.parse.quote(topic, safe="")


def agent_rules(conf=None, stage=""):
    rules = TRIAGE_AGENT_RULES if str(stage).strip() == "Triage" else AGENT_RULES
    if str(stage).strip() == "Verify":
        rules = rules.replace(
            "=== КОНЕЦ ПРАВИЛ ===",
            VERIFY_AGENT_OVERRIDE.strip() + "\n=== КОНЕЦ ПРАВИЛ ===",
        )
    channel = notification_channel(conf)
    if not channel:
        return rules
    return rules.replace(
        "=== КОНЕЦ ПРАВИЛ ===",
        "8. Канал срочных уведомлений владельца: " + channel + "\n"
        "=== КОНЕЦ ПРАВИЛ ===",
    )


def context_with_agent_rules(context, conf=None, stage=""):
    """Replace every managed rules block with the current configured rules."""
    start = "=== ПРАВИЛА ДЛЯ АГЕНТА (обязательны, проверяются машиной) ==="
    end = "=== КОНЕЦ ПРАВИЛ ==="
    managed = re.compile(
        r"\n*" + re.escape(start) + r".*?" + re.escape(end) + r"\n*",
        re.DOTALL,
    )
    ctx = managed.sub("\n\n", str(context or "")).strip()
    rules = agent_rules(conf, stage).strip()
    ctx = ctx[:max(0, 60000 - len(rules) - 2)].rstrip()
    return ((ctx + "\n\n") if ctx else "") + rules


def create_task(body, conf=None):
    active_tasks = (conf or {}).get("_active_work_tasks")
    if (str(body.get("title", "")).startswith(PREFIX)
            and isinstance(active_tasks, list)
            and len(active_auto_works(active_tasks)) >= int(
                (conf or {}).get("max_parallel_works", MAX_PARALLEL_WORKS))):
        raise ParallelWorkLimit("parallel_work_limit: stage deferred")
    if conf and not host_load_admits(
            conf.get("_host_load_tasks"), stage_from_title(body.get("title", "")),
            conf.get("_host_load_snapshot"), conf.get("respect_host_load", True)):
        raise RuntimeError("host_load_admission: stage deferred")
    if conf and str(body.get("title", "")).startswith(PREFIX):
        money_guard(conf, body["title"])
    if str(body.get("title", "")).startswith(PREFIX):
        body["context"] = context_with_agent_rules(
            body.get("context"), conf, stage_from_title(body.get("title", "")))
    """Create a task robustly. Attempt chain:
    1. exact worker + repository (fast path when already advertised);
    2. route + same worker (lets the worker acquire the repo dynamically);
    3. route without a worker pin (any eligible worker takes it - better a
       different model tier than a dead button).
    Every fallback is logged with the control-plane error that caused it."""
    try:
        out = api("/tasks", body)
        _note_admitted_task(conf, out, body)
        return out
    except urllib.error.HTTPError as e:
        msg = _http_err(e)
        if "repository_not_advertised" not in msg:
            raise
        first_err = msg

    rid = body.get("repository_id", "")
    identity = ""
    for r in api("/repositories").get("repositories") or []:
        if r["id"] == rid:
            identity = r.get("remote_identity", "")
    if not identity:
        raise RuntimeError(f"create_task: no remote identity for repo {rid}; original: {first_err}")

    route_body = {k: v for k, v in body.items() if k != "repository_id"}
    route_body["route"] = {"repository_remote_identity": identity,
                           "source_access": {"provider": "github", "hostname": "github.com"}}

    b2 = dict(route_body)
    try:
        out = api("/tasks", b2)
        log(f"task create: acquired {identity} dynamically for pinned worker")
        _note_admitted_task(conf, out, body)
        return out
    except urllib.error.HTTPError as e:
        log(f"task create: route+worker failed ({_http_err(e)}); trying any eligible worker")

    if not (conf or {}).get("allow_any_worker", False):
        # Routing to "any eligible worker" once sent work to broken Codex
        # workers that fail in seconds, which then looped through auto-answer.
        raise RuntimeError(
            "create_task: chosen worker cannot take the repository and "
            "allow_any_worker is off (protects from routing to broken workers)")
    b3 = {k: v for k, v in route_body.items() if k != "worker_id"}
    out = api("/tasks", b3)
    wid = (out.get("task") or {}).get("worker_id", "?")
    log(f"task create: routed to substitute worker {wid} (original tier unavailable)")
    _note_admitted_task(conf, out, body)
    return out


def create_child_task(body, parent, conf=None, correction_kind=None):
    """The only Pilot builder for a continuation or correction task."""
    parent_id = (parent or {}).get("id")
    if not parent_id:
        raise RuntimeError("child task requires a source task id")
    body = dict(body)
    body["parent_task_id"] = parent_id
    if correction_kind:
        body["correction_kind"] = correction_kind
    return create_task(body, conf)


def continuation_request_key(parent_task_id, workflow_revision_id):
    """Stable key makes a concurrent/retried handoff one storage operation."""
    value = f"{parent_task_id}:{workflow_revision_id}".encode("utf-8")
    return "pilot-handoff:" + hashlib.sha256(value).hexdigest()


def _note_admitted_task(conf, response, body):
    """Keep the cycle snapshot honest after a successful create."""
    activity = (conf or {}).get("_cycle_activity")
    if isinstance(activity, dict):
        activity["task_created"] = True
    task = dict((response or {}).get("task") or {})
    task.setdefault("title", body.get("title", ""))
    task.setdefault("state", "created")
    # Reserve an initial stage immediately even when the API response has not
    # populated work_id yet. A child must inherit its parent's identity here;
    # otherwise two completed attempts of one work can both create the same
    # heavy next stage while this cycle is refilling several slots.
    work_id = body.get("work_id") or task.get("work_id")
    parent_id = body.get("parent_task_id")
    if not work_id and parent_id:
        for key in ("_active_work_tasks", "_host_load_tasks"):
            parent = next((candidate for candidate in ((conf or {}).get(key) or [])
                           if candidate.get("id") == parent_id), None)
            if parent:
                work_id = task_work_id(parent)
                break
    task.setdefault("work_id", work_id or task.get("id"))
    for key in ("_active_work_tasks", "_host_load_tasks"):
        tasks = (conf or {}).get(key)
        if (isinstance(tasks, list)
                and not any(existing.get("id") == task.get("id")
                            for existing in tasks)):
            tasks.append(task)


def _work_marker(work_id):
    return f"<!-- factory-work-id:{work_id} -->" if work_id else ""


def _marked_work_id(body):
    """Return a work id only when the immutable marker appears exactly once."""
    markers = re.findall(r"<!--\s*factory-work-id:([^<>\s]+)\s*-->", body or "")
    return markers[0] if len(markers) == 1 else ""


def gh_merge(repo_identity, branch, title, expected_head="", work_id=""):
    """Open (best-effort) and squash-merge the branch into the default branch."""
    repo = repo_identity.split("github.com/")[-1]
    if expected_head:
        current = gh_json(["api", f"repos/{repo}/branches/{branch}"])
        actual = ((current or {}).get("commit") or {}).get("sha", "")
        if actual != expected_head:
            return False, "delivery branch changed after Verify"
    env = dict(os.environ, HOME=HOME)
    subprocess.run(
        ["gh", "pr", "create", "--repo", repo, "--head", branch,
         "--title", title or branch,
         "--body", "Automated by the Factory pipeline after Verify PASS.\n" + _work_marker(work_id)],
        capture_output=True, text=True, env=env, timeout=120)
    if expected_head:
        current = gh_json(["api", f"repos/{repo}/branches/{branch}"])
        actual = ((current or {}).get("commit") or {}).get("sha", "")
        if actual != expected_head:
            return False, "delivery branch changed after Verify"
    merge_args = ["gh", "pr", "merge", branch, "--repo", repo, "--squash",
                  "--delete-branch"]
    if expected_head:
        # Unlike a separate branch lookup, GitHub evaluates this constraint
        # atomically with the merge and closes the final force-push window.
        merge_args.extend(["--match-head-commit", expected_head])
    r = subprocess.run(
        merge_args,
        capture_output=True, text=True, env=env, timeout=180)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def gh_close_pr(repo, number, superseded_by):
    """Close a stale Pilot PR with a durable, human-readable audit comment."""
    env = dict(os.environ, HOME=HOME)
    comment = f"Closed: this work was merged by PR #{superseded_by}."
    result = subprocess.run(
        ["gh", "pr", "close", str(number), "--repo", repo, "--comment", comment],
        capture_output=True, text=True, env=env, timeout=120)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


# ---------------------------------------------------------------- planner ----

def parse_subtasks(result):
    """Extract the plan from an Epic Planning result. Prefer the last fenced
    ```json block; fall back to the last bare {...} object. Returns
    (epic_name, [ {title, detail, complexity}, ... ]) or (None, [])."""
    if not result:
        return None, []
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", result, re.S)
    candidates = list(blocks)
    if not candidates:
        start, end = result.find("{"), result.rfind("}")
        if start != -1 and end > start:
            candidates = [result[start:end + 1]]
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        subs = data.get("subtasks")
        if not isinstance(subs, list) or not subs:
            continue
        clean = []
        for s in subs:
            if isinstance(s, str):
                s = {"title": s}
            if not isinstance(s, dict):
                continue
            title = (s.get("title") or s.get("name") or "").strip()
            if not title:
                continue
            cx = (s.get("complexity") or "medium").lower()
            if cx not in ("low", "medium", "high"):
                cx = "medium"
            clean.append({
                "title": title[:180],
                "detail": (s.get("detail") or s.get("why") or s.get("description") or "").strip(),
                "complexity": cx,
            })
        if clean:
            name = (data.get("epic") or data.get("goal") or data.get("title") or "").strip()
            return (name or None), clean
    return None, []


def write_epic(epic_id, name, goal, repo_id, subtasks, origin=""):
    os.makedirs(EPIC_DIR, exist_ok=True)
    epic = {
        "id": epic_id,
        "name": name or goal[:80] or epic_id,
        "goal": goal,
        "repository_id": repo_id,
        "status": "planned",          # planned -> running -> done
        "subtasks": subtasks,
        "children": [],               # created [auto] task ids, once started
        "created_from_task": epic_id,
        "origin": origin or ORIGIN_ORCHESTRATOR,
    }
    save(f"{EPIC_DIR}/{epic_id}.json", epic)
    return epic


def load_epics():
    out = []
    try:
        for fn in sorted(os.listdir(EPIC_DIR)):
            if fn.endswith(".json"):
                e = load(f"{EPIC_DIR}/{fn}", None)
                if e:
                    out.append(e)
    except FileNotFoundError:
        pass
    return out


def first_stage(conf):
    stages = [s["workflow"] for s in conf["stages"]]
    return (stages[0] if stages else None), len(stages)


WORKS_PATH = f"{HOME}/pilot/works.json"
DUPLICATE_ROOT_EVENTS_PATH = f"{HOME}/pilot/duplicate_root_prevented.json"
WORK_ARCHIVE_DAYS = 90
WORK_TERMINAL_STATES = frozenset(("succeeded", "failed", "cancelled"))

# Кто поставил работу. Владельцу важно отличать своё от чужого.
ORIGIN_OWNER = "owner"              # завёл человек: голосом или кнопкой
ORIGIN_ASSISTANT = "assistant"      # завёл помощник из переписки
ORIGIN_ORCHESTRATOR = "orchestrator"  # развернулось из эпика само
WORK_ORIGINS = frozenset((
    ORIGIN_OWNER, ORIGIN_ASSISTANT, ORIGIN_ORCHESTRATOR,
    "worker", "agent", "patrol",
))


def _duplicate_root_crash_boundary(_name):
    """Test hook for proving that the durable outbox survives every boundary."""


def _duplicate_root_outbox():
    raw = load(DUPLICATE_ROOT_EVENTS_PATH, {}) or {}
    if raw.get("version") == 1 and isinstance(raw.get("events"), dict):
        raw.setdefault("acknowledged", {})
        return raw
    # Upgrade the original task-id marker map without losing its evidence.
    events = {}
    for task_id, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        event_id = "pilot_duplicate_root_prevented:" + task_id
        events[event_id] = {
            "event_id": event_id,
            "event_type": "pilot_duplicate_root_prevented",
            "payload": payload,
        }
    return {"version": 1, "events": events,
            "acknowledged": {event_id: True for event_id in events}}


def note_duplicate_root_prevented(task):
    """Put one complete correction event in the durable idempotent outbox.

    The outbox record, rather than the best-effort stdout mirror, is the
    authoritative observable event.  Acknowledgement never removes it.
    """
    task_id = (task or {}).get("id") or ""
    if not task_id:
        return
    event_id = "pilot_duplicate_root_prevented:" + task_id
    outbox = _duplicate_root_outbox()
    event = outbox["events"].get(event_id)
    if event is None:
        payload = {
            "task_id": task_id,
            "work_id": (task or {}).get("work_id") or "",
            "parent_task_id": (task or {}).get("parent_task_id") or "",
            "correction_kind": (task or {}).get("correction_kind") or "",
        }
        event = {"event_id": event_id,
                 "event_type": "pilot_duplicate_root_prevented",
                 "payload": payload}
        outbox["events"][event_id] = event
        _duplicate_root_crash_boundary("before_journal_append")
        save(DUPLICATE_ROOT_EVENTS_PATH, outbox)
        _duplicate_root_crash_boundary("after_journal_append")
    if event_id in outbox["acknowledged"]:
        return
    _duplicate_root_crash_boundary("before_acknowledgement")
    # Claim delivery durably before the optional stdout mirror.  Even if the
    # process dies next, the complete event remains queryable in the outbox.
    outbox["acknowledged"][event_id] = True
    save(DUPLICATE_ROOT_EVENTS_PATH, outbox)
    _duplicate_root_crash_boundary("after_acknowledgement")
    log(event["event_type"], json.dumps(
        dict(event["payload"], event_id=event_id),
        ensure_ascii=False, sort_keys=True))


def note_work(base, origin, start_stage="", skipped=None, reason="", work_id=""):
    """Запись о происхождении работы. Пишется один раз, при заведении:
    повторные стадии её не трогают."""
    try:
        rec = load(WORKS_PATH, {})
        key = work_id or base
        if key in rec:
            return
        rec[key] = {
            "origin": origin,
            "base_title": base,
            "start_stage": start_stage or "",
            "skipped": list(skipped or []),
            "reason": reason or "",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        save(WORKS_PATH, rec)
    except Exception as e:
        log("note_work_error", repr(e))


def _archive_dates(now=None):
    now = time.time() if now is None else now
    return (
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        time.strftime("%Y-%m-%dT%H:%M:%SZ",
                      time.gmtime(now + WORK_ARCHIVE_DAYS * 86400)),
    )


def _same_work(left, right):
    return base_title(str(left or "")).strip().casefold() == base_title(
        str(right or "")
    ).strip().casefold()


def close_work(base, reason):
    """Persist an explicit terminal boundary without disguising it as a pause."""
    closed_at, retention_until = _archive_dates()
    works = load(WORKS_PATH, {}) or {}
    meta = works.setdefault(base, {
        "origin": ORIGIN_OWNER, "start_stage": "", "skipped": [],
        "reason": "", "at": closed_at,
    })
    if not meta.get("closed"):
        meta.update({"closed": closed_at, "closed_reason": reason,
                     "retention_until": retention_until})
        save(WORKS_PATH, works)
    statuses = load(f"{HOME}/pilot/work_status.json", {}) or {}
    statuses[base] = {"state": "archived", "text": reason,
                      "retention_until": meta.get("retention_until", retention_until)}
    save(f"{HOME}/pilot/work_status.json", statuses)


TRIAGE_CLOSE_RE = re.compile(
    r"^\s*(?:\*\*)?(?:VERDICT\s*:\s*)?"
    r"(?:CLOSE\s*/\s*DUPLICATE|CLOSE|DUPLICATE)\b",
    re.I,
)


def close_triage_without_work(task, result):
    """Finish an honest Triage close instead of inventing a next stage."""
    first_line = next(
        (line.strip() for line in str(result or "").splitlines() if line.strip()),
        "",
    )
    if not TRIAGE_CLOSE_RE.match(first_line):
        return False
    base = base_title((task or {}).get("title", ""))
    reason = "Разбор закрыл работу: она уже выполнена или дублирует существующую."
    close_work(base, reason)
    task_id = (task or {}).get("id") or ""
    for idea in ideas_all():
        if (idea.get("state") in ("planned", "in_work")
                and idea.get("task_id") == task_id):
            set_idea(idea["id"], state="done", reason=reason)
    log(f"TRIAGE CLOSED base={base!r} task={task_id}: {first_line[:120]}")
    return True


def reopen_work(base, generation, reason="Владелец явно запустил новое поколение работы."):
    """Open a new generation while retaining the previous close receipt."""
    works = load(WORKS_PATH, {}) or {}
    meta = works.get(base)
    if meta:
        if meta.get("closed"):
            history = list(meta.get("closed_generations") or [])
            history.append({key: meta[key] for key in (
                "closed", "closed_reason", "retention_until"
            ) if meta.get(key)})
            meta["closed_generations"] = history
        for key in ("closed", "closed_reason", "retention_until",
                    "implementation_artifact", "delivery_artifact"):
            meta.pop(key, None)
        meta.update({"run_generation": generation, "reopened_reason": reason})
        save(WORKS_PATH, works)
    statuses = load(f"{HOME}/pilot/work_status.json", {}) or {}
    if (statuses.get(base) or {}).get("state") == "archived":
        statuses.pop(base, None)
        save(f"{HOME}/pilot/work_status.json", statuses)
    conf = load(CONF_PATH, None)
    if isinstance(conf, dict):
        stopped = list(conf.get("stopped_pipelines") or [])
        kept = [name for name in stopped if not _same_work(name, base)]
        if kept != stopped:
            conf["stopped_pipelines"] = kept
            save(CONF_PATH, conf)


def work_lifecycle_block(base, task=None, tasks=None):
    """Return the durable reason why an old task may not create more work.

    An active Plan card is a generation boundary: while it is merely planned,
    none of the old tasks belongs to the new run; once linked, only that task
    and tasks created after it do.  Terminal Plan cards and archive receipts
    close the preceding generation across Pilot restarts.
    """
    matching = [idea for idea in ideas_all() if _same_work(idea.get("title"), base)]
    active = [idea for idea in matching if idea.get("state") in ("planned", "in_work")]
    if active:
        current = active[-1]
        linked_id = current.get("task_id") or ""
        if not linked_id:
            return "новое поколение запланировано, но ещё не начато"
        if task and task.get("id") == linked_id:
            return ""
        # Every continuation created by the control plane carries the durable
        # root work identity.  The linked Plan root can legitimately fall
        # outside the API's current 100-task page; its descendants still
        # belong to this exact generation and must not be mistaken for an old
        # run merely because the boundary row is not in the snapshot.
        if task and task.get("work_id") == linked_id:
            return ""
        linked = next((item for item in (tasks or []) if item.get("id") == linked_id), None)
        boundary = (linked or {}).get("created_at") or ""
        if task and boundary and (task.get("created_at") or "") >= boundary:
            return ""
        return "задача относится к поколению до явного повторного запуска"
    terminal = [idea for idea in matching if idea.get("state") in ("done", "rejected")]
    if terminal:
        rec = terminal[-1]
        return (rec.get("reason") or
                ("карточка Плана завершена" if rec.get("state") == "done"
                 else "карточка Плана отклонена"))

    works = load(WORKS_PATH, {}) or {}
    meta = next((value for name, value in works.items() if _same_work(name, base)), {})
    if task and any(item.get("task_id") == task.get("id")
                    for item in meta.get("archived_attempts", [])):
        return "эту попытку заменила более новая попытка работы"
    if meta.get("closed"):
        return meta.get("closed_reason") or "работа закрыта и сохранена в истории"

    if task:
        number = stage_no_of(task.get("title"))
        created = task.get("created_at") or ""
        newer = [item for item in (tasks or [])
                 if item.get("id") != task.get("id")
                 and _same_work(item.get("title"), base)
                 and (item.get("created_at") or "") > created
                 and stage_no_of(item.get("title")) <= number]
        if number and created and newer:
            return "эту попытку заменила более новая попытка работы"
    return ""


def _technical_cancel(task):
    """Recognise only known cancelled service runs, not every Automation."""
    if task.get("state") != "cancelled":
        return False
    title = base_title(str(task.get("title") or "")).strip().casefold()
    marker = " ".join((str(task.get("request_key") or ""), title)).casefold()
    if re.search(r"(^|[^a-z])(helper|debug)([^a-z]|$)", marker):
        return True
    # Schedule request keys contain only an opaque Automation id and therefore
    # cannot distinguish the Factory patrol from a product Automation.  The
    # schedule runtime does preserve its title before ``: scheduled/run now``.
    return bool(re.match(
        r"^(?:патруль(?:\s+factory)?|factory(?:\s+pipeline)?\s+patrol|"
        r"patrol(?:\s+factory)?)(?=$|\s*:)",
        title,
    ))


def _work_stage(task):
    match = STAGE_TITLE_RE.match(str(task.get("title") or ""))
    return match.group(1).strip() if match else ""


def _work_time(value):
    """Parse API RFC3339 or the merge journal's legacy local timestamp as UTC."""
    value = str(value or "").strip()
    if not value:
        return None
    try:
        if "T" in value:
            parsed = datetime.datetime.fromisoformat(
                value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
            )
            if parsed.tzinfo is None:
                return None
            return parsed.astimezone(datetime.timezone.utc)
        # Old merge receipts were written without an offset in the server's
        # time.Local.  mktime applies that location (including historical DST)
        # before fromtimestamp returns an explicitly timezone-aware UTC value.
        local_epoch = time.mktime(time.strptime(value, "%Y-%m-%d %H:%M:%S"))
        return datetime.datetime.fromtimestamp(local_epoch, datetime.timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def _merged_work():
    merged_at = {}
    try:
        with open(MERGES_PATH, encoding="utf-8") as merges:
            for line in merges:
                try:
                    rec = json.loads(line)
                except (TypeError, ValueError):
                    continue
                base = str(rec.get("base") or "").strip()
                at = _work_time(rec.get("at"))
                if base and at and at > merged_at.get(base, datetime.datetime.min.replace(
                        tzinfo=datetime.timezone.utc)):
                    merged_at[base] = at
    except OSError:
        pass
    return merged_at


def cleanup_work_archive(conf, tasks):
    """Close server-known service/finished work without deleting task history.

    ``works.json`` is the durable archive receipt consumed by the Work screen;
    ``work_status.json`` carries the same human reason.  Existing receipts are
    never refreshed, so retries cannot silently extend retention.
    """
    works = load(WORKS_PATH, {}) or {}
    statuses = load(f"{HOME}/pilot/work_status.json", {}) or {}
    questions = load_questions()
    open_question_tasks = {q.get("task_id") for q in questions
                           if q.get("status") == "open"}
    stopped = set(conf.get("stopped_pipelines") or [])
    merged = _merged_work()
    grouped = {}
    for task in tasks or []:
        base = base_title(task.get("title", ""))
        if base:
            grouped.setdefault(task_work_id(task), {"base": base, "tasks": []})[
                "tasks"].append(task)

    closed_at, retention_until = _archive_dates()
    works_changed = False
    statuses_changed = False
    for work_key, grouped_work in grouped.items():
        base, group = grouped_work["base"], grouped_work["tasks"]
        group.sort(key=lambda task: (
            _work_time(task.get("created_at"))
            or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
            task.get("id") or "",
        ))
        new_meta = work_key not in works
        inferred_origin = (ORIGIN_ORCHESTRATOR
                           if str(group[0].get("request_key") or "").startswith("automation:")
                           else ORIGIN_OWNER)
        meta = works.setdefault(work_key, {
            "origin": inferred_origin, "start_stage": "", "skipped": [],
            "reason": "", "base_title": base,
            "at": group[0].get("created_at") or closed_at,
        })
        if new_meta:
            works_changed = True

        # Every terminal row replaced by a later row remains addressable in
        # task history, but is no longer an unfinished attempt of the work.
        archived_ids = {item.get("task_id") for item in meta.get("archived_attempts", [])}
        attempts = list(meta.get("archived_attempts", []))
        for index, task in enumerate(group):
            task_id = task.get("id")
            technical = _technical_cancel(task)
            replaced = (index < len(group) - 1
                        and task.get("state") in WORK_TERMINAL_STATES)
            if not task_id or task_id in archived_ids or not (technical or replaced):
                continue
            attempt_reason = (
                "Отменённая служебная попытка helper/debug/patrol сохранена в истории."
                if technical else
                "Попытку заменила более новая попытка этой работы."
            )
            attempts.append({
                "task_id": task_id,
                "closed": closed_at,
                "closed_reason": attempt_reason,
                "retention_until": retention_until,
            })
            archived_ids.add(task_id)
            works_changed = True
        if attempts:
            meta["archived_attempts"] = attempts

        if meta.get("closed"):
            continue
        live = any(task.get("state") in PIPELINE_LIVE_STATES for task in group)
        open_question = any(task.get("id") in open_question_tasks for task in group)
        status_state = (statuses.get(base) or {}).get("state")
        protected = live or open_question or base in stopped or status_state == "stopped_owner"
        # A genuine dead end stays visible.  A newer live generation already
        # wins above and clears stale stuck state through pipeline_watch.
        if status_state == "stuck" and not live:
            protected = True
        if protected:
            continue

        reason = ""
        if group and all(_technical_cancel(task) for task in group):
            reason = "Отменённая служебная попытка helper/debug/patrol сохранена в истории."
        latest_created = _work_time(group[-1].get("created_at"))
        if (base in merged and latest_created
                and all(task.get("state") in WORK_TERMINAL_STATES for task in group)
                and merged[base] >= latest_created):
            reason = "Работа уже влита; её терминальные стадии сохранены в истории."
        else:
            stages = {_work_stage(task) for task in group}
            stages.discard("")
            manual_check = (
                meta.get("origin") in (
                    ORIGIN_OWNER, ORIGIN_ASSISTANT, ORIGIN_ORCHESTRATOR
                )
                and meta.get("start_stage") in ("Review", "Verify")
                and bool(meta.get("skipped"))
                and meta.get("start_stage") not in meta.get("skipped", [])
                and stages
                and stages.issubset({"Review", "Verify"})
                and all(task.get("state") in WORK_TERMINAL_STATES for task in group)
            )
            if manual_check:
                reason = "Независимая ручная проверка завершена и сохранена в истории."
        if not reason:
            continue

        meta.update({"closed": closed_at, "closed_reason": reason,
                     "retention_until": retention_until})
        statuses[base] = {"state": "archived", "text": reason,
                          "retention_until": retention_until}
        for idea in ideas_all():
            if (_same_work(idea.get("title"), base)
                    and idea.get("state") in ("new", "planned", "in_work")):
                set_idea(idea["id"], state="done", reason=reason)
        works_changed = True
        statuses_changed = True
        log(f"WORK ARCHIVE base={base!r}: {reason}")

    if works_changed:
        save(WORKS_PATH, works)
    if statuses_changed:
        save(f"{HOME}/pilot/work_status.json", statuses)


def launch_subtask(conf, epic, index, workflows, workers):
    """Send ONE subtask into the pipeline at its first stage.
    Мелкие подзадачи (complexity=low) начинают сразу с разработки: гонять пять
    полноценных агентов ради однострочной правки — чистая трата токенов."""
    stages_all = [s["workflow"] for s in conf["stages"]]
    nstages = len(stages_all)
    sub = epic["subtasks"][index]
    cx = sub.get("complexity", "medium")
    skip = conf.get("skip_stages_for_low") or []
    start = 0
    if cx == "low":
        while start < nstages - 1 and stages_all[start] in skip:
            start += 1
    stage_name = stages_all[start] if stages_all else None
    nw = workflows.get(stage_name)
    if not stage_name or not nw or not nw.get("enabled"):
        return None, f"first stage '{stage_name}' has no enabled workflow"
    worker = workers.get(stage_worker(
        conf, stage_name, cx, workers,
        repository_id=epic.get("repository_id")))
    if not worker:
        return None, f"нет свободного воркера для стадии {stage_name}"
    done_before = [s["title"] for s in epic["subtasks"][:index]]
    prior = ("\n".join(f"- {t}" for t in done_before)) or "(это первая подзадача)"
    title = f"[auto] [{start + 1}/{nstages} {stage_name}] {sub['title']}"[:200]
    skipped_note = ("" if start == 0 else
                    f"Стадии {', '.join(stages_all[:start])} пропущены: задача мелкая. "
                    "Работай сразу по описанию ниже.\n")
    # Подзадача наследует происхождение эпика: если эпик завёл помощник,
    # владельцу важно видеть именно это, а не безликое «развернулось само».
    note_work(sub["title"], epic.get("origin") or ORIGIN_ORCHESTRATOR,
              stage_name, stages_all[:start],
              "задача мелкая — разбор и спецификация не окупаются"
              if start else "")
    context = (
        f"Epic: {epic['name']} (id {epic['id']})\n"
        f"Overall goal: {epic['goal']}\n\n"
        f"Подзадача {index + 1} из {len(epic['subtasks'])}: {sub['title']}\n"
        f"{sub.get('detail','')}\n\n"
        f"УЖЕ ВЫПОЛНЕНО в этом эпике (опирайся на результат, не повторяй):\n{prior}\n\n"
        f"{skipped_note}"
        "You are the first pipeline stage. Treat this subtask as the unit of work; "
        "later stages continue on the branch you (or Implement) push."
    )[:60000]
    body = {
        "request_key": str(uuid.uuid4()),
        "title": title,
        "context": context,
        "worker_id": worker["id"],
        "repository_id": epic.get("repository_id", ""),
        "timeout_seconds": conf.get("timeout_seconds", 7200),
        "workflow_revision_id": nw["revision_id"],
    }
    try:
        r = create_task(body, conf)
        tid = r.get("task", {}).get("id")
        sub["status"] = "running"
        sub["task_id"] = tid
        sub["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(f"{EPIC_DIR}/{epic['id']}.json", epic)
        log(f"epic '{epic['name']}' -> подзадача {index+1}/{len(epic['subtasks'])}: {sub['title']} ({tid})")
        return tid, ""
    except Exception as e:
        return None, f"{e}"


def start_epic(conf, epic, workflows, workers):
    """Start the epic: subtasks run STRICTLY ONE AFTER ANOTHER, because a later
    one normally depends on the result of an earlier one."""
    for sub in epic["subtasks"]:
        sub.setdefault("status", "pending")
    tid, err = launch_subtask(conf, epic, 0, workflows, workers)
    if not tid:
        return False, f"не удалось запустить первую подзадачу: {err}"
    epic["status"] = "running"
    epic["children"] = [{"task_id": tid, "title": epic["subtasks"][0]["title"],
                         "complexity": epic["subtasks"][0].get("complexity", "medium")}]
    save(f"{EPIC_DIR}/{epic['id']}.json", epic)
    return True, (f"запущена подзадача 1 из {len(epic['subtasks'])}; "
                  "остальные пойдут по очереди, каждая после предыдущей")


def _unused_parallel_start(conf, epic, workflows, workers):
    stage_name, nstages = first_stage(conf)
    nw = workflows.get(stage_name)
    created = []
    for i, sub in enumerate(epic["subtasks"], 1):
        cx = sub.get("complexity", "medium")
        worker_name = stage_worker(conf, stage_name, cx)
        worker = workers.get(worker_name)
        if not worker:
            log(f"epic-start: no worker for '{stage_name}' cx={cx}; skipping subtask '{sub['title']}'")
            continue
        title = f"[auto] [1/{nstages} {stage_name}] {sub['title']}"[:200]
        context = (
            f"Epic: {epic['name']} (id {epic['id']})\n"
            f"Overall goal: {epic['goal']}\n\n"
            f"This subtask: {sub['title']}\n"
            f"{sub.get('detail','')}\n\n"
            "You are the first pipeline stage. Treat this subtask as the unit of work; "
            "later stages continue on the branch you (or Implement) push."
        )[:60000]
        body = {
            "request_key": str(uuid.uuid4()),
            "title": title,
            "context": context,
            "worker_id": worker["id"],
            "repository_id": epic.get("repository_id", ""),
            "timeout_seconds": conf.get("timeout_seconds", 7200),
            "workflow_revision_id": nw["revision_id"],
        }
        try:
            r = create_task(body, conf)
            tid = r.get("task", {}).get("id")
            created.append({"task_id": tid, "title": sub["title"], "complexity": cx})
            log(f"epic-start '{epic['name']}' -> child {tid} :: {sub['title']}")
        except Exception as e:
            log(f"epic-start create failed for '{sub['title']}': {e!r}")
    epic["children"] = created
    epic["status"] = "running" if created else "planned"
    save(f"{EPIC_DIR}/{epic['id']}.json", epic)
    return bool(created), f"created {len(created)}/{len(epic['subtasks'])} tasks"


def explain_failure(conf, stage, base, raw):
    """Turn a raw stage failure into plain Russian for the owner."""
    prompt = (
        "Ты объясняешь владельцу-непрограммисту, почему остановился этап "
        f"'{stage}' задачи '{base}'. Вот сырой вывод/ошибка:\n---\n{(raw or '')[:12000]}\n---\n\n"
        "Ответь ТОЛЬКО JSON без прозы: {\"situation_ru\": \"<2-3 коротких предложения "
        "по-русски: что произошло, простыми словами, без жаргона и английских терминов>\", "
        "\"question_ru\": \"<один конкретный вопрос по-русски, на который владелец может "
        "ответить одной фразой голосом, чтобы работа продолжилась>\", "
        "\"options_ru\": [\"<2-4 коротких вероятных варианта ответа по-русски>\"]}"
    )
    try:
        text, _eng = brain(conf, prompt, timeout=180)
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    except Exception as e:
        log("explain_error", repr(e))
        return {"situation_ru": "Этап не завершился, автоматический разбор не удался.",
                "question_ru": "Посмотри задачу и скажи, что делать дальше.", "options_ru": []}


# ------------------------------------------------------------------- Мозг ---
# Решения оркестратора не должны зависеть от одной подписки. Цепочка движков:
# берём первый, чей провайдер сейчас не заблокирован и который ответил.

BRAIN_STATE = f"{HOME}/pilot/brain_state.json"
BRAIN_DOWN = f"{HOME}/pilot/brain_down.json"


def engine_down(model):
    """Модель отдыхает после собственного лимита? Час — и пробуем снова."""
    try:
        return float((load(BRAIN_DOWN, {}) or {}).get(model or "", 0)) > time.time()
    except Exception:
        return False


def note_engine_down(model, hours=1):
    try:
        d = load(BRAIN_DOWN, {}) or {}
        d[model or ""] = time.time() + hours * 3600
        save(BRAIN_DOWN, d)
        log(f"BRAIN ENGINE DOWN {model}: своя квота исчерпана, отдыхает {hours} ч")
    except Exception as e:
        log("brain_down_error", repr(e))

BRAIN_DEFAULT = [
    {"cli": "claude", "model": "fable", "provider": "claude"},
    {"cli": "codex", "model": "gpt-5.6-sol", "provider": "codex"},
    {"cli": "claude", "model": "opus", "provider": "claude"},
    {"cli": "codex", "model": "gpt-5.6-terra", "provider": "codex"},
]


def brain_chain(conf):
    return (conf or {}).get("brain_chain") or BRAIN_DEFAULT


def brain(conf, prompt, timeout=180):
    """Спросить мозг. Возвращает (текст, движок) или ("", None)."""
    limits = load_limits()
    chain = brain_chain(conf)
    problems = []
    for i, eng in enumerate(chain):
        if limit_active(eng.get("provider", ""), limits):
            problems.append(f"{eng.get('model')}: провайдер заблокирован")
            continue
        if engine_down(eng.get("model")):
            problems.append(f"{eng.get('model')}: своя квота исчерпана")
            continue
        try:
            if eng.get("cli") == "codex":
                env = dict(os.environ, HOME=HOME)
                p = subprocess.run(
                    ["codex", "exec", "-m", eng["model"], "--skip-git-repo-check", "-"],
                    input=prompt, capture_output=True, text=True,
                    timeout=timeout, env=env, cwd=HOME)
            else:
                env = dict(os.environ, HOME=HOME, ANTHROPIC_MODEL=eng["model"])
                p = subprocess.run(
                    ["claude", "-p", prompt, "--output-format", "text"],
                    capture_output=True, text=True, timeout=timeout, env=env, cwd=HOME)
            out = (p.stdout or "").strip()
            both = (p.stdout or "") + (p.stderr or "")
            # «Твой лимит исчерпан» — это не ответ, а отказ. Короткий текст с
            # признаками лимита разбирать нельзя: откладываем эту модель.
            if out and len(out) < 400 and LIMIT_SIGNS.search(out):
                note_engine_down(eng.get("model"))
                problems.append(f"{eng.get('model')}: своя квота исчерпана")
                continue
            if out:
                # Успешный ответ — доказательство, что лимита нет: снимаем
                # застрявший блок с этого провайдера сами.
                try:
                    lm = load_limits()
                    if (lm.get(eng.get("provider")) or {}).get("state") in ("exhausted", "throttled"):
                        clear_limit(eng["provider"])
                        log("LIMIT CLEARED by success: " + str(eng.get("provider")))
                except Exception:
                    pass
                if i:
                    log(f"BRAIN FALLBACK: отвечает {eng['cli']}/{eng['model']} "
                        f"(первые {i} не смогли)")
                try:
                    save(BRAIN_STATE, {
                        "cli": eng.get("cli", ""), "model": eng.get("model", ""),
                        "provider": eng.get("provider", ""), "note": eng.get("note", ""),
                        "fallback": bool(i), "skipped": problems[-3:],
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    })
                except Exception:
                    pass
                return out, eng
            if LIMIT_SIGNS.search(both):
                note_limit(conf, eng.get("provider", ""), both[:200])
                limits = load_limits()
                problems.append(f"{eng.get('model')}: упёрлись в лимит")
            else:
                problems.append(f"{eng.get('model')}: пустой ответ")
        except Exception as e:
            problems.append(f"{eng.get('model')}: {e!r}")
    log("BRAIN ALL FAILED", "; ".join(problems)[:400])
    return "", None


def project_context():
    try:
        with open(CONTEXT_PATH) as f:
            return f.read()[:12000]
    except Exception:
        return ""


# ------------------------------------------------------- Чей это проект ----
# Общий контекст описывает торговый проект. Если не назвать репозиторий
# задачи явно, мозг переносит его адреса и команды на любую другую работу.

REPO_IDENTITY = {}

PROJECT_BRIEFS = {
    "timafen/factory": (
        "ПРОЕКТ ЗАДАЧИ: сама Фабрика, репозиторий github.com/timafen/factory "
        "(форк owainlewis/factory, рабочая ветка main).\n"
        "Это панель управления фабрикой: сервер на Go плюс интерфейс на React. "
        "Живёт по адресу https://factory.timafen.com, служба factory-server. "
        "Сборка: `npx vite build` в web/, затем `go build ./cmd/factory-server` "
        "(интерфейс вшивается в бинарь через go:embed), затем перезапуск службы.\n"
        "Проверка типов — ТОЛЬКО `npx tsc -p tsconfig.app.json --noEmit` в web/: "
        "голый `npx tsc --noEmit` там ничего не проверяет и всегда молчит.\n"
        "ПЕРВЫМ ДЕЛОМ, ДО ЛЮБОЙ ПРАВКИ: `git fetch origin` и отрежь свою ветку "
        "от свежего `origin/main`. Если ветка уже была создана раньше — перенеси "
        "на свежий main только СВОИ файлы, остальное не тащи. Пока это не сделано, "
        "разница с main покажет десятки чужих файлов, ревью честно откажет, и круг "
        "повторится. Это не придирка ревью — это признак того, что ветка устарела.\n"
        "Перед сдачей проверь сам: `git diff --name-only origin/main` должен "
        "показывать ТОЛЬКО файлы твоей задачи. Если файлов больше — ты ещё не готов.\n"
        "ВЫКАТ ФАБРИКИ ДЕЛАЕТСЯ САМОЙ ФАБРИКОЙ, руками владельца или помощника — НЕТ.\n"
        "Команда: `sudo -n /usr/local/bin/fx factory release` — она сама берёт "
        "main с GitHub, проверяет типы, собирает интерфейс и сервер, "
        "ставит и перезапускает службу, проверяет здоровье и при неудаче "
        "возвращает предыдущую версию. Откат вручную: `fx factory rollback`. "
        "Что сейчас выкачено: `fx factory release-info`. Состояние и логи: "
        "`fx factory status`, `fx factory logs`. Релиз не поедет, если "
        "`npx tsc -p tsconfig.app.json --noEmit` не прошёл — это не помеха, а защита.\n"
        "ВАЖНО: изменение должно быть в ветке main на GitHub, иначе "
        "выкатывать нечего — правка в рабочей копии на сервере релизом не считается.\n"
        "У этого проекта НЕТ отдельного стенда и НЕТ продакшна — это внутренний "
        "инструмент в одном экземпляре, выкат сразу боевой. Адреса ops.tarser.net, "
        "staging-automation.tarser.net, automation.tarser.net, механизм deploy-release "
        "и команды `fx staging ...` / `fx prod ...` к нему НЕ ОТНОСЯТСЯ (у Фабрики "
        "своя команда `fx factory ...`): это "
        "другой проект. Проверять сделанное здесь — глазами на "
        "https://factory.timafen.com."
    ),
    "timafen/tarser-operations": (
        "ПРОЕКТ ЗАДАЧИ: торговая система, репозиторий "
        "github.com/timafen/tarser-operations.\n"
        "Стенд — https://staging-automation.tarser.net, продакшн — "
        "https://automation.tarser.net. Старые имена staging.ops.tarser.net "
        "и ops.tarser.net ещё отвечают, но в отчётах и ссылках используй "
        "только новые. "
        "Выкат только штатным deploy-release, служебные операции — через "
        "`fx staging ...` и `fx prod ...`. Разработка ведётся на стенде; "
        "продакшн трогается только по прямому подтверждению владельца."
    ),
}


def _identity_of(repo_key):
    """По id репозитория — его адрес на GitHub. Кэш заполняется по требованию,
    поэтому функция одинаково работает и в пилоте, и в приёмнике."""
    key = (repo_key or "").strip()
    if not key or "/" in key:
        return key
    if key not in REPO_IDENTITY:
        try:
            for r in api("/repositories").get("repositories") or []:
                REPO_IDENTITY[r["id"]] = r.get("remote_identity", "")
        except Exception:
            pass
    return REPO_IDENTITY.get(key, "")


def repo_brief(repo_key):
    """Короткая справка о проекте задачи — и о том, что к нему не относится."""
    ident = _identity_of(repo_key)
    for key, text in PROJECT_BRIEFS.items():
        if key in ident:
            return text
    if ident:
        return ("ПРОЕКТ ЗАДАЧИ: репозиторий " + ident + ". Отдельной справки о нём "
                "нет — не переноси на него адреса, стенды и команды других "
                "проектов из общего контекста.")
    return ("Репозиторий задачи неизвестен. Не называй конкретных адресов стендов "
            "и команд выката: их легко перепутать с другим проектом. Если знание "
            "проекта необходимо для ответа — это повод спросить владельца.")


def orchestrator_answer(conf, stage, base, situation, question, prior_result,
                        repo_id="", action_result=""):
    """The orchestrator has the project context - it answers technical questions
    itself and escalates to the owner only when the decision is genuinely his."""
    if not conf.get("auto_answer", True):
        return {"decision": "escalate", "answer": "", "reason": "auto_answer disabled"}
    prompt = (
        "Ты — оркестратор фабрики разработки, технический директор владельца.\n\n"
        "КОНТЕКСТ ПРОЕКТА:\n" + project_context() + "\n\n"
        + repo_brief(repo_id) + "\n\n"
        f"Этап '{stage}' задачи '{base}' остановился.\n"
        f"Ситуация: {situation}\n"
        f"Вопрос агента: {question}\n\n"
        f"Вывод этапа (сокращённо):\n{(prior_result or '')[:8000]}\n\n"
        "Реши: можешь ли ты ответить сам, опираясь на контекст и инженерное "
        "суждение, или это решение действительно владельца.\n"
        "Владельцу эскалируем ТОЛЬКО если: выбор продуктовой функциональности или "
        "приоритета; трата денег; необратимое/разрушительное действие (удаление "
        "данных, деплой в production, ротация ключей); нужны доступы/секреты, "
        "которых нет на сервере; принципиальный выбор архитектуры с долгими "
        "последствиями.\n"
        "Всё остальное (какую среду использовать, как чинить, перезапускать ли "
        "упавший по таймауту этап, где взять сведения о коде) — решай САМ.\n\n"
        "Если для ответа нужна безопасная техническая проверка на staging, можешь "
        "выбрать admin_action. Это ТОЛЬКО scope staging и один из verb status, "
        "health, restart, manage, sandbox, env-names, release-info. "
        "Для manage нельзя выбирать migrate; collectstatic допустим. Для sandbox "
        "допустим только --dry-run, без создания или перезаписи данных и без --force. "
        "Никогда не выбирай admin_action для prod, factory, release, rollback, "
        "секретов, трат, удаления или неизвестных аргументов.\n\n"
        + ("Уже выполненная admin-операция дала результат:\n" + action_result[:2000]
           + "\nТеперь верни только answer, wait или escalate; новую admin_action "
             "выбирать нельзя.\n\n" if action_result else "")
        + "Если правильное решение — ждать выполнения условия и пока НЕ запускать "
        "следующий этап, выбери отдельное решение wait. Не маскируй паузу текстом "
        "обычного answer.\n\n"
        'Ответь ТОЛЬКО JSON: {"decision": "answer", "wait", "escalate"'
        + (' или "admin_action"' if not action_result else '')
        + ', "action": {"scope":"staging", "verb":"health", "args":[]}, '
        '"answer": "<если answer: конкретный исполнимый ответ агенту по-русски, '
        '2-5 предложений, как будто это сказал владелец>", '
        '"reason": "<если wait: почему работу надо оставить на паузе; если '
        'escalate: одной фразой почему это решение владельца>"}'
    )
    try:
        text, _eng = brain(conf, prompt, timeout=240)
        v = json.loads(text[text.find("{"):text.rfind("}") + 1])
        if v.get("decision") == "answer" and (v.get("answer") or "").strip():
            return v
        if v.get("decision") == "wait" and (v.get("reason") or "").strip():
            return v
        if not action_result and v.get("decision") == "admin_action" and isinstance(v.get("action"), dict):
            return v
        return {"decision": "escalate", "answer": "",
                "reason": v.get("reason", "оркестратор передал решение владельцу")}
    except Exception as e:
        log("orchestrator_answer_error", repr(e))
        return {"decision": "escalate", "answer": "", "reason": f"сбой авто-ответа: {e}"}


def archived_attempt_ids(reference):
    """Task IDs archived for this exact work generation."""
    works = load(WORKS_PATH, {}) or {}
    if not isinstance(works, dict):
        return set()

    metas = []
    if isinstance(reference, dict) and reference.get("work_id"):
        meta = works.get(reference["work_id"])
        if isinstance(meta, dict):
            metas.append(meta)
    else:
        title = (base_title(reference.get("title") or "")
                 if isinstance(reference, dict) else str(reference or ""))
        metas.extend(
            meta for name, meta in works.items()
            if isinstance(meta, dict)
            and _same_work(meta.get("base_title") or name, title)
        )

    archived_ids = set()
    for meta in metas:
        attempts = meta.get("archived_attempts") or []
        if not isinstance(attempts, list):
            continue
        archived_ids.update(
            item.get("task_id") for item in attempts
            if isinstance(item, dict) and item.get("task_id")
        )
    return archived_ids


def admin_fx_argv(action):
    """Return the only argv an orchestrator admin intention may execute."""
    if not isinstance(action, dict) or action.get("scope") != "staging":
        return None, "разрешены только действия staging"
    verb = action.get("verb")
    args = action.get("args", [])
    if not isinstance(verb, str) or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return None, "неверный формат административного действия"
    simple = {"status", "health", "env-names", "release-info"}
    if verb in simple and not args:
        pass
    elif verb == "restart" and args in ([], ["gunicorn"], ["worker"], ["notifications"], ["order-reconcile"], ["all"]):
        pass
    elif verb == "manage" and args in (["check"], ["showmigrations"], ["collectstatic"]):
        pass
    elif (verb == "sandbox" and args
          and args[0] in ("bootstrap-accounts", "seller-policies", "listings")
          and "--dry-run" in args[1:]
          and all(re.fullmatch(
              r"--(?:tenant-id|account-id|fulfillment-policy-id|payment-policy-id|return-policy-id|listing-count)=[A-Za-z0-9_.-]+|--dry-run|--interactive-bootstrap|--role=seller|--consent-status=[A-Za-z0-9_.-]+",
              arg) for arg in args[1:])):
        pass
    else:
        return None, "операция или аргументы не входят в безопасный список fx"
    return ["sudo", "-n", "/usr/local/bin/fx", "staging", verb, *args], ""


def stage_attempts(tasks, stage, base):
    """How many times this exact work already went through this exact stage."""
    archived_ids = archived_attempt_ids(base)
    n = 0
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if (m and m.group(1).strip() == stage
                and same_task_work(t, base)
                and t.get("id") not in archived_ids):
            n += 1
    return n


def stage_no_of(title):
    """Номер стадии из заголовка '[auto] [3/5 Implement + Test] ...' -> 3."""
    m = re.match(r"^\[auto\]\s*\[(\d+)/", title or "")
    return int(m.group(1)) if m else 0


def prioritize_terminal_handoffs(tasks, processed, recovery_ids=()):
    """Put unfinished late-stage handoffs ahead of early-stage backlog."""
    processed = set(processed or ())
    recovery_ids = set(recovery_ids or ())
    urgent = []
    rest = []
    for task in tasks or []:
        task_id = task.get("id")
        pending = task_id not in processed or task_id in recovery_ids
        if pending and task.get("state") in ("succeeded", "failed", "cancelled"):
            urgent.append(task)
        else:
            rest.append(task)
    # Python's sort is stable: the existing terminal cursor still provides
    # fairness between tasks on the same stage while later stages move ahead.
    urgent.sort(
        key=lambda task: stage_no_of(task.get("title", "")),
        reverse=True,
    )
    return urgent + rest


def rotate_terminal_handoffs(tasks, cursor, processed, recovery_ids=()):
    """Rotate fairly without moving an earlier delivery stage behind a later one."""
    tasks = list(tasks or [])
    cursor_index = next((index for index, task in enumerate(tasks)
                         if task.get("id") == cursor), None)
    if cursor_index is None:
        return tasks
    rotated = tasks[cursor_index + 1:] + tasks[:cursor_index + 1]
    # Reapply stage priority after rotation. Stable sorting preserves the
    # round-robin order inside one stage, while Verify/Review stay ahead of
    # Implement/Specification/Triage.
    return prioritize_terminal_handoffs(rotated, processed, recovery_ids)


def recent_terminal_handoff_history(tasks, limit=TERMINAL_HANDOFF_HISTORY_LIMIT,
                                    pinned_ids=()):
    """Keep the live handoff scan bounded to the newest task-list window.

    ``all_tasks()`` is still used as the source of truth for duplicate and
    lifecycle checks.  Treating every never-recorded archival task as a new
    handoff, however, makes a newly upgraded Pilot replay years of history
    before it reaches a completion that only just fell beyond page one.
    """
    try:
        limit = max(int(limit), 1)
    except (TypeError, ValueError):
        limit = TERMINAL_HANDOFF_HISTORY_LIMIT
    tasks = list(tasks or [])
    bounded = tasks[:limit]
    pinned_ids = set(pinned_ids or ())
    if not pinned_ids:
        return bounded
    included = {task.get("id") for task in bounded}
    bounded.extend(
        task for task in tasks[limit:]
        if task.get("id") in pinned_ids and task.get("id") not in included
    )
    return bounded


def live_or_done_at(tasks, base, stage_no, since=None):
    """Задача по этой же работе на стадии stage_no или дальше, живая либо успешная.
    Единственный источник правды для защиты от дублей: и при продвижении по
    конвейеру, и при возобновлении после ответа владельца.
    since — момент, начиная с которого задача считается «новой»: старый хвост от
    прошлого прогона дублем не считается и не мешает доработке."""
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m or not same_task_work(t, base):
            continue
        if since and (t.get("created_at") or "") <= since:
            continue
        if stage_no_of(t.get("title")) >= stage_no and t.get("state") in (
                "created", "running", "queued", "preparing", "succeeded"):
            return t
    return None


def restart_recovery_detail(conf, tasks, task, stages, detail=None):
    """Return detail only for a safe, still-missing startup handoff."""
    task_id = task.get("id")
    recovery_ids = conf.get("_restart_recovery_ids") or ()
    if task_id not in recovery_ids or task.get("state") != "succeeded":
        return None
    watermark = _work_time(conf.get("_restart_recovery_watermark"))
    if not watermark:
        return None
    base = base_title(task.get("title", ""))
    if work_lifecycle_block(base, task, tasks) or is_stopped(conf, base):
        return None
    if detail is None:
        try:
            detail = api(f"/tasks/{task_id}")
        except Exception as error:
            log(f"restart recovery skip task={task_id}: {error}")
            return None
    execution = detail.get("execution") or {}
    attempts = detail.get("attempts") or []
    finished = _work_time(execution.get("updated_at"))
    if not finished:
        finished = next(
            (_work_time(attempt.get("completed_at"))
             for attempt in reversed(attempts)
             if _work_time(attempt.get("completed_at"))),
            None,
        )
    if not finished or finished <= watermark:
        return None
    workflow = (detail.get("workflow") or {}).get("title")
    if workflow not in stages or stages.index(workflow) + 1 >= len(stages):
        return None
    if live_or_done_at(
            tasks, task, stages.index(workflow) + 2,
            since=task.get("created_at")):
        return None
    return detail


def load_restart_recovery_tasks(conf, tasks):
    """Load recovery IDs hidden beyond the current task-list page by detail."""
    recovery_ids = set(conf.get("_restart_recovery_ids") or ())
    visible = {task.get("id") for task in tasks}
    details = {}
    for task_id in recovery_ids - visible:
        try:
            detail = api(f"/tasks/{task_id}")
            task = dict(detail.get("task") or {})
        except Exception as error:
            log(f"restart recovery skip task={task_id}: {error}")
            continue
        task.setdefault("id", task_id)
        if task:
            tasks.append(task)
            details[task_id] = detail
    return details


def retry_terminal_task(conf, state, task_id):
    """Requeue a terminal task without advancing a startup recovery cursor."""
    if task_id in state["processed"]:
        state["processed"].remove(task_id)
    retry_ids = state.setdefault("terminal_retry_ids", [])
    if task_id not in retry_ids:
        retry_ids.append(task_id)
    if task_id in (conf.get("_restart_recovery_ids") or ()):
        conf["_restart_recovery_retry"] = True


def resume_stage_for(stages, wf, next_stage):
    """Куда возвращать работу после остановки конвейера.
    Ревью и финальная проверка означают доработку — значит назад в разработку,
    а не вперёд. Иначе следующий агент получает пустую ветку и честно говорит
    «проверять нечего»."""
    impl = "Implement + Test" if "Implement + Test" in stages else None
    if wf in ("Review", "Verify") and impl:
        return impl
    if wf == impl:
        return impl
    return next_stage or wf


def mark_final(task_id, stage, passed):
    """Запомнить, прошла ли последняя стадия по существу (а не просто «задача
    отработала»). Эпик двигается только по настоящему PASS."""
    try:
        os.makedirs(VERDICT_DIR, exist_ok=True)
        rec = load(f"{VERDICT_DIR}/{task_id}.json", {}) or {}
        rec.update({"task_id": task_id, "stage": stage, "final_pass": bool(passed)})
        save(f"{VERDICT_DIR}/{task_id}.json", rec)
    except Exception as e:
        log("mark_final_error", repr(e))


def save_stage_verdict(task_id, stage, verdict, result, repo_id=""):
    """Save the compact board record for a completed pipeline stage.

    Review return reasons must survive subsequent repair laps: the Work board
    uses one record per task to explain why every lap was sent back.
    """
    rec = {"task_id": task_id, "stage": stage,
           "verdict": verdict["verdict_ru"],
           "action": verdict["action"]}
    reason = str(verdict.get("reason") or "").strip()
    if reason:
        rec["reason"] = reason[:1000]
    seen = try_url(result, repo_id)
    if seen and any(u in seen for u in TRY_USELESS):
        seen = ""
    if seen:
        rec["try_url"] = seen
    pf = proof_of(result)
    if pf:
        rec["proof"] = pf
    os.makedirs(VERDICT_DIR, exist_ok=True)
    save(f"{VERDICT_DIR}/{task_id}.json", rec)


def final_ok(task_id, strict=False):
    """Прошла ли финальная проверка по существу.

    strict=True — для решения «подзадача эпика готова». Там отсутствие отметки
    не значит «всё хорошо»: отметку пишет соседний цикл, и раньше эпик успевал
    посмотреть до неё, защёлкнуть «готово» и убежать дальше по недоделанному."""
    rec = load(f"{VERDICT_DIR}/{task_id}.json", None)
    if not rec or "final_pass" not in rec:
        return not strict
    return bool(rec["final_pass"])


def supersede_stale_questions(tasks):
    """Вопрос, висящий на отменённой/упавшей задаче, блокирует эпик навсегда,
    хотя работа уже прошла эту стадию в другой задаче. Такие вопросы снимаем."""
    by_id = {t["id"]: t for t in tasks}
    for q in load_questions():
        if q.get("status") != "open":
            continue
        t = by_id.get(q.get("task_id"))
        if not t or t.get("state") not in ("cancelled", "failed"):
            continue
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m:
            continue
        newer = live_or_done_at(tasks, t, stage_no_of(t.get("title")),
                                since=t.get("created_at"))
        if not newer or newer["id"] == t["id"]:
            continue
        q["status"] = "obsolete"
        q["escalation_reason"] = (
            f"вопрос снят автоматически: эта работа уже прошла стадию "
            f"в задаче {newer['id'][:8]} ({newer.get('state')})")
        save(f"{QUESTION_DIR}/{q['id']}.json", q)
        log(f"QUESTION OBSOLETE q={q['id'][:8]} stage={q.get('stage')} "
            f"-> перекрыт задачей {newer['id'][:8]}")


def cleanup_orphaned_paused_pipelines(conf, tasks):
    """Remove pauses that no longer have a visible reason to exist.

    Keep memory unchanged until the updated config is safely on disk.  A bad
    read or failed atomic save can therefore be retried by the next cycle
    without making this cycle believe that the pause was removed.
    """
    if not (conf.get("stopped_pipelines") or []):
        return False

    def name(value):
        return base_title(str(value or "")).strip().casefold()

    try:
        disk = load(CONF_PATH, None)
        if not isinstance(disk, dict):
            raise ValueError("config is unavailable or invalid")

        stopped = list(disk.get("stopped_pipelines") or [])
        active_names = {
            name(idea.get("title"))
            for idea in ideas_all()
            if idea.get("state") in ("new", "planned", "in_work")
        }
        active_names.update(
            name(question.get("title"))
            for question in load_questions()
            if question.get("status") == "open" or (
                question.get("status") == "resolved"
                and question.get("machine_action") == "wait"
            )
        )
        active_names.update(
            name(task.get("title"))
            for task in (tasks or [])
            if task.get("state") in ("preparing", "queued", "running")
        )
        kept = [base for base in stopped if name(base) in active_names]
        if kept == stopped:
            return False

        updated = dict(disk)
        updated["stopped_pipelines"] = kept
        save(CONF_PATH, updated)
        conf["stopped_pipelines"] = kept
        log("PIPELINE PAUSES CLEANED " + repr(
            [base for base in stopped if base not in kept]))
        return True
    except Exception as e:
        log("paused_pipeline_cleanup_error", repr(e))
        return False


# --------------------------------------- Потолок ≠ решение владельца -------
# Сколько раз оркестратор уже вытаскивал эту стадию после потолка. Без счётчика
# «другой подход» превратится в тот же круг, только без человека.
RESCUE_PATH = f"{HOME}/pilot/cap_rescues.json"


def cap_rescues(base, stage):
    return int((load(RESCUE_PATH, {}) or {}).get(f"{base}::{stage}", 0))


def note_cap_rescue(base, stage):
    rec = load(RESCUE_PATH, {}) or {}
    key = f"{base}::{stage}"
    rec[key] = int(rec.get(key, 0)) + 1
    save(RESCUE_PATH, rec)


def create_cap_rescue(base, stage, body, conf=None, parent=None,
                      correction_kind="execution_retry"):
    """Create a return task before consuming its durable rescue allowance."""
    created = create_child_task(body, parent, conf, correction_kind)
    task = created.get("task") if isinstance(created, dict) else None
    if not isinstance(task, dict) or not task.get("id"):
        raise RuntimeError(f"{stage} return: create_task returned no task")
    note_cap_rescue(base, stage)
    return created


LOOP_NOTE = (
    "\n\nВНИМАНИЕ: эта работа прошла один и тот же этап {n} раз(а) и каждый раз "
    "возвращалась. Значит мешает не качество кода, а что-то системное: сломанное "
    "окружение, недоступный сервис, придирка к тексту заметок или требование, "
    "которое исполнитель физически не может выполнить. Ответ «перезапусти» и "
    "«попробуй ещё раз» НЕ ПРИНИМАЕТСЯ — он уже не сработал {n} раз. "
    "Прими решение сам: либо назови ДРУГОЙ способ закрыть замечание, либо разреши "
    "принять работу с этим замечанием и записать его в долги, либо укажи, что именно "
    "починить в окружении. К владельцу это уходит ТОЛЬКО если вопрос про деньги, "
    "про боевую систему или про выбор продукта — тогда так и скажи прямым текстом. "
    "Если работа по сути СДЕЛАНА (код запушен, тесты зелёные), а замечание можно "
    "записать в долги — начни ответ ровно словом ПРИНЯТО: и одной фразой почему; "
    "тогда конвейер двинет работу вперёд, а не на новый круг.")

ACCEPT_MARK = re.compile(
    r"^\s*[«\"']?(ПРИНЯТО\b|Принима\w*|"
    r"Работа\s+выполнена|Считаю\s+выполненн)", re.I)
NEXT_STAGE = {"Implement + Test": "Review", "Review": "Verify", "Verify": "Verify"}


def accept_forward(stage, answer):
    """«Принято» оркестратора — движение ВПЕРЁД: принятая разработка идёт в
    Ревью, принятое Ревью — в Проверку. Раньше «принято» рождало ещё один
    круг той же стадии, и работа крутилась вечно."""
    nxt = NEXT_STAGE.get(str(stage))
    if nxt and ACCEPT_MARK.match(answer or ""):
        log(f"ACCEPT FORWARD {stage} -> {nxt}")
        return nxt
    return None


CAP_NOTE = (
    "\n\nВАЖНО: этот этап уже выполнялся {n} раз(а) и каждый раз не проходил. "
    "Просто перезапустить его тем же способом НЕЛЬЗЯ — это сожжёт деньги и "
    "вернёт тот же результат. Либо предложи ДРУГОЙ подход (сузить задание, "
    "починить конкретную причину, поменять порядок шагов), либо честно скажи, "
    "что решение действительно владельца. Ответ «перезапусти» не принимается."
)


RETRY_WORDS = ("перезапус", "повтори", "запусти заново", "попробуй ещё раз",
               "просто запусти", "прогони ещё")


def looks_like_retry(answer):
    """«Перезапусти» после пяти падений — это не решение, а тот же круг."""
    a = (answer or "").lower()
    return any(w in a for w in RETRY_WORDS) and len(a) < 240


LOOP_BASE_PATH = f"{HOME}/pilot/loop_baseline.json"


def loop_baseline(base):
    """С какого круга считать заново. Ставится в момент остановки: после того
    как владелец разобрался и открыл работу снова, ей даётся полный запас
    кругов, а не мгновенный повторный стоп на старом счётчике."""
    try:
        return int((load(LOOP_BASE_PATH, {}) or {}).get(base, 0))
    except Exception:
        return 0


def set_loop_baseline(base, n):
    try:
        d = load(LOOP_BASE_PATH, {}) or {}
        d[base] = int(n)
        save(LOOP_BASE_PATH, d)
    except Exception as e:
        log("loop_baseline_error", repr(e))


def pause_pipeline(conf, base):
    """Остановить конвейер по этой работе. Пилот её больше не двигает, что бы
    ни отвечал оркестратор, пока владелец не уберёт её из списка."""
    try:
        c = load(CONF_PATH, {}) or {}
        lst = list(c.get("stopped_pipelines") or [])
        if base not in lst:
            lst.append(base)
            c["stopped_pipelines"] = lst
            save(CONF_PATH, c)
        conf["stopped_pipelines"] = lst
        log("PIPELINE PAUSED " + repr(base[:60]))
    except Exception as e:
        log("pause_pipeline_error", repr(e))


# ---------------------------------------- Замок по областям работы --------
# Две работы, правящие один файл, гарантированно испортят друг другу ветку:
# кто влился первым, у того всё хорошо, у второго разница с main показывает
# чужие файлы, и ревью честно отказывает. Поэтому работы с пересекающейся
# областью идут по очереди, а не одновременно.
AREAS_PATH = f"{HOME}/pilot/areas.json"
AREA_LINE = re.compile(r"^\s*ОБЛАСТЬ:\s*(.+)$", re.M)


def area_of(base, context="", repo=""):
    """Какие файлы трогает работа. Берём из строки ОБЛАСТЬ в задании и помним."""
    known = load(AREAS_PATH, {}) or {}
    if base in known:
        return set(known[base])
    files = set()
    for m in AREA_LINE.finditer(context or ""):
        for p in m.group(1).replace(";", ",").split(","):
            p = p.strip()
            if not p or "<" in p or ">" in p:
                continue  # шаблонная строка из правил, не настоящий путь
            if "/" not in p and "." not in p:
                continue
            files.add(repo + "::" + p)
    if not files:
        return set()
    known[base] = sorted(files)
    save(AREAS_PATH, known)
    log("AREA " + repr(base[:50]) + " -> " + ", ".join(sorted(files))[:120])
    return files


NOISE_PATHS = ("__pycache__", ".pyc", "node_modules/")


def area_extend(base, result, repo=""):
    """Агент назвал свои файлы в отчёте — запоминаем их как область работы.
    Иначе машинная чистка выбрасывает то, что он же и сделал."""
    files = set()
    for m in AREA_LINE.finditer(result or ""):
        for p in m.group(1).replace(";", ",").split(","):
            p = p.strip().strip("`")
            if not p or "<" in p or ">" in p:
                continue
            if "/" not in p and "." not in p:
                continue
            files.add((repo + "::" + p) if repo else p)
    if not files:
        return set()
    known = load(AREAS_PATH, {}) or {}
    was = set(known.get(base) or [])
    if files - was:
        known[base] = sorted(was | files)
        save(AREAS_PATH, known)
        log(f"AREA+ {base[:40]!r}: +{len(files - was)} файлов из отчёта")
    return files


def other_areas(base, active_tasks=None, repo=""):
    """Файлы живых ДРУГИХ работ в том же репозитории.

    areas.json — это журнал заявок, а не вечный список запретов.  Закончившаяся
    работа не должна держать файл в замке, иначе старая область превращает
    совершенно новую поставку в ложное пересечение.
    """
    known = load(AREAS_PATH, {}) or {}
    active = None
    if active_tasks is not None:
        active = set()
        for t in active_tasks:
            if t.get("state") not in ("running", "queued"):
                continue
            m = STAGE_TITLE_RE.match(t.get("title", ""))
            if m:
                active.add(m.group(2).strip())
    out = set()
    for k, v in known.items():
        if k == base or (active is not None and k not in active):
            continue
        for p in v or []:
            owner, path = (p.split("::", 1) if "::" in p else ("", p))
            if repo and owner and owner != repo:
                continue
            out.add(path)
    return out


def area_replace(base, files, repo=""):
    """Зафиксировать реальную, а не когда-то заявленную область поставки."""
    paths = sorted({p.strip() for p in files if p and p.strip()})
    known = load(AREAS_PATH, {}) or {}
    known[base] = [(repo + "::" + p) if repo else p for p in paths]
    save(AREAS_PATH, known)
    log(f"AREA= {base[:40]!r}: {len(paths)} файлов по финальному diff")
    return set(known[base])


def _area_rank(tasks, base):
    """Старшинство работы в споре за файл: (номер самой дальней живой стадии,
    более ранний старт, заголовок). Сравнивается кортежами: строго старший
    получает файл, младший ждёт. Антисимметрично, поэтому взаимное ожидание
    невозможно: из двух спорящих ровно одна работа проходит."""
    best_no, first_seen = 0, ""
    for t in tasks:
        if t.get("state") not in ("running", "queued"):
            continue
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m or m.group(2).strip() != base:
            continue
        best_no = max(best_no, stage_no_of(t.get("title", "")))
        created = str(t.get("created_at") or "")
        if created and (not first_seen or created < first_seen):
            first_seen = created
    # Ранний старт важнее позднего: инвертируем строку даты посимвольно,
    # чтобы «раньше начал» означало «кортеж больше».
    inverted = "".join(chr(0x10FFFF - ord(ch)) for ch in first_seen)
    return (best_no, inverted, base)


def area_busy(tasks, base, context="", repo=""):
    """Кто уже занял тот же файл. Возвращает имя работы или пустую строку.

    Реально выполняющийся этап (running) держит файл безусловно. Если же
    пересеклись только ожидающие (queued) работы, файл достаётся старшей по
    _area_rank — той, что дальше прошла по конвейеру, при равенстве начатой
    раньше. Раньше обе стороны честно уступали друг другу и вставали навсегда
    (взаимное AREA WAIT); теперь спор решается детерминированно."""
    mine = area_of(base, context, repo)
    if not mine:
        return ""
    known = load(AREAS_PATH, {}) or {}
    my_rank = None
    for t in tasks:
        if t.get("state") not in ("running", "queued"):
            continue
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m:
            continue
        other = m.group(2).strip()
        if other == base.strip():
            continue
        if not (mine & set(known.get(other) or [])):
            continue
        if t.get("state") == "running":
            return other
        if my_rank is None:
            my_rank = _area_rank(tasks, base.strip())
        if _area_rank(tasks, other) > my_rank:
            return other
    return ""


# ------------------------------------------------------------- предложения ---
# Ничто найденное по пути не теряется. Термины намеренно не взаимозаменяемы:
# помощник или владелец добавляет ПРЕДЛОЖЕНИЕ, а НАХОДКА рождается только
# внутри выполняемой воркером работы и всегда хранит источник этой работы.
IDEAS_PATH = f"{HOME}/pilot/ideas.json"
IDEA_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(ПРЕДЛОЖЕНИЕ|НАХОДКА)(?:\*\*)?\s*:\s*(.+?)\s*$", re.M)
IDEA_KINDS = ("idea", "finding")
IDEA_STATES = ("new", "planned", "in_work", "done", "rejected")
IDEA_SKIP = ("нет", "none", "-", "н/д", "нету", "n/a")
FINDING_ORIGINS = ("worker", "agent")  # ``agent`` keeps old worker records valid.
PLAN_REVALIDATE_AFTER_SECONDS = 3600
PLAN_REVALIDATION_QUEUE = 10


def ideas_all():
    d = load(IDEAS_PATH, None)
    if not isinstance(d, list):
        return []
    changed = False
    for item in d:
        source = str(item.get("source") or "").strip()
        if (item.get("kind") == "finding"
                and (item.get("origin") not in FINDING_ORIGINS or not source)):
            item["kind"] = "idea"
            item["key"] = _idea_key("idea", item.get("repo"), item.get("title"))
            changed = True
    if changed:
        save(IDEAS_PATH, d)
    return d


def _idea_key(kind, repo, title):
    t = re.sub(r"[^\w ]+", " ", title or "", flags=re.U)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return kind + "|" + (repo or "") + "|" + t[:200]


def _idea_id(items):
    n = int(time.time() * 1000)
    used = {i.get("id") for i in items}
    while ("p" + format(n, "x")) in used:
        n += 1
    return "p" + format(n, "x")


def add_idea(kind, title, repo="", why="", origin="assistant", source="",
             state="new", order=None):
    """Заводит карточку, соблюдая словарь Плана.

    Находкой считается только результат, который воркер сообщил из конкретной
    работы. Ручной ввод владельца или помощника всегда является предложением,
    даже если старый клиент передал ``kind=finding``.
    """
    title = re.sub(r"\s+", " ", (title or "").strip())
    if not title:
        return None
    kind = kind if kind in IDEA_KINDS else "idea"
    source = (source or "").strip()
    if kind == "finding" and (origin not in FINDING_ORIGINS or not source):
        kind = "idea"
    items = ideas_all()
    key = _idea_key(kind, repo, title)
    for it in items:
        if it.get("key") == key and it.get("state") != "rejected":
            return it
    now = time.strftime("%Y-%m-%d %H:%M")
    if order is None:
        order = max([int(i.get("order") or 0) for i in items] or [0]) + 10
    rec = {"id": _idea_id(items), "key": key, "kind": kind, "title": title[:300],
           "why": (why or "")[:2000], "repo": repo or "", "origin": origin,
           "source": source[:200],
           "state": state if state in IDEA_STATES else "new",
           "reason": "", "task_id": "", "order": int(order),
           "created": now, "updated": now}
    items.append(rec)
    save(IDEAS_PATH, items)
    try:
        conf_now = load(CONF_PATH, {}) or {}
        kind_ru = "Находка" if kind == "finding" else "Предложение"
        who = {"worker": "нашёл исполнитель по ходу работы",
               "owner": "предложил ты",
               "assistant": "предложил помощник",
               "codex": "предложил помощник",
               "claude": "предложил помощник",
               "patrol": "предложил помощник"}.get(origin, "добавлено в план")
        body = kind_ru + " · " + who + chr(10) + title[:200]
        if why:
            body += chr(10) + chr(10) + cut(why, 260)
        notify(conf_now, "Новое в Плане", body,
               tags="bulb", click=f"{UI_BASE}/intake/plan")
    except Exception as e:
        log("idea_notify_error", repr(e))
    log("IDEA + [" + kind + "] " + repr(title[:70]) + " repo=" + (repo or "-"))
    return rec


def set_idea(idea_id, **fields):
    items = ideas_all()
    for it in items:
        if it.get("id") == idea_id:
            for k, v in fields.items():
                if k in ("id", "key", "created"):
                    continue
                it[k] = v
            it["updated"] = time.strftime("%Y-%m-%d %H:%M")
            save(IDEAS_PATH, items)
            return it
    return None


def plan_idea(idea_id):
    """Schedule a fresh run while keeping retries of that run idempotent."""
    idea = next((item for item in ideas_all() if item.get("id") == idea_id), None)
    generation = str(uuid.uuid4())
    updated = set_idea(idea_id, state="planned", task_id="", reason="",
                       run_generation=generation)
    if idea:
        reopen_work(idea.get("title", ""), generation)
    if isinstance(updated, dict):
        return updated
    return dict(idea or {}, state="planned", task_id="", reason="",
                run_generation=generation)


def cleanup_completed_plan_cards(tasks, final_stage_no):
    """Close plan cards whose linked pipeline reached an accepted final stage.

    The linked task is the run boundary.  This deliberately refuses title-only
    guesses and old successful runs, either of which could hide fresh work.
    """
    by_id = {t.get("id"): t for t in tasks or [] if t.get("id")}
    open_questions = {q.get("task_id") for q in load_questions()
                      if q.get("status") == "open"}
    closed = []
    for idea in ideas_all():
        if idea.get("state") not in ("planned", "in_work"):
            continue
        linked = by_id.get(idea.get("task_id"))
        since = (linked or {}).get("created_at")
        if not linked or not since:
            continue
        base = base_title(linked.get("title", ""))
        candidates = []
        for task in tasks or []:
            if (task.get("created_at") or "") < since:
                continue
            if base_title(task.get("title", "")) != base:
                continue
            if stage_no_of(task.get("title")) != final_stage_no:
                continue
            candidates.append(task)
        candidates.sort(key=lambda t: (t.get("created_at") or "", t.get("id") or ""))
        final = candidates[-1] if candidates else None
        if (not final or final.get("state") != "succeeded"
                or final.get("id") in open_questions
                or not final_ok(final.get("id"), strict=True)):
            continue
        set_idea(idea["id"], state="done")
        closed.append(idea["id"])
        log(f"PLAN DONE idea={idea['id']} task={final.get('id')}")
    return closed


def reconcile_stale_plan_cards(tasks, now=None):
    """Return abandoned Plan runs to Triage instead of pretending they run.

    A short gap belongs to the ordinary continuation watcher.  Once a linked
    generation has had no live task for an hour, its original finding may no
    longer describe current ``main``.  Queue a bounded fresh Triage generation
    so the normal first-stage verdict can close duplicates and already-fixed
    work before any expensive implementation stage is admitted.
    """
    now = time.time() if now is None else float(now)
    items = ideas_all()
    room = max(0, PLAN_REVALIDATION_QUEUE - sum(
        1 for item in items
        if item.get("state") == "planned" and item.get("revalidation")
    ))
    if not room:
        return []
    by_id = {task.get("id"): task for task in tasks or [] if task.get("id")}
    open_questions = [q for q in load_questions() if q.get("status") == "open"]
    queued = []

    def activity_epoch(task):
        for field in ("updated_at", "completed_at", "created_at"):
            parsed = _work_time((task or {}).get(field))
            if parsed is not None:
                return parsed.timestamp()
        return 0

    def idea_epoch(item):
        value = str(item.get("updated") or item.get("created") or "")
        try:
            return time.mktime(time.strptime(value, "%Y-%m-%d %H:%M"))
        except (OverflowError, TypeError, ValueError):
            return 0

    for idea in items:
        if room <= 0:
            break
        if idea.get("state") != "in_work":
            continue
        linked_id = idea.get("task_id") or ""
        linked = by_id.get(linked_id)
        boundary = (linked or {}).get("created_at") or ""
        title = idea.get("title") or ""
        generation = [task for task in (tasks or []) if (
            task_work_id(task) == linked_id
            or (linked and _same_work(task.get("title"), title)
                and (task.get("created_at") or "") >= boundary)
        )]
        if any(task.get("state") in PLAN_ACTIVE_STATES for task in generation):
            continue
        generation_ids = {task.get("id") for task in generation if task.get("id")}
        if any(
            question.get("task_id") in generation_ids
            or question.get("work_id") == linked_id
            or _same_work(question.get("title"), title)
            for question in open_questions
        ):
            continue
        last_activity = max(
            [activity_epoch(task) for task in generation] + [idea_epoch(idea)]
        )
        if last_activity and now - last_activity < PLAN_REVALIDATE_AFTER_SECONDS:
            continue
        run_generation = str(uuid.uuid4())
        idea.update({
            "state": "planned",
            "task_id": "",
            "run_generation": run_generation,
            "revalidation": True,
            "reason": (
                "Предыдущий запуск давно остановился без живого этапа. "
                "Актуальность будет повторно проверена на Разборе."
            ),
            "updated": time.strftime("%Y-%m-%d %H:%M"),
        })
        queued.append(idea.get("id"))
        room -= 1
        log("PLAN RECHECK " + repr(title[:70]))
    if queued:
        save(IDEAS_PATH, items)
    return queued


def _rfc3339(value):
    """Parse an RFC3339 timestamp and require an explicit timezone."""
    text = str(value or "").strip()
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--before must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("--before must include a timezone")
    return parsed.astimezone(datetime.timezone.utc)


def _cleanup_task_time(task_id):
    detail = api(f"/tasks/{task_id}")
    task = detail.get("task") or {}
    execution = detail.get("execution") or task.get("execution") or {}
    value = execution.get("updated_at")
    if not value:
        raise ValueError(f"task {task_id} has no execution.updated_at")
    return _rfc3339(value)


def cleanup_legacy_plan_cards(before, apply=False, now_fn=None):
    """Find, and optionally atomically close, cards left before auto-cleanup."""
    cutoff = _rfc3339(before)
    tasks = all_tasks()
    by_id = {task.get("id"): task for task in tasks if task.get("id")}
    items = load(IDEAS_PATH, None)
    if not isinstance(items, list):
        raise ValueError("ideas.json must contain a list")
    changes, skipped = [], []
    terminal = {"succeeded", "failed", "cancelled"}

    for idea in items:
        if idea.get("state") not in ("planned", "in_work"):
            continue
        task_id = str(idea.get("task_id") or "").strip()
        if not task_id:
            skipped.append((idea, "no_task_id"))
            continue
        linked = by_id.get(task_id)
        if not linked:
            changes.append((idea, "linked_task_missing"))
            continue

        work_id = linked.get("work_id")
        if work_id:
            boundary = [task for task in tasks if task.get("work_id") == work_id]
        else:
            repo = linked.get("repository_id") or ""
            title = base_title(linked.get("title") or "")
            since = linked.get("created_at") or ""
            if not repo or not title or not since:
                skipped.append((idea, "ambiguous_legacy_link"))
                continue
            boundary = [task for task in tasks
                        if not task.get("work_id")
                        and task.get("repository_id") == repo
                        and base_title(task.get("title") or "") == title
                        and (task.get("created_at") or "") >= since]
        boundary.sort(key=lambda task: (task.get("created_at") or "", task.get("id") or ""))
        latest = boundary[-1] if boundary else None
        state = (latest or {}).get("state")
        if not latest or state not in terminal or state == "cancelled":
            skipped.append((idea, "work_not_terminal"))
            continue
        if state == "succeeded":
            match = PIPELINE_TITLE.match(latest.get("title") or "")
            if (not match or match.group(1) != match.group(2)
                    or not final_ok(latest.get("id"), strict=True)):
                skipped.append((idea, "success_not_accepted_final"))
                continue
        if _cleanup_task_time(latest["id"]) >= cutoff:
            skipped.append((idea, "terminal_not_before_cutoff"))
            continue
        changes.append((idea, "terminal_before_cutoff"))

    for idea, reason in changes:
        log(f"CLEANUP PLAN {idea.get('id')} {idea.get('title', '')!r} reason={reason}")
    for idea, reason in skipped:
        log(f"CLEANUP SKIP {idea.get('id')} {idea.get('title', '')!r} reason={reason}")
    log(f"CLEANUP TOTAL changes={len(changes)} skipped={len(skipped)} apply={bool(apply)}")
    if apply and changes:
        stamp = (now_fn or (lambda: datetime.datetime.now(datetime.timezone.utc)))()
        stamp = stamp.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        for idea, reason in changes:
            idea.update(state="done", reason="закрыто уборкой", cleanup_at=stamp,
                        cleanup_reason=reason,
                        updated=time.strftime("%Y-%m-%d %H:%M"))
        save(IDEAS_PATH, items)
    return len(changes)


def collect_ideas(result, repo_id="", source=""):
    """Разбирает отчёт агента и заводит карточки. Вернёт их число."""
    n = 0
    for kind_ru, text in IDEA_LINE.findall(result or ""):
        kind = "idea" if kind_ru.startswith("ПРЕД") else "finding"
        text = (text or "").strip().strip("*").strip()
        if len(text) < 8 or text.lower() in IDEA_SKIP:
            continue
        title, sep, why = text.partition(" — ")
        if not sep:
            title, sep, why = text.partition(" - ")
        if not sep and len(title) > 140:
            title, why = title[:140].rsplit(" ", 1)[0], text
        if add_idea(kind, title or text, repo_id, why, origin="worker",
                    source=source):
            n += 1
    return n


def collect_automation_findings(state, tasks):
    """Persist findings emitted by completed Automation workflow runs.

    Automation tasks do not use the ``[auto] [n/m Stage]`` title contract, so
    the normal pipeline result loop intentionally ignores them. Keep a
    separate durable cursor and feed their successful reports through the same
    de-duplicating Plan collector used by pipeline stages.
    """
    processed = state.setdefault("automation_results_processed", [])
    collected = 0
    for task in tasks:
        task_id = task.get("id") or ""
        request_key = str(task.get("request_key") or "")
        task_state = task.get("state")
        if (not task_id or not request_key.startswith("automation:")
                or task_state not in ("succeeded", "failed", "cancelled")
                or task_id in processed):
            continue
        if task_state != "succeeded":
            processed.append(task_id)
            log(f"automation result state={task_state} task={task_id} -> no findings")
            continue

        detail = api(f"/tasks/{task_id}")
        attempts = detail.get("attempts") or []
        result = next(
            (attempt.get("result") for attempt in reversed(attempts)
             if attempt.get("result")),
            "",
        ) or ""
        repository_id = detail.get("task", {}).get("repository_id") or ""
        workflow_title = (detail.get("workflow") or {}).get("title")
        source = f"Automation: {workflow_title or task.get('title') or task_id}"
        found = collect_ideas(result, repository_id, source)
        processed.append(task_id)
        collected += found
        log(f"automation findings task={task_id} collected={found}")
    return collected


PLAN_ACTIVE_STATES = ("running", "queued", "pending", "created", "starting", "preparing")

PLAN_REPOSITORY_ALIASES = {
    "factory": "timafen/factory",
    "tarser": "timafen/tarser-operations",
    "trading": "timafen/tarser-operations",
    "tarser-operations": "timafen/tarser-operations",
}


def resolve_plan_repository(repository_id):
    """Translate legacy human project names in Plan cards to control-plane ids."""
    alias = PLAN_REPOSITORY_ALIASES.get((repository_id or "").strip().lower())
    if not alias:
        return repository_id
    repositories = api("/repositories").get("repositories") or []
    matches = []
    for repository in repositories:
        identity = (repository.get("remote_identity") or "").lower()
        if identity.endswith(".git"):
            identity = identity[:-4]
        if identity.endswith(alias):
            matches.append(repository.get("id"))
    matches = [repo_id for repo_id in matches if repo_id]
    if len(matches) != 1:
        raise RuntimeError(
            f"plan repository alias {repository_id!r} resolved to {len(matches)} repositories"
        )
    return matches[0]


def is_plan_repository_error(error):
    text = str(error).lower()
    return any(marker in text for marker in (
        "repository_not_advertised",
        "no remote identity for repo",
        "plan repository alias",
    ))


def explain_bad_plan_repository(conf, candidate, detail=""):
    reason = "Не запущено автоматически: у карточки указан несуществующий проект. Выберите проект заново."
    already_explained = candidate.get("state") == "new" and candidate.get("reason") == reason
    set_idea(candidate["id"], state="new", reason=reason)
    log("PLAN skip " + repr(candidate.get("title", "")[:70])
        + ": invalid repository " + repr(detail[:180]))
    if not already_explained:
        notify(conf, "Не взял из Плана", candidate.get("title", ""),
               body=reason, tags="warning", click=UI_BASE + "/intake/plan")


def active_auto_works(tasks):
    """Unique pipeline works that currently occupy an executor slot.

    A work waiting for the owner's answer remains visible in Questions, but it
    must not reduce execution capacity: no worker is running for it.
    """
    active = set()
    for task in tasks:
        match = STAGE_TITLE_RE.match(task.get("title", "") or "")
        if match and task.get("state") in PLAN_ACTIVE_STATES:
            active.add(task_work_id(task))
    return active


def autostart_plan(conf, tasks, workflows, workers):
    """Start one suitable Plan card when the pipeline has a free slot.

    Explicitly planned cards keep priority.  With automatic planning enabled
    (the default), a new card is promoted just before its first task is
    created.  That durable transition gives retries a stable generation while
    leaving Triage responsible for semantic decisions about the proposal.
    """
    if len(active_auto_works(tasks)) >= int(
            conf.get("max_parallel_works", MAX_PARALLEL_WORKS)):
        return None
    states = ("planned", "new") if conf.get("auto_plan", True) else ("planned",)
    candidates = sorted(
        (i for i in ideas_all() if i.get("state") in states),
        key=lambda i: (
            0 if i.get("state") == "planned" else 1,
            int(i.get("order") or 0),
            i.get("created") or "",
        ),
    )
    if not candidates:
        return None
    stage_name, nstages = first_stage(conf)
    workflow = workflows.get(stage_name) or {}
    if not stage_name or not workflow.get("enabled"):
        return None
    for rec in candidates:
        if is_stopped(conf, rec.get("title") or ""):
            log("PLAN paused " + repr(rec.get("title", "")[:70]))
            continue
        if rec.get("state") == "new":
            live = next((task for task in tasks or []
                         if task.get("state") in PLAN_ACTIVE_STATES
                         and _same_work(task.get("title"), rec.get("title"))), None)
            if live:
                reason = "Не запущено повторно: эта работа уже идёт."
                set_idea(rec["id"], state="in_work", task_id=live.get("id", ""),
                         reason=reason)
                log("PLAN linked existing " + repr(rec.get("title", "")[:70]))
                continue
            closed_reason = work_lifecycle_block(rec.get("title") or "", tasks=tasks)
            if closed_reason:
                reason = "Не запущено повторно: " + closed_reason
                set_idea(rec["id"], state="rejected", reason=reason)
                log("PLAN rejected " + repr(rec.get("title", "")[:70])
                    + ": " + closed_reason)
                continue
        if not rec.get("repo"):
            reason = "Не запущено автоматически: сначала выберите проект."
            already_explained = rec.get("state") == "new" and rec.get("reason") == reason
            set_idea(rec["id"], state="new", reason=reason)
            log("PLAN skip " + repr(rec.get("title", "")[:70]) + ": no repository")
            if not already_explained:
                notify(conf, "Не взял из Плана", rec.get("title", ""),
                       body=reason, tags="warning", click=UI_BASE + "/intake/plan")
            continue

        if rec.get("state") == "new":
            generation = str(uuid.uuid4())
            set_idea(rec["id"], state="planned", task_id="", reason="",
                     run_generation=generation)
            rec = dict(rec, state="planned", task_id="", reason="",
                       run_generation=generation)

        title = f"[auto] [1/{nstages} {stage_name}] {rec['title']}"[:200]
        source = rec.get("source") or "не указан"
        context = (
            "Конвейер автоматически взял верхнюю карточку из Плана.\n\n"
            f"Что разобрать: {rec['title']}\n\n"
            f"Зачем: {rec.get('why') or 'не записано'}\n\n"
            f"Источник: {source}.\n\n"
            "Это этап Triage: проверь готовность работы, границы и риски; "
            "продолжай только с вердиктом READY."
        )[:60000]
        generation = rec.get("run_generation")
        if not generation:
            generation = str(uuid.uuid4())
            set_idea(rec["id"], run_generation=generation)
            rec["run_generation"] = generation
        stored_repository_id = rec.get("repo") or ""
        try:
            repository_id = resolve_plan_repository(stored_repository_id)
            worker_name = stage_worker(
                conf, stage_name, "medium", workers,
                repository_id=repository_id)
            worker = workers.get(worker_name)
            if not worker:
                return None
            created = create_task({
                "request_key": f"plan-autostart:{rec['id']}:{generation}",
                "title": title, "context": context, "worker_id": worker["id"],
                "repository_id": repository_id,
                "timeout_seconds": conf.get("timeout_seconds", 7200),
                "workflow_revision_id": workflow["revision_id"],
            }, conf)
        except RuntimeError as error:
            if not is_plan_repository_error(error):
                raise
            explain_bad_plan_repository(conf, rec, str(error))
            continue
        task_id = (created.get("task") or {}).get("id", "")
        if not task_id:
            raise RuntimeError("create_task returned no task.id")
        updates = {"state": "in_work", "task_id": task_id}
        if repository_id != stored_repository_id:
            updates["repo"] = repository_id
        set_idea(rec["id"], **updates)
        note_work(rec["title"], rec.get("origin") or ORIGIN_OWNER, stage_name)
        notify(conf, "Взял из Плана", rec["title"], tags="robot", click=UI_BASE + "/work")
        created_task = dict((created or {}).get("task") or {})
        created_task.setdefault("id", task_id)
        created_task.setdefault("title", title)
        created_task.setdefault("state", "created")
        created_task.setdefault("work_id", task_id)
        if not any(task.get("id") == task_id for task in tasks or []):
            tasks.append(created_task)
        worker["active_count"] = int(worker.get("active_count") or 0) + 1
        return task_id
    return None


def replenish_plan(conf, tasks, workflows, workers):
    """Fill every free work slot from Plan in the same Pilot cycle."""
    limit = int(conf.get("max_parallel_works", MAX_PARALLEL_WORKS))
    started = []
    free_slots = max(0, limit - len(active_auto_works(tasks)))
    for _ in range(free_slots):
        task_id = autostart_plan(conf, tasks, workflows, workers)
        if not task_id:
            break
        started.append(task_id)
    return started


# --------------------------------------------------------- сторож конвейера ---
# Работа, у которой не бежит ни одна задача, не должна молча умирать.
# Так уже случалось: этап закончился, следующий не создали (замок по области,
# перегрузка, пауза), и повод создать его больше никогда не появлялся.
STALL_PATH = f"{HOME}/pilot/stalled.json"
STALL_WAIT = 450      # 25% быстрее прежних 600 секунд, сохраняя безопасную паузу
STALL_NUDGES = 2      # сколько раз толкаем сами, дальше — к хозяину
PIPELINE_LIVE_STATES = frozenset(
    ("running", "queued", "pending", "created", "starting")
)
POLL_ACTIVE_STATES = PIPELINE_LIVE_STATES | {"preparing"}


def next_poll_hint(conf, tasks, fast=False):
    """Choose the next Pilot interval without changing pipeline semantics."""
    idle = max(float((conf or {}).get("poll_seconds", 30)), 1)
    if fast:
        return {"seconds": min(float(FAST_POLL_SECONDS), idle), "reason": "handoff"}
    active = any(
        str(task.get("title") or "").startswith(PREFIX)
        and task.get("state") in POLL_ACTIVE_STATES
        and not is_stopped(conf or {}, base_title(task.get("title", "")))
        for task in (tasks or [])
    )
    if active:
        return {"seconds": min(float(ACTIVE_POLL_SECONDS), idle), "reason": "active"}
    return {"seconds": idle, "reason": "idle"}


def remember_new_terminal_tasks(conf, state, tasks):
    """Return a one-shot handoff signal for newly observed terminal stages."""
    seen_ids = state.setdefault("poll_terminal_seen", [])
    already_seen = set(seen_ids)
    terminal = [
        task for task in (tasks or [])
        if str(task.get("title") or "").startswith(PREFIX)
        and task.get("state") in ("succeeded", "failed", "cancelled")
    ]
    fast = any(
        task.get("id") not in already_seen
        and not is_stopped(conf or {}, base_title(task.get("title", "")))
        for task in terminal
    )
    seen_ids.extend(
        task.get("id") for task in terminal
        if task.get("id") and task.get("id") not in already_seen
    )
    state["poll_terminal_seen"] = seen_ids[-PROCESSED_RETENTION:]
    return fast


def stage_names(conf):
    st = conf.get("stages")
    if isinstance(st, list):
        return [x.get("workflow") for x in st if x.get("workflow")]
    return list(st or [])


def work_status_write(mem):
    """Пишем словами, почему работа стоит: экран не должен врать."""
    out = load(f"{HOME}/pilot/work_status.json", {}) or {}
    transient = {"stopped_owner", "stuck", "nudged", "idle"}
    out = {base: rec for base, rec in out.items()
           if rec.get("state") not in transient or base in (mem or {})}
    for base, rec in (mem or {}).items():
        why = rec.get("why")
        if why == "owner":
            out[base] = {"state": "stopped_owner",
                         "text": "остановлена: конвейер по этой работе на паузе"}
        elif why == "give_up":
            out[base] = {"state": "stuck",
                         "text": "не могу сдвинуть сам: этап закончился, "
                                 "следующий не запускается"
                                 + ((" — " + rec["reason"])
                                    if rec.get("reason") else "")}
        elif why == "nudge_failed":
            out[base] = {"state": "stuck",
                         "text": "конвейер встал, продолжить не вышло: "
                                 + (rec.get("reason")
                                    or "панель отказала, попробую ещё")}
        elif why == "nudged":
            out[base] = {"state": "nudged",
                         "text": "конвейер встал, я запустил следующий этап сам"}
        elif why == "closed":
            out[base] = {"state": "archived",
                         "text": rec.get("reason") or "работа закрыта"}
        else:
            out[base] = {"state": "idle",
                         "text": "ничего не бежит, жду следующий этап"}
    save(f"{HOME}/pilot/work_status.json", out)


def pipeline_watch(conf, tasks, workflows, workers):
    stages = stage_names(conf)
    if not stages:
        return
    mem = load(STALL_PATH, {}) or {}
    now = int(time.time())
    active_tasks = conf.get("_active_work_tasks")
    if (isinstance(active_tasks, list)
            and len(active_auto_works(active_tasks)) >= int(
                conf.get("max_parallel_works", MAX_PARALLEL_WORKS))):
        # Nothing in the stalled backlog can be admitted while every work slot
        # is occupied.  Avoid rebuilding and cross-checking the entire task
        # history (thousands of records in production) merely to rediscover
        # that fact once per stalled work.  Preserve the soft-wait semantics so
        # capacity deferral still consumes no nudge attempt.
        capacity_deferred = 0
        for rec in mem.values():
            if (isinstance(rec, dict)
                    and rec.get("why") not in ("closed", "owner", "give_up")):
                rec["since"] = now
                capacity_deferred += 1
        save(STALL_PATH, mem)
        log(f"watch_capacity_deferred count={capacity_deferred or 'all'}")
        return
    stopped = set(conf.get("stopped_pipelines") or [])
    groups = {}
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", "") or "")
        if m:
            key = task_work_id(t)
            groups.setdefault(key, {"base": m.group(2).strip(), "tasks": []})[
                "tasks"].append((m.group(1).strip(), t))
    gave_up = []
    capacity_deferred = 0
    for work_key, group in groups.items():
        base, lst = group["base"], group["tasks"]
        allowed = []
        blocked = []
        for stage, task in lst:
            reason = work_lifecycle_block(base, task, tasks)
            if reason:
                blocked.append(reason)
            else:
                allowed.append((stage, task))
        if not allowed:
            if any("закрыт" in reason or "завершена" in reason
                   or "отклонена" in reason for reason in blocked):
                mem[work_key] = {"why": "closed", "reason": blocked[-1],
                             "since": now}
            else:
                mem.pop(work_key, None)
            continue
        lst = allowed
        if any(t.get("state") in PIPELINE_LIVE_STATES for _, t in lst):
            mem.pop(work_key, None)
            continue
        if base in stopped:
            rec = mem.get(work_key) or {}
            rec["why"] = "owner"
            rec.setdefault("since", now)
            mem[work_key] = rec
            continue
        idx = [stages.index(st) for st, t in lst
               if t.get("state") == "succeeded" and st in stages]
        if not idx:
            continue
        far = max(idx)
        if far >= len(stages) - 1:
            mem.pop(work_key, None)          # дошли до конца конвейера
            continue
        rec = mem.get(work_key) or {}
        rec.setdefault("since", now)
        rec.setdefault("nudges", 0)
        mem[work_key] = rec
        if now - int(rec["since"]) < STALL_WAIT:
            continue
        if int(rec["nudges"]) >= STALL_NUDGES:
            if rec.get("why") != "give_up":
                rec["why"] = "give_up"
                gave_up.append((base, stages[far]))
            continue
        active_tasks = conf.get("_active_work_tasks")
        if (isinstance(active_tasks, list)
                and len(active_auto_works(active_tasks)) >= int(
                    conf.get("max_parallel_works", MAX_PARALLEL_WORKS))):
            # Capacity is already known from the shared cycle snapshot.  Do
            # not ask the control plane the same doomed question once per
            # stale work: after a release restart that can be hundreds of
            # sequential HTTP 400s before Pilot records the release result.
            rec["since"] = now
            capacity_deferred += 1
            continue
        nxt = stages[far + 1]
        nw = workflows.get(nxt)
        src = next((t for st, t in lst if st == stages[far]), None)
        rid = (src or {}).get("repository_id") or ""
        wname = stage_worker(
            conf, nxt, "medium", workers, repository_id=rid)
        worker = workers.get(wname)
        if not nw or not nw.get("enabled") or not worker:
            continue
        title = f"[auto] [{far + 2}/{len(stages)} {nxt}] {base}"[:200]
        fallback_branch = branch_from_history(tasks, base)
        identity_lines = implementation_context_lines(base, fallback_branch)
        try:
            created = create_child_task({"request_key": str(uuid.uuid4()), "title": title,
                         "context": ("Конвейер встал: предыдущий этап закончился, "
                                     "а следующий никто не создал. Продолжай с того "
                                     "же места, на той же ветке, ничего не начиная "
                                     "заново.\n\nРабота: " + base +
                                     "\nПредыдущий этап: " + stages[far] + "\n" +
                                     identity_lines)[:60000],
                         "worker_id": worker["id"], "repository_id": rid,
                         "timeout_seconds": conf.get("timeout_seconds", 7200),
                         "workflow_revision_id": nw["revision_id"]}, src, conf)
            created_task = created.get("task") if isinstance(created, dict) else None
            created_task = dict(created_task) if isinstance(created_task, dict) else {}
            created_task.setdefault("title", title)
            created_task.setdefault("repository_id", rid)
            created_task.setdefault("state", "created")
            created_task.setdefault(
                "created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            if created_task.get("id"):
                tasks.append(created_task)
            rec["nudges"] = int(rec["nudges"]) + 1
            rec["since"] = now
            rec["why"] = "nudged"
            log("WATCH сдвинул застрявшую работу " + repr(base[:60]) +
                ": " + stages[far] + " -> " + nxt)
            notify(conf, "Сдвинул застрявшую работу",
                   base + "\n" + stages[far] + " → " + nxt, tags="wrench")
        except Exception as e:
            # Неудача обязана стоить попытки и сдвигать окно ожидания, иначе
            # сторож долбит панель каждые полминуты до бесконечности — так
            # уже было: 2600 отказов в час по давно закрытым работам.
            reason = _http_err(e) if isinstance(e, urllib.error.HTTPError) else str(e)
            if "stage deferred" in reason:
                rec["since"] = now      # слот занят — мягкая пауза без счёта
                log("watch_deferred " + repr(base[:60]) + ": " + reason[:120])
                continue
            rec["nudges"] = int(rec["nudges"]) + 1
            rec["since"] = now
            rec["why"] = "nudge_failed"
            rec["reason"] = cut(reason, 180)
            log("watch_create_error " + repr(base[:60]) + ": " + reason[:300])
    for key in list(mem):
        if key not in groups:
            # задач этой работы больше нет в панели — запись выдохлась,
            # держать её значит толкать призраков вместо живых работ
            mem.pop(key, None)
    if capacity_deferred:
        log(f"watch_capacity_deferred count={capacity_deferred}")
    if gave_up:
        if len(gave_up) == 1:
            base, stage = gave_up[0]
            notify(conf, "Не могу продолжить сам",
                   base + "\nЭтап «" + stage + "» закончился, "
                   "а следующий не запускается даже после двух попыток.",
                   priority="high", tags="warning")
        else:
            listing = "\n".join(b for b, _ in sorted(gave_up)[:6])
            if len(gave_up) > 6:
                listing += "\n… и ещё " + str(len(gave_up) - 6)
            notify(conf, "Не могу продолжить " + str(len(gave_up)) + " работ",
                   listing + "\n\nПанель не даёт запустить следующий этап "
                   "даже после двух попыток — причины на экране «Работа».",
                   priority="high", tags="warning")
    save(STALL_PATH, mem)
    try:
        work_status_write(mem)
    except Exception as e:
        log("work_status_error", repr(e))


# ------------------------------------------------------ ворота перед Ревью ---
# Разбор сорока решений показал: Ревью чаще всего отказывает не по сути,
# а по гигиене — ветки нет в хранилище или в диффе чужие файлы. Проверять
# это умеет машина за секунды. Дорогое Ревью получает уже проверенный факт.

def gh_json(args, timeout=30, strict=False):
    env = dict(os.environ, HOME=HOME)
    r = subprocess.run(["gh"] + args, capture_output=True, text=True,
                       env=env, timeout=timeout)
    if r.returncode != 0:
        # Most callers use None as a deliberately soft failure.  Branch
        # handoff is different: only a real 404 proves that an artifact was
        # not published; a network/service failure must be retried later.
        failure = (r.stderr or r.stdout or "gh failed").strip()
        if strict and "HTTP 404" not in failure:
            raise RuntimeError(failure)
        return None
    try:
        return json.loads(r.stdout)
    except Exception as e:
        if strict:
            raise RuntimeError("gh returned invalid JSON") from e
        return None


# --------------------------------------------------- обещания «готово, когда»
# Спецификация записывает проверяемые машиной факты. Дальше их сверяет код,
# а не мнение модели: список файлов приходит из GitHub, сравнение — точное.
PROMISES_PATH = f"{HOME}/pilot/promises.json"
PROMISE_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?ГОТОВО-КОГДА:\s*(файл|команда)\s*[:\-]?\s*(.+?)\s*$",
    re.M | re.I)


def save_promises(base, text):
    """Разбирает строки «ГОТОВО-КОГДА: файл …» и «ГОТОВО-КОГДА: команда …»."""
    files, cmds = [], []
    for kind, val in PROMISE_LINE.findall(text or ""):
        val = val.strip().strip("`")
        if not val:
            continue
        if kind.lower().startswith("файл"):
            files.append(val)
        else:
            cmds.append(val)
    if not files and not cmds:
        return
    d = load(PROMISES_PATH, {}) or {}
    d[base] = {"files": files[:40], "commands": cmds[:5],
               "at": time.strftime("%Y-%m-%d %H:%M")}
    save(PROMISES_PATH, d)
    log("PROMISES %r: файлов %d, команд %d" % (base[:40], len(files), len(cmds)))


def record_promise_delivery_state(base, state):
    """Expose a short operator-facing delivery state without Git internals."""
    promises = load(PROMISES_PATH, {}) or {}
    item = promises.get(base)
    if not isinstance(item, dict):
        return
    item["delivery_status"] = state
    promises[base] = item
    save(PROMISES_PATH, promises)


GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def pinned_review_range(base_sha, candidate_sha):
    """Build the only revision range allowed to define Review's scope."""
    if not GIT_SHA.fullmatch(str(base_sha or "")):
        raise ValueError("invalid pinned review base")
    if not GIT_SHA.fullmatch(str(candidate_sha or "")):
        raise ValueError("invalid pinned review candidate")
    return str(base_sha) + "..." + str(candidate_sha)


def _remote_url(repo_identity):
    """Return the canonical read-only URL without looking at a worker checkout."""
    if str(repo_identity or "").startswith(("file://", "http://", "https://", "ssh://")):
        return str(repo_identity)
    short = (repo_identity or "").split("github.com/")[-1].strip("/")
    return f"https://github.com/{short}.git" if short and "/" in short else ""


def _default_branch(url):
    """Resolve the remote's symbolic HEAD; never assume that it is `main`."""
    rc, out = _git(None, "ls-remote", "--symref", url, "HEAD")
    if rc:
        return "", "cannot resolve remote default branch: " + out.strip()[:240]
    match = re.search(r"^ref:\s+refs/heads/([^\s]+)\s+HEAD$", out, re.M)
    if not match:
        return "", "remote did not advertise a default branch"
    return match.group(1), ""


def fresh_branch_snapshot(repo_identity, branch):
    """Fetch and pin the exact remote base and candidate in an isolated repo.

    This is deliberately independent of a retained worker worktree: cached
    refs can be stale and a review must never checkout, switch, or reset the
    branch that belongs to the worker.  A caller may only use the returned
    immutable SHA values for ancestry and diff decisions.
    """
    url = _remote_url(repo_identity)
    if not url or not branch:
        return {"state": "blocked", "reason": "missing repository or candidate branch"}
    default, error = _default_branch(url)
    if error:
        return {"state": "blocked", "reason": error}
    try:
        with tempfile.TemporaryDirectory(prefix="factory-review-") as work:
            rc, out = _git(work, "init", "-q")
            if rc:
                return {"state": "blocked", "reason": "cannot create review repository: " + out[:180]}
            rc, out = _git(work, "remote", "add", "origin", url)
            if rc:
                return {"state": "blocked", "reason": "cannot configure review remote: " + out[:180]}
            # A separate ls-remote lets a genuinely missing delivery remain a
            # delivery issue while every resolution/fetch failure is BLOCKED.
            rc, heads = _git(work, "ls-remote", "--heads", "origin", "refs/heads/" + branch)
            if rc:
                return {"state": "blocked", "reason": "cannot resolve candidate branch: " + heads[:180]}
            if not heads.strip():
                return {"state": "missing", "default_branch": default}
            refs = ["+refs/heads/%s:refs/remotes/origin/%s" % (default, default)]
            if branch != default:
                refs.append("+refs/heads/%s:refs/remotes/origin/%s" % (branch, branch))
            rc, out = _git(work, "fetch", "--prune", "origin", *refs)
            if rc:
                return {"state": "blocked", "reason": "cannot fetch authoritative refs: " + out[:240]}
            rc, base_sha = _git(work, "rev-parse", "refs/remotes/origin/" + default)
            if rc:
                return {"state": "blocked", "reason": "cannot pin fetched base: " + base_sha[:180]}
            rc, candidate_sha = _git(work, "rev-parse", "refs/remotes/origin/" + branch)
            if rc:
                return {"state": "blocked", "reason": "cannot pin fetched candidate: " + candidate_sha[:180]}
            base_sha, candidate_sha = base_sha.strip(), candidate_sha.strip()
            if not GIT_SHA.fullmatch(base_sha) or not GIT_SHA.fullmatch(candidate_sha):
                return {"state": "blocked", "reason": "remote returned an invalid commit SHA"}
            review_range = pinned_review_range(base_sha, candidate_sha)
            # A published candidate can legitimately have been cut before the
            # default branch advanced.  It is still reviewable from their
            # shared merge-base; only genuinely unrelated histories block it.
            rc, merge_base_sha = _git(work, "merge-base", base_sha, candidate_sha)
            if rc:
                return {"state": "blocked", "reason": "base and candidate have unrelated history"}
            merge_base_sha = merge_base_sha.strip()
            if not GIT_SHA.fullmatch(merge_base_sha):
                return {"state": "blocked", "reason": "cannot pin shared merge base"}
            rc, out = _git(work, "diff", "--name-only", review_range)
            if rc:
                return {"state": "blocked", "reason": "cannot calculate pinned delivery scope: " + out[:180]}
            rc, ahead = _git(work, "rev-list", "--count", merge_base_sha + ".." + candidate_sha)
            if rc:
                return {"state": "blocked", "reason": "cannot calculate pinned delivery distance: " + ahead[:180]}
            rc, base_ahead = _git(work, "rev-list", "--count", merge_base_sha + ".." + base_sha)
            if rc:
                return {"state": "blocked", "reason": "cannot classify default branch advancement: " + base_ahead[:180]}
            return {"state": "ok", "default_branch": default, "base_sha": base_sha,
                    "candidate_sha": candidate_sha, "merge_base_sha": merge_base_sha,
                    "base_advanced": merge_base_sha != base_sha,
                    "base_ahead_by": int(base_ahead.strip()),
                    "files": [p for p in out.splitlines() if p][:80],
                    "ahead_by": int(ahead.strip())}
    except Exception as e:
        return {"state": "blocked", "reason": "review snapshot failed: " + str(e)[:240]}


def branch_report(repo_identity, branch):
    """Legacy GitHub reporting seam used outside the authoritative Review path."""
    repo = repo_identity.split("github.com/")[-1]
    if not repo or not branch:
        return "", []
    b = gh_json(["api", f"repos/{repo}/branches/{branch}"], strict=True)
    if b is None:
        return "нет", []
    cmp_ = gh_json(["api", f"repos/{repo}/compare/main...{branch}"], strict=True)
    files = [f.get("filename") for f in (cmp_ or {}).get("files", [])][:80]
    return "есть", files


IMPLEMENTATION_COMMIT_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?Implementation commit:\s*`?([0-9a-f]{40})`?\s*[—-]\s*\S",
    re.M)
CARD_IMPLEMENTED_STATUS_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?Status:\s*Implemented(?:\s+[—-].*)?\s*$",
    re.I | re.M)
CARD_HEAD_SECTION = re.compile(r"^## HEAD\s*$([\s\S]*?)(?=^## |\Z)", re.M)
CARD_LINE = re.compile(r"^Card:\s*(CARD-\d{4,})\s*$", re.M)
SPECIFICATION_HEAD_LINE = re.compile(r"^HEAD:\s*([0-9a-f]{40})\s*$", re.M)
CARD_FILE_NUMBER = re.compile(r"^CARD-(\d+)\b")
CARD_RESERVATIONS_KEY = "card_reservations"


def reserved_card_number(state, repo_identity, branch):
    """Reserve one card number for a published branch, durably and idempotently.

    The Pilot has one state writer, so saving before task creation makes this a
    small transaction: a failed create may leave a gap but can never reuse a
    number for another branch.
    """
    if not repo_identity or not branch:
        return None
    reservations = state.get(CARD_RESERVATIONS_KEY, {})
    if not isinstance(reservations, dict):
        reservations = {}
    key = repo_identity + "::" + branch
    reserved = reservations.get(key)
    if isinstance(reserved, int) and reserved > 0:
        return f"CARD-{reserved:04d}"

    repo = repo_identity.split("github.com/")[-1]
    cards = gh_json(["api", f"repos/{repo}/contents/knowledge/cards?ref=main"])
    if not isinstance(cards, list):
        return None
    existing = [int(match.group(1)) for item in cards if isinstance(item, dict)
                for match in [CARD_FILE_NUMBER.match(str(item.get("name") or ""))]
                if match]
    local = [number for reserve_key, number in reservations.items()
             if reserve_key.startswith(repo_identity + "::")
             and isinstance(number, int) and number > 0]
    number = max(existing + local + [0]) + 1
    state[CARD_RESERVATIONS_KEY] = reservations
    reservations[key] = number
    save(STATE_PATH, state)
    return f"CARD-{number:04d}"


def extract_card(result, prev_context):
    """Keep the reservation as a pipeline identity through every handoff."""
    # The context is the durable pipeline identity.  A later agent report can
    # repeat it, but must not silently replace it with a different card.
    match = CARD_LINE.search(prev_context or "") or CARD_LINE.search(result or "")
    return match.group(1) if match else ""


def extract_specification_head(result):
    """Carry the exact published Specification revision into Implement."""
    match = SPECIFICATION_HEAD_LINE.search(result or "")
    return match.group(1) if match else ""


def specification_head_gate(result):
    """Require the exact full SHA before Specification can create Implement."""
    if SPECIFICATION_HEAD_LINE.search(result or ""):
        return None
    if not re.search(r"^HEAD:\s*\S+\s*$", result or "", re.M):
        reason = "отсутствует строка HEAD"
    else:
        reason = "строка HEAD должна содержать ровно 40 hex-символов"
    return ("Спецификацию нельзя передать в разработку: " + reason + ". "
            "Повтори Specification и укажи точный полный SHA опубликованного коммита.")


def implementation_commit_gate(repo_identity, branch, files):
    """Validate the stable code-commit evidence in every delivered card.

    A card is itself committed after the implementation.  Comparing its field
    to the moving branch tip therefore creates an impossible Review loop.  The
    GitHub API lets the cheap gate instead prove three stable facts: the label
    exists, its commit is an ancestor of this branch, and that commit changed
    something other than a knowledge card.  Transport failures remain
    non-blocking, like the rest of the pre-Review GitHub gate.
    """
    cards = [path for path in files if path.startswith("knowledge/cards/") and path.endswith(".md")]
    if not cards:
        return {"back": True, "note": (
            "Машинная проверка перед Ревью: в поставке нет отдельной карточки "
            "знаний в knowledge/cards/. Создай её и укажи стабильную строку "
            "Implementation commit: <полный SHA> — <что реализовано>.")}
    repo = repo_identity.split("github.com/")[-1]
    if not repo:
        return None
    for path in cards:
        encoded_branch = urllib.parse.quote(branch, safe="")
        data = gh_json(["api", f"repos/{repo}/contents/{path}?ref={encoded_branch}"])
        if not isinstance(data, dict) or not data.get("content"):
            return None
        try:
            body = base64.b64decode(data["content"]).decode("utf-8")
        except (ValueError, UnicodeDecodeError, TypeError):
            return {"back": True, "note": f"Машинная проверка: карточка {path} повреждена или не читается как UTF-8."}
        head = CARD_HEAD_SECTION.search(body)
        if not head or not CARD_IMPLEMENTED_STATUS_LINE.search(head.group(1)):
            return {"back": True, "note": (
                f"Машинная проверка: в опубликованной карточке {path} нет строки "
                "`Status: Implemented` в HEAD. Верни работу в Implement и обнови "
                "статус только после успешной реализации и тестов.")}
        match = IMPLEMENTATION_COMMIT_LINE.search(body)
        if not match:
            return {"back": True, "note": (
                f"Машинная проверка: в карточке {path} нет строки `Implementation commit: "
                "<полный SHA> — <что реализовано>`. `Head commit` не подходит: "
                "финальная запись карточки меняет HEAD.")}
        commit = match.group(1)
        compare = gh_json(["api", f"repos/{repo}/compare/{commit}...{encoded_branch}"])
        if not isinstance(compare, dict):
            return None
        if compare.get("status") not in ("ahead", "identical"):
            return {"back": True, "note": (
                f"Машинная проверка: Implementation commit {commit} из {path} "
                "не является коммитом этой ветки. Укажи реальный коммит реализации.")}
        # `identical` proves that the claimed code commit is the card commit
        # itself, so it cannot be the required predecessor.
        if compare.get("status") != "ahead":
            return {"back": True, "note": (
                f"Машинная проверка: Implementation commit {commit} совпадает с вершиной "
                "ветки. Сначала закоммить код, затем отдельным коммитом карточку.")}
        details = gh_json(["api", f"repos/{repo}/commits/{commit}"])
        changed = (details or {}).get("files") if isinstance(details, dict) else None
        if not isinstance(changed, list):
            return None
        if not any(isinstance(item, dict) and not str(item.get("filename") or "").startswith("knowledge/cards/")
                   for item in changed):
            return {"back": True, "note": (
                f"Машинная проверка: Implementation commit {commit} меняет только карточки. "
                "Укажи существующий коммит с реализацией кода до карточки.")}
    return None


REBUILD_DIR = f"{HOME}/pilot/rebuild"


def _git(cwd, *args, timeout=180, input_text=None):
    env = dict(os.environ, HOME=HOME, GIT_TERMINAL_PROMPT="0")
    p = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       text=True, timeout=timeout, env=env, input=input_text)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def refresh_stale_branch(repo_identity, branch):
    """Bring a published candidate onto the current default branch before Review.

    A candidate can wait behind an overlapping work for hours.  Letting that
    stale head pass Review and Verify only discovers a predictable merge
    conflict after all expensive checks have run.  Merge the freshly fetched
    default branch into the same candidate instead: this preserves the
    implementation commit recorded by the card and makes a concurrent remote
    update fail safely at push time.
    """
    url = _remote_url(repo_identity)
    if not url or not branch:
        return {"state": "blocked", "reason": "missing repository or candidate branch"}
    default, error = _default_branch(url)
    if error:
        return {"state": "blocked", "reason": error}
    try:
        with tempfile.TemporaryDirectory(prefix="factory-refresh-") as work:
            for args in (("init", "-q"),
                         ("remote", "add", "origin", url),
                         ("fetch", "--prune", "origin",
                          "+refs/heads/" + default + ":refs/remotes/origin/" + default,
                          "+refs/heads/" + branch + ":refs/remotes/origin/" + branch),
                         ("checkout", "-q", "-B", "candidate", "origin/" + branch)):
                rc, out = _git(work, *args)
                if rc:
                    return {"state": "blocked", "reason": (
                        "cannot prepare stale candidate refresh: " + out.strip()[:240])}
            rc, old_head = _git(work, "rev-parse", "HEAD")
            if rc or not GIT_SHA.fullmatch(old_head.strip()):
                return {"state": "blocked", "reason": "cannot pin stale candidate head"}
            old_head = old_head.strip()
            rc, out = _git(work, "-c", "user.name=Factory Pilot",
                           "-c", "user.email=pilot@factory", "merge", "--no-edit",
                           "refs/remotes/origin/" + default)
            if rc:
                _git(work, "merge", "--abort")
                return {"state": "conflict", "reason": out.strip()[:400]}
            rc, new_head = _git(work, "rev-parse", "HEAD")
            if rc or not GIT_SHA.fullmatch(new_head.strip()):
                return {"state": "blocked", "reason": "cannot pin refreshed candidate head"}
            new_head = new_head.strip()
            if new_head != old_head:
                rc, out = _git(work, "push", "origin",
                               "HEAD:refs/heads/" + branch)
                if rc:
                    return {"state": "blocked", "reason": (
                        "candidate changed while it was being refreshed: "
                        + out.strip()[:240])}
            snapshot = fresh_branch_snapshot(repo_identity, branch)
            if snapshot.get("state") != "ok":
                return {"state": "blocked", "reason": snapshot.get("reason")
                        or "refreshed candidate is not published"}
            if snapshot.get("base_advanced"):
                return {"state": "blocked", "reason": (
                    "default branch advanced again while candidate was being refreshed")}
            return {"state": "ok", "branch": branch, "snapshot": snapshot}
    except Exception as e:
        return {"state": "blocked", "reason": "candidate refresh failed: " + str(e)[:240]}


def rebuild_clean_branch(repo_identity, dirty_branch, keep_files, base, area_repo=""):
    """Собрать ветку от свежей главной, сохранив весь diff задачи.

    Переносим патч, а не снимок файлов: так сохраняются удаления и все hunks
    задачи.  До push сверяем итоговый трёхточечный diff с исходным списком —
    карточка знаний не может молча заменить пропавший файл реализации.
    """
    if not (repo_identity and dirty_branch and keep_files):
        return ""
    url = _remote_url(repo_identity)
    if not url:
        return ""
    os.makedirs(REBUILD_DIR, exist_ok=True)
    work = f"{REBUILD_DIR}/{re.sub(chr(91) + '^a-zA-Z0-9' + chr(93), '_', dirty_branch)[:60]}"
    try:
        if os.path.isdir(work):
            subprocess.run(["rm", "-rf", work], timeout=60)
        rc, out = _git(REBUILD_DIR, "init", "-q", work)
        if rc:
            log("rebuild: init " + out[:120]); return ""
        default, error = _default_branch(url)
        if error:
            log("rebuild: " + error[:160]); return ""
        for args in (("remote", "add", "origin", url),
                     ("fetch", "origin",
                      "+refs/heads/" + default + ":refs/remotes/origin/" + default),
                     ("fetch", "origin",
                      "+refs/heads/" + dirty_branch + ":refs/remotes/origin/" + dirty_branch)):
            rc, out = _git(work, *args)
            if rc:
                log("rebuild: " + args[0] + " " + out[:160]); return ""
        clean = dirty_branch + "-clean"
        rc, out = _git(work, "checkout", "-q", "-B", clean, "origin/" + default)
        if rc:
            log("rebuild: base " + out[:160]); return ""
        selected = sorted(set(keep_files))
        rc, source = _git(work, "diff", "--name-only",
                          "origin/" + default + "...origin/" + dirty_branch, "--", *selected)
        if rc:
            log("rebuild: source diff " + source[:160]); return ""
        expected = {p.strip() for p in source.splitlines() if p.strip()}
        if not expected:
            log("rebuild: ни один файл области не перенесён"); return ""
        rc, patch = _git(work, "diff", "--binary",
                         "origin/" + default + "...origin/" + dirty_branch, "--", *sorted(expected))
        if rc or not patch:
            log("rebuild: patch " + patch[:160]); return ""
        rc, out = _git(work, "apply", "--index", "--3way", "-",
                       input_text=patch)
        if rc:
            log("rebuild: apply " + out[:200]); return ""
        rc, out = _git(work, "-c", "user.name=Factory Pilot",
                       "-c", "user.email=pilot@factory", "commit", "-q", "-m",
                       "Пересобрано машиной от свежей главной: " + base[:90])
        if rc:
            log("rebuild: commit " + out[:160]); return ""
        rc, final = _git(work, "diff", "--name-only", "origin/" + default + "...HEAD")
        if rc:
            log("rebuild: final diff " + final[:160]); return ""
        final_paths = {p.strip() for p in final.splitlines() if p.strip()}
        missing = sorted(expected - final_paths)
        if missing:
            log("rebuild: пропали обещанные файлы: " + ", ".join(missing)[:240])
            return ""
        rc, out = _git(work, "push", "-q", "--force-with-lease", "origin",
                       "HEAD:" + clean)
        if rc:
            log("rebuild: push " + out[:200]); return ""
        area_replace(base, final_paths, area_repo or repo_identity)
        log(f"REBUILD OK: {clean} собрана от главной, файлов {len(final_paths)}")
        return clean
    except Exception as e:
        log("rebuild_error", repr(e))
        return ""
    finally:
        try:
            subprocess.run(["rm", "-rf", work], timeout=60)
        except Exception:
            pass


def rebuild_stale_delivery(repo_identity, base, promised_files, area_repo=""):
    """Rebuild a stale delivery only from its verified implementation artifact.

    A delivery branch is not a source of truth: it may have been published
    before the default branch advanced.  The durable implementation artifact
    is the only branch allowed to supply the promised paths.
    """
    artifact = implementation_artifact(base)
    if not artifact or not promised_files:
        return {"state": "unavailable"}
    source = fresh_branch_snapshot(repo_identity, artifact["branch"])
    if source.get("state") != "ok":
        return {"state": "blocked", "reason": source.get("reason") or "cannot fetch implementation artifact"}
    if source.get("candidate_sha") != artifact["head"]:
        return {"state": "unavailable"}
    if not set(promised_files).issubset(set(source.get("files") or [])):
        return {"state": "unavailable"}
    clean = rebuild_clean_branch(repo_identity, artifact["branch"], promised_files,
                                 base, area_repo=area_repo)
    if not clean:
        return {"state": "blocked", "reason": "cannot rebuild delivery from implementation artifact"}
    rebuilt = fresh_branch_snapshot(repo_identity, clean)
    if rebuilt.get("state") != "ok":
        return {"state": "blocked", "reason": rebuilt.get("reason") or "rebuilt candidate is not published"}
    if not set(promised_files).issubset(set(rebuilt.get("files") or [])):
        return {"state": "blocked", "reason": "rebuilt candidate lost promised paths"}
    return {"state": "ok", "branch": clean, "snapshot": rebuilt}


def review_gate(conf, base, branch, repo_identity, active_tasks=None, area_repo="",
                expected_card=""):
    """Create Review context only from a freshly fetched, pinned snapshot."""
    snapshot = fresh_branch_snapshot(repo_identity, branch)
    if snapshot.get("state") == "blocked":
        reason = snapshot.get("reason") or "unknown review infrastructure failure"
        log("REVIEW BLOCKED " + repr(reason))
        return {"blocked": True, "note": (
            "BLOCKED: review infrastructure. Невозможно получить свежую основную "
            "ветку или зафиксировать SHA до проверки; возврат на доработку не создавался. "
            "Причина: " + reason)}
    else:
        state_ = "нет" if snapshot.get("state") == "missing" else "есть"
    files = snapshot.get("files") or []
    if state_ == "нет":
        note_cap = cap_rescues(base, "GATE")
        if note_cap >= 2:
            return None  # дважды возвращали за то же — пусть решает Ревью
        log(f"GATE '{base}': ветка {branch!r} не запушена — возвращаю в разработку без Ревью")
        return {"back": True,
                "cap_stage": "GATE",
                "alert": "Вернул сам: разработка не загрузила работу",
                "alert_msg": ("Агент сказал «готово», но не загрузил свою работу "
                              "в хранилище — проверять нечего. Вернул в разработку "
                              "с инструкцией. Твоего участия не нужно."),
                "note": (f"Машинная проверка перед Ревью: ветки {branch} НЕТ в хранилище. "
                         "Работа, которой нет в хранилище, не существует — проверить её нельзя. "
                         "Сделай: git push -u origin " + (branch or "<ветка>") +
                         " и сдай заново. Ничего не переписывай, только запушь и проверь дифф.")}
    if state_ == "есть" and not files:
        return {"back": True, "note": (
            "Машинная проверка перед Ревью: закреплённое сравнение "
            f"{snapshot['base_sha']}...{snapshot['candidate_sha']} не содержит "
            "файлов реализации. Поставка пуста — добавь реализацию, запушь ветку "
            "и сдай работу заново.")}
    if state_ == "есть" and files:
        listing = "\n".join("  - " + f for f in files)

        if expected_card and not any(
                path.startswith("knowledge/cards/" + expected_card + "-")
                and path.endswith(".md") for path in files):
            return {"back": True, "note": (
                "Машинная проверка перед Ревью: для выданного номера "
                f"{expected_card} в поставке нет карточки "
                f"knowledge/cards/{expected_card}-<slug>.md. "
                "Не выбирай другой номер: создай карточку с выданным префиксом.")}

        implementation_gate = implementation_commit_gate(repo_identity, branch, files)
        if implementation_gate:
            implementation_gate.setdefault("alert", "Вернул сам: карточка не подтверждает реализацию")
            implementation_gate.setdefault("alert_msg", "Карточка должна ссылаться на настоящий коммит кода до своей финальной записи.")
            return implementation_gate

        # Не даём очистке маскировать уже потерянный обещанный код карточкой
        # или любым другим файлом. Проверяем исходную ветку до rebuild.
        prom = (load(PROMISES_PATH, {}) or {}).get(base) or {}
        if not isinstance(prom, dict):
            prom = {}
        promised_files = sorted(set(prom.get("files") or []))
        missing_promises = sorted(set(promised_files) - set(files))
        if missing_promises:
            # Only a branch genuinely left behind by the freshly pinned
            # default branch qualifies for recovery.  Empty, service, and
            # unverified sources deliberately keep the old safe return.
            if snapshot.get("base_advanced"):
                rebuilt = rebuild_stale_delivery(repo_identity, base, promised_files,
                                                 area_repo=area_repo)
                if rebuilt.get("state") == "blocked":
                    return {"blocked": True, "note": (
                        "BLOCKED: review infrastructure. Отставшую поставку нельзя "
                        "безопасно пересобрать и заново закрепить перед Review. Причина: "
                        + rebuilt.get("reason", "unknown rebuild failure"))}
                if rebuilt.get("state") == "ok":
                    rebuilt_snapshot = rebuilt["snapshot"]
                    record_promise_delivery_state(base, "пересобрана и заново закреплена")
                    return {"back": False, "branch": rebuilt["branch"],
                            "head": rebuilt_snapshot["candidate_sha"],
                            "note": ("Отставшая ветка поставки пересобрана из подтверждённой "
                                     "реализации только по обещанным файлам и заново закреплена "
                                     "перед Review.")}
            log(f"GATE '{base}': нет обещанных файлов: " + ", ".join(missing_promises))
            return {"back": True,
                    "alert": "Вернул сам: исчез обещанный файл реализации",
                    "alert_msg": ("Ветка не содержит все файлы, обещанные спецификацией; "
                                  "документация не заменяет реализацию."),
                    "note": ("Машинная проверка перед Ревью: в исходной ветке "
                             "нет обещанных файлов:\n"
                             + "\n".join("  - " + f for f in missing_promises)
                             + "\nВосстанови реализацию в этой же ветке, запушь и сдай снова.")}

        # Область: файлы вне заявленной зоны — возврат кодом, без Ревью.
        known = load(AREAS_PATH, {}) or {}
        mine = {p.split("::", 1)[1] if "::" in p else p
                for p in known.get(base) or []}
        alien = other_areas(base, active_tasks, area_repo or repo_identity)
        overlaps = sorted(f for f in files if f in alien)
        noise = sorted(f for f in files if any(n in f for n in NOISE_PATHS))
        if overlaps:
            # Нельзя «разрулить» настоящее пересечение удалением файлов из
            # одной ветки: это как раз и теряет готовую реализацию. Замок
            # остаётся строгим — ждём, пока соседняя живая работа освободит
            # область, затем пересчитаем её по фактическому diff.
            holder = "другая живая работа"
            for t in active_tasks or []:
                m = STAGE_TITLE_RE.match(t.get("title", ""))
                if (t.get("state") in ("running", "queued") and m
                        and m.group(2).strip() != base
                        and set(overlaps) & {p.split("::", 1)[1] if "::" in p else p
                                             for p in known.get(m.group(2).strip()) or []}):
                    holder = m.group(2).strip()
                    break
            log(f"AREA WAIT {base!r} ждёт: пересечение с {holder!r}: "
                + ", ".join(overlaps)[:160])
            return {"wait": True,
                    "note": "Жду завершения пересекающейся работы: " + holder}

        foreign = noise
        if foreign:
            keep = [f for f in files if f not in set(foreign)]
            kwargs = {"area_repo": area_repo} if area_repo else {}
            clean = rebuild_clean_branch(repo_identity, branch, keep, base, **kwargs)
            if clean:
                if not _remote_url(repo_identity):
                    # Preserve the narrow legacy unit-test seam. Real
                    # repositories always pin the published rebuild below.
                    return {"back": False, "branch": clean,
                            "note": ("Ветка пересобрана машиной от свежей главной: "
                                     "проверяй ветку " + clean + ".")}
                clean_snapshot = fresh_branch_snapshot(repo_identity, clean)
                if clean_snapshot.get("state") != "ok":
                    reason = (clean_snapshot.get("reason")
                              or "rebuilt candidate branch is not published")
                    return {"blocked": True, "note": (
                        "BLOCKED: review infrastructure. Пересобранная ветка создана, "
                        "но закрепить её SHA перед Review не удалось. Причина: " + reason)}
                return {"back": False, "branch": clean,
                        "head": clean_snapshot["candidate_sha"],
                        "note": ("Ветка пересобрана машиной от свежей главной: "
                                 "в поставке остались только файлы области "
                                 "(" + ", ".join(sorted(mine))[:400] + "). "
                                 "Проверяй ветку " + clean + ".")}
        if foreign and cap_rescues(base, "DIRT") < 1:
            log(f"GATE '{base}': {len(foreign)} файлов вне области — возвращаю без Ревью")
            return {"back": True,
                    "cap_stage": "DIRT",
                    "alert": "Вернул сам: в поставке чужие файлы",
                    "alert_msg": ("В работе оказались файлы, не относящиеся к задаче "
                                  "(%d шт.) — вернул в разработку с точным списком, "
                                  "что убрать. Твоего участия не нужно." % len(foreign)),
                    "rebuild": True,
                    "note": ("Ветку НЕ чисти по файлу — собери заново от свежей главной "
                             "(git fetch origin main; git reset --hard origin/main; "
                             "затем git checkout <старая ветка> -- <только свои файлы>). "
                             "Машинная проверка перед Ревью: в поставке файлы ВНЕ "
                             "заявленной области работы:\n"
                             + "\n".join("  - " + f for f in foreign)
                             + "\nЗаявленная область:\n"
                             + "\n".join("  - " + f for f in sorted(mine))
                             + "\nУбери чужое из ветки: git checkout origin/main -- <файл>; "
                             "запушь и сдай снова. Если область расширилась осознанно — "
                              "напиши в отчёте новую строку ОБЛАСТЬ: с полным списком и почему.")}

        # An area lock can keep a finished implementation waiting while main
        # moves underneath it.  Refresh only after the overlap has cleared;
        # otherwise two works could mutate the shared area concurrently.
        if snapshot.get("base_advanced"):
            refreshed = refresh_stale_branch(repo_identity, branch)
            if refreshed.get("state") == "conflict":
                return {"back": True,
                        "alert": "Вернул сам: ветка конфликтует со свежей основной",
                        "alert_msg": ("Пока работа ждала, основная ветка изменилась в тех же "
                                      "местах. Конфликт нужно устранить до Ревью."),
                        "note": ("Машинная проверка перед Ревью: ветка отстала от основной "
                                 "и не объединяется автоматически. Подтяни свежую основную "
                                 "ветку в эту же ветку, разреши конфликт, прогони целевые "
                                 "тесты, запушь и сдай снова.")}
            if refreshed.get("state") != "ok":
                return {"blocked": True, "note": (
                    "BLOCKED: review infrastructure. Отставшую ветку нельзя безопасно "
                    "обновить перед Review. Причина: "
                    + refreshed.get("reason", "unknown refresh failure"))}
            snapshot = refreshed["snapshot"]
            files = snapshot.get("files") or []
            listing = "\n".join("  - " + f for f in files)
            missing_after_refresh = sorted(set(promised_files) - set(files))
            if missing_after_refresh:
                return {"blocked": True, "note": (
                    "BLOCKED: review infrastructure. После обновления ветки исчезли "
                    "обещанные файлы:\n"
                    + "\n".join("  - " + f for f in missing_after_refresh))}

        # Обещания: что Спецификация записала как «готово, когда».
        missing = [f for f in (prom.get("files") or []) if f not in files]
        prom_note = ""
        if prom.get("files") or prom.get("commands"):
            prom_note = "\nОбещания Спецификации («готово, когда»):"
            for f in prom.get("files") or []:
                mark = "НЕ ТРОНУТ!" if f in missing else "есть в поставке"
                prom_note += f"\n  - файл {f} — {mark}"
            for c in prom.get("commands") or []:
                prom_note += f"\n  - команда должна пройти: {c} — ПРОГОНИ ЕЁ и покажи вывод"
            if missing:
                prom_note += ("\nОбещанные, но не тронутые файлы — повод вернуть работу, "
                              "если в отчёте нет внятного объяснения.")

        base_status = ("Основная ветка продвинулась после публикации кандидата "
                       f"на {snapshot['base_ahead_by']} коммит(а); область остаётся "
                       "вычисленной от общего merge-base. "
                       if snapshot.get("base_advanced") else "")
        return {"back": False,
                "head": snapshot["candidate_sha"],
                "note": (f"Машинная проверка: ветка {branch} в хранилище ЕСТЬ. "
                         "Проверяется свежая remote-основа "
                         f"{snapshot.get('default_branch', 'unknown')} (base_sha={snapshot['base_sha']}, "
                         f"candidate_sha={snapshot['candidate_sha']}, "
                         f"merge_base_sha={snapshot.get('merge_base_sha', 'unknown')}, ahead_by={snapshot.get('ahead_by', 'unknown')}). "
                         + base_status
                         + f"Файлы в поставке по pinned SHA ({len(files)}):\n{listing}"
                         + prom_note + "\n"
                         "Сверяй записку с этим списком, а не с памятью. "
                         "Возвращай работу только по правилам из инструкций: чужие файлы, "
                         "нет заявленного поведения, сломано работавшее. "
                         "Формулировки в записке — не повод для возврата.")}
    return None


def verify_gate(repo_identity, branch):
    """Pin the published delivery again before Verify can trigger a merge.

    Review's snapshot is intentionally short-lived: the candidate may be
    force-pushed or the default branch may advance while Verify is running.
    A failed refresh is an infrastructure BLOCKED result, never permission to
    merge the last cached or reported SHA.
    """
    snapshot = fresh_branch_snapshot(repo_identity, branch)
    if snapshot.get("state") == "ok":
        return {"ok": True, "snapshot": snapshot}
    if snapshot.get("state") == "missing":
        reason = "candidate branch is no longer published"
    else:
        reason = snapshot.get("reason") or "unknown review infrastructure failure"
    return {"blocked": True, "note": (
        "BLOCKED: review infrastructure. Невозможно заново получить свежую "
        "основную ветку и закрепить SHA Verify до слияния. Причина: " + reason)}


# ------------------------------------------------- настоящие лимиты подписок ---
# Кодекс пишет остаток лимита в журнал каждой сессии (used_percent, окно,
# время сброса). Антропик отвечает на служебную точку, которой пользуется
# сам Claude Code, но пускает не чаще раза в час. Пилот собирает обе цифры
# в pilot/provider_limits.json и будит хозяина на 80% и 95%.
PROVIDER_LIMITS_PATH = f"{HOME}/pilot/provider_limits.json"


def codex_real_limits():
    """Последний снимок лимита из журналов кодекса. Ничего не спрашивает
    у сети — читает то, что кодекс уже записал сам."""
    import glob
    newest = None
    for f in glob.glob(HOME + "/.codex-*/sessions/*/*/*/rollout-*.jsonl"):
        m = os.path.getmtime(f)
        if not newest or m > newest[0]:
            newest = (m, f)
    if not newest:
        return None
    hit = None
    try:
        for line in io.open(newest[1], encoding="utf-8", errors="ignore"):
            if "rate_limit" in line:
                hit = line
    except Exception:
        return None
    if not hit:
        return None

    def find(o):
        if isinstance(o, dict):
            if "rate_limits" in o:
                return o["rate_limits"]
            for v in o.values():
                r = find(v)
                if r is not None:
                    return r
        if isinstance(o, list):
            for v in o:
                r = find(v)
                if r is not None:
                    return r
        return None

    try:
        rl = find(json.loads(hit))
    except Exception:
        return None
    if not rl:
        return None
    pri = rl.get("primary") or {}
    return {"used_percent": pri.get("used_percent"),
            "window_minutes": pri.get("window_minutes"),
            "resets_at": pri.get("resets_at"),
            "plan": rl.get("plan_type"),
            "source": os.path.basename(newest[1])[:40],
            "at": int(newest[0])}


def claude_real_limits(prev):
    """Остаток подписки Антропика. Точка пускает редко, поэтому не чаще
    раза в 65 минут; между опросами живём на прошлом ответе."""
    now = int(time.time())
    if prev and now - int(prev.get("asked_at") or 0) < 3900:
        return prev
    tok = ""
    try:
        cp = HOME + "/.claude/.credentials.json"
        cred = json.load(io.open(cp))
        o = cred.get("claudeAiOauth") or {}
        if int(o.get("expiresAt") or 0) / 1000 > now + 60:
            tok = o.get("accessToken") or ""
        elif o.get("refreshToken"):
            # срок ключа вышел — обновляем сами, как официальный клиент
            body = json.dumps({"grant_type": "refresh_token",
                               "refresh_token": o.get("refreshToken"),
                               "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e"}).encode()
            rq = urllib.request.Request(
                "https://platform.claude.com/v1/oauth/token", data=body,
                headers={"content-type": "application/json",
                         "User-Agent": "claude-code/2.0.0 (external, cli)",
                         "Accept": "application/json"})
            with urllib.request.urlopen(rq, timeout=20) as rr:
                dd = json.loads(rr.read())
            o["accessToken"] = dd.get("access_token") or ""
            if dd.get("refresh_token"):
                o["refreshToken"] = dd["refresh_token"]
            o["expiresAt"] = int((now + int(dd.get("expires_in") or 3600)) * 1000)
            cred["claudeAiOauth"] = o
            io.open(cp, "w").write(json.dumps(cred))
            tok = o["accessToken"]
            log("CLAUDE TOKEN refreshed, живёт часов: " + str(int(dd.get("expires_in") or 0) // 3600))
    except Exception as e:
        log("claude_token_refresh_error " + repr(e)[:80])
    if not tok:
        try:
            for line in io.open(HOME + "/.claude/oauth.env"):
                if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
        except Exception:
            pass
    if not tok:
        return {"error": "нет токена", "asked_at": now}
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": "Bearer " + tok,
                 "anthropic-beta": "oauth-2025-04-20",
                 "User-Agent": "claude-code/2.0.0 (external, cli)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.loads(r.read())
    except Exception as e:
        out = {"error": str(e)[:120], "asked_at": now}
        if prev:
            for k in ("percents", "raw"):
                if prev.get(k) is not None:
                    out[k] = prev[k]
        return out
    percents = {}

    def dig(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                dig(v, (path + "." + str(k)).strip("."))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                dig(v, path + "[%d]" % i)
        elif isinstance(o, (int, float)):
            low = path.lower()
            if "util" in low or "percent" in low or "used" in low:
                percents[path] = o

    dig(raw)
    return {"percents": percents, "raw": raw, "asked_at": now}


def limits_alert(conf, name, used, resets_at):
    """Один раз на уровень в окно: 80 — предупреждение, 95 — тревога."""
    st = load(PROVIDER_LIMITS_PATH, {}) or {}
    marks = st.get("alerted") or {}
    key = "%s:%s" % (name, resets_at or "?")
    level = 95 if used >= 95 else (80 if used >= 80 else 0)
    if not level or marks.get(key, 0) >= level:
        return marks
    marks[key] = level
    left = ""
    if resets_at:
        hours = max(0, int(resets_at) - int(time.time())) // 3600
        left = " До сброса примерно %d ч." % hours
    notify(conf,
           ("Подписка почти сожжена: %s" % name) if level == 95
           else ("Подписка %s: израсходовано %d%%" % (name, int(used))),
           "Израсходовано %d%% лимита.%s" % (int(used), left),
           priority="high" if level == 95 else "default",
           tags="money_with_wings")
    return marks


def provider_limits_tick(conf):
    st = load(PROVIDER_LIMITS_PATH, {}) or {}
    cx = codex_real_limits()
    if cx:
        st["codex"] = cx
        if isinstance(cx.get("used_percent"), (int, float)):
            st["alerted"] = limits_alert(conf, "codex", cx["used_percent"],
                                         cx.get("resets_at"))
    if cx and isinstance(cx.get("used_percent"), (int, float)) and cx["used_percent"] >= 95:
        # Не ждём, пока агенты начнут падать: настоящий счётчик уже сказал,
        # что подписка на дне. Блокируем провайдера сами, до пожара.
        reset_iso = ""
        try:
            reset_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime(int(cx.get("resets_at") or 0)))
        except Exception:
            pass
        note_limit(conf, "codex",
                   "настоящий счётчик подписки: израсходовано %d%%" % int(cx["used_percent"]),
                   reset_iso)
    cl = claude_real_limits(st.get("claude"))
    if cl:
        st["claude"] = cl
        # Общий недельный счётчик подписки. Лимит ОТДЕЛЬНОЙ модели (например
        # Fable) не значит, что подписка кончилась: соседние модели живы.
        pc = cl.get("percents") or {}
        best = pc.get("seven_day.utilization")
        if not isinstance(best, (int, float)):
            best = max([v for v in pc.values()
                        if isinstance(v, (int, float)) and 0 <= v <= 100] or [0])
        if best:
            st["alerted"] = limits_alert(conf, "claude", best, None)
            if best >= 95:
                note_limit(conf, "claude",
                           "настоящий счётчик подписки: израсходовано %d%%" % int(best), "")
    st["checked"] = int(time.time())
    save(PROVIDER_LIMITS_PATH, st)


DIAG_PROMPT = (
    "Ты старший инженер фабрики. Работа буксует: этап прошёл {n} кругов подряд "
    "и каждый раз возвращался. Ниже — последние отчёты и ошибки стадий.\n\n"
    "Определи НАСТОЯЩУЮ причину: это дефект кода, поломка окружения (доступ, "
    "ключи, права, сеть), недостижимое требование или придирка проверяющего.\n\n"
    "Ответь строго JSON без пояснений:\n"
    "{{\"причина\": \"<одна фраза по-русски, для человека, без жаргона>\", "
    "\"решение\": \"<что сделать, одна-две фразы>\", "
    "\"нужен_владелец\": true|false}}\n\n"
    "нужен_владелец = true ТОЛЬКО если это про деньги, боевую систему, доступы "
    "владельца или выбор продукта. Всё остальное чинится без него.\n\n"
    "РАБОТА: {base}\n\nПОСЛЕДНЕЕ:\n{tail}")

DIAG_REPAIR_PATH = f"{HOME}/pilot/diagnosis_repairs.json"
TERMINAL_TASK_STATES = ("succeeded", "failed", "cancelled")


def _save_diag_repair(base, repair):
    repairs = load(DIAG_REPAIR_PATH, {}) or {}
    repairs[base] = repair
    save(DIAG_REPAIR_PATH, repairs)


def _fail_diag_repair(conf, base, repair, reason):
    repair["status"] = "failed"
    repair["failure"] = str(reason)[:500]
    _save_diag_repair(base, repair)
    log(f"DIAG REPAIR STOP base={base!r}: {repair['failure']}")
    notify(conf, "Автопочинка остановлена",
           f"{base}\n\nПричина: {repair['failure']}\n"
           "Повторно отменять или продолжать эту работу автоматически не буду.",
           priority="high", tags="warning", click=f"{UI_BASE}/work")


def _all_tasks_for_diag_repair():
    """Read every task page before making an irreversible repair decision."""
    tasks = []
    cursor = ""
    seen_cursors = set()
    while True:
        path = "/tasks?limit=200"
        if cursor:
            path += "&cursor=" + urllib.parse.quote(cursor, safe="")
        page = api(path)
        tasks.extend(page.get("tasks") or [])
        cursor = page.get("next_cursor") or ""
        if not cursor:
            return tasks
        if cursor in seen_cursors:
            raise RuntimeError("API повторил курсор списка задач")
        seen_cursors.add(cursor)


def begin_diag_repair(conf, base, stage, verdict, tasks, candidate):
    """Cancel one proven looping run. A later sweep resumes it after terminal state."""
    repairs = load(DIAG_REPAIR_PATH, {}) or {}
    if base in repairs:
        return False
    try:
        all_tasks = _all_tasks_for_diag_repair()
    except Exception as e:
        repair = {"status": "failed", "task_id": candidate.get("id", "")}
        _fail_diag_repair(conf, base, repair,
                          f"не удалось проверить все активные запуски: {e}")
        return False
    live = []
    live_ids = set()
    for task in all_tasks:
        if (base_title(task.get("title", "")) != base
                or task.get("state") not in ("running", "queued", "preparing")):
            continue
        task_id = task.get("id")
        if task_id and task_id in live_ids:
            continue
        live.append(task)
        if task_id:
            live_ids.add(task_id)
    candidate_state = candidate.get("state")
    running_candidate = (candidate_state == "running" and len(live) == 1
                         and live[0].get("id") == candidate.get("id"))
    terminal_candidate = (candidate_state in TERMINAL_TASK_STATES and not live)
    if not (running_candidate or terminal_candidate):
        reason = ("нельзя достоверно выбрать единственный выполняющийся запуск: "
                  f"найдено активных запусков — {len(live)}")
        repair = {"status": "failed", "task_id": candidate.get("id", ""),
                  "failure": reason}
        _save_diag_repair(base, repair)
        log(f"DIAG REPAIR SKIP base={base!r}: {reason}")
        notify(conf, "Автопочинка не начата", f"{base}\n\nПричина: {reason}",
               priority="high", tags="warning", click=f"{UI_BASE}/work")
        return False
    try:
        detail = api(f"/tasks/{candidate['id']}")
    except Exception as e:
        repair = {"status": "failed", "task_id": candidate["id"]}
        _fail_diag_repair(conf, base, repair,
                          f"не удалось прочитать зациклившийся запуск: {e}")
        return False
    task = detail.get("task") or {}
    workflow = detail.get("workflow") or {}
    branch = (extract_branch(detail.get("context") or task.get("context") or "", "")
              or branch_from_history(tasks, base))
    repair = {
        "status": "cancel_pending" if running_candidate else "resume_pending",
        "task_id": candidate["id"],
        "title": candidate.get("title", ""),
        "stage": stage,
        "repository_id": task.get("repository_id", ""),
        "worker_id": task.get("worker_id", ""),
        "workflow_revision_id": workflow.get("revision_id", ""),
        "context": (detail.get("context") or task.get("context") or "")[:20000],
        "branch": branch,
        "reason": str(verdict.get("причина") or "")[:1000],
        "solution": str(verdict.get("решение") or "")[:2000],
        "request_key": str(uuid.uuid4()),
    }
    required = {
        "название задачи": repair["title"],
        "репозиторий": repair["repository_id"],
        "исполнитель": repair["worker_id"],
        "версия процесса": repair["workflow_revision_id"],
        "прежняя ветка": repair["branch"],
    }
    missing = [label for label, value in required.items() if not value]
    if missing:
        _fail_diag_repair(
            conf, base, repair,
            "до отмены не удалось сохранить данные для безопасного продолжения: "
            + ", ".join(missing))
        return False
    # A failed run reaches this path from cycle() after it is already terminal;
    # no cancellation is needed and reconciliation may resume it immediately.
    if terminal_candidate:
        _save_diag_repair(base, repair)
        reconcile_diag_repairs(conf, tasks)
        return True
    # Persist before the HTTP call: after an uncertain response we must never
    # cancel a second time. Cancelling the same identified task is idempotent.
    _save_diag_repair(base, repair)
    try:
        api(f"/tasks/{candidate['id']}/cancel", {})
    except Exception as e:
        _fail_diag_repair(conf, base, repair,
                          f"отмена зациклившегося запуска не подтверждена: {e}")
        return False
    repair["status"] = "cancellation_requested"
    _save_diag_repair(base, repair)
    log(f"DIAG REPAIR CANCEL task={candidate['id']} base={base!r}")
    notify(conf, "Чиню застрявшую работу",
           f"{base}\n\nПричина: {cut(repair['reason'], 220)}\n"
           "Останавливаю только зациклившийся запуск; после его остановки "
           "один раз продолжу ту же работу.",
           tags="wrench", click=f"{UI_BASE}/work")
    return True


def reconcile_diag_repairs(conf, tasks):
    """Resume each diagnosed repair once, and only after its source is terminal."""
    repairs = load(DIAG_REPAIR_PATH, {}) or {}
    by_id = {t.get("id"): t for t in tasks}
    for base, repair in list(repairs.items()):
        status = repair.get("status")
        source = by_id.get(repair.get("task_id")) or {
            "id": repair.get("task_id"), "title": repair.get("title", "")
        }
        closed_reason = work_lifecycle_block(base, source, tasks)
        if closed_reason:
            repair["status"] = "closed"
            repair["closed_reason"] = closed_reason
            _save_diag_repair(base, repair)
            log(f"DIAG REPAIR CLOSED base={base!r}: {closed_reason}")
            continue
        if status == "cancel_pending":
            # A restart may happen after the control plane accepted the cancel
            # but before we persisted its result. Cancelling the same task is
            # idempotent, so replay the exact operation instead of abandoning
            # the repair in its durable transition state.
            try:
                api(f"/tasks/{repair['task_id']}/cancel", {})
            except Exception as e:
                _fail_diag_repair(conf, base, repair,
                                  f"отмена зациклившегося запуска не подтверждена: {e}")
                continue
            repair["status"] = "cancellation_requested"
            _save_diag_repair(base, repair)
            status = "cancellation_requested"
            log(f"DIAG REPAIR CANCEL RECOVERED task={repair['task_id']} base={base!r}")
        if status not in ("cancellation_requested", "resume_pending"):
            continue
        if status == "cancellation_requested":
            source = by_id.get(repair.get("task_id"))
            if not source:
                try:
                    detail = api(f"/tasks/{repair['task_id']}")
                    source = detail.get("task") or {}
                except Exception as e:
                    log(f"DIAG REPAIR SOURCE READ WAIT base={base!r}: {e}")
                    continue
            if source.get("state") not in TERMINAL_TASK_STATES:
                continue
        branch = repair.get("branch") or ""
        branch_note = ""
        if branch:
            branch_note = (
                f"\n\nПродолжай прежнюю ветку {branch}: оставайся на назначенной "
                f"ветке, выполни `git fetch origin {branch} && git reset --hard "
                "FETCH_HEAD`, затем внеси исправление и перед сдачей перебазируйся "
                "на свежий origin/main.")
        context = (
            repair.get("context", "")[:15000]
            + "\n\nАВТОМАТИЧЕСКИЙ РЕМОНТ ПОСЛЕ ТЕХНИЧЕСКОГО ЗАЦИКЛИВАНИЯ:\n"
            + "Причина: " + repair.get("reason", "") + "\n"
            + "Утверждённое исправление: " + repair.get("solution", "")
            + branch_note
        )[:20000]
        body = {
            "request_key": repair["request_key"],
            "title": repair.get("title", "")[:200],
            "context": context,
            "worker_id": repair.get("worker_id", ""),
            "repository_id": repair.get("repository_id", ""),
            "timeout_seconds": conf.get("timeout_seconds", 7200),
            "workflow_revision_id": repair.get("workflow_revision_id", ""),
        }
        # Persist before creation. After a restart, resume_pending replays this
        # exact body; the stable request key makes task creation idempotent.
        if status == "cancellation_requested":
            repair["status"] = "resume_pending"
            _save_diag_repair(base, repair)
        try:
            result = create_child_task(body, source, conf, "diagnostic_repair")
        except Exception as e:
            _fail_diag_repair(conf, base, repair,
                              f"одноразовое продолжение не удалось: {e}")
            continue
        repair["status"] = "resumed"
        repair["resumed_task_id"] = (result.get("task") or {}).get("id", "")
        _save_diag_repair(base, repair)
        log(f"DIAG REPAIR RESUMED base={base!r} task={repair['resumed_task_id']}")
        notify(conf, "Застрявшая работа продолжена",
               f"{base}\n\nЗапуск остановлен, найденное исправление передано "
               "в ту же работу. Повторного автопродолжения не будет.",
               tags="arrow_forward", click=f"{UI_BASE}/work")


def load_tasks_safe(limit=60):
    try:
        return api(f"/tasks?limit={limit}").get("tasks") or []
    except Exception:
        return []


def recent_stage_text(tasks, base, limit=3):
    """Последние отчёты и ошибки стадий этой работы — материал для разбора."""
    out = []
    for t in tasks:
        if base not in (t.get("title") or ""):
            continue
        if t.get("state") not in ("succeeded", "failed", "cancelled"):
            continue
        try:
            d = api(f"/tasks/{t['id']}")
        except Exception:
            continue
        atts = d.get("attempts") or []
        res = next((a.get("result") for a in reversed(atts) if a.get("result")), "") or ""
        err = next((a.get("error") for a in reversed(atts) if a.get("error")), "") or ""
        out.append(f"--- {t.get('title', '')[:80]} [{t.get('state')}]\n"
                   f"{squeeze(err, 800)}\n{squeeze(res, 1600)}")
        if len(out) >= limit:
            break
    return "\n\n".join(out)[:9000]


def deep_diagnose(conf, base, stage, rounds, tasks, repair_task=None):
    """Зовём сильную модель разобраться и говорим владельцу по-человечески.
    Один разбор на работу — дальше конвейер действует по найденному решению."""
    diag_already_counted = cap_rescues(base, "DIAG") >= 1
    # Repair tasks used to bypass this guard. As a result, every later stage
    # return paid for another senior diagnosis even though begin_diag_repair()
    # would refuse a second repair for the same work. The only safe exception
    # is a crash window where the DIAG marker exists but no durable repair was
    # ever recorded; then the terminal path must finish the promised first
    # repair once.
    if diag_already_counted:
        repairs = load(DIAG_REPAIR_PATH, {}) or {}
        if repair_task is None or base in repairs:
            return None
    if not diag_already_counted:
        note_cap_rescue(base, "DIAG")
    tail = recent_stage_text(tasks, base)
    try:
        text, eng = brain(conf, DIAG_PROMPT.format(n=rounds, base=base, tail=tail),
                          timeout=240)
        verdict = json.loads(text[text.find("{"):text.rfind("}") + 1])
    except Exception as e:
        log("diag_error", repr(e))
        return None
    why = str(verdict.get("причина") or "").strip()
    what = str(verdict.get("решение") or "").strip()
    owner = bool(verdict.get("нужен_владелец"))
    log(f"DIAG {base[:40]!r} кругов={rounds}: {why[:90]} | владелец={owner}")
    if owner:
        notify(conf, "Застряла — нужен ты",
               f"{base}\n\nРабота прошла {rounds} кругов и не движется.\n"
               f"Причина: {cut(why, 220)}\n"
               f"Что предлагаю: {cut(what, 220)}\n"
               "Без твоего решения дальше не пойдёт.",
               priority="high", tags="warning", click=f"{UI_BASE}/answer")
    else:
        if repair_task is not None:
            verdict["repair_started"] = bool(
                begin_diag_repair(conf, base, stage, verdict, tasks, repair_task))
        else:
            notify(conf, "Разобрался в застрявшей",
                   f"{base}\n\nБуксовала {rounds} кругов. Причина: {cut(why, 220)}\n"
                   f"Делаю: {cut(what, 220)}\n"
                   "Твоего участия не нужно.",
                   tags="mag", click=f"{UI_BASE}/work")
    return verdict


def diag_sweep(conf, tasks):
    """Обход всех живых работ: у кого кругов больше порога — зовём старшую
    модель разобраться. Один разбор на работу, дальше конвейер идёт по нему."""
    diag_at = int(conf.get("deep_diag_rounds", 5))
    seen = set()
    for t in tasks:
        title = t.get("title") or ""
        if not title.startswith(PREFIX):
            continue
        if t.get("state") not in ("running", "queued"):
            continue
        m = STAGE_TITLE_RE.match(title)
        if not m:
            continue
        base = m.group(2).strip()
        if base in seen:
            continue
        seen.add(base)
        if is_stopped(conf, base):
            continue
        # The live sweep is an early warning, not a minute-by-minute brain
        # loop. A terminal stage can still invoke deep_diagnose later through
        # route_question, where a safe repair has enough evidence to start.
        if cap_rescues(base, "DIAG") >= 1:
            continue
        rounds = max(stage_attempts(tasks, "Implement + Test", base),
                     stage_attempts(tasks, "Review", base))
        if rounds < diag_at:
            continue
        try:
            stage = m.group(1).strip()
            verdict = deep_diagnose(conf, base, stage, rounds, tasks,
                                    repair_task=t)
            if verdict and verdict.get("нужен_владелец"):
                pause_pipeline(conf, base)
                stages = [s.get("workflow") for s in conf.get("stages", [])]
                resume = resume_stage_for(stages, stage, stage)
                reason = str(verdict.get("причина") or "").strip()
                solution = str(verdict.get("решение") or "").strip()
                rec = write_question(
                    t["id"], stage, resume, base,
                    t.get("repository_id") or "",
                    reason or f"Работа прошла {rounds} кругов и не движется.",
                    ("Как поступить? Предложение диагностики: " + solution)
                    if solution else "Как поступить дальше?",
                    [], recent_stage_text(tasks, base),
                )
                rec["owner_only"] = True
                rec["escalation_reason"] = (
                    f"старшая диагностика после {rounds} кругов определила, "
                    "что без решения владельца продолжать нельзя"
                )
                save(f"{QUESTION_DIR}/{t['id']}.json", rec)
                log(f"DIAG OWNER STOP base={base!r} task={t['id']}")
        except Exception as e:
            log("diag_sweep_error", repr(e))


def resolve_orchestrator_wait(conf, verdict, task_id, stage, resume_stage, base,
                              repo_id, situation, question, options,
                              prior_result, branch, record=None):
    """Persist an explicit Pilot pause without turning it into a resume answer."""
    if verdict.get("decision") != "wait":
        return False
    reason = str(verdict.get("reason") or "").strip()
    # Keep the original admin audit record: replacing it makes a technical
    # pause indistinguishable from an owner question in the control plane.
    rec = record if record is not None else write_question(
        task_id, stage, resume_stage, base, repo_id, situation, question,
        options, prior_result, branch, status="resolved")
    rec["status"] = "resolved"
    rec["answer"] = reason
    rec["answered_by"] = "orchestrator"
    rec["machine_action"] = "wait"
    rec["escalation_reason"] = reason
    save(f"{QUESTION_DIR}/{task_id}.json", rec)
    pause_pipeline(conf, base)
    log(f"AUTO-WAIT task={task_id} stage={stage}: {reason[:100]}")
    notify(conf, f"Поставил на паузу · {stage}",
           f"{base}\n\n{reason}\n\nСледующий этап не запущен.",
           priority="low", tags="hourglass", click=f"{UI_BASE}/answer")
    return True


def resolve_admin_action(conf, verdict, task_id, stage, resume_stage, base, repo_id,
                         situation, question, options, prior_result, branch):
    """Execute a permitted admin action; return None for non-admin verdicts."""
    if verdict.get("decision") != "admin_action":
        return None
    action = verdict.get("action") or {}
    argv, why = admin_fx_argv(action)
    rec = write_question(task_id, stage, resume_stage, base, repo_id, situation,
                         question, options, prior_result, branch)
    rec["authority"] = "admin"
    rec["admin_action"] = action
    if not argv:
        rec["owner_only"] = True
        rec["admin_result"] = "denied"
        rec["escalation_reason"] = why
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        notify(conf, f"Нужен твой ответ · {stage}",
               f"{base}\n\n❓ {question}\n\n(сам решить не могу: {why})",
               priority="high", tags="raising_hand", click=f"{UI_BASE}/answer")
        return True
    ok, output = _fixed_command(argv, timeout=60)
    rec["admin_command"] = argv
    rec["admin_result"] = "executed" if ok else "failed"
    rec["admin_output"] = squeeze(output, 2000)
    if not ok:
        rec["owner_only"] = True
        rec["escalation_reason"] = "fx отказал или завершился с ошибкой"
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        notify(conf, f"Нужен твой ответ · {stage}",
               f"{base}\n\n❓ {question}\n\n(fx не выполнил разрешённую проверку)",
               priority="high", tags="raising_hand", click=f"{UI_BASE}/answer")
        return True
    follow_up = orchestrator_answer(
        conf, stage, base, situation, question, prior_result, repo_id,
        action_result="fx успешно выполнен:\n" + squeeze(output, 2000))
    if follow_up.get("decision") == "answer":
        rec["status"] = "answered"
        rec["answer"] = follow_up["answer"]
        rec["answered_by"] = "orchestrator"
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        notify(conf, f"Решил сам · {stage}",
               f"{base}\n\nРазрешённая проверка выполнена. {follow_up['answer']}",
               priority="low", tags="robot", click=f"{UI_BASE}/answer")
        return False
    if resolve_orchestrator_wait(
            conf, follow_up, task_id, stage, resume_stage, base, repo_id,
            situation, question, options, prior_result, branch, record=rec):
        return False
    rec["owner_only"] = True
    rec["escalation_reason"] = follow_up.get(
        "reason", "после результата fx нужно решение владельца")
    save(f"{QUESTION_DIR}/{task_id}.json", rec)
    notify(conf, f"Нужен твой ответ · {stage}",
           f"{base}\n\n❓ {question}\n\n(после проверки: {rec['escalation_reason']})",
           priority="high", tags="raising_hand", click=f"{UI_BASE}/answer")
    return True


def route_question(conf, task_id, stage, resume_stage, base, repo_id, situation,
                   question, options, prior_result, attempts_so_far=0, branch="",
                   repair_task=None):
    """Try to resolve the question with the orchestrator; escalate if it's the
    owner's call OR if this stage has already been retried too many times."""
    cap = conf.get("max_stage_attempts", 3)
    # Порог разбора: столько кругов подряд — и зовём сильную модель разобраться,
    # а владельцу уходит одно человеческое сообщение вместо десяти пушей.
    diag_at = int(conf.get("deep_diag_rounds", 5))
    if attempts_so_far >= diag_at:
        try:
            diag_tasks = load_tasks_safe()
            v = deep_diagnose(conf, base, stage, attempts_so_far, diag_tasks,
                              repair_task=repair_task)
            if v and str(v.get("решение") or "").strip():
                situation = (situation + "\n\nРАЗБОР СТАРШЕЙ МОДЕЛИ: "
                             + str(v.get("причина") or "") + " Решение: "
                             + str(v.get("решение") or ""))
                if v.get("repair_started"):
                    return False
        except Exception as e:
            log("diag_hook_error", repr(e))
    # Стоп-кран. Восемь кругов подряд — это уже не плохой код, а помеха,
    # которую конвейер сам убрать не может: сломанное окружение, недоступный
    # сервер, требование, которое агент не в силах выполнить. Дальше он просто
    # жжёт процессор. Останавливаем работу целиком и зовём владельца.
    hard = int(conf.get("max_work_rounds", 8))
    if attempts_so_far - loop_baseline(base) >= hard:
        # Круг разорван — но это НЕ значит, что решение стало владельческим.
        # Сначала даём оркестратору один заход с прямым запретом отвечать
        # «перезапусти»: почти всегда петля техническая, и владельцу тут
        # делать нечего. К владельцу идём, только если оркестратор сам
        # скажет, что вопрос про деньги, прод или выбор продукта.
        v = orchestrator_answer(conf, stage, base,
                                situation + LOOP_NOTE.format(n=attempts_so_far),
                                question, prior_result, repo_id)
        admin_result = resolve_admin_action(
            conf, v, task_id, stage, resume_stage, base, repo_id, situation,
            question, options, prior_result, branch)
        if admin_result is not None:
            return admin_result
        if resolve_orchestrator_wait(
                conf, v, task_id, stage, resume_stage, base, repo_id, situation,
                question, options, prior_result, branch):
            return False
        if v["decision"] == "answer" and not looks_like_retry(v.get("answer", "")):
            note_cap_rescue(base, "LOOP")
            rec = write_question(task_id, stage,
                                 accept_forward(stage, v.get("answer", "")) or resume_stage,
                                 base, repo_id,
                                 situation, question, options, prior_result, branch,
                                 status="answered")
            rec["answer"] = v["answer"]
            rec["answered_by"] = "orchestrator"
            save(f"{QUESTION_DIR}/{task_id}.json", rec)
            log(f"LOOP BROKEN BY ORCHESTRATOR task={task_id} base={base!r} "
                f"rounds={attempts_so_far}: {v['answer'][:120]}")
            notify(conf, f"Разорвал круг сам · {stage}",
                   f"{base}\n\nЭтап шёл по кругу {attempts_so_far} раз(а). "
                   f"Решил сам, другим способом:\n{cut(v['answer'])}\n\n"
                   "Если не согласен — открой и поправь.",
                   priority="low", tags="robot", click=f"{UI_BASE}/answer")
            return False
        pause_pipeline(conf, base)
        set_loop_baseline(base, attempts_so_far)
        rec = write_question(task_id, stage, resume_stage, base, repo_id, situation,
                             question, options, prior_result, branch)
        rec["owner_only"] = True
        rec["escalation_reason"] = (
            "работа прошла этап «{st}» {n} раз(а) и снова вернулась. "
            "Столько кругов подряд конвейер не разрывает сам — значит мешает "
            "не код, а что-то снаружи. Конвейер по этой работе остановлен, "
            "пока ты не решишь."
        ).format(st=resume_stage, n=attempts_so_far)
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        log(f"LOOP BREAK task={task_id} base={base!r} rounds={attempts_so_far}")
        notify(conf, "Кручусь по кругу, остановился",
               f"{base}\n\nЭтап «{resume_stage}» прошёл {attempts_so_far} раз(а), "
               "и работа всё возвращается. Дальше это сжигание процессора, "
               "а не работа. Конвейер по этой задаче остановлен — нужен твой разбор.",
               priority="high", tags="warning", click=f"{UI_BASE}/answer")
        return True
    if budget_stopped(base):
        rec = write_question(task_id, stage, resume_stage, base, repo_id, situation,
                             question, options, prior_result, branch)
        rec["escalation_reason"] = (
            "работа остановлена по денежному потолку — перезапуск только "
            "по решению владельца, иначе следующий заход сожжёт столько же")
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        log(f"BUDGET ESCALATE task={task_id} stage={stage}")
        notify(conf, "Не влезло в деньги \u00b7 " + str(stage),
               base + "\n\n\u0417\u0430\u0434\u0430\u0447\u0430 \u0443\u043f\u0451\u0440\u043b\u0430\u0441\u044c \u0432 \u0434\u0435\u043d\u0435\u0436\u043d\u044b\u0439 \u043f\u043e\u0442\u043e\u043b\u043e\u043a. "
               "\u0421\u0430\u043c \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a\u0430\u0442\u044c \u043d\u0435 \u0431\u0443\u0434\u0443 \u2014 \u0440\u0435\u0448\u0438, \u043f\u043e\u0434\u043d\u044f\u0442\u044c \u043f\u043e\u0442\u043e\u043b\u043e\u043a "
               "\u0438\u043b\u0438 \u0440\u0430\u0437\u0431\u0438\u0442\u044c \u0440\u0430\u0431\u043e\u0442\u0443 \u043d\u0430 \u0447\u0430\u0441\u0442\u0438.",
               priority="high", tags="warning", click=f"{UI_BASE}/answer")
        return True
    if attempts_so_far >= cap:
        # Потолок — защита от бессмысленного повтора, а не признак того, что
        # решение стало владельческим. Сначала спрашиваем оркестратора, прямо
        # запретив ему отвечать «перезапусти».
        used = cap_rescues(base, stage)
        limit = conf.get("max_cap_rescues", 2)
        if used < limit:
            v = orchestrator_answer(conf, stage, base,
                                    situation + CAP_NOTE.format(n=attempts_so_far),
                                    question, prior_result, repo_id)
            admin_result = resolve_admin_action(
                conf, v, task_id, stage, resume_stage, base, repo_id, situation,
                question, options, prior_result, branch)
            if admin_result is not None:
                return admin_result
            if resolve_orchestrator_wait(
                    conf, v, task_id, stage, resume_stage, base, repo_id,
                    situation, question, options, prior_result, branch):
                return False
            if v["decision"] == "answer" and not looks_like_retry(v.get("answer", "")):
                note_cap_rescue(base, stage)
                rec = write_question(task_id, stage,
                                     accept_forward(stage, v.get("answer", "")) or resume_stage,
                                     base, repo_id,
                                     situation, question, options, prior_result, branch,
                                     status="answered")
                rec["answer"] = v["answer"]
                rec["answered_by"] = "orchestrator"
                save(f"{QUESTION_DIR}/{task_id}.json", rec)
                log(f"CAP RESCUE task={task_id} stage={stage} "
                    f"попытка {used + 1}/{limit}: {v['answer'][:120]}")
                notify(conf, f"Сменил подход · {stage}",
                       f"{base}\n\nЭтап падал {attempts_so_far} раз(а). "
                       f"Решил сам, другим способом:\n{cut(v['answer'])}\n\n"
                       "Если не согласен — открой и поправь.",
                       priority="low", tags="robot", click=f"{UI_BASE}/answer")
                return False
            why = v.get("reason") or "оркестратор передал решение владельцу"
        else:
            # Запас «смены подхода» исчерпан — но это по-прежнему не делает
            # вопрос владельческим. Даём оркестратору последний заход с
            # прямым запретом отвечать «перезапусти». К владельцу уходим
            # ТОЛЬКО если он сам скажет, что это его решение.
            v = orchestrator_answer(conf, stage, base,
                                    situation + LOOP_NOTE.format(n=attempts_so_far),
                                    question, prior_result, repo_id)
            admin_result = resolve_admin_action(
                conf, v, task_id, stage, resume_stage, base, repo_id, situation,
                question, options, prior_result, branch)
            if admin_result is not None:
                return admin_result
            if resolve_orchestrator_wait(
                    conf, v, task_id, stage, resume_stage, base, repo_id,
                    situation, question, options, prior_result, branch):
                return False
            if v["decision"] == "answer" and not looks_like_retry(v.get("answer", "")):
                rec = write_question(task_id, stage,
                                     accept_forward(stage, v.get("answer", "")) or resume_stage,
                                     base, repo_id,
                                     situation, question, options, prior_result, branch,
                                     status="answered")
                rec["answer"] = v["answer"]
                rec["answered_by"] = "orchestrator"
                save(f"{QUESTION_DIR}/{task_id}.json", rec)
                log(f"CAP BROKEN BY ORCHESTRATOR task={task_id} stage={stage} "
                    f"attempts={attempts_so_far}: {v['answer'][:120]}")
                notify(conf, f"Решил сам · {stage}",
                       f"{base}\n\nЭтап падал {attempts_so_far} раз(а). "
                       f"Решение принял сам:\n{cut(v['answer'])}",
                       priority="low", tags="robot", click=f"{UI_BASE}/answer")
                return False
            why = v.get("reason") or "оркестратор сказал, что это решение владельца"
        rec = write_question(task_id, stage, resume_stage, base, repo_id, situation,
                             question, options, prior_result, branch)
        rec["escalation_reason"] = (
            f"этап выполнялся {attempts_so_far} раз(а) и не прошёл; {why}")
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        log(f"RETRY CAP hit task={task_id} stage={stage} attempts={attempts_so_far} "
            f"rescues={used} -> владельцу: {why[:80]}")
        notify(conf, f"Зациклилось · {stage}",
               f"{base}\n\nЭтап выполнялся {attempts_so_far} раз(а) и снова упал. "
               "Автоперезапуски остановлены — нужен твой взгляд.\n\n"
               f"❓ {question}",
               priority="high", tags="warning", click=f"{UI_BASE}/answer")
        return True
    verdict = orchestrator_answer(conf, stage, base, situation, question,
                                  prior_result, repo_id)
    admin_result = resolve_admin_action(
        conf, verdict, task_id, stage, resume_stage, base, repo_id, situation,
        question, options, prior_result, branch)
    if admin_result is not None:
        return admin_result
    if resolve_orchestrator_wait(
            conf, verdict, task_id, stage, resume_stage, base, repo_id,
            situation, question, options, prior_result, branch):
        return False
    rec = write_question(task_id, stage, resume_stage, base, repo_id, situation,
                         question, options, prior_result, branch)
    if verdict["decision"] == "answer":
        rec["status"] = "answered"          # handle_answers() resumes it next cycle
        rec["answer"] = verdict["answer"]
        rec["answered_by"] = "orchestrator"
        save(f"{QUESTION_DIR}/{task_id}.json", rec)
        log(f"AUTO-ANSWERED task={task_id} stage={stage}: {verdict['answer'][:100]}")
        notify(conf, f"Решил сам · {stage}",
               f"{base}\n\nВопрос: {question}\nМой ответ: {verdict['answer']}\n\n"
               "Работа продолжается. Если не согласен — открой и поправь.",
               priority="low", tags="robot", click=f"{UI_BASE}/answer")
        return False
    rec["escalation_reason"] = verdict.get("reason", "")
    save(f"{QUESTION_DIR}/{task_id}.json", rec)
    log(f"ESCALATED task={task_id} stage={stage}: {verdict.get('reason','')[:100]}")
    notify(conf, f"Нужен твой ответ · {stage}",
           f"{base}\n\n{situation}\n\n❓ {question}\n\n"
           f"(сам решить не могу: {verdict.get('reason','')})",
           priority="high", tags="raising_hand", click=f"{UI_BASE}/answer")
    return True


def write_question(task_id, stage, resume_stage, base, repo_id, situation, question,
                   options, prior_result, branch="", status="open"):
    """Record a pipeline stop that needs the owner. The UI shows these and the
    answer resumes the pipeline."""
    os.makedirs(QUESTION_DIR, exist_ok=True)
    branch, implementation_head = selected_delivery(base, branch)
    rec = {
        "id": task_id,
        "task_id": task_id,
        "stage": stage,
        "resume_stage": resume_stage,
        "title": base,
        "repository_id": repo_id,
        "situation": situation or "",
        "question": question or "",
        "options": options or [],
        "branch": branch or "",
        "implementation_head": implementation_head,
        "prior_result": squeeze(prior_result, 12000),
        "asked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Сразу нужный статус: раньше ответ оркестратора сперва сохранялся
        # как «открыт» и успевал мигнуть у владельца во вкладке «Нужен ответ».
        "status": status,          # open -> answered -> resolved
        "answer": "",
    }
    save(f"{QUESTION_DIR}/{task_id}.json", rec)
    return rec


def load_questions():
    out = []
    try:
        for fn in sorted(os.listdir(QUESTION_DIR)):
            if fn.endswith(".json"):
                q = load(f"{QUESTION_DIR}/{fn}", None)
                if q:
                    out.append(q)
    except FileNotFoundError:
        pass
    return out


def attach_question_work_id(task):
    """Bind a freshly written question to the same durable work as its task."""
    work_id = (task or {}).get("work_id") or ""
    task_id = (task or {}).get("id") or ""
    if not work_id or not task_id:
        return
    path = f"{QUESTION_DIR}/{task_id}.json"
    question = load(path, None)
    if isinstance(question, dict) and question.get("work_id") != work_id:
        question["work_id"] = work_id
        save(path, question)


def subtask_state(tasks, open_q, last_stage, base, since=""):
    """Что сейчас с подзадачей: 'none' — конвейер не начинался, 'working' —
    что-то выполняется, 'waiting' — ждёт ответа владельца, 'done' — прошла
    всю цепочку с настоящим PASS, 'stuck' — остановилась не дойдя до конца."""
    base = (base or "").strip()
    mine = []
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m or m.group(2).strip() != base:
            continue
        # Задачи с тем же названием из прошлых прогонов не считаются: иначе
        # подзадача объявляется готовой по чужому давнему успеху.
        if since and (t.get("created_at") or "") < since:
            continue
        mine.append((m.group(1).strip(), t))
    if not mine:
        return "none"
    if any(t["state"] in ("running", "queued", "preparing") for _, t in mine):
        return "working"
    if any(t["id"] in open_q for _, t in mine):
        return "waiting"
    if any(st == last_stage and t["state"] == "succeeded" and final_ok(t["id"], strict=True)
           for st, t in mine):
        return "done"
    return "stuck"


def merge_receipt(base, since=""):
    """Return one canonical successful-merge receipt for this subtask run.

    The task API deliberately forgets terminal history.  ``merges.jsonl`` is
    the durable record written only after ``gh_merge`` succeeds, so it is the
    only fallback allowed to restore a running epic subtask.  A title match is
    exact and the merge must belong to this generation (not predate its start).
    """
    base = (base or "").strip()
    try:
        with open(MERGES_PATH, encoding="utf-8") as merges:
            records = list(merges)
    except OSError:
        return None
    for line in reversed(records):
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        at = str(record.get("at") or "")
        if record.get("base") != base or not at:
            continue
        if since and not receipt_after(at, since):
            continue
        return {key: record[key] for key in ("task_id", "base", "at")
                if key in record}
    return None


def receipt_after(receipt_at, started_at):
    """Whether a merge receipt is no older than the subtask generation."""
    receipt_time = receipt_epoch(receipt_at)
    started_time = receipt_epoch(started_at)
    return receipt_time is not None and started_time is not None and receipt_time >= started_time


def receipt_epoch(value):
    """Parse both legacy local merge dates and new UTC receipt dates."""
    value = str(value or "").strip()
    if not value:
        return None
    utc = value.endswith("Z")
    value = value.rstrip("Z").replace("T", " ").split(".", 1)[0]
    try:
        parsed = time.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return calendar.timegm(parsed) if utc else time.mktime(parsed)


def complete_subtask(sub, source, receipt, completed_at=""):
    """Persist a completion proof so a history cleanup cannot reopen it."""
    sub.update({
        "status": "done",
        "completed_at": completed_at or receipt.get("at") or
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completion_source": source,
        "completion_receipt": receipt,
    })


def task_completion_receipt(tasks, last_stage, base, since=""):
    """Return the final successful task that proved this subtask complete."""
    for task in reversed(tasks):
        match = STAGE_TITLE_RE.match(task.get("title", ""))
        if not match or match.group(1).strip() != last_stage:
            continue
        if match.group(2).strip() != (base or "").strip():
            continue
        if since and (task.get("created_at") or "") < since:
            continue
        if task.get("state") == "succeeded" and final_ok(task["id"], strict=True):
            return {"task_id": task["id"], "stage": last_stage,
                    "created_at": task.get("created_at", "")}
    return {"task_id": "", "stage": last_stage}


def subtask_is_held(sub):
    return sub.get("status") == "hold" or bool(str(sub.get("hold_reason") or "").strip())


def advance_epics(conf, tasks, workflows, workers):
    """Подзадачи идут по очереди: следующая стартует, когда предыдущая прошла
    всю цепочку. Исключение — подзадачи, помеченные `parallel_ok`: они ни от
    чего не зависят и могут идти одновременно с текущей. Если подзадача
    застряла или ждёт владельца, эпик держим, а не бежим дальше."""
    stages = [s["workflow"] for s in conf["stages"]]
    last_stage = stages[-1] if stages else ""
    open_q = {q.get("task_id") for q in load_questions() if q.get("status") == "open"}
    cap = int(conf.get("max_parallel_subtasks", 3))

    for epic in load_epics():
        if epic.get("status") != "running":
            continue
        subs = epic.get("subtasks") or []
        if not subs:
            continue
        path = f"{EPIC_DIR}/{epic['id']}.json"

        # Подхват сирот: подзадача числится ожидающей, а конвейер по ней уже идёт.
        for i, sub in enumerate(subs):
            if sub.get("status", "pending") != "pending":
                continue
            floor = epic.get("started_at") or epic.get("created_at") or ""
            live = [t for t in tasks
                    if (STAGE_TITLE_RE.match(t.get("title", ""))
                        and STAGE_TITLE_RE.match(t["title"]).group(2).strip() == sub["title"].strip()
                        and t["state"] in ("running", "queued", "preparing")
                        and (not floor or (t.get("created_at") or "") >= floor))]
            if live:
                sub.update({"status": "running", "task_id": live[0]["id"],
                            "started_at": live[0].get("created_at", ""), "adopted": True})
                save(path, epic)
                log(f"epic '{epic['name']}': подхватил уже идущую подзадачу {i+1} ({sub['title'][:40]})")

        # 1. Закрываем всё, что дошло до конца — сразу по всем идущим,
        #    а не только по первой: иначе параллельные висят до её финиша.
        finished = []
        restarted = False
        for i, sub in enumerate(subs):
            # Смотрим и на идущие, и на уже помеченные готовыми.  У готовой
            # подзадачи receipt остаётся истиной после очистки истории; снять
            # её можно только по живому новому поколению, не по отсутствию API.
            if sub.get("status") not in ("running", "done"):
                continue
            since = sub.get("started_at") or epic.get("started_at") or epic.get("created_at") or ""
            state_now = subtask_state(tasks, open_q, last_stage, sub["title"], since)
            if state_now == "done":
                if sub.get("status") != "done":
                    receipt = task_completion_receipt(tasks, last_stage, sub["title"], since)
                    complete_subtask(sub, "task_history", receipt)
                    finished.append(i)
            elif state_now == "none" and sub.get("status") == "running":
                receipt = merge_receipt(sub["title"], since)
                if receipt:
                    complete_subtask(sub, "merge_journal", receipt, receipt["at"])
                    finished.append(i)
            elif sub.get("status") == "done" and state_now in ("working", "waiting", "stuck"):
                new_generation = state_now in ("working", "waiting") or any(
                    STAGE_TITLE_RE.match(task.get("title", ""))
                    and STAGE_TITLE_RE.match(task["title"]).group(2).strip() == sub["title"].strip()
                    and sub.get("completed_at")
                    and receipt_after(task.get("created_at", ""), sub["completed_at"])
                    for task in tasks)
                if not new_generation:
                    continue
                # Новое живое/перезапущенное поколение всегда важнее старого
                # receipt; его ``started_at`` отсечёт прежние merge-записи.
                sub["status"] = "running"
                matching = [t for t in tasks
                            if (STAGE_TITLE_RE.match(t.get("title", ""))
                                and STAGE_TITLE_RE.match(t["title"]).group(2).strip() == sub["title"].strip())]
                if matching:
                    # Failed and stuck tasks also start a generation.  Once the
                    # API removes them, this boundary must still reject an old
                    # merge receipt with the same title.
                    newest = max(matching, key=lambda t: t.get("created_at") or "")
                    sub.update({"task_id": newest.get("id", ""),
                                "started_at": newest.get("created_at", "")})
                restarted = True
                log("EPIC RESTARTED подзадача " + repr(sub["title"][:50])
                    + ": состояние стало " + state_now + ", старый receipt не применяю")
        if finished or restarted:
            save(path, epic)
            for i in finished:
                log(f"epic '{epic['name']}': подзадача {i+1}/{len(subs)} готова")

        if all(s.get("status") == "done" for s in subs):
            epic["status"] = "done"
            save(path, epic)
            log(f"EPIC DONE '{epic['name']}'")
            notify(conf, "Эпик завершён", f"{epic['name']}: все подзадачи готовы",
                   tags="tada", click=f"{UI_BASE}/epics")
            continue

        running = [i for i, s in enumerate(subs) if s.get("status") == "running"]
        running_seq = [i for i in running if not subs[i].get("parallel_ok")]
        pending = [i for i, s in enumerate(subs) if s.get("status", "pending") == "pending"]
        started = []

        # 2. Независимые подзадачи можно пускать одновременно с текущей.
        for i in pending:
            if len(running) + len(started) >= cap:
                break
            if not subs[i].get("parallel_ok") or subtask_is_held(subs[i]):
                continue
            tid, err = launch_subtask(conf, epic, i, workflows, workers)
            if tid:
                started.append(i)
                epic.setdefault("children", []).append(
                    {"task_id": tid, "title": subs[i]["title"],
                     "complexity": subs[i].get("complexity", "medium")})
                save(path, epic)
                log(f"epic '{epic['name']}': параллельно пошла подзадача {i+1} ({subs[i]['title'][:40]})")
            else:
                log(f"epic '{epic['name']}': не смог запустить параллельную {i+1}: {err}")

        # 3. Очередная последовательная — только если ни одна последовательная не идёт
        #    И перед ней нет отложенной: отложенная держит хвост очереди, иначе
        #    запустится то, что как раз и зависит от отложенного.
        if not running_seq:
            nxt = next((i for i in pending if i not in started and not subs[i].get("parallel_ok")
                        and not subtask_is_held(subs[i])), None)
            if nxt is not None and any(subtask_is_held(s) for s in subs[:nxt]):
                held = next(i for i, s in enumerate(subs[:nxt]) if subtask_is_held(s))
                log(f"epic '{epic['name']}': подзадача {nxt+1} ждёт — впереди отложенная {held+1}")
                nxt = None
            if nxt is not None:
                tid, err = launch_subtask(conf, epic, nxt, workflows, workers)
                if tid:
                    epic.setdefault("children", []).append(
                        {"task_id": tid, "title": subs[nxt]["title"],
                         "complexity": subs[nxt].get("complexity", "medium")})
                    save(path, epic)
                    done_n = sum(1 for s in subs if s.get("status") == "done")
                    notify(conf, f"Эпик: пошла подзадача {nxt + 1} из {len(subs)}",
                           f"{epic['name']}\n\nГотово: {done_n} из {len(subs)}\n"
                           f"Сейчас: {subs[nxt]['title']}",
                           tags="arrow_forward", click=f"{UI_BASE}/epics")
                else:
                    log(f"epic '{epic['name']}': не смог запустить подзадачу {nxt+1}: {err}")


def record_new_works(conf, tasks, max_age_min=180):
    """Новая работа без записи о происхождении — значит, её завели из окна
    «Delegate task» или голосом. Пишем: поставил владелец, начали с такой-то
    стадии, ранние шаги пропущены осознанно."""
    stages = [s["workflow"] for s in conf.get("stages", [])]
    if not stages:
        return
    known = load(WORKS_PATH, {})
    # A Plan card already has the trustworthy author.  Do not overwrite it
    # with "owner" merely because Pilot noticed the created task one tick
    # before the normal note_work call completed.
    planned_origins = {
        base_title(item.get("title") or "").strip().casefold(): item.get("origin")
        for item in ideas_all()
        if item.get("origin") in WORK_ORIGINS and item.get("title")
    }
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                           time.gmtime(time.time() - max_age_min * 60))
    # Явно созданная владельцем новая live-задача после durable close — это
    # новое поколение. Старый terminal-снимок условию live/created-after-close
    # не соответствует и потому никогда не снимает архивную границу.
    reopened = set()
    for task in tasks:
        title = task.get("title") or ""
        base = base_title(title)
        if has_task_provenance(task) and not task_is_root(task):
            if (task.get("correction_kind") and title.startswith(PREFIX)
                    and (task.get("created_at") or "") >= cutoff):
                note_duplicate_root_prevented(task)
            continue
        key = task_work_id(task)
        meta = known.get(key) or {}
        if (not title.startswith(PREFIX) or base in reopened or not meta.get("closed")
                or task.get("state") not in PIPELINE_LIVE_STATES):
            continue
        created = _work_time(task.get("created_at"))
        closed = _work_time(meta.get("closed"))
        if not created or not closed or created <= closed:
            continue
        generation = str(uuid.uuid4())
        reopen_work(base, generation)
        conf["stopped_pipelines"] = [name for name in
                                     (conf.get("stopped_pipelines") or [])
                                     if not _same_work(name, base)]
        for idea in ideas_all():
            if (_same_work(idea.get("title"), base)
                    and idea.get("state") in ("done", "rejected")):
                set_idea(idea["id"], state="in_work", task_id=task.get("id") or "",
                         reason="", run_generation=generation)
        reopened.add(base)
        log(f"WORK REOPEN base={base!r}: owner-created task={task.get('id', '')}")
    if reopened:
        known = load(WORKS_PATH, {})

    # самая ранняя стадия каждой работы среди свежих задач
    first = {}
    for t in tasks:
        title = t.get("title") or ""
        if not title.startswith(PREFIX):
            continue
        if (t.get("created_at") or "") < cutoff:
            continue
        if has_task_provenance(t) and not task_is_root(t):
            if t.get("correction_kind"):
                note_duplicate_root_prevented(t)
            continue
        base = base_title(title)
        key = task_work_id(t)
        n = stage_no_of(title)
        if not base or not n or key in known:
            continue
        if key not in first or n < first[key][0]:
            first[key] = (n, t.get("created_at") or "", base,
                          t.get("work_id") or "", t)
    for _key, (n, _at, base, work_id, task) in first.items():
        skipped = stages[: n - 1]
        # The durable request key is the strongest evidence: an Automation ran
        # the task even if an older Plan card for the same title says "owner".
        if str(task.get("request_key") or "").startswith("automation:"):
            origin = ORIGIN_ORCHESTRATOR
        else:
            origin = planned_origins.get(base.strip().casefold())
        origin = origin or ORIGIN_OWNER
        skipped_reason = {
            ORIGIN_OWNER: "владелец завёл работу сразу с этого шага",
            ORIGIN_ASSISTANT: "помощник завёл работу сразу с этого шага",
            ORIGIN_ORCHESTRATOR: "Factory запустила работу сразу с этого шага",
        }.get(origin, "Factory запустила работу по находке сразу с этого шага")
        note_work(base, origin,
                  stages[n - 1] if n <= len(stages) else "",
                  skipped,
                  skipped_reason if skipped else "",
                  work_id=work_id)
        if skipped:
            log(f"WORK ORIGIN base={base!r} origin={origin} начал с {stages[n - 1]}, "
                f"пропущено: {', '.join(skipped)}")


def handle_answers(conf, workflows, workers, tasks):
    """An answered question resumes its pipeline from resume_stage."""
    stages = [s["workflow"] for s in conf["stages"]]
    applied = 0
    for q in load_questions():
        if q.get("status") not in ("answered", "no_worker") or not q.get("answer"):
            continue
        # re-read right before acting: an external writer (UI, one-off script)
        # may have changed the record since the listing was taken.
        fresh = load(f"{QUESTION_DIR}/{q['id']}.json", None)
        if (not fresh or fresh.get("status") not in ("answered", "no_worker")
                or fresh.get("resumed_task_id")):
            continue
        q = fresh
        src_task = next((t for t in tasks if t.get("id") == q.get("task_id")), None)
        closed_reason = work_lifecycle_block(q.get("title", ""), src_task, tasks)
        if closed_reason:
            q["status"] = "resolved"
            q["escalation_reason"] = "не возобновлена: " + closed_reason
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"answer: '{q.get('title','')[:40]}' закрыта — {closed_reason}")
            continue
        stage = q.get("resume_stage")
        if stage not in stages:
            log(f"answer: unknown resume stage {stage!r} for {q['id']}")
            continue
        idx = stages.index(stage)
        nw = workflows.get(stage)
        cx_hint = q.get("complexity_hint") or "medium"
        # Модель, которая дважды не справилась с этапом, третий раз денег
        # не заслужила: третий заход отдаём исполнителю уровнем выше.
        try:
            rounds = stage_attempts(
                tasks, stage, src_task or base_title(q.get("title", "")))
        except Exception:
            rounds = 0
        repository_id = q.get("repository_id", "")
        selected_worker = stage_worker(
            conf, stage, cx_hint, workers, repository_id=repository_id)
        if rounds >= 2 and cx_hint != "high":
            was = selected_worker
            candidate = stage_worker(
                conf, stage, "high", workers, exact_tier=True,
                repository_id=repository_id)
            if (candidate and worker_capability_rank(candidate)
                    > worker_capability_rank(was)):
                cx_hint = "high"
                selected_worker = candidate
                log(f"ESCALATE '{q.get('title','')[:40]}' {stage}: "
                    f"{rounds} провала — {was} -> {candidate}")
                if cap_rescues(q.get("title") or "", "ESCNOTE") < 1:
                    note_cap_rescue(q.get("title") or "", "ESCNOTE")
                    notify(conf, "Исполнитель повышен",
                           (q.get("title") or "") + "\nЭтап «" + str(stage)
                           + "» провалился " + str(rounds)
                           + " раз(а). Повышаю: " + str(was) + " → "
                           + str(candidate) + ".",
                           tags="arrow_double_up", click=f"{UI_BASE}/work")
            else:
                log(f"ESCALATE SKIP '{q.get('title','')[:40]}' {stage}: "
                    f"нет исполнителя сильнее {was} (кандидат={candidate})")
        worker = workers.get(selected_worker)
        if not nw or not nw.get("enabled") or not worker:
            log(f"answer: no workflow/worker for {stage}")
            continue
        base = base_title(q.get("title", ""))
        br = (q.get("branch") or extract_branch(q.get("prior_result", ""), "")
              or branch_from_history(tasks, base))
        br, implementation_head = selected_delivery(base, br)
        branch_line = resume_branch_line(base, br, rounds)
        head_line = (f"Implementation head: {implementation_head}\n"
                     if implementation_head else "")
        context = (
            f"Pipeline: {q['title']}\n"
            f"Previous stage: {q['stage']} (остановлена, владелец ответил на вопрос)\n"
            f"{branch_line}{head_line}"
            f"ВОПРОС АГЕНТА: {q.get('question','')}\n"
            f"ОТВЕТ ВЛАДЕЛЬЦА (утверждено, действуй по нему): {q['answer']}\n\n"
            f"Отчёт остановленной стадии (сокращён):\n{squeeze(q.get('prior_result',''))}"
        )[:20000]
        body = {
            "request_key": str(uuid.uuid4()),
            "title": f"[auto] [{idx + 1}/{len(stages)} {stage}] {q['title']}"[:200],
            "context": context,
            "worker_id": worker["id"],
            "repository_id": q.get("repository_id", ""),
            "timeout_seconds": conf.get("timeout_seconds", 7200),
            "workflow_revision_id": nw["revision_id"],
        }
        # Защита от дублей: тот же ответ мог прийти по двум путям (вопрос от
        # Review и повтор отменённой стадии) — второй раз задачу не создаём.
        if is_stopped(conf, q.get("title", "")):
            q["status"] = "resolved"
            q["escalation_reason"] = "работа остановлена владельцем — конвейер не возобновляется"
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"answer: '{q.get('title','')[:40]}' остановлена владельцем — не возобновляю")
            continue

        dup = live_or_done_at(tasks, src_task or q["title"], idx + 1,
                              since=(src_task or {}).get("created_at"))
        if dup:
            q["status"] = "resolved"
            q["resumed_task_id"] = dup["id"]
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"answer: '{q['title'][:40]}' уже имеет задачу на стадии {stage} "
                f"({dup['id'][:8]} {dup.get('state')}) — дубль не создаю")
            continue

        tries = int(q.get("resume_tries", 0))
        if tries >= 5:
            # Ответ уже есть — хозяин тут ни при чём. Исполнителей нет чаще
            # всего из-за лимита подписки, а он проходит сам. Поэтому не
            # сдаёмся навсегда, а пробуем раз в десять минут, честно
            # подписав состояние: «жду свободного исполнителя».
            last = str(q.get("last_error") or "")
            cap_hit = "day_task_cap" in last or "work_day_cap" in last
            if q.get("status") != "no_worker":
                q["status"] = "no_worker"
                q["escalation_reason"] = (
                    "ответ есть; упёрлись в дневной потолок задач — жду, пока окно освободится"
                    if cap_hit else
                    "ответ есть; жду свободного исполнителя (лимит подписки или воркеры недоступны)")
                save(f"{QUESTION_DIR}/{q['id']}.json", q)
                log(f"answer resume: {q['id']} ждёт ({'потолок' if cap_hit else 'исполнителя'}) "
                    f"после {tries} попыток :: {last[:80]}")
                if cap_hit:
                    notify(conf, "Уперлись в дневной потолок задач",
                           f"{q['title']}\nОтвет есть, но на сегодня выбран потолок числа задач. "
                           "Продолжу сам, как только окно освободится. Потолок правится "
                           "в настройках: day_task_cap.",
                           tags="hourglass", click=f"{UI_BASE}/settings")
                else:
                    notify(conf, "Ответ есть, исполнителей нет — жду",
                           f"{q['title']}\nПродолжу сам, как только освободится исполнитель для {stage}.",
                           tags="hourglass", click=f"{UI_BASE}/work")
            if time.time() - float(q.get("last_resume_try") or 0) < 600:
                continue
            q["last_resume_try"] = time.time()
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
        try:
            correction_kind = {
                "Review": "review_return",
                "Verify": "verify_return",
            }.get(q.get("stage"), "answer_resume")
            r = create_child_task(
                body, src_task or {"id": q.get("task_id")}, conf,
                correction_kind)
            tid = r.get("task", {}).get("id")
            q["status"] = "resolved"
            q["resumed_task_id"] = tid
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"ANSWER APPLIED q={q['id']} -> {stage} new_task={tid}")
            applied += 1
            notify(conf, "Ответ принят, работа продолжена",
                   f"{q['title']}\nСтадия: {stage}", tags="arrow_forward",
                   click=f"{UI_BASE}/tasks/{tid}")
        except ParallelWorkLimit:
            log(f"answer resume deferred for {q['id']}: заняты все слоты работ")
            break
        except Exception as e:
            q["resume_tries"] = tries + 1
            q["last_error"] = repr(e)[:200]
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"answer resume failed for {q['id']} (попытка {tries+1}/5): {e}")
    return applied


def refill_open_work_slots(conf, workflows, workers, admit_new_plan=True):
    """Give unfinished continuations every newly opened slot before Plan.

    A terminal handoff backlog means an already-started work is waiting for
    its next stage.  Keep newly opened capacity reserved for that backlog
    instead of admitting another root task which can starve the continuation.
    """
    tasks = api("/tasks?limit=100").get("tasks") or []
    # All admissions in this pass share the same authoritative snapshot.
    # handle_answers/create_task appends successful continuations to it, so
    # replenish_plan can only use capacity which really remains afterwards.
    conf["_active_work_tasks"] = tasks
    answered = handle_answers(conf, workflows, workers, tasks)
    if admit_new_plan:
        replenish_plan(conf, tasks, workflows, workers)
    return answered


def decide(conf, stage, next_stage, title, result, repo_id=""):
    """Ask the decision model what to do. Returns dict(action, reason, handoff)."""
    guide = {
        "Triage": "Advance ONLY if the triage verdict is READY (ready to specify/implement). "
                  "If NEEDS INFORMATION, WAIT, or CLOSE/DUPLICATE - stop.",
        "Specification": "Advance if the specification is complete and actionable. "
                         "If it raises decisions a human must approve first, stop.",
        "Implement + Test": "Advance if implementation finished and checks are green. "
                            "If checks failed or work is partial, stop.",
        "Review": "Advance ONLY if the verdict is APPROVE. On REQUEST CHANGES, stop.",
        "Verify": "This is the last automated stage. Always stop here. On PASS the branch is squash-merged into main AUTOMATICALLY by the orchestrator and then deployed to staging. Do NOT write that the change 'awaits the owner decision' or that it is 'ready to be merged' - that is false and misleads the owner. State plainly what was verified and that it goes to main and staging on its own. Only the PRODUCTION release is a human decision.",
    }.get(stage, "Use your judgement; when unsure, stop.")
    prompt = (
        "You are the orchestrator of a software factory pipeline. "
        + repo_brief(repo_id) + " "
        f"Stage '{stage}' of pipeline task '{title}' has finished. "
        f"Routing rule: {guide}\n"
        f"Next stage would be: {next_stage or 'none (end of pipeline)'}.\n\n"
        f"Stage result:\n---\n{result[:20000]}\n---\n\n"
        "Also rate how demanding the NEXT stage will be, to pick a model tier and save "
        "tokens: 'low' (trivial/mechanical), 'medium' (ordinary work), 'high' (complex "
        "logic, high risk, subtle bugs, architecture).\n"
        'Reply with ONLY a JSON object, no prose: {"action": "advance" or "stop", '
        '"reason": "<one short sentence>", '
        '"handoff": "<what the next stage must know: the distilled outcome of this stage>", '
        '"next_complexity": "low" or "medium" or "high", '
        '"situation_ru": "<ONLY when action=stop: 2-3 short sentences IN RUSSIAN for a '
        'non-programmer owner: what the agent did and what exactly is blocking. Plain '
        'language, no jargon, no English terms>", '
        '"question_ru": "<ONLY when action=stop: the single concrete question the owner '
        'must answer, IN RUSSIAN, phrased so it can be answered in one spoken sentence. '
        'If there are several, ask the most important one and mention the rest briefly>", '
        '"options_ru": ["<ONLY when action=stop: 2-4 short plausible answers in Russian '
        'the owner could pick, most likely first>"], '
        '"verdict_ru": "<ALWAYS: 2-4 sentences IN RUSSIAN for a non-programmer owner - '
        'what this stage actually did and what the outcome is. Concrete (what was '
        'changed/checked/found), no jargon, no English terms, no code>"}'
    )
    try:
        text, _eng = brain(conf, prompt, timeout=180)
        start, end = text.find("{"), text.rfind("}")
        verdict = json.loads(text[start:end + 1])
        if verdict.get("action") not in ("advance", "stop"):
            raise ValueError("bad action")
        return verdict
    except Exception as e:
        log("decision_error", repr(e))
        return {"action": "stop", "reason": f"decision model failed: {e}", "handoff": ""}


# ------------------------------------------------- Где пощупать сделанное ---
# Строка TRY: в отчёте — единственный способ превратить «сделано» в «вот оно».
TRY_LINE = re.compile(r"^\s*TRY:\s*(\S+)\s*$", re.M)
TRY_BASE = {
    "timafen/factory": "https://factory.timafen.com",
    "timafen/tarser-operations": "https://staging-automation.tarser.net",
}
TRY_HOSTS = ("factory.timafen.com", "staging-automation.tarser.net",
             "staging.ops.tarser.net")
# Старое имя стенда ещё отвечает и зашито в коде приложения, но владельцу
# показываем только новое: пусть ссылка ведёт туда, где он на самом деле живёт.
TRY_ALIASES = (("staging.ops.tarser.net", "staging-automation.tarser.net"),)
INFRA_SIGNS = re.compile(
    r"refresh_token_reused|Please try signing in again|401 Unauthorized|"
    r"could not be refreshed|Not logged in|Permission denied|"
    r"connection reset|temporary failure in name resolution", re.I)

TRY_NONE = ("none", "нет", "-", "n/a")
PROOF_LINE = re.compile(r"^\s*ДОКАЗАТЕЛЬСТВО:\s*(.+?)\s*$", re.M)
# служебные страницы: человек там результата не увидит
TRY_USELESS = ("/health", "/login", "/admin/login", "/work", "/answer",
               "/settings", "/workers", "/epics")


def _generic_screen(u):
    """Общий экран панели — не результат: жмёшь «посмотреть» и попадаешь
    туда же, откуда нажал."""
    tail = (u or "").rstrip("/")
    return any(tail.endswith(g) for g in TRY_USELESS)


def cut(t, n=300):
    """Обрезка по границе слова: текст на полуслове выглядит как обрыв связи."""
    t = (t or "").strip()
    if len(t) <= n:
        return t
    c = t[:n]
    sp = c.rfind(" ")
    if sp > n // 2:
        c = c[:sp]
    return c.rstrip(" ,;:.-") + "…"


def proof_of(result):
    m = None
    for m in PROOF_LINE.finditer(result or ""):
        pass
    return (cut(m.group(1), 300) if m else "")


def _is_bare_root(u):
    """Ссылка на корень панели ничего не показывает: жмёшь «посмотреть» —
    и попадаешь туда же, откуда нажал. Такую ссылку не показываем вовсе."""
    u = (u or "").rstrip("/")
    return u.count("/") <= 2


def try_url(result, repo_id=""):
    """Ссылка «посмотреть»: агент называет её сам, мы только проверяем, что
    она ведёт на наш стенд. Отчёт агента — данные, а не команда."""
    m = TRY_LINE.search(result or "")
    if not m:
        return ""
    path = m.group(1).strip().strip(chr(96) + chr(34) + chr(39) + "«»")
    if path.lower() in TRY_NONE:
        return ""
    if path.startswith("http"):
        if not any(h in path for h in TRY_HOSTS):
            return ""
        for was, now in TRY_ALIASES:
            path = path.replace(was, now)
        return "" if _generic_screen(path) else path
    ident = _identity_of(repo_id)
    base = next((url for key, url in TRY_BASE.items() if key in ident), "")
    if not base:
        return ""
    _u = base + (path if path.startswith("/") else "/" + path)
    return "" if (_is_bare_root(_u) or _generic_screen(_u)) else _u


BRANCH_LINE = re.compile(r"^\s*BRANCH:\s*(\S+)\s*$", re.M)
BRANCH_ANY = re.compile(r"\bfactory/[A-Za-z0-9._/-]+")
CONTEXT_BRANCH = re.compile(r"^Branch:\s*(\S+)\s*$", re.M)


def branch_candidates(result, prev_context):
    """Все имена веток, что встретились, в порядке доверия: сначала явная
    строка отчёта, потом упоминания в отчёте, потом контекст задания."""
    out = []
    for source, pattern in ((result, BRANCH_LINE), (result, BRANCH_ANY),
                            (prev_context, CONTEXT_BRANCH), (prev_context, BRANCH_ANY)):
        for m in pattern.finditer(source or ""):
            name = m.group(1) if pattern.groups else m.group(0)
            name = (name or "").strip().strip("`,.;")
            if name and name not in out:
                out.append(name)
    return out


def pushed_branch(candidates, repo_identity):
    """Ветка, которой нет в хранилище, для проверки не существует.
    Берём первую опубликованную; если хранилище недоступно — первую вообще."""
    if not candidates:
        return ""
    short = (repo_identity or "").split("github.com/")[-1]
    if not short:
        return candidates[0]
    for name in candidates[:6]:
        info = gh_json(["api", f"repos/{short}/branches/{name}"])
        if isinstance(info, dict) and info.get("name") == name:
            if name != candidates[0]:
                log(f"BRANCH PICK: беру опубликованную {name} вместо {candidates[0]}")
            return name
    return candidates[0]


FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def implementation_artifact(base):
    """Return the durable, generation-scoped implementation branch and head."""
    works = load(WORKS_PATH, {}) or {}
    meta = works.get(base) or {}
    artifact = meta.get("implementation_artifact") or {}
    if (artifact.get("generation") or "") != (meta.get("run_generation") or ""):
        return {}
    if not artifact.get("branch") or not FULL_GIT_SHA.fullmatch(artifact.get("head") or ""):
        return {}
    return artifact


def record_implementation_artifact(base, task_id, task_title, result, context,
                                   repo_identity):
    """Persist only a published implementation branch with a non-empty diff."""
    if is_service_work(base) or is_service_work(task_title):
        return {}
    repo = (repo_identity or "").split("github.com/")[-1]
    if not repo:
        return {}
    for branch in branch_candidates(result, context):
        info = gh_json(["api", f"repos/{repo}/branches/{branch}"], strict=True)
        if not isinstance(info, dict) or info.get("name") != branch:
            continue
        head = ((info.get("commit") or {}).get("sha") or "").lower()
        if not FULL_GIT_SHA.fullmatch(head):
            continue
        comparison = gh_json(
            ["api", f"repos/{repo}/compare/main...{branch}"], strict=True)
        if not isinstance(comparison, dict) or not comparison.get("files"):
            continue
        works = load(WORKS_PATH, {}) or {}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        meta = works.setdefault(base, {
            "origin": ORIGIN_OWNER, "start_stage": "", "skipped": [],
            "reason": "", "at": now,
        })
        artifact = {
            "branch": branch,
            "head": head,
            "task_id": task_id,
            "recorded_at": now,
            "generation": meta.get("run_generation") or "",
        }
        previous = meta.get("implementation_artifact") or {}
        meta["implementation_artifact"] = artifact
        # Re-reading the same completed Implement task happens after
        # review_gate has refreshed its branch onto a newer main.  The remote
        # head then legitimately differs from the original Implement report,
        # but the gate-selected delivery head is still the authority for
        # Review, Verify, and merge.  Only a genuinely different Implement
        # task/branch/generation may invalidate that selection.
        implementation_identity = ("branch", "task_id", "generation")
        if any(previous.get(key) != artifact[key]
               for key in implementation_identity):
            meta.pop("delivery_artifact", None)
        save(WORKS_PATH, works)
        return artifact
    return {}


def canonical_implementation(base, branch=""):
    """Prefer proven implementation identity over a later task's branch text."""
    artifact = implementation_artifact(base)
    return artifact.get("branch") or branch, artifact.get("head") or ""


def delivery_artifact(base):
    """Return the generation-scoped branch selected by the delivery gate."""
    works = load(WORKS_PATH, {}) or {}
    meta = works.get(base) or {}
    artifact = meta.get("delivery_artifact") or {}
    if (artifact.get("generation") or "") != (meta.get("run_generation") or ""):
        return {}
    if (not artifact.get("branch")
            or not FULL_GIT_SHA.fullmatch(artifact.get("head") or "")):
        return {}
    return artifact


def record_delivery_artifact(base, branch, head):
    """Keep review_gate's pinned branch and head for Review, Verify, and merge."""
    head = (head or "").lower()
    if not branch or not FULL_GIT_SHA.fullmatch(head):
        return {}
    works = load(WORKS_PATH, {}) or {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta = works.setdefault(base, {
        "origin": ORIGIN_OWNER, "start_stage": "", "skipped": [],
        "reason": "", "at": now,
    })
    artifact = {
        "branch": branch,
        "head": head,
        "selected_at": now,
        "generation": meta.get("run_generation") or "",
    }
    meta["delivery_artifact"] = artifact
    save(WORKS_PATH, works)
    return artifact


def pin_reviewed_delivery(base, repo_identity, branch, result):
    """Restore the immutable delivery pin from a completed, still-current Review."""
    match = SPECIFICATION_HEAD_LINE.search(result or "")
    reviewed_head = (match.group(1).lower() if match else "")
    repo = (repo_identity or "").split("github.com/")[-1]
    if not repo or not branch or not FULL_GIT_SHA.fullmatch(reviewed_head):
        return {}, "Review не указал точный HEAD проверенной ветки."
    info = gh_json(["api", f"repos/{repo}/branches/{branch}"], strict=True)
    current_head = (((info or {}).get("commit") or {}).get("sha") or "").lower()
    if not FULL_GIT_SHA.fullmatch(current_head):
        return {}, "Не удалось подтвердить текущий HEAD проверенной ветки."
    if current_head != reviewed_head:
        return {}, "Ветка изменилась после Review; нужен Review нового снимка."
    return record_delivery_artifact(base, branch, current_head), ""


def selected_delivery(base, branch=""):
    """Prefer the gate-selected delivery branch; canonical is the fallback."""
    artifact = delivery_artifact(base)
    if artifact:
        return artifact["branch"], artifact["head"]
    return canonical_implementation(base, branch)


def implementation_context_lines(base, branch=""):
    branch, head = selected_delivery(base, branch)
    return ((f"Branch: {branch}\n" if branch else "")
            + (f"Implementation head: {head}\n" if head else ""))


def extract_branch(result, prev_context):
    """Find the pushed working branch: explicit BRANCH: line first, then any
    factory/* mention in the result, then the branch carried in the previous
    stage's context."""
    for source, pattern in ((result, BRANCH_LINE), (result, BRANCH_ANY),
                            (prev_context, CONTEXT_BRANCH), (prev_context, BRANCH_ANY)):
        match = pattern.search(source or "")
        if match:
            return match.group(1) if pattern.groups else match.group(0)
    return ""


def resume_branch_line(base, br, rounds=0):
    """Как продолжать работу: поверх старой ветки или с чистого листа.
    Ветка, которую уже возвращали за чужие файлы, тащит их в каждый круг —
    такую собираем заново от свежей главной и переносим только своё."""
    if not br:
        return ""
    dirty = cap_rescues(base, "DIRT") > 0 or cap_rescues(base, "GATE") > 0
    if dirty or rounds >= 3:
        return (
            f"Прошлая работа лежит в ветке: {br}\n"
            "ВЕТКУ НЕ ПРОДОЛЖАЙ: она уже тащит посторонние файлы, и каждый круг "
            "они возвращаются. Собери работу заново, с чистого листа:\n"
            "1) git fetch origin main\n"
            "2) git reset --hard origin/main   (ты остаёшься на своей ветке)\n"
            f"3) забери из старой ветки ТОЛЬКО свои файлы: git checkout {br} -- <файл> ... \n"
            "   (по одному, ровно те, что в ОБЛАСТИ задачи; ничего лишнего)\n"
            "4) git diff --name-only origin/main...HEAD — в списке ТОЛЬКО твои файлы\n"
            "5) git push --force-with-lease -u origin HEAD\n\n")
    return (
        f"Прошлая работа лежит в ветке: {br}\n"
        "ВЕТКУ В РАБОЧЕЙ КОПИИ НЕ ПЕРЕКЛЮЧАЙ — checkout чужой ветки ломает "
        "рабочую копию воркера. Оставайся на своей ветке и забери прошлую "
        f"работу так: `git fetch origin {br} && git reset --hard FETCH_HEAD`. "
        "Перед сдачей перебазируйся: `git fetch origin main && git rebase origin/main`. "
        "Запушь СВОЮ ветку: `git push --force-with-lease -u origin HEAD`.\n\n")


def branch_from_history(tasks, base, limit=8):
    """Ветка работы могла потеряться: стадия рухнула, и её отчёт пуст.
    Тогда ищем ветку в контексте предыдущих задач той же работы — иначе
    следующая стадия увидит пустой diff и справедливо всё отвергнет."""
    seen = 0
    for t in tasks or []:
        if base_title(t.get("title") or "") != base:
            continue
        seen += 1
        if seen > limit:
            break
        try:
            d = api(f"/tasks/{t['id']}")
        except Exception:
            continue
        task = d.get("task") or {}
        br = extract_branch("", task.get("context") or "")
        if not br:
            for a in (d.get("attempts") or []):
                br = extract_branch(a.get("output") or a.get("result") or "", "")
                if br:
                    break
        if br:
            return br
    return ""


# Порядок цены: haiku дешевле всех, fable/opus дороже всех примерно впятеро.
# Порядок цены по выходным токенам: haiku 4, luna 6, sonnet и terra 15,
# sol 30, opus и fable 75. Sol НЕ в одной группе с Opus — он втрое дешевле.
PRICE_RANK = (("haiku", 0), ("luna", 0), ("sonnet", 1), ("terra", 1),
              ("sol", 2), ("opus", 3), ("fable", 3))


SESSION_ROOT = f"{HOME}/.claude/projects"
PRICE = {"opus": (15.0, 75.0), "fable": (15.0, 75.0),
         "sonnet": (3.0, 15.0), "haiku": (0.80, 4.0),
         # GPT-5.6, официальные цены OpenAI за миллион токенов
         "sol": (5.0, 30.0), "terra": (2.50, 15.0), "luna": (1.0, 6.0)}
_usage_cache = {}          # путь файла -> (смещение, накопленный расход)
_codex_rollout_cache = {}  # путь -> состояние парсера и уже найденные события

# Версия тарифа намеренно привязана к точным API-именам. Похожее имя нельзя
# оценивать ценой соседней модели: в таком случае интерфейс показывает, что
# стоимость не определена. Суммы — USD за миллион токенов standard processing.
OPENAI_API_PRICE_VERSIONS = ({
    "effective_from": "2026-08-09",
    "source": "https://openai.com/api/pricing/",
    "models": {
        "gpt-5.6-sol": {"input": 5.0, "cached_input": 0.50, "output": 30.0},
        "gpt-5.6-terra": {"input": 2.50, "cached_input": 0.25, "output": 15.0},
        "gpt-5.6-luna": {"input": 1.0, "cached_input": 0.10, "output": 6.0},
    },
},)


def openai_api_cost(model, input_tokens, cached_input_tokens, output_tokens,
                    cache_write_tokens=0):
    """Расчётная API-стоимость или None для модели без точного тарифа."""
    price = OPENAI_API_PRICE_VERSIONS[-1]["models"].get(model)
    if not price:
        return None
    long_context = input_tokens + cached_input_tokens + cache_write_tokens > 272000
    input_multiplier = 2.0 if long_context else 1.0
    output_multiplier = 1.5 if long_context else 1.0
    return (input_tokens * price["input"] * input_multiplier
            + cached_input_tokens * price["cached_input"] * input_multiplier
            + cache_write_tokens * price["input"] * 1.25 * input_multiplier
            + output_tokens * price["output"] * output_multiplier) / 1e6


def _event_epoch(value):
    try:
        return calendar.timegm(time.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0


def _codex_usage_events(path):
    """Досчитать события Codex, читая у неизменённого rollout только хвост."""
    state = _codex_rollout_cache.get(path)
    try:
        size = os.path.getsize(path)
        if state is None or size < state["offset"]:
            state = {"offset": 0, "model": "", "previous_total": None,
                     "events": []}
        if size == state["offset"]:
            return state["events"]
        with open(path, errors="ignore") as fh:
            fh.seek(state["offset"])
            while True:
                line_offset = fh.tell()
                line = fh.readline()
                if not line:
                    break
                if not line.endswith("\n"):
                    fh.seek(line_offset)
                    break
                if '"model"' not in line and '"token_count"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if obj.get("type") == "turn_context":
                    model = payload.get("model")
                    if isinstance(model, str) and model:
                        state["model"] = model
                    continue
                if obj.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                usage = info.get("last_token_usage")
                total = info.get("total_token_usage")
                if usage is not None and not isinstance(usage, dict):
                    continue
                if total is not None and not isinstance(total, dict):
                    continue
                keys = ("input_tokens", "cached_input_tokens", "output_tokens",
                        "cache_write_input_tokens")
                containers = [value for value in (usage, total) if value is not None]
                model = usage.get("model") if usage is not None else None
                values = [container.get(key, 0) for container in containers for key in keys]
                if (model is not None and not isinstance(model, str)) or any(
                        isinstance(value, bool) or not isinstance(value, int) or value < 0
                        for value in values):
                    continue
                cache_write_known = any("cache_write_input_tokens" in value
                                        for value in containers)
                current = tuple(total.get(k, 0) for k in keys) if total is not None else None
                if not usage:
                    if current is None:
                        continue
                    if state["previous_total"] is None:
                        usage = dict(zip(keys, current))
                    else:
                        usage = dict(zip(keys, (max(0, n - old)
                                               for n, old in zip(current, state["previous_total"]))))
                if current is not None:
                    state["previous_total"] = current
                raw_input = usage.get("input_tokens", 0)
                cached = usage.get("cached_input_tokens", 0)
                cache_write = usage.get("cache_write_input_tokens", 0)
                output = usage.get("output_tokens", 0)
                if raw_input or cached or cache_write or output:
                    state["events"].append({"at": _event_epoch(obj.get("timestamp")),
                                            "model": model or state["model"],
                                            "input": max(0, raw_input - cached - cache_write),
                                            "cache_read": cached, "cache_write": cache_write,
                                            "cache_write_known": cache_write_known,
                                            "output": output})
            state["offset"] = fh.tell()
        _codex_rollout_cache[path] = state
    except OSError:
        pass
    return state["events"] if state else []


def codex_usage_snapshot(*since_epochs):
    """Один снимок журналов Codex сразу для всех запрошенных периодов."""
    paths = set(glob.glob(f"{HOME}/.codex/sessions/*/*/*/rollout-*.jsonl"))
    paths.update(glob.glob(f"{HOME}/.codex-*/sessions/*/*/*/rollout-*.jsonl"))
    events = [event for path in paths for event in _codex_usage_events(path)]
    result = {}
    for since_epoch in since_epochs:
        totals = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0,
                  "total_tokens": 0, "cost_usd": 0.0, "cost_defined": True,
                  "base_estimate": False, "unknown_models": []}
        unknown = set()
        for event in events:
            if event["at"] < since_epoch:
                continue
            totals["input"] += event["input"]
            totals["cache_read"] += event["cache_read"]
            totals["cache_write"] += event["cache_write"]
            totals["output"] += event["output"]
            cost = openai_api_cost(event["model"], event["input"],
                                   event["cache_read"], event["output"],
                                   event["cache_write"])
            if not event["cache_write_known"]:
                totals["base_estimate"] = True
            if cost is None:
                unknown.add(event["model"] or "неизвестная модель")
            else:
                totals["cost_usd"] += cost
        totals["total_tokens"] = (totals["input"] + totals["cache_read"]
                                  + totals["cache_write"] + totals["output"])
        totals["cost_defined"] = not unknown
        totals["unknown_models"] = sorted(unknown)
        result[since_epoch] = totals
    return result


def codex_usage_since(since_epoch):
    """Общий расход Codex с указанного момента, без ложной связи с задачей."""
    return codex_usage_snapshot(since_epoch)[since_epoch]


def _scan_usage(path):
    """Досчитать расход по журналу сессии, читая только новый хвост файла."""
    off, tot = _usage_cache.get(path, (0, {"in": 0, "cw": 0, "cr": 0, "out": 0, "model": ""}))
    try:
        size = os.path.getsize(path)
        if size < off:                       # файл пересоздан
            off, tot = 0, {"in": 0, "cw": 0, "cr": 0, "out": 0, "model": ""}
        if size == off:
            return tot
        with open(path, errors="ignore") as fh:
            fh.seek(off)
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    m = (json.loads(line).get("message") or {})
                except Exception:
                    continue
                u = m.get("usage") or {}
                if not u:
                    continue
                tot["in"] += u.get("input_tokens", 0)
                tot["cw"] += u.get("cache_creation_input_tokens", 0)
                tot["cr"] += u.get("cache_read_input_tokens", 0)
                tot["out"] += u.get("output_tokens", 0)
                tot["model"] = m.get("model") or tot["model"]
            off = fh.tell()
        _usage_cache[path] = (off, tot)
    except OSError:
        pass
    return tot


def task_cost_usd(attempt_ids):
    """Сколько уже стоила задача по журналам Claude Code. Это единственный
    источник правды: в API Factory расхода нет."""
    total = 0.0
    try:
        dirs = os.listdir(SESSION_ROOT)
    except OSError:
        return 0.0
    for att in attempt_ids:
        for d in dirs:
            if not d.endswith(att):
                continue
            p = os.path.join(SESSION_ROOT, d)
            try:
                files = os.listdir(p)
            except OSError:
                continue
            for fn in files:
                if not fn.endswith(".jsonl"):
                    continue
                t = _scan_usage(os.path.join(p, fn))
                key = next((k for k in PRICE if k in (t["model"] or "sonnet").lower()), "sonnet")
                pin, pout = PRICE[key]
                total += (t["in"] + t["cw"] * 1.25 + t["cr"] * 0.1) / 1e6 * pin
                total += t["out"] / 1e6 * pout
    return total


BUDGET_STOPS = f"{HOME}/pilot/budget_stops.json"


def note_budget_stop(base):
    """Работа, остановленная по деньгам, не должна перезапускаться сама.
    Иначе выходит круг: отмена -> автоответ «перезапусти» -> ещё один потолок.
    Так мы уже сожгли деньги дважды подряд без единой строчки кода."""
    try:
        rec = load(BUDGET_STOPS, {})
        rec[base] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(BUDGET_STOPS, rec)
    except Exception as e:
        log("budget_stop_write_error", repr(e))


def budget_stopped(base):
    try:
        rec = load(BUDGET_STOPS, {}) or {}
        if base not in rec:
            return False
        # Работу уже оживили (её нет в остановленных) — метка устарела:
        # снимаем, иначе любой обычный вопрос красится в «деньги».
        conf_disk = load(CONF_PATH, {}) or {}
        if base not in (conf_disk.get("stopped_pipelines") or []):
            rec.pop(base, None)
            save(BUDGET_STOPS, rec)
            return False
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ Деньги --
# Это не счёт из банка: воркеры работают на подписках, суммы — пересчёт по
# прайсу. Но как мера того, сколько подписки съедено, они годятся.
#
# Главное правило блока: потраченное само по себе ничего не значит. Большая
# работа честно стоит дорого. Плохо не «дорого», а «дорого и без движения».
# Поэтому потолок — только повод посмотреть, а решает признак движения:
# сдвинулась ли вершина рабочей ветки.

STAGE_BASE_USD = {"Triage": 1.5, "Specification": 2.5,
                  "Implement + Test": 8.0, "Review": 3.0, "Verify": 3.0}
COMPLEXITY_FACTOR = {"low": 0.6, "medium": 1.0, "high": 2.0}
WORK_CAP_USD = {"low": 15.0, "medium": 40.0, "high": 90.0}
# Множитель потолка — отношение к выходной цене sonnet ($15).
MODEL_FACTOR = (("haiku", 0.3), ("luna", 0.4), ("terra", 1.0), ("sonnet", 1.0),
                ("sol", 2.0), ("opus", 5.0), ("fable", 5.0))
BUDGET_PATH = f"{HOME}/pilot/budget.json"
CHEAPER = {"high": "medium", "medium": "low", "low": "low"}
MAX_EXTENSIONS = 2


def model_factor(worker_name):
    """Дорогая модель получает больше долларов не в награду, а чтобы шагов
    у неё вышло примерно столько же, сколько у дешёвой."""
    n = (worker_name or "").lower()
    for key, f in MODEL_FACTOR:
        if key in n:
            return f
    return 1.0


def complexity_of(conf, stage, worker_name):
    """Сложность нигде не хранится — она видна по тому, какому воркеру
    досталась стадия."""
    for s in conf.get("stages", []):
        if s.get("workflow") != stage:
            continue
        tiers = s.get("workers")
        if isinstance(tiers, dict):
            for cx, name in tiers.items():
                if name and name == worker_name:
                    return cx
    return "medium"


def stage_cap(conf, stage, complexity, worker_name):
    base = float((conf.get("stage_base_usd") or STAGE_BASE_USD).get(stage, 4.0))
    cf = float((conf.get("complexity_factor") or COMPLEXITY_FACTOR).get(complexity, 1.0))
    return round(base * cf * model_factor(worker_name), 2)


def work_cap(conf, complexity):
    return float((conf.get("work_cap_usd") or WORK_CAP_USD).get(complexity, 40.0))


_attempts_cache = {}


def attempts_of(task_id, finished):
    """Попытки завершённой задачи больше не меняются — их можно запомнить."""
    if finished and task_id in _attempts_cache:
        return _attempts_cache[task_id]
    try:
        d = api(f"/tasks/{task_id}")
    except Exception:
        return []
    ids = [a["id"] for a in (d.get("attempts") or []) if a.get("id")]
    if finished:
        _attempts_cache[task_id] = ids
    return ids


def _live(task):
    return task.get("state") in ("running", "queued", "preparing")


def work_spent(tasks, base):
    """Сколько съела работа целиком — все стадии и все перезапуски. Считать по
    одной задаче бессмысленно: перезапуск заводит новую, и ровно так конвейер
    трижды заплатил один и тот же потолок."""
    atts = []
    for t in tasks:
        if base_title(t.get("title") or "") != base:
            continue
        atts += attempts_of(t["id"], not _live(t))
    return task_cost_usd(atts)


def day_spent(tasks, codex_day=None):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    atts = []
    for t in tasks:
        if (t.get("created_at") or "")[:10] != today:
            continue
        atts += attempts_of(t["id"], not _live(t))
    start = calendar.timegm(time.strptime(today, "%Y-%m-%d"))
    codex_day = codex_day or codex_usage_since(start)
    return task_cost_usd(atts) + codex_day["cost_usd"]


def branch_head(branch):
    """Вершина рабочей ветки на origin — признак того, что работа движется."""
    # Ветка приходит из отчёта агента. Допускаем только простые сегменты
    # служебных веток, чтобы это значение никогда не становилось командой.
    if not re.fullmatch(
            r"factory/(?:[A-Za-z0-9][A-Za-z0-9._-]*)(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*",
            branch or ""):
        return ""
    ok, out = _fixed_command(
        ["sudo", "-n", "/usr/local/bin/fx", "repo", "head", branch])
    if not ok:
        return ""
    m = re.search(r"\b[0-9a-f]{40}\b", out or "")
    return m.group(0) if m else ""


def stop_pipeline(conf, base):
    """Насовсем остановить работу: пилот её больше не двигает."""
    try:
        disk = load(CONF_PATH, {})
        sp = disk.get("stopped_pipelines") or []
        if base not in sp:
            sp.append(base)
            disk["stopped_pipelines"] = sp
            save(CONF_PATH, disk)
        conf["stopped_pipelines"] = sp
    except Exception as e:
        log("stop_pipeline_error", repr(e))


def write_budget_retry(conf, task_id, stage, base, repo_id, complexity, branch, spent, cap):
    """Автоматическое решение вместо вопроса владельцу: перезапустить ту же
    стадию ступенью дешевле и с прямым указанием сузить объём."""
    rec = write_question(
        task_id, stage, stage, base, repo_id,
        "Стадия съела ${:.2f} при потолке ${:.2f}, а рабочая ветка "
        "за это время не сдвинулась.".format(spent, cap),
        "Перезапустить ту же стадию на модели попроще и с более узким заданием?",
        [], "", branch)
    rec["status"] = "answered"
    rec["answered_by"] = "budget"
    rec["complexity_hint"] = complexity
    rec["answer"] = (
        "Перезапусти эту же стадию, но сузь объём. Не пытайся сделать всё за "
        "один заход: возьми самый маленький кусок, который можно довести до "
        "рабочего состояния, закоммить и запушь его, и только потом берись за "
        "следующий. Если работа целиком не влезает — сделай часть и честно "
        "напиши в отчёте, что осталось. Пустую ветку не оставляй.")
    save(QUESTION_DIR + "/" + task_id + ".json", rec)


def budget_guard(conf, tasks, workers=None):
    """Два сторожа под две разные беды.

    Первый — потолок работы целиком: сумма по всем стадиям и перезапускам
    одного названия. Второй — ловец кругов: он смотрит не на сумму, а на то,
    сдвинулась ли ветка. Агент, крутящийся на месте, останавливается, даже
    если съел доллар; работа, которая честно идёт, продлевается сама.

    Решения принимаются здесь, владельцу уходит уведомление, а не вопрос.
    Единственное, что требует его участия, — исчерпанный потолок работы.
    """
    st = load(BUDGET_PATH, {})
    changed = False

    by_id = {}
    seq = (workers or {}).values() if isinstance(workers, dict) else (workers or [])
    for w in seq:
        if isinstance(w, dict) and w.get("id"):
            by_id[w["id"]] = w

    for t in tasks:
        if t.get("state") not in ("running", "preparing"):
            continue
        title = t.get("title") or ""
        if not title.startswith(PREFIX):
            continue
        m = STAGE_TITLE_RE.match(title)
        if not m:
            continue
        stage, base = m.group(1).strip(), m.group(2).strip()

        wname = (by_id.get(t.get("worker_id")) or {}).get("name", "")
        cx = complexity_of(conf, stage, wname)
        rec = st.setdefault(base, {"extensions": 0, "downgrades": 0,
                                   "last_head": "", "stopped": ""})
        ext = int(rec.get("extensions") or 0)
        cap = stage_cap(conf, stage, cx, wname) * (1.5 ** ext)

        # Запоминаем вершину заранее, пока задача ещё укладывается в бюджет.
        # Иначе первая проверка после перерасхода примет уже существующий
        # коммит за прогресс этой задачи и подарит ей несколько дорогих кругов.
        branch = branch_from_history(tasks, base)
        head = branch_head(branch)
        if not rec.get("last_head") and head:
            rec["last_head"] = head
            changed = True

        spent = task_cost_usd(attempts_of(t["id"], False))
        if spent < cap:
            continue

        moved = bool(head) and head != (rec.get("last_head") or "")
        # credit — списание за прошлые сгоревшие заходы, в которых виновата
        # не работа, а наша собственная поломка.
        total = work_spent(tasks, base) - float(rec.get("credit") or 0)
        total = max(0.0, total)
        wcap = work_cap(conf, cx)

        # Работа идёт — продлеваем сами и молча.
        if moved and total < wcap and ext < MAX_EXTENSIONS:
            rec["extensions"] = ext + 1
            rec["last_head"] = head
            changed = True
            log(f"BUDGET EXTEND base={base!r} stage={stage} "
                f"потрачено=${spent:.2f} новый потолок=${cap * 1.5:.2f} (ветка движется)")
            if rec["extensions"] >= MAX_EXTENSIONS:
                notify(conf, f"Продлил бюджет · {stage}",
                       f"{base}\n\nРабота идёт, но дороже ожидаемого: "
                       f"${total:.2f} из ${wcap:.0f}. Продлил сам, от тебя ничего не нужно.",
                       tags="hourglass", click=f"{UI_BASE}/work")
            continue

        try:
            api(f"/tasks/{t['id']}/cancel", {})
        except Exception as e:
            log(f"budget: не смог остановить {t['id'][:8]}: {e}")
            continue

        # Потолок работы исчерпан или дешёвый перезапуск уже был — стоп.
        if total >= wcap or int(rec.get("downgrades") or 0) >= 1:
            rec["stopped"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if total >= wcap:
                why_stop = ("Потолок работы исчерпан: съедено {0:.2f} из {1:.0f} "
                            "долларов.".format(total, wcap))
            else:
                why_stop = ("Два захода подряд сожгли бюджет этапа, а работа не "
                            "сдвинулась ни на один коммит (съедено {0:.2f} из {1:.0f} "
                            "долларов). Жечь дальше без нового плана не буду."
                            .format(total, wcap))
            changed = True
            note_budget_stop(base)
            stop_pipeline(conf, base)
            log(f"BUDGET HARD STOP base={base!r} всего=${total:.2f} "
                f"потолок работы=${wcap:.0f}")
            notify(conf, "Остановил работу · деньги",
                   base + chr(10) + chr(10) + why_stop + chr(10) +
                   "Оживить: скажи Клоду — или в Настройках убери работу из поля «Остановленные процессы».",
                   priority="high", tags="moneybag", click=f"{UI_BASE}/work")
            continue

        # Круг: денег ушло много, ветка не сдвинулась. Один автоматический
        # перезапуск ступенью дешевле и с более узким заданием.
        rec["downgrades"] = int(rec.get("downgrades") or 0) + 1
        rec["extensions"] = 0
        rec["last_head"] = head
        changed = True
        cheaper = CHEAPER.get(cx, "low")
        repo_id = ""
        try:
            repo_id = (api(f"/tasks/{t['id']}").get("task") or {}).get("repository_id") or ""
        except Exception:
            pass
        write_budget_retry(conf, t["id"], stage, base, repo_id, cheaper, branch, spent, cap)
        log(f"BUDGET DOWNGRADE base={base!r} stage={stage} {cx} -> {cheaper} "
            f"потрачено=${spent:.2f} потолок=${cap:.2f}, движения нет")
        notify(conf, f"Перезапускаю дешевле · {stage}",
               f"{base}\n\nАгент крутился на месте и съел ${spent:.2f}. "
               "Перезапускаю на модели попроще с более узким заданием. "
               "Решение принято, от тебя ничего не нужно.",
               tags="arrows_counterclockwise", click=f"{UI_BASE}/work")

    if changed:
        save(BUDGET_PATH, st)


def day_budget_blocks(conf, tasks, codex_day=None):
    """Стоп-кран по подпискам. Доллары тут условные: агенты работают на
    подписках, а не по счёту API. Настоящий предел — проценты, которые
    провайдеры сообщают сами."""
    pct_cap = float(conf.get("day_pct_cap") or 90)
    real = load(PROVIDER_LIMITS_PATH, {}) or {}
    hot = []
    for prov in ("codex", "claude"):
        rec = real.get(prov) or {}
        up = rec.get("used_percent")
        if not isinstance(up, (int, float)):
            up = (rec.get("percents") or {}).get("seven_day.utilization")
        if isinstance(up, (int, float)) and up >= pct_cap:
            hot.append((prov, up))
    if len(hot) >= 2:
        st = load(BUDGET_PATH, {})
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if st.get("_day_notified") != today:
            st["_day_notified"] = today
            save(BUDGET_PATH, st)
            names = ", ".join("%s %d%%" % (p, u) for p, u in hot)
            log("DAY CAP по подпискам: " + names)
            notify(conf, "Подписки на исходе",
                   "Обе подписки почти израсходованы (" + names + "). "
                   "Начатое доигрываю, новое не беру, пока лимит не обновится.",
                   tags="moneybag", click=f"{UI_BASE}/")
        return True
    cap = float(conf.get("day_cap_usd") or 0)
    if cap <= 0:
        return False
    spent = day_spent(tasks, codex_day)
    if spent < cap:
        return False
    st = load(BUDGET_PATH, {})
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if st.get("_day_notified") != today:
        st["_day_notified"] = today
        save(BUDGET_PATH, st)
        log(f"DAY CAP: за сегодня ${spent:.2f} при потолке ${cap:.0f} — "
            "новые задачи не запускаю")
        notify(conf, "Дневной потолок",
               f"За сегодня ушло ${spent:.2f} при потолке ${cap:.0f}. "
               "Начатое доигрывается, новое не беру до завтра.",
               tags="moneybag", click=f"{UI_BASE}/")
    return True


LIMITS_PATH = f"{HOME}/pilot/limits.json"

# По каким словам в ошибке понятно, что мы упёрлись в лимит подписки, а не в баг.
LIMIT_SIGNS = re.compile(
    r"(usage limit reached|rate.?limit|429|too many requests|quota exceeded|"
    r"weekly limit|limit reached|out of (?:credits|usage)|resets? at|try again (?:later|at)|"
    r"upgrade to increase|плат[её]жный лимит|лимит исчерпан|"
    r"reached your [^.]{0,40}limit|usage-credits|out of usage limits)", re.I)
RESET_AT = re.compile(
    r"(?:resets?(?:\s+at)?|try again at|available again at)\s*[:\-]?\s*"
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2})?Z?|[0-9]{1,2}:[0-9]{2}\s*(?:AM|PM)?)", re.I)


def provider_of(worker_name):
    """К какой подписке относится воркер."""
    n = (worker_name or "").lower()
    if n.startswith("claude"):
        return "claude"
    if n.startswith("codex"):
        return "codex"
    return "other"


def load_limits():
    return load(LIMITS_PATH, {}) or {}


def limit_active(provider, limits=None):
    """Провайдер сейчас в блоке? Блок бывает двух видов: ручной — владелец
    выключил провайдера рубильником, и автоматический — упёрлись в лимит.
    Автоматический снимается сам, когда проходит срок; ручной — только руками."""
    rec = (limits if limits is not None else load_limits()).get(provider) or {}
    if rec.get("manual_off"):
        return True
    if rec.get("state") not in ("exhausted", "throttled"):
        return False
    until = rec.get("resets_at") or ""
    if until:
        try:
            if time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) >= until:
                return False
        except Exception:
            pass
    else:
        # без явного срока держим блок час — этого хватает, чтобы не долбиться
        seen = rec.get("detected_at") or ""
        if seen and (time.time() - rec.get("detected_epoch", 0)) > 900:
            return False
    return True


def note_limit(conf, provider, evidence, resets_at=""):
    """Записать, что подписка упёрлась в лимит. Дальше пилот сам не полезет
    в этого провайдера, пока срок не выйдет."""
    limits = load_limits()
    prev = limits.get(provider) or {}
    limits[provider] = {
        "manual_off": bool(prev.get("manual_off")),
        "state": "exhausted",
        "resets_at": resets_at,
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "detected_epoch": int(time.time()),
        "evidence": (evidence or "")[:300],
    }
    save(LIMITS_PATH, limits)
    if prev.get("state") != "exhausted":
        log(f"LIMIT provider={provider} до {resets_at or 'через час'}: {(evidence or '')[:120]}")
        notify(conf, f"Упёрлись в лимит · {provider}",
               f"Подписка {provider} исчерпана."
               + (f"\nВосстановится: {resets_at}" if resets_at else "\nПопробую снова через час.")
               + "\n\nРабота уходит на второго провайдера, если он свободен.",
               priority="default", tags="hourglass", click=f"{UI_BASE}/access")


def clear_limit(provider):
    limits = load_limits()
    if provider in limits and limits[provider].get("state") != "ok":
        limits[provider] = {"state": "ok",
                            "manual_off": bool((limits.get(provider) or {}).get("manual_off")),
                            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        save(LIMITS_PATH, limits)
        log(f"LIMIT CLEARED provider={provider}")


def detect_limits(conf, tasks, workers_by_id):
    """Разбор свежих неудач: если этап упал из-за лимита подписки, это не повод
    перезапускать его три раза — это повод подождать."""
    for t in tasks[:15]:                       # только свежие, вглубь не лезем
        if t.get("state") != "failed":
            continue
        wname = (workers_by_id.get(t.get("worker_id")) or {}).get("name", "")
        prov = provider_of(wname)
        if prov == "other":
            continue
        try:
            detail = api(f"/tasks/{t['id']}")
        except Exception:
            continue
        atts = detail.get("attempts") or []
        # Только ошибка последней неудачной попытки является сигналом провайдера.
        # Result — свободный отчёт агента: в нём могут законно обсуждаться лимиты.
        text = str((atts[-1] if atts else {}).get("error") or "").strip()
        if not text or not LIMIT_SIGNS.search(text):
            continue
        # Сбой входа/сети — не лимит подписки, а поломка окружения.
        if INFRA_SIGNS.search(text):
            continue
        m = RESET_AT.search(text)
        note_limit(conf, prov, text, m.group(1) if m else "")


DASH_PATH = f"{HOME}/pilot/dashboard.json"
AUTOMATION_STATUS_PATH = f"{HOME}/pilot/automation-status.json"
AUTOMATION_STATUS_UNITS = (
    ("factory-pilot", "pilot"),
    ("factory-release-broker", "release_broker"),
    ("factory-intake", "release"),
)
_dash_slow = {"at": 0, "data": {}}


def parse_systemd_timestamp(timestamp):
    """Return a UTC ISO timestamp without relabelling a local wall-clock time."""
    timestamp = timestamp.strip()
    try:
        return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(
            datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass
    match = re.fullmatch(r"\w{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+)", timestamp)
    if not match:
        return None
    offsets = {"UTC": 0, "GMT": 0, "CDT": -5, "CST": -6, "EDT": -4, "EST": -5,
               "MDT": -6, "MST": -7, "PDT": -7, "PST": -8}
    offset = offsets.get(match.group(2))
    if offset is None:
        return None
    parsed = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=offset))).astimezone(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_automation_timestamp(timestamp):
    """Return a valid host timestamp normalized to UTC, or None."""
    try:
        parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def is_future_automation_timestamp(timestamp, now=None):
    """Reject clock-skewed activity so it cannot be shown as live."""
    try:
        parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return True
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc) > now
    except ValueError:
        return True


def write_automation_status(run=None, janitor_log="/var/log/factory-janitor.log", pilot_completed_at=None):
    """Write a minimal allowlisted host snapshot; one failed unit stays visible."""
    run = run or subprocess.run
    rows = []
    for unit, category in AUTOMATION_STATUS_UNITS:
        row = {"source": "host", "id": unit, "category": category,
               "status": "unknown", "data_status": "no_data"}
        try:
            result = run(["systemctl", "show", f"{unit}.service",
                          "--property=ActiveState", "--property=ActiveEnterTimestamp"],
                         capture_output=True, text=True, timeout=5, check=False)
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            timestamp = parse_systemd_timestamp(fields.get("ActiveEnterTimestamp", ""))
            if (result.returncode == 0 and fields.get("ActiveState") and timestamp
                    and not is_future_automation_timestamp(timestamp)):
                row.update(status=fields["ActiveState"], data_status="ok",
                           last_activity_at=timestamp)
        except Exception:
            pass
        rows.append(row)
    janitor = {"source": "host", "id": "factory-janitor", "category": "janitor",
               "status": "unknown", "data_status": "no_data"}
    try:
        with open(janitor_log, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-100:]
        matches = [re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})", line) for line in lines]
        stamps = [parse_automation_timestamp(match.group(0)) for match in matches if match]
        stamps = [stamp for stamp in stamps if stamp and not is_future_automation_timestamp(stamp)]
        if stamps:
            janitor.update(status="completed", data_status="ok", last_activity_at=stamps[-1])
    except (OSError, UnicodeError):
        pass
    rows.append(janitor)
    if pilot_completed_at is not None:
        rows[0].update(data_status="ok", last_activity_at=pilot_completed_at,
                       status="active")
    save(AUTOMATION_STATUS_PATH, {"observed_at": datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z"), "automations": rows})

PROJECT_READINESS_CHECKS = (
    ("repository", "Репозиторий"),
    ("workers", "Исполнители"),
    ("safe_environment", "Безопасный стенд"),
    ("access", "Доступы"),
    ("tests", "Тесты"),
    ("release", "Выпуск"),
    ("rollback", "Откат"),
    ("secrets", "Секреты"),
    ("browser", "Браузерный доступ"),
)
PROJECT_PROVIDER_CATALOG = {
    "trade": {
        "safe_scope": "staging",
        "release_environment": "Стейдж",
        "rollback_argv": ("sudo", "-n", "/usr/local/bin/fx", "staging", "rollback"),
    },
    "factory": {
        "safe_scope": "",
        "release_environment": "Прод",
        "rollback_argv": ("sudo", "-n", "/usr/local/bin/fx", "factory", "rollback"),
    },
}
BROWSER_READINESS_MAX_AGE_SECONDS = 24 * 60 * 60


def _sh(cmd, timeout=25):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or p.stderr or "").strip()
    except Exception as e:
        return f"ошибка: {e}"


def _project_repo_dirs(repository_id):
    """Return only an exact managed-repository cache, never a guessed path."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", repository_id or ""):
        return []
    matches = glob.glob(f"{HOME}/workers/*/repositories/{repository_id}")
    return [path for path in matches if os.path.isdir(os.path.join(path, ".git"))]


def _project_repo_dir(repository_id):
    return next(iter(_project_repo_dirs(repository_id)), "")


def _fixed_command(args, timeout=25):
    """Run a code-owned argv without a shell and preserve success separately."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout or result.stderr or "").strip()
    except Exception:
        return False, ""


def _project_main(repository_id):
    candidates = []
    for repo in _project_repo_dirs(repository_id):
        ok, remote_head = _fixed_command(
            ["git", "-c", "safe.directory=*", "-C", repo, "symbolic-ref", "--short",
             "refs/remotes/origin/HEAD"], 10)
        if not ok:
            ok, advertised = _fixed_command(
                ["git", "-c", "safe.directory=*", "-C", repo, "ls-remote", "--symref",
                 "origin", "HEAD"], 25)
            default_match = re.search(r"^ref:\s+refs/heads/([^\s]+)\s+HEAD$", advertised,
                                      re.MULTILINE) if ok else None
            remote_head = f"origin/{default_match.group(1)}" if default_match else ""
        if not ok or not re.fullmatch(r"origin/[A-Za-z0-9._/-]+", remote_head):
            continue
        branch = remote_head.removeprefix("origin/")
        fetched, _ = _fixed_command(
            ["git", "-c", "safe.directory=*", "-C", repo, "fetch", "origin", branch], 25)
        if not fetched:
            continue
        ok, value = _fixed_command(
            ["git", "-c", "safe.directory=*", "-C", repo, "log", "-1", "--format=%ct%x00%s",
             remote_head], 10)
        if ok and "\x00" in value:
            timestamp, subject = value.split("\x00", 1)
            if timestamp.isdigit() and subject:
                candidates.append((int(timestamp), subject[:90]))
    return {"main_subject": max(candidates)[1]} if candidates else {}


def _provider_environments(provider_type):
    if provider_type == "trade":
        return (("Стейдж", "staging"), ("Прод", "prod"))
    if provider_type == "factory":
        return (("Прод", "factory"),)
    return ()


def _environment_snapshot(label, scope, repository_id):
    prefix = ["sudo", "-n", "/usr/local/bin/fx", scope]
    release_ok, release_out = _fixed_command(prefix + ["release-info"])
    match = re.search(r"current\s*->\s*(\S+)", release_out) if release_ok else None
    factory_label = re.search(r"^(релиз[^\n]+)", release_out, re.IGNORECASE) if release_ok else None
    health_ok, health_out = _fixed_command(prefix + ["health"])
    health_codes = re.findall(r"HTTP\s+([1-5]\d\d)", health_out) if health_ok else []
    if not (match or factory_label) or not health_codes:
        return {"name": label, "status": "unavailable"}
    release_id = os.path.basename(match.group(1).rstrip("/")) if match else ""
    release_label = factory_label.group(1) if factory_label else f"Сборка {release_id}"
    if match:
        for repo in _project_repo_dirs(repository_id):
            subject_ok, subject = _fixed_command(
                ["git", "-c", "safe.directory=*", "-C", repo, "log", "-1", "--format=%s", release_id], 10)
            if subject_ok and subject:
                release_label = subject[:90]
                break
    return {
        "name": label,
        "status": "available",
        "release_label": release_label,
        "health": "healthy" if all(code.startswith(("2", "3")) for code in health_codes) else "unhealthy",
    }


def _readiness_check(key, state, reason):
    title = dict(PROJECT_READINESS_CHECKS)[key]
    return {"key": key, "title": title, "state": state, "reason": reason}


def _readiness_verdict(checks):
    states = [check.get("state") for check in checks]
    if "blocked" in states:
        return "blocked"
    if len(states) == len(PROJECT_READINESS_CHECKS) and all(state == "ready" for state in states):
        return "ready"
    return "needs_configuration"


def _browser_readiness(now=None, path=None):
    now = time.time() if now is None else now
    path = path or f"{HOME}/pilot/browser-readiness.json"
    if not os.path.exists(path):
        return _readiness_check("browser", "unknown", "Нет подтверждения sandbox smoke браузера.")
    try:
        marker = load(path, None)
        passed_at = marker.get("passed_at", "") if isinstance(marker, dict) else ""
        fingerprint = marker.get("browser_fingerprint", "") if isinstance(marker, dict) else ""
        passed = datetime.datetime.fromisoformat(passed_at.replace("Z", "+00:00")).timestamp()
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("invalid browser fingerprint")
    except Exception:
        return _readiness_check("browser", "blocked", "Маркер browser smoke повреждён.")
    age = now - passed
    if age < -300 or age > BROWSER_READINESS_MAX_AGE_SECONDS:
        return _readiness_check("browser", "unknown", "Подтверждение browser smoke просрочено.")
    return _readiness_check("browser", "ready", "Свежий sandbox smoke браузера прошёл.")


def _access_readiness(scopes, safe_scope):
    if not safe_scope:
        return _readiness_check(
            "access", "unknown", "Безопасный стенд не выбран; production-write не требуется.")
    matching = next((scope for scope in scopes if isinstance(scope, dict)
                     and scope.get("key") == safe_scope), None)
    if matching is None:
        return _readiness_check("access", "unknown", f"Нет данных о доступе {safe_scope}.")
    if not matching.get("enabled"):
        return _readiness_check("access", "blocked", f"Доступ {safe_scope} выключен.")
    return _readiness_check(
        "access", "ready", f"Доступ {safe_scope} разрешён; production-write не требуется.")


def _verify_readiness(tasks, repository_id):
    candidates = [task for task in tasks
                  if task.get("repository_id") == repository_id
                  and (match := STAGE_TITLE_RE.match(task.get("title", "")))
                  and match.group(1) == "Verify"
                  and task.get("state") in ("succeeded", "failed", "cancelled")]
    candidates.sort(key=lambda task: (task.get("created_at", ""), task.get("id", "")), reverse=True)
    if not candidates:
        return _readiness_check("tests", "unknown", "Нет завершённой проверки Verify для проекта.")
    try:
        detail = api(f"/tasks/{candidates[0]['id']}")
    except Exception:
        return _readiness_check("tests", "unknown", "Итог последней Verify недоступен.")
    attempts = detail.get("attempts") or []
    completed = next((attempt for attempt in reversed(attempts)
                      if attempt.get("state") in ("succeeded", "failed", "cancelled")), None)
    result = str((completed or {}).get("result") or "")
    if result.startswith("PASS"):
        checked = str((completed or {}).get("completed_at") or "")[:16]
        suffix = f" ({checked})" if checked else ""
        return _readiness_check("tests", "ready", "Последняя Verify завершилась PASS" + suffix + ".")
    if candidates[0].get("state") == "failed" or (completed or {}).get("state") == "failed":
        return _readiness_check("tests", "blocked", "Последняя Verify завершилась неуспешно.")
    return _readiness_check("tests", "unknown", "У последней Verify нет подтверждения PASS.")


def _rollback_event_reason(provider_type):
    latest = ""
    try:
        with open(RELEASE_EVENTS_PATH, encoding="utf-8", errors="replace") as event_file:
            for line in event_file:
                event = json.loads(line)
                command_key = str(event.get("command_key") or event.get("id") or "")
                expected = "factory" if provider_type == "factory" else "staging"
                if event.get("rollback") is True and expected in command_key:
                    latest = str(event.get("at") or event.get("created_at") or "")[:16]
    except Exception:
        pass
    return (f" Последний зафиксированный откат: {latest}." if latest
            else " Зафиксированных событий отката нет.")


def _project_readiness(repository, provider_type, environments, tasks, access_scopes,
                       browser_check, now=None):
    repository_id = str(repository.get("id", ""))
    checks = []
    if _project_repo_dirs(repository_id):
        checks.append(_readiness_check("repository", "ready", "Точный checkout репозитория доступен."))
    else:
        checks.append(_readiness_check("repository", "blocked", "Точный checkout репозитория недоступен."))

    try:
        routing = api(f"/repositories/{repository_id}/readiness")
        if routing.get("routing_ready") is True:
            checks.append(_readiness_check("workers", "ready", "Маршрутизация на готового исполнителя подтверждена."))
        elif "routing_ready" in routing:
            reasons = sorted(str(worker.get("reason", ""))[:120]
                             for worker in routing.get("workers") or []
                             if isinstance(worker, dict) and worker.get("reason"))
            reason = "Нет готового исполнителя." + ((" " + "; ".join(reasons[:2])) if reasons else "")
            checks.append(_readiness_check("workers", "blocked", reason))
        else:
            checks.append(_readiness_check("workers", "unknown", "Данные маршрутизации недоступны."))
    except Exception:
        checks.append(_readiness_check("workers", "unknown", "Данные маршрутизации недоступны."))

    provider = PROJECT_PROVIDER_CATALOG.get(provider_type)
    safe_scope = provider.get("safe_scope", "") if provider else ""
    if not provider:
        checks.append(_readiness_check("safe_environment", "unknown", "Провайдер безопасного стенда не настроен."))
    elif not safe_scope:
        checks.append(_readiness_check("safe_environment", "unknown", "Для Factory отдельный безопасный стенд не выбран."))
    else:
        ok, output = _fixed_command(["sudo", "-n", "/usr/local/bin/fx", safe_scope, "health"])
        codes = re.findall(r"HTTP\s+([1-5]\d\d)", output) if ok else []
        if not ok:
            checks.append(_readiness_check("safe_environment", "blocked", "Health безопасного стенда завершился ошибкой."))
        elif not codes:
            checks.append(_readiness_check("safe_environment", "unknown", "Health безопасного стенда не дал проверяемого статуса."))
        elif all(code.startswith(("2", "3")) for code in codes):
            checks.append(_readiness_check("safe_environment", "ready", "Безопасный staging отвечает."))
        else:
            checks.append(_readiness_check("safe_environment", "blocked", "Безопасный staging отвечает с ошибкой."))

    checks.append(_access_readiness(access_scopes, safe_scope))
    checks.append(_verify_readiness(tasks, repository_id))

    if not provider:
        checks.append(_readiness_check("release", "unknown", "Провайдер сведений о выпуске не настроен."))
        checks.append(_readiness_check("rollback", "unknown", "Процедура отката не описана."))
    else:
        release_environment = next((item for item in environments
                                    if item.get("name") == provider["release_environment"]), None)
        if release_environment and release_environment.get("status") == "available":
            checks.append(_readiness_check("release", "ready", "Метка текущего выпуска распознана."))
        else:
            checks.append(_readiness_check("release", "unknown", "Метка текущего выпуска недоступна."))
        # Presence in this immutable catalog is the proof. The argv is never executed here.
        checks.append(_readiness_check(
            "rollback", "ready", "Процедура отката описана." + _rollback_event_reason(provider_type)))

    if not safe_scope:
        checks.append(_readiness_check("secrets", "unknown", "Безопасный scope для проверки имён секретов не выбран."))
    else:
        ok, output = _fixed_command(
            ["sudo", "-n", "/usr/local/bin/fx", safe_scope, "env-names"])
        names = sorted({line.strip() for line in output.splitlines()
                        if re.fullmatch(r"[A-Z][A-Z0-9_]*", line.strip())}) if ok else []
        if not ok:
            checks.append(_readiness_check("secrets", "unknown", "Имена секретов недоступны."))
        elif not names:
            checks.append(_readiness_check("secrets", "unknown", "Проверяемых имён секретов нет."))
        else:
            checks.append(_readiness_check("secrets", "ready", f"Доступны имена секретов: {len(names)}."))

    checks.append(dict(browser_check))
    ordered = {check["key"]: check for check in checks}
    checks = [ordered[key] for key, _title in PROJECT_READINESS_CHECKS]
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
        time.time() if now is None else now))
    return {"verdict": _readiness_verdict(checks), "checked_at": checked_at, "checks": checks}


def dashboard_slow(conf):
    """Тяжёлая часть: проекты, выпуски и здоровье сред. Раз в пять минут."""
    if time.time() - _dash_slow["at"] < 300:
        return _dash_slow["data"]
    configured = {str(item.get("remote_identity", "")).strip().lower(): item.get("type", "")
                  for item in conf.get("project_providers", []) if isinstance(item, dict)}
    try:
        tasks = all_tasks()
    except Exception:
        tasks = []
    try:
        access_scopes = api("/access").get("scopes") or []
    except Exception:
        access_scopes = []
    now = time.time()
    browser_check = _browser_readiness(now)
    projects = []
    for repository in api("/repositories").get("repositories") or []:
        if not repository.get("enabled"):
            continue
        identity = str(repository.get("remote_identity", ""))
        project = {
            "id": repository.get("id", ""),
            "remote_identity": identity,
            "name": identity.rstrip("/").rsplit("/", 1)[-1] or identity,
            **_project_main(repository.get("id", "")),
        }
        provider_type = configured.get(identity.lower(), "")
        environments = _provider_environments(provider_type)
        if not environments:
            project["provider_status"] = "not_configured"
            project["environments"] = []
        else:
            project["provider_status"] = "configured"
            project["environments"] = [_environment_snapshot(label, scope, repository.get("id", ""))
                                       for label, scope in environments]
        project["readiness"] = _project_readiness(
            repository, provider_type, project["environments"], tasks, access_scopes,
            browser_check, now)
        projects.append(project)
    _dash_slow.update({"at": time.time(), "data": projects})
    return projects


def brain_block(conf):
    """Чем думает оркестратор: цепочка и кто отвечал в последний раз."""
    limits = load_limits()
    chain = [{"cli": e.get("cli", ""), "model": e.get("model", ""),
              "provider": e.get("provider", ""), "note": e.get("note", ""),
              "blocked": bool(limit_active(e.get("provider", ""), limits))}
             for e in brain_chain(conf)]
    return {"chain": chain, "last": load(BRAIN_STATE, {})}


# ------------------------------------------------------------- Сервер ------
# Пороги подобраны под нашу работу: агенты собирают, ставят пакеты и гоняют
# тесты, поэтому упираемся мы обычно в процессор, потом в память, и лишь
# затем в диск.

def _verdict(value, ok, tight):
    """Три состояния вместо числа: человеку нужно решение, а не проценты."""
    if value < ok:
        return "ok"
    if value < tight:
        return "tight"
    return "over"


def host_block(workers=None):
    out = {}
    try:
        cores = os.cpu_count() or 1
        load1 = os.getloadavg()[0]
        per_core = load1 / cores
        out["cpu"] = {"load1": round(load1, 2), "cores": cores,
                      "percent": round(per_core * 100),
                      "state": _verdict(per_core, 1.2, 2.0)}
    except Exception:
        pass
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                mem[k] = int(v.split()[0])
        total = mem.get("MemTotal", 1)
        avail = mem.get("MemAvailable", 0)
        used_share = 1 - avail / total
        out["memory"] = {"total_gb": round(total / 1048576, 1),
                         "available_gb": round(avail / 1048576, 1),
                         "percent": round(used_share * 100),
                         "state": _verdict(used_share, 0.70, 0.85)}
    except Exception:
        pass
    try:
        st = os.statvfs(HOME)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used_share = 1 - free / total if total else 0
        out["disk"] = {"total_gb": round(total / 1073741824, 1),
                       "free_gb": round(free / 1073741824, 1),
                       "percent": round(used_share * 100),
                       "state": _verdict(used_share, 0.80, 0.90)}
    except Exception:
        pass
    try:
        seq = (workers or {}).values() if isinstance(workers, dict) else (workers or [])
        busy = cap = 0
        for w in seq:
            if isinstance(w, dict) and w.get("online"):
                busy += int(w.get("active_count") or 0)
                cap += int(w.get("capacity") or 0)
        share = busy / cap if cap else 0
        out["slots"] = {"busy": busy, "capacity": cap,
                        "percent": round(share * 100),
                        "state": _verdict(share, 0.7, 0.95)}
    except Exception:
        pass
    worst = "ok"
    for k in ("cpu", "memory", "disk"):
        st = (out.get(k) or {}).get("state")
        if st == "over":
            worst = "over"
        elif st == "tight" and worst == "ok":
            worst = "tight"
    out["state"] = worst
    return out


def host_overloaded(conf, workers=None):
    """Перегружен ли сервер настолько, что новую работу брать не стоит."""
    if not conf.get("respect_host_load", True):
        return False
    return host_block(workers).get("state") == "over"


def stage_from_title(title):
    match = STAGE_TITLE_RE.match(str(title or ""))
    return match.group(1).strip() if match else ""


def host_load_admits(tasks, stage, load, respect_host_load=True):
    """Decide whether a pipeline stage may start under the current host load."""
    if not respect_host_load or not load or load.get("state") != "over":
        return True
    if any((load.get(resource) or {}).get("state") == "over"
           for resource in ("memory", "disk")):
        return False
    # Pipeline continuations share one CPU reservation. Counting task rows
    # would briefly consume two slots during a handoff, while using a title
    # would merge two independent, equally named works.
    active = len({task_work_id(task) for task in (tasks or [])
                  if task.get("state") in HOST_LOAD_ACTIVE_STATES})
    if active < HOST_LOAD_MINIMUM_ACTIVE:
        return True
    return stage in HOST_LOAD_LIGHT_STAGES


MERGES_PATH = f"{HOME}/pilot/merges.jsonl"


def merge_recorded(task_id):
    """True when this Verify task has already completed its merge.

    ``state[\"processed\"]`` is deliberately only a short-lived cursor: a
    restart between the merge and saving that cursor must not turn one Verify
    PASS into a second merge or a second entry on the dashboard.
    """
    try:
        with open(MERGES_PATH, encoding="utf-8") as merges:
            for line in merges:
                try:
                    if json.loads(line).get("task_id") == task_id:
                        return True
                except (TypeError, ValueError):
                    continue
    except OSError:
        pass
    return False


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def pipeline_health(tasks):
    """Числа вместо ощущений: влито сегодня/вчера, кругов разработки на
    влитую работу, Ревью с первого раза, минуты от старта до вливания."""
    out = {"merged_today": 0, "merged_yesterday": 0}
    try:
        lines = io.open(MERGES_PATH, encoding="utf-8").readlines()[-60:]
    except Exception:
        lines = []
    merges = []
    for line in lines:
        try:
            merges.append(json.loads(line))
        except Exception:
            pass
    today = time.strftime("%Y-%m-%d")
    yday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    out["merged_today"] = sum(1 for m in merges if str(m.get("at", "")).startswith(today))
    out["merged_yesterday"] = sum(1 for m in merges if str(m.get("at", "")).startswith(yday))
    rounds, first_pass, minutes = [], [], []
    seen = set()
    for m in reversed(merges):
        base = m.get("base") or ""
        if not base or base in seen:
            continue
        seen.add(base)
        if len(seen) > 8:
            break
        impl = [t for t in tasks if base in (t.get("title") or "")
                and "Implement" in (t.get("title") or "")]
        rev = [t for t in tasks if base in (t.get("title") or "")
               and "Review" in (t.get("title") or "")]
        if impl:
            rounds.append(len(impl))
        if rev:
            first_pass.append(1 if len(rev) == 1 else 0)
        starts = sorted(t.get("created_at") or "" for t in impl + rev if t.get("created_at"))
        try:
            if starts:
                t0 = receipt_epoch(starts[0])
                t1 = receipt_epoch(m.get("at"))
                if t0 is not None and t1 is not None and 0 < t1 - t0 < 86400:
                    minutes.append(int((t1 - t0) / 60))
        except Exception:
            pass
    out["rounds_median"] = _median(rounds)
    out["review_first_pass"] = (sum(first_pass), len(first_pass)) if first_pass else None
    out["minutes_median"] = _median(minutes)
    return out


def codex_snapshot_windows(codex_snapshot, windows):
    """Read the exact time windows used to create a shared usage snapshot."""
    day_start, week_start = windows
    return codex_snapshot[day_start], codex_snapshot[week_start]


def write_dashboard(conf, tasks, workers, codex_snapshot=None, codex_windows=None):
    """Снимок состояния фабрики одним файлом: интерфейсу остаётся только показать."""
    now = time.time()
    by_state = {}
    for t in tasks:
        by_state.setdefault(t.get("state"), []).append(t)

    def age_h(t):
        try:
            return (now - time.mktime(time.strptime(t["created_at"][:19], "%Y-%m-%dT%H:%M:%S"))) / 3600
        except Exception:
            return 1e9

    spend = {"day_usd": 0.0, "day_tokens": 0, "week_usd": 0.0, "week_tokens": 0,
             "wasted_usd": 0.0, "worst": None, "day_cost_defined": True,
             "week_cost_defined": True, "day_base_estimate": False,
             "week_base_estimate": False, "day_unknown_models": [],
             "week_unknown_models": []}
    for t in tasks[:60]:
        h = age_h(t)
        if h > 24 * 7:
            continue
        try:
            detail = api(f"/tasks/{t['id']}")
        except Exception:
            continue
        atts = [a["id"] for a in (detail.get("attempts") or []) if a.get("id")]
        if not atts:
            continue
        usd = task_cost_usd(atts)
        if usd <= 0:
            continue
        spend["week_usd"] += usd
        if h <= 24:
            spend["day_usd"] += usd
            if t.get("state") in ("failed", "cancelled"):
                spend["wasted_usd"] += usd
            if not spend["worst"] or usd > spend["worst"]["usd"]:
                spend["worst"] = {"usd": round(usd, 2), "title": (t.get("title") or "")[:70],
                                  "id": t["id"]}

    if codex_windows is None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        day_start = calendar.timegm(time.strptime(today, "%Y-%m-%d"))
        week_start = time.time() - 7 * 86400
        codex_windows = (day_start, week_start)
    else:
        day_start, week_start = codex_windows
    codex_snapshot = codex_snapshot or codex_usage_snapshot(day_start, week_start)
    day_codex, week_codex = codex_snapshot_windows(codex_snapshot, codex_windows)
    spend["day_usd"] += day_codex["cost_usd"]
    spend["week_usd"] += week_codex["cost_usd"]
    spend["day_tokens"] = day_codex["total_tokens"]
    spend["week_tokens"] = week_codex["total_tokens"]
    spend["day_cost_defined"] = day_codex["cost_defined"]
    spend["week_cost_defined"] = week_codex["cost_defined"]
    spend["day_base_estimate"] = day_codex["base_estimate"]
    spend["week_base_estimate"] = week_codex["base_estimate"]
    spend["day_unknown_models"] = day_codex["unknown_models"]
    spend["week_unknown_models"] = week_codex["unknown_models"]

    prov = {}
    for w in workers.values() if isinstance(workers, dict) else workers:
        if not w.get("online"):
            continue
        p = provider_of(w.get("name"))
        d = prov.setdefault(p, {"total": 0, "healthy": 0})
        d["total"] += 1
        if w.get("health") == "healthy":
            d["healthy"] += 1

    questions = [q for q in load_questions() if q.get("status") in ("open", "stuck")]

    data = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "now": {
            "running": [{"id": t["id"], "title": (t.get("title") or "")[:80]}
                        for t in by_state.get("running", [])[:5]],
            "running_count": len(by_state.get("running", [])),
            "queued_count": len(by_state.get("queued", [])),
            "questions": [{"id": q.get("id"), "title": (q.get("title") or "")[:70],
                           "question": (q.get("question") or "")[:140]} for q in questions[:5]],
            "questions_count": len(questions),
        },
        "spend": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in spend.items()},
        "brain": brain_block(conf),
        "host": host_block(workers),
        "workers": prov,
        "limits": limits_view(),
        "access": load(f"{HOME}/pilot/access.json", {}),
        "projects": dashboard_slow(conf),
        "recent_done": recent_done_block(tasks),
        "health": pipeline_health(tasks),
        "janitor": _sh("tail -1 /var/log/factory-janitor.log 2>/dev/null")[:160],
    }
    release_train = release_train_block(load(STATE_PATH, {}), tasks, now)
    if release_train is not None:
        data["release_train"] = release_train
    save(DASH_PATH, data)


def recent_done_block(tasks, n=5):
    """Recent owner work, based on pipeline facts rather than push wording.

    Only the merge journal proves successful completion.  Failed and cancelled
    stages are terminal results; successful stages without a merge are merely
    pipeline progress.  Old notification-only records remain a small fallback
    while the task history ages in.
    """
    delivered = set()
    try:
        with io.open(DELIVERY_RECEIPTS_PATH, encoding="utf-8") as stream:
            lines = stream.readlines()[-400:]
        for line in reversed(lines):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("task_id"):
                delivered.add(r["task_id"])
    except Exception:
        pass

    latest = {}
    for task in tasks:
        parsed = pipeline_title(task)
        if not parsed or task.get("state") not in ("succeeded", "failed", "cancelled"):
            continue
        if task.get("state") == "succeeded" and task.get("id") not in delivered:
            continue
        title, stage = parsed
        if not title or is_service_work(title):
            continue
        at = task.get("finished_at") or task.get("updated_at") or task.get("created_at") or ""
        old = latest.get(title)
        if old is None or at >= old[0]:
            latest[title] = (at, task, stage)

    out = []
    for title, (at, task, stage) in sorted(latest.items(), key=lambda item: item[1][0], reverse=True):
        state = task.get("state")
        if task.get("id") in delivered:
            status, detail = "delivered", "Выпуск принят и проверен."
        elif state == "succeeded":
            status, detail = "passed", "Проверка прошла; слияние не подтверждено."
        else:
            status, detail = "failed", f"Этап «{stage}» не прошёл; в main не влито."
        try:
            attempts = api(f"/tasks/{task['id']}").get("attempts") or []
            proof = proof_of((attempts[-1].get("result") if attempts else "") or "")
            if proof:
                detail += " Проверено: " + proof
        except Exception:
            pass
        out.append({"title": title[:120], "detail": detail[:180], "at": at,
                    "status": status})
        if len(out) >= n:
            return out

    if out:
        return out

    # Before structured task history exists, show old real notifications but
    # never revive the service noise that prompted this view's redesign.
    try:
        with io.open(NOTIFY_LOG_PATH, encoding="utf-8") as stream:
            lines = stream.readlines()[-400:]
        for line in reversed(lines):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("title") != "Задача выполнена":
                continue
            body = (r.get("message") or "").split(chr(10))
            title = body[0].strip()
            if not title or is_service_work(title) or title in latest:
                continue
            out.append({"title": title[:120],
                        "detail": " ".join(x for x in body[1:] if x)[:180],
                        "at": r.get("at") or "", "status": "legacy"})
            if len(out) >= n:
                break
    except Exception:
        pass
    return out


def limits_view():
    """Экран получает правду: блок гаснет по сроку сам, а рядом — настоящий
    процент подписки из provider_limits.json, а не догадка по словам."""
    limits = load_limits()
    real = load(PROVIDER_LIMITS_PATH, {}) or {}
    out = {}
    for prov, rec in limits.items():
        rec = dict(rec or {})
        if rec.get("state") in ("exhausted", "throttled") and not limit_active(prov, limits):
            clear_limit(prov)
            rec = {"state": "ok", "manual_off": bool(rec.get("manual_off"))}
        r = real.get(prov) or {}
        if isinstance(r.get("used_percent"), (int, float)):
            rec["used_percent"] = r["used_percent"]
        else:
            pc = r.get("percents") or {}
            wk = pc.get("seven_day.utilization")
            if isinstance(wk, (int, float)):
                rec["used_percent"] = wk
        out[prov] = rec
    return out


def is_stopped(conf, base):
    """Работа, которую владелец закрыл насовсем. Пилот её не двигает и не
    перезапускает, что бы ни отвечал оркестратор."""
    b = (base or "").strip().lower()
    for s in conf.get("stopped_pipelines") or []:
        if s.strip().lower() in b:
            return True
    return False


def squeeze(text, limit=12000):
    """Обрезать длинный отчёт, оставив начало и конец. Всё, что мы кладём в
    задание, потом перечитывается моделью НА КАЖДОМ ХОДУ — поэтому хвост чужого
    вывода в 40 тысяч символов стоит дороже, чем вся полезная работа."""
    text = text or ""
    if len(text) <= limit:
        return text
    head = limit // 4
    tail = limit - head
    return (text[:head] + f"\n\n[... вырезано {len(text) - limit} символов середины: "
            "если нужны подробности — открой задачу или ветку ...]\n\n" + text[-tail:])


def worker_price_rank(name):
    n = (name or "").lower()
    rank = next((r for key, r in PRICE_RANK if key in n), 2)
    return (rank, "think" in n, n)      # без think дешевле: меньше ходов размышления


def worker_capability_rank(name):
    """Comparable capability for the named Codex/Claude worker.

    Model family is the primary step; reasoning effort is the step inside a
    family. The rank is deliberately used only to prevent a claimed escalation
    from selecting the same or a weaker worker.
    """
    n = (name or "").lower()
    family = next((rank for key, rank in (
        ("haiku", 0), ("luna", 0), ("sonnet", 1), ("terra", 1),
        ("sol", 2), ("opus", 3), ("fable", 3),
    ) if key in n), 1)
    effort = next((rank for suffix, rank in (
        ("-low", 0), ("-medium", 1), ("-high", 2), ("-max", 3),
        ("-think", 2),
    ) if n.endswith(suffix)), 1)
    return family * 10 + effort


# ----------------------------------------------- Очередь у больного --------


def _age_min(stamp):
    try:
        t = time.strptime((stamp or "")[:19], "%Y-%m-%dT%H:%M:%S")
        return (time.time() - calendar.timegm(t)) / 60.0
    except Exception:
        return 0.0


def rescue_queued(conf, tasks, workflows, workers):
    """Переложить задачи, застрявшие в очереди у заболевшего исполнителя.

    Осторожно: трогаем только `queued` (ничего не начато, терять нечего),
    только когда исполнитель действительно нездоров, и только после паузы —
    здоровая очередь это нормально и вмешиваться в неё не надо."""
    wait = conf.get("queue_rescue_min", 8)
    pool = list(workers.values()) if isinstance(workers, dict) else list(workers or [])
    by_id = {w.get("id"): w for w in pool if isinstance(w, dict)}
    for t in tasks or []:
        if t.get("state") != "queued" or _age_min(t.get("created_at")) < wait:
            continue
        sick = by_id.get(t.get("worker_id"))
        repository_id = t.get("repository_id")
        retention_full = worker_retention_full(sick, repository_id)
        if (sick and sick.get("online") and sick.get("health") == "healthy"
                and not retention_full):
            continue                      # просто ждёт очереди — это не беда
        try:
            detail = api(f"/tasks/{t['id']}")
            stage = (detail.get("workflow") or {}).get("title") or ""
            nw = workflows.get(stage)
            if not nw or not nw.get("enabled"):
                continue
            if not host_load_admits(
                    tasks, stage, conf.get("_host_load_snapshot"),
                    conf.get("respect_host_load", True)):
                continue
            cx = complexity_of(conf, stage, (sick or {}).get("name", "")) or "medium"
            # A worker at the retained-worktree safety limit still reports
            # healthy and online, but the control plane will reject every
            # claim for this repository. Hide all such routes from selection
            # so queue rescue cannot select the same blocked worker again.
            routing_workers = {}
            if isinstance(workers, dict):
                for worker_name, worker in workers.items():
                    candidate = dict(worker)
                    if worker_retention_full(candidate, repository_id):
                        candidate["health"] = "retention_full"
                    routing_workers[worker_name] = candidate
            name = stage_worker(
                conf, stage, cx, routing_workers or workers,
                repository_id=repository_id)
            fresh = workers.get(name) if isinstance(workers, dict) else None
            if not fresh or fresh.get("id") == t.get("worker_id"):
                continue
            api(f"/tasks/{t['id']}/cancel", {})
            body = {
                "request_key": str(uuid.uuid4()),
                "title": t.get("title", "")[:200],
                "context": detail.get("context", "")[:20000],
                "worker_id": fresh["id"],
                "repository_id": detail["task"].get("repository_id") or "",
                "timeout_seconds": conf.get("timeout_seconds", 7200),
                "workflow_revision_id": nw["revision_id"],
            }
            created = create_child_task(body, t, conf,
                                        "execution_retry")
            log(f"QUEUE RESCUE task={t['id'][:8]} {stage} "
                f"{(sick or {}).get('name', '?')} "
                f"({'нет места для сохранённых работ' if retention_full else 'нездоров'}) -> {name} "
                f"new={created.get('task', {}).get('id', '?')[:8]}")
        except Exception as e:
            log("queue_rescue_error", repr(e))


def worker_retention_full(worker, repository_id=None):
    """Whether retained worktrees make a worker unable to claim more work.

    The Go control plane deliberately stops claims at ten retained worktrees
    per repository. Heartbeats remain healthy in that state, so the pilot must
    include repository headroom in its own routing health check.
    """
    if not isinstance(worker, dict):
        return False
    repositories = worker.get("repositories") or []
    if repository_id:
        repositories = [repository for repository in repositories
                        if repository.get("id") == repository_id]
    for repository in repositories:
        try:
            if int(repository.get("retained_count") or 0) >= MAX_RETAINED_PER_REPOSITORY:
                return True
        except (TypeError, ValueError):
            continue
    return False


def stage_worker(conf, stage_name, complexity, workers=None, exact_tier=False,
                 repository_id=None):
    """Pick the worker for a stage. Prefer the tier the orchestrator asked for,
    but never hand work to an unhealthy worker: fall back to the other tiers of
    the SAME stage, then to any healthy worker configured anywhere in the
    pipeline. Never to an arbitrary unknown worker."""
    limits = load_limits()

    def healthy(name):
        if not name:
            return False
        if limit_active(provider_of(name), limits):
            return False              # подписка исчерпана — туда не ходим
        if not workers:
            return True
        w = workers.get(name)
        return bool(w and w.get("online") and w.get("health") == "healthy"
                    and not worker_retention_full(w))

    def available(name):
        """Prefer a worker with a free execution slot instead of queueing on a busy one."""
        if not workers:
            return True
        w = workers.get(name) or {}
        capacity = int(w.get("capacity") or 1)
        active = int(w.get("active_count") or 0)
        return active < capacity

    def repository_ready(name):
        if not repository_id or not workers:
            return True
        worker = workers.get(name) or {}
        return any(repository.get("id") == repository_id
                   for repository in (worker.get("repositories") or []))

    tiers, ordered = None, []
    for s in conf["stages"]:
        if s["workflow"] == stage_name:
            tiers = s.get("workers")
            if isinstance(tiers, dict):
                ordered = [tiers.get(complexity), tiers.get("medium"),
                           tiers.get("high"), tiers.get("low")]
            else:
                ordered = [s.get("worker")]
            break
    if exact_tier and isinstance(tiers, dict):
        exact = tiers.get(complexity)
        if healthy(exact) and repository_ready(exact):
            # An escalation must really use the configured higher tier. Queue
            # there when it is busy instead of silently falling back downward.
            return exact
    # Prefer a worker that already advertises this repository. This preserves
    # the requested stage/tier order while avoiding a known-bad pinned route.
    # Dynamic acquisition remains the fallback when no configured worker has
    # the repository yet.
    if repository_id:
        for name in ordered:
            if (name and healthy(name) and available(name)
                    and repository_ready(name)):
                return name
        pool = []
        for s in conf["stages"]:
            t = s.get("workers")
            pool += (list(t.values()) if isinstance(t, dict) else [s.get("worker")])
        for name in sorted({n for n in pool if n}, key=worker_price_rank):
            if healthy(name) and available(name) and repository_ready(name):
                log(f"stage_worker: {stage_name}/{complexity} -> repository-ready {name}")
                return name
        for name in ordered:
            if name and healthy(name) and repository_ready(name):
                return name
        for name in sorted({n for n in pool if n}, key=worker_price_rank):
            if healthy(name) and repository_ready(name):
                return name

    for name in ordered:
        if name and healthy(name) and available(name):
            return name
    # Последний резерв — только внутри нашей же конфигурации и от ДЕШЁВЫХ к дорогим,
    # иначе подмена больного воркера сама по себе разоряет (fable/opus в 5 раз дороже).
    pool = []
    for s in conf["stages"]:
        t = s.get("workers")
        pool += (list(t.values()) if isinstance(t, dict) else [s.get("worker")])
    for name in sorted({n for n in pool if n}, key=worker_price_rank):
        if healthy(name) and available(name):
            log(f"stage_worker: {stage_name}/{complexity} -> подменён на здорового {name}")
            return name
    # All configured workers are full. Keep the preferred healthy route queued
    # instead of treating temporary saturation as a provider failure.
    for name in ordered:
        if name and healthy(name):
            return name
    for name in sorted({n for n in pool if n}, key=worker_price_rank):
        if healthy(name):
            return name
    return next((n for n in ordered if n), None)


def handle_epics(conf, state, tasks, workflows, workers, repo_identity_by_id):
    """Planner pass: decompose finished Epic Planning tasks; fan out on approval.
    Fully guarded - never raises into the main pipeline."""
    state.setdefault("epics_processed", [])
    state.setdefault("epic_starts_processed", [])

    # UI "Start" button: epics flipped to start-requested by the control plane
    for e in load_epics():
        if e.get("status") == "start-requested":
            e["status"] = "planned"  # start_epic flips to running on success
            ok, msg = start_epic(conf, e, workflows, workers)
            log(f"EPIC START (ui) epic='{e.get('name')}' ok={ok} :: {msg}")
            notify(conf, "Эпик запущен" if ok else "Эпик НЕ запустился",
                   f"{e.get('name')}: {msg}", tags="rocket" if ok else "warning", click=f"{UI_BASE}/epics")
            if not ok:
                # leave it planned so the button can be pressed again
                save(f"{EPIC_DIR}/{e['id']}.json", e)

    def make_epic_from(tid, title, detail):
        attempts = detail.get("attempts") or []
        result = next((a.get("result") for a in reversed(attempts) if a.get("result")), "") or ""
        name, subs = parse_subtasks(result)
        if not subs:
            log(f"epic-plan task={tid}: no subtasks parsed -> skipped")
            return
        goal = re.sub(r"^\[epic-plan\]\s*", "", title).strip() or (name or "")
        repo_id = (detail.get("task", {}).get("repository_id")
                   or detail.get("repository", {}).get("id", ""))
        epic = write_epic(tid, name, goal, repo_id, subs)
        log(f"EPIC PLANNED id={tid} name='{epic['name']}' subtasks={len(subs)} "
            f"-> awaiting [epic-start]")
        notify(conf, "План эпика готов — жду подтверждения",
               f"{epic['name']}: {len(subs)} подзадач", tags="clipboard", click=f"{UI_BASE}/epics")

    for t in tasks:
        tid, title, tstate = t["id"], t.get("title", ""), t.get("state")

        # (a) an [epic-start] approval task -> fan out the matching planned epic.
        #     Checked by title first so it can never be mistaken for a plan.
        if title.startswith(EPIC_START_PREFIX):
            if tid in state["epic_starts_processed"]:
                continue
            state["epic_starts_processed"].append(tid)
            substr = re.sub(r"^\[epic-start\]\s*", "", title).strip().lower()
            planned = [e for e in load_epics() if e.get("status") == "planned"]
            if not planned:
                log(f"epic-start task={tid}: no planned epics to start")
                continue
            match = None
            if substr:
                match = next((e for e in reversed(planned)
                              if substr in (e.get("name", "") + " " + e.get("goal", "")).lower()),
                             None)
            if not match:
                match = planned[-1]  # most recent planned epic
            ok, msg = start_epic(conf, match, workflows, workers)
            log(f"EPIC START task={tid} epic='{match['name']}' ok={ok} :: {msg}")
            notify(conf, "Эпик запущен" if ok else "Эпик НЕ запустился",
                   f"{match['name']}: {msg}", tags="rocket" if ok else "warning", click=f"{UI_BASE}/epics")
            continue

        # ignore pipeline stage tasks here; the main loop owns them
        if title.startswith(PREFIX):
            continue

        # (b) a finished planning task -> write a 'planned' epic.
        #     Explicit [epic-plan] title, or any task run through the
        #     'Epic Planning' workflow (the UI path, no prefix).
        if tstate == "succeeded" and tid not in state["epics_processed"]:
            if title.startswith(EPIC_PLAN_PREFIX):
                state["epics_processed"].append(tid)
                make_epic_from(tid, title, api(f"/tasks/{tid}"))
            else:
                # fetch once to check the workflow; mark checked either way
                state["epics_processed"].append(tid)
                detail = api(f"/tasks/{tid}")
                if (detail.get("workflow") or {}).get("title") == EPIC_PLAN_WF:
                    make_epic_from(tid, title, detail)


DELIVERY_STATE_KEY = "delivery_state_v2"
DELIVERY_RECEIPTS_PATH = f"{HOME}/pilot/delivery-receipts.jsonl"
DELIVERY_OUTBOX_PATH = f"{HOME}/pilot/delivery-outbox.jsonl"
DELIVERY_BROKER_SOCKET = "/run/factory/project-release-broker.sock"
DELIVERY_RETRY_DELAY = 60
DELIVERY_PHASES = frozenset(("reserved", "launching", "running", "completed", "failed"))
DELIVERY_TARGET_TITLES = {"factory": "Factory", "tarser-staging": "Tarser staging"}


def release_train_block(state, tasks, now):
    """Build the public, read-only release view from durable V2 state."""
    durable = state.get(DELIVERY_STATE_KEY) if isinstance(state, dict) else None
    targets = durable.get("targets") if isinstance(durable, dict) and durable.get("version") == 2 else None
    if not isinstance(targets, dict) or not targets:
        return None
    task_titles = {}
    for task in tasks if isinstance(tasks, list) else []:
        task_id = task.get("id") if isinstance(task, dict) else None
        if not task_id:
            continue
        parsed = pipeline_title(task)
        task_titles[task_id] = (parsed[0] if parsed else str(task.get("title") or "").strip())

    def passengers(waits):
        if not isinstance(waits, dict):
            return []
        return [{"title": task_titles.get(task_id) or "Работа из выпуска (название недоступно)"}
                for task_id in waits]

    def public_time(value):
        return value if isinstance(value, str) and receipt_epoch(value) is not None else None

    current_time = now
    trains = []
    for target_key, target in targets.items():
        if target_key not in DELIVERY_TARGET_TITLES or not isinstance(target, dict):
            return None
        generations = target.get("generations")
        if not isinstance(generations, dict):
            return None
        current_id = target.get("current_generation")
        current = generations.get(current_id) if current_id else None
        if current_id and (not isinstance(current, dict) or current.get("phase") not in DELIVERY_PHASES):
            return None
        item = {"target": DELIVERY_TARGET_TITLES[target_key], "state": "idle",
                "passengers": [], "next": {"requested": False, "passengers": []}}
        if current:
            phase = current["phase"]
            item["state"] = {"reserved": "waiting", "launching": "running", "running": "running",
                             "completed": "succeeded", "failed": "failed"}[phase]
            if isinstance(current.get("sequence"), int):
                item["generation"] = current["sequence"]
            item["gate"] = {"reserved": "ожидает broker", "launching": "запускается",
                            "running": "выполняется", "completed": "принят",
                            "failed": "не прошёл"}[phase]
            item["passengers"] = passengers(current.get("waits"))
            started = public_time(current.get("started_at") or current.get("reserved_at"))
            if started and phase in ("reserved", "launching", "running"):
                item["started_at"] = started
                item["elapsed_seconds"] = max(0, int(current_time - receipt_epoch(started)))
            requested = bool(target.get("next_requested")) and phase != "reserved"
            item["next"] = {"requested": requested,
                            "passengers": passengers(target.get("next_waits")) if requested else []}
            retry_at = current.get("next_retry_at")
            if phase == "reserved" and isinstance(retry_at, (int, float)):
                item["next"]["retry_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(retry_at))

            terminal = [generation for generation in generations.values()
                        if isinstance(generation, dict)
                        and generation is not current
                        and generation.get("phase") in ("completed", "failed")]
            if terminal:
                previous = max(terminal, key=lambda generation: generation.get("sequence", -1))
                item["previous"] = {
                    "state": "succeeded" if previous["phase"] == "completed" else "failed",
                    "passengers": passengers(previous.get("waits")),
                }
                finished = public_time(previous.get("finished_at"))
                if finished:
                    item["previous"]["finished_at"] = finished
        trains.append(item)
    return {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)),
            "trains": sorted(trains, key=lambda train: train["target"])}


def retry_pending_factory_deploy(_conf, _state):
    """Compatibility seam for older callers; V2 polling is the only runner."""
    return None


def _delivery_state(state):
    """Return the only active delivery model and audit old, unsafe state once."""
    current = state.get(DELIVERY_STATE_KEY)
    if not isinstance(current, dict) or current.get("version") != 2:
        current = {"version": 2, "targets": {}, "outbox": {}, "audit": {}}
        legacy = state.pop("post_merge_deploys", None)
        if legacy is not None:
            current["audit"]["legacy_post_merge_deploys"] = legacy
        state.pop("pending_factory_deploy", None)
        state[DELIVERY_STATE_KEY] = current
    return current


def _delivery_target(repo_identity):
    identity = (repo_identity or "").lower().removesuffix(".git")
    if identity.endswith("timafen/factory"):
        return "factory", "fx-factory-release"
    if identity.endswith("timafen/tarser-operations"):
        return "tarser-staging", "tarser-staging-deploy-release"
    if identity:
        # An ordinary repository has no Factory-owned release adapter.  Its
        # durable delivery boundary is the accepted merge itself, but it must
        # still enter the same state machine so owner completion is replayable.
        return "external-" + hashlib.sha256(identity.encode()).hexdigest()[:16], "external-merge"
    return "", ""


def _delivery_generation(state, repo_identity, commit_sha, wait, now=None):
    durable = _delivery_state(state)
    target_key, adapter = _delivery_target(repo_identity)
    if not target_key or not re.fullmatch(r"[0-9a-f]{40,64}", commit_sha or ""):
        return None
    target = durable["targets"].setdefault(target_key, {"id": target_key, "last_generation": 0,
        "current_generation": None, "next_requested": False, "generations": {}})
    current = target.get("current_generation")
    if current:
        generation = target["generations"].get(current)
        if generation and generation["phase"] == "reserved":
            # Reserved N has not been accepted by the broker.  Its source
            # snapshot is therefore intentionally mutable: a merge arriving
            # during lock retry is released once, from the newest main head.
            generation["adapter"] = adapter
            generation["commit_sha"] = commit_sha
            generation["waits"][wait["task_id"]] = wait
            generation.setdefault("merge_receipts", []).append(wait["merge_receipt"])
            return generation
        if generation and generation["phase"] in ("launching", "running"):
            target["next_requested"] = True
            target.setdefault("next_waits", {})[wait["task_id"]] = wait
            target["next_input"] = {"adapter": adapter, "commit_sha": commit_sha}
            return generation
    target["last_generation"] += 1
    sequence = target["last_generation"]
    gid = f"{target_key}-{sequence}-{uuid.uuid4().hex}"
    generation = {"id": gid, "sequence": sequence, "phase": "reserved",
        "adapter": adapter, "commit_sha": commit_sha, "waits": {wait["task_id"]: wait},
        "merge_receipts": [wait["merge_receipt"]],
        "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
            time.time() if now is None else now))}
    if adapter == "external-merge":
        # The merge receipt is the terminal delivery proof for a repository
        # whose deployment is not operated by Factory.
        generation["phase"] = "completed"
    target["current_generation"] = gid
    target["generations"][gid] = generation
    return generation


def broker_operation(socket_path, method, operation_id, payload=None):
    """Small Unix-socket client; unknown I/O is deliberately not success."""
    endpoint = "http://release-broker/v1/operations"
    if method == "GET":
        endpoint += "/" + operation_id
    args = ["curl", "--silent", "--show-error", "--unix-socket", socket_path,
            "--max-time", "10", "-X", method, endpoint]
    if payload is not None:
        args[args.index("-X"):args.index("-X")] = ["-H", "Content-Type: application/json", "--data", json.dumps(payload)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if result.returncode:
            return None
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _delivery_record(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + chr(10))


def _delivery_record_once(path, record):
    """Append immutable journal records at most once across process restarts."""
    record_id = record.get("id")
    if record_id and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as stream:
                for line in stream:
                    if line.strip() and json.loads(line).get("id") == record_id:
                        return False
        except (OSError, ValueError):
            pass
    _delivery_record(path, record)
    return True


def _complete_generation(conf, state, generation):
    durable = _delivery_state(state)
    completed = generation.setdefault("completed_waits", {})
    for task_id, wait in generation["waits"].items():
        if task_id in completed:
            continue
        receipt = dict(wait.get("merge_receipt") or {})
        receipt.update({"id": generation["id"] + ":" + task_id,
                        "generation_id": generation["id"], "task_id": task_id,
                        "base": wait.get("base", ""),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        _delivery_record_once(DELIVERY_RECEIPTS_PATH, receipt)
        completed[task_id] = receipt["id"]
        mark_final(task_id, "Verify", True)
    durable["outbox"].setdefault(generation["id"] + ":done", {"id": generation["id"] + ":done",
        "generation_id": generation["id"], "status": "pending", "waits": list(generation["waits"].values())})


def _fail_generation(state, target, generation, category, now):
    """Persist one owner-safe event for a terminal train failure."""
    generation["phase"] = "failed"
    generation["failure_category"] = category
    generation["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    event_id = generation["id"] + ":failed"
    titles = [no_bare_hashes(str(wait.get("base") or "Работа из выпуска"))
              for wait in generation.get("waits", {}).values() if isinstance(wait, dict)]
    _delivery_state(state)["outbox"].setdefault(event_id, {
        "id": event_id, "kind": "failed", "status": "pending",
        "target": DELIVERY_TARGET_TITLES.get(target.get("id"), "Проект"),
        "titles": titles, "category": category, "at": generation["finished_at"],
    })


def dispatch_delivery_outbox(conf, state):
    durable = _delivery_state(state)
    for item in durable["outbox"].values():
        if item.get("status") == "sent":
            continue
        # Journal first: local owner history is deduplicated even if the
        # process dies while the best-effort push transport is in flight.
        record = {"id": item["id"], "at": item.get("at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if item.get("kind") == "failed":
            record.update({key: item.get(key) for key in ("target", "titles", "category")})
        _delivery_record_once(DELIVERY_OUTBOX_PATH, record)
        item["status"] = "journaled"
        save(STATE_PATH, state)
        if item.get("kind") == "failed":
            names = " · ".join(item.get("titles") or []) or "названия работ недоступны"
            notify(conf, "Выпуск не прошёл", f"{item.get('target', 'Проект')}: {names}",
                   tags="warning", click=f"{UI_BASE}/", journal_id=item["id"])
        else:
            wait = item["waits"][0] if item["waits"] else {}
            notify(conf, "Задача выполнена", wait.get("base", "Выпуск принят"), tags="white_check_mark",
                   click=wait.get("link") or f"{UI_BASE}/work", journal_id=item["id"])
        item["status"] = "sent"
        save(STATE_PATH, state)


def poll_delivery_state(conf, state, now=None):
    current_time = time.time() if now is None else now
    durable = _delivery_state(state)
    for target in durable["targets"].values():
        for generation in list(target["generations"].values()):
            if generation.get("phase") not in DELIVERY_PHASES:
                generation["phase"] = "failed"
            if generation["phase"] == "completed":
                # A process can die after the broker's terminal status was
                # durably observed but before receipts/outbox were written.
                # Completed is authoritative, so recovery must finish this
                # local transaction without a new broker call.
                _complete_generation(conf, state, generation)
                response = None
            elif generation["phase"] == "reserved" and current_time >= generation.get("next_retry_at", 0):
                response = broker_operation(conf.get("release_broker_socket", DELIVERY_BROKER_SOCKET), "POST", generation["id"],
                    {"operation_id": generation["id"], "adapter": generation["adapter"], "commit_sha": generation["commit_sha"]})
            elif generation["phase"] in ("launching", "running"):
                response = broker_operation(conf.get("release_broker_socket", DELIVERY_BROKER_SOCKET), "GET", generation["id"])
            else:
                response = None
            status = (response or {}).get("status")
            if status in ("launching", "running"):
                generation["phase"] = status
                generation.setdefault("started_at", time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)))
                # The broker has durably accepted this boundary; persist the
                # matching Pilot phase before a process can disappear.
                save(STATE_PATH, state)
            elif status == "succeeded":
                # Terminal broker proof must survive before receipts/outbox.
                # A restart from this exact point only finishes the local
                # transaction and never POSTs a second physical release.
                generation["phase"] = "completed"
                generation["finished_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time))
                save(STATE_PATH, state)
                _complete_generation(conf, state, generation)
            elif status == "locked":
                generation["phase"] = "reserved"
                generation["next_retry_at"] = current_time + DELIVERY_RETRY_DELAY
                save(STATE_PATH, state)
            elif status in ("failed", "rollback_failed", "release_failed_rolled_back"):
                _fail_generation(state, target, generation, status, current_time)
                save(STATE_PATH, state)
            elif response is None and generation["phase"] in ("launching", "running"):
                _fail_generation(state, target, generation, "broker_status_unknown", current_time)
                save(STATE_PATH, state)
        save(STATE_PATH, state)
        current = target.get("current_generation")
        active = target["generations"].get(current) if current else None
        if active and active["phase"] in ("completed", "failed") and target.get("next_requested"):
            pending = target.pop("next_waits", {})
            source = target.pop("next_input", {})
            target["next_requested"] = False
            target["last_generation"] += 1
            sequence = target["last_generation"]
            gid = f"{target.get('id', active['id'].rsplit('-', 2)[0])}-{sequence}-{uuid.uuid4().hex}"
            target["generations"][gid] = {"id": gid, "sequence": sequence, "phase": "reserved",
                "adapter": source.get("adapter", active["adapter"]),
                "commit_sha": source.get("commit_sha", active["commit_sha"]), "waits": pending,
                "merge_receipts": [w["merge_receipt"] for w in pending.values()],
                "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time))}
            target["current_generation"] = gid
        # This also makes a just-created N+1 survive before its first POST.
        save(STATE_PATH, state)
    dispatch_delivery_outbox(conf, state)


def deploy_after_merge(conf, repo_identity, state=None, commit_sha="", wait=None, now=None):
    """Create/join a generation; it never launches raw release commands."""
    state = state if state is not None else {}
    wait = wait or {"task_id": "manual-" + uuid.uuid4().hex, "base": "", "merge_receipt": {}}
    generation = _delivery_generation(state, repo_identity, commit_sha, wait, now)
    if generation:
        save(STATE_PATH, state)
        if generation["phase"] == "completed":
            _complete_generation(conf, state, generation)
            dispatch_delivery_outbox(conf, state)
    return generation


def _intent_has_wait(state, task_id):
    for target in _delivery_state(state)["targets"].values():
        for generation in target["generations"].values():
            if task_id in generation.get("waits", {}):
                return True
    return False


def _merge_journaled(task_id):
    try:
        with open(MERGES_PATH, encoding="utf-8") as stream:
            return any(json.loads(line).get("task_id") == task_id
                       for line in stream if line.strip())
    except (OSError, ValueError):
        return False


def _verified_merge_result(repo, branch, expected_head):
    """Whether GitHub records this exact verified head as merged."""
    owner = repo.split("/", 1)[0]
    head = urllib.parse.quote(f"{owner}:{branch}", safe="")
    pulls = gh_json(["api", f"repos/{repo}/pulls?state=all&head={head}&per_page=100"])
    if not isinstance(pulls, list):
        return False
    return any(
        pull.get("merged_at") and (pull.get("head") or {}).get("sha") == expected_head
        for pull in (pulls or [])
    )


def _merged_commit_sha(repo, branch, expected_head=""):
    """Настоящий коммит в main после squash-merge этой ветки.

    GitHub при squash пересобирает изменение в НОВЫЙ коммит; head ветки до
    вливания в main не попадает и после удаления ветки может вовсе исчезнуть.
    Поезд обязан получать именно merge_commit_sha — иначе выпуск честно
    отвечает «нет такой точки сборки» (так падали поколения 7–9)."""
    owner = repo.split("/", 1)[0]
    head = urllib.parse.quote(f"{owner}:{branch}", safe="")
    pulls = gh_json(["api", f"repos/{repo}/pulls?state=all&head={head}&per_page=100"])
    if not isinstance(pulls, list):
        return ""
    for pull in pulls:
        if not pull.get("merged_at"):
            continue
        if expected_head and (pull.get("head") or {}).get("sha") != expected_head:
            continue
        sha = pull.get("merge_commit_sha") or ""
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    return ""


def _merge_rounds(tasks, reference):
    """Return completed rounds for this work generation, including replacements.

    Archived attempts no longer spend the retry limit in ``stage_attempts``,
    but they remain real rounds for the delivery journal.  Durable ``work_id``
    provenance keeps completed generations with the same title out.
    """
    counts = []
    for stage in ("Implement + Test", "Review", "Verify"):
        count = 0
        for task in tasks:
            match = STAGE_TITLE_RE.match(task.get("title", ""))
            if (match and match.group(1).strip() == stage
                    and same_task_work(task, reference)):
                count += 1
        counts.append(count)
    return max(counts, default=0)


def _supersede_conflicted_pr(intent):
    """Close only our stale PR when a separately merged PR proves the work landed.

    Every uncertain GitHub response returns False, preserving the ordinary
    correction path.  The snapshot fields are deliberately never inferred from
    a title or branch name.
    """
    work_id = intent.get("work_id", "")
    repo = intent.get("repository", "").split("github.com/")[-1]
    branch, base = intent.get("branch", ""), intent.get("base_branch", "")
    if not work_id or not repo or not branch or not base:
        return False
    try:
        owner = repo.split("/", 1)[0]
        head = urllib.parse.quote(f"{owner}:{branch}", safe="")
        current = gh_json(["api", f"repos/{repo}/pulls?state=open&head={head}&per_page=100"])
        pulls = gh_json(["api", f"repos/{repo}/pulls?state=all&per_page=100"])
    except Exception as error:
        log(f"AUTO-MERGE supersede lookup failed: {error}")
        return False
    if not isinstance(current, list) or not isinstance(pulls, list):
        return False
    matching = [pull for pull in current
                if (pull.get("state") == "open"
                    and (pull.get("head") or {}).get("ref") == branch
                    and (pull.get("base") or {}).get("ref") == base
                    and _marked_work_id(pull.get("body", "")) == work_id)]
    if len(matching) != 1:
        return False
    stale = matching[0]
    candidates = [pull for pull in pulls
                  if (pull.get("number") != stale.get("number")
                      and pull.get("merged_at")
                      and (pull.get("base") or {}).get("ref") == base
                      and _marked_work_id(pull.get("body", "")) == work_id)]
    if len(candidates) != 1 or not candidates[0].get("number"):
        return False
    replacement = candidates[0]
    ok, output = gh_close_pr(repo, stale.get("number"), replacement["number"])
    if not ok:
        log(f"AUTO-MERGE stale PR close failed: {output[:200]}")
        return False
    intent.update({"phase": "superseded", "superseded_by": replacement["number"],
                   "superseded_url": replacement.get("html_url", ""),
                   "supersede_reason": "same work already merged by another PR",
                   "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return True


def recover_merge_intents(conf, state):
    """Resume merge → receipt → delivery in that order before `processed`.

    The intent is enough to ask GitHub whether its branch is already in main;
    a crash after a successful external merge therefore cannot create a second
    merge merely because the task cursor was saved first.
    """
    for task_id, intent in list(state.setdefault("merge_intents", {}).items()):
        if _intent_has_wait(state, task_id):
            continue
        # A content conflict cannot heal by repeating the same merge request.
        # A separate correction task rebases the same branch and sends it
        # through Review and Verify again.
        if intent.get("phase") in ("conflict", "repairing", "superseding", "superseded", "stale"):
            continue
        repo, branch = intent.get("repository", ""), intent.get("branch", "")
        if not repo or not branch:
            intent["phase"] = "failed"
            continue
        merged = intent.get("phase") in ("merged", "journaled", "waiting")
        if not merged:
            api_repo = repo.split("github.com/")[-1]
            expected_head = intent.get("commit_sha", "")
            current = gh_json(["api", f"repos/{api_repo}/branches/{branch}"])
            actual_head = ((current or {}).get("commit") or {}).get("sha", "")
            exact_merge = _verified_merge_result(api_repo, branch, expected_head)
            if actual_head and actual_head != expected_head:
                intent.update({
                    "phase": "stale",
                    "merge_error": "delivery branch changed after Verify",
                })
                save(STATE_PATH, state)
                continue
            if exact_merge:
                intent.setdefault("actor", "owner")
                merged = True
            else:
                intent["actor"] = "automatic"
                intent["phase"] = "merging"
                save(STATE_PATH, state)
                merge_args = (repo, branch, intent.get("base", branch), expected_head)
                if intent.get("work_id"):
                    merge_args += (intent["work_id"],)
                ok, output = gh_merge(*merge_args)
                log(f"AUTO-MERGE recovery branch={branch} ok={ok} :: {output[:200]}")
                if not ok:
                    if MERGE_CONFLICT_RE.search(output or ""):
                        conflicts = int(intent.get("conflict_count") or 0) + 1
                        intent.update({
                            "phase": "conflict",
                            "merge_error": (output or "")[:2000],
                            "conflict_count": conflicts,
                            "conflict_at": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        })
                        if conflicts >= 2 and _supersede_conflicted_pr(intent):
                            log(f"AUTO-MERGE stale PR superseded task={task_id}")
                        save(STATE_PATH, state)
                    continue
                merged = True
            intent["phase"] = "merged"
            save(STATE_PATH, state)
        if merged:
            receipt = {"task_id": task_id, "base": intent.get("base", ""),
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "actor": intent.get("actor", "automatic"),
                       "actor_id": intent.get("actor_id"),
                       "rounds": max(1, int(intent.get("rounds") or 0))}
            # The physical journal is the boundary before a delivery wait.
            # A restart after this append recognizes it by task id and cannot
            # let an already-processed Verify task suppress its missing wait.
            if not _merge_journaled(task_id):
                _delivery_record(MERGES_PATH, receipt)
            intent["phase"] = "journaled"
            save(STATE_PATH, state)
            wait = {"task_id": task_id, "base": intent.get("base", ""),
                    "link": intent.get("link", ""), "merge_receipt": receipt}
            # Поезду — коммит, который реально лёг в main после squash,
            # а не head ветки до вливания (его после merge уже не существует).
            released_sha = (intent.get("released_sha")
                            or _merged_commit_sha(repo.split("github.com/")[-1], branch,
                                                  intent.get("commit_sha", ""))
                            or intent.get("commit_sha", ""))
            intent["released_sha"] = released_sha
            generation = deploy_after_merge(conf, repo, state, released_sha, wait)
            if generation:
                intent["phase"] = "waiting"; intent["generation_id"] = generation["id"]
                save(STATE_PATH, state)


def resume_merge_conflicts(conf, state, tasks, workflows, workers):
    """Return a conflicted release to the same pipeline exactly once.

    The correction keeps the original work id through parent provenance, uses
    the already-reviewed branch, and must pass Review and Verify again after it
    catches up with current main.
    """
    stages = [item.get("workflow") for item in conf.get("stages", [])]
    implementation = "Implement + Test"
    if implementation not in stages:
        return 0
    workflow = workflows.get(implementation) or {}
    if not workflow.get("enabled") or not workflow.get("revision_id"):
        return 0
    created_count = 0
    for task_id, intent in list(state.setdefault("merge_intents", {}).items()):
        if intent.get("phase") != "conflict":
            continue
        existing = next((task for task in tasks
                         if task.get("parent_task_id") == task_id
                         and task.get("correction_kind") == "merge_conflict_return"
                         and task.get("id")), None)
        if existing:
            intent.update({"phase": "repairing",
                           "repair_task_id": existing.get("id", "")})
            save(STATE_PATH, state)
            continue
        parent = next((task for task in tasks if task.get("id") == task_id), None)
        detail = None
        if parent is None:
            try:
                detail = api(f"/tasks/{task_id}")
                parent = dict((detail or {}).get("task") or {})
                parent.setdefault("id", task_id)
            except Exception as error:
                log(f"MERGE CONFLICT repair wait task={task_id}: {error}")
                continue
        repository_id = parent.get("repository_id") or ""
        if not repository_id and detail:
            repository_id = ((detail.get("task") or {}).get("repository_id") or "")
        branch = intent.get("branch", "")
        if not repository_id or not branch:
            log(f"MERGE CONFLICT repair wait task={task_id}: "
                "repository/branch missing")
            continue
        try:
            worker_name = stage_worker(
                conf, implementation, "high", workers,
                repository_id=repository_id)
        except Exception as error:
            log(f"MERGE CONFLICT repair wait task={task_id}: worker lookup: {error}")
            continue
        worker = workers.get(worker_name)
        if not worker:
            log(f"MERGE CONFLICT repair wait task={task_id}: worker missing")
            continue
        base = intent.get("base") or base_title(parent.get("title", ""))
        stage_number = stages.index(implementation) + 1
        context = (
            f"Pipeline: {base}\n"
            f"Branch: {branch}\n"
            f"Previous verified head: {intent.get('commit_sha', '')}\n\n"
            "GitHub found a content conflict with current main. Continue the SAME branch. "
            "Fetch origin/main, rebase or merge it into this branch, resolve only the "
            "conflicts needed for this work, run the full required test set, and push the "
            "updated branch. Do not create a replacement branch. Review and Verify will "
            "run again after this correction.\n\n"
            f"GitHub response:\n{intent.get('merge_error', '')}"
        )[:20000]
        try:
            created = create_child_task({
                "request_key": f"merge-conflict-return:{task_id}:{intent.get('commit_sha', '')}",
                "title": (f"[auto] [{stage_number}/{len(stages)} {implementation}] "
                          f"{base}")[:200],
                "context": context,
                "worker_id": worker["id"],
                "repository_id": repository_id,
                "timeout_seconds": conf.get("timeout_seconds", 7200),
                "workflow_revision_id": workflow["revision_id"],
            }, parent, conf, "merge_conflict_return")
        except Exception as error:
            log(f"MERGE CONFLICT repair deferred task={task_id}: {error}")
            continue
        repair_task_id = ((created or {}).get("task") or {}).get("id", "")
        if not repair_task_id:
            log(f"MERGE CONFLICT repair wait task={task_id}: create returned no task")
            continue
        intent.update({"phase": "repairing", "repair_task_id": repair_task_id})
        save(STATE_PATH, state)
        log(f"MERGE CONFLICT returned task={task_id} -> {repair_task_id}")
        created_count += 1
    return created_count


def cycle(conf, state):
    stages = [s["workflow"] for s in conf["stages"]]
    recovery_ids = frozenset(conf.pop("_restart_recovery_ids", ()) or ())
    if recovery_ids:
        # Keep the startup snapshot available to the recovery helpers until
        # this cycle classifies it.  The key is consumed at the end below so
        # a long-lived Pilot never replays the same startup pass.
        conf["_restart_recovery_ids"] = recovery_ids
    activity = {
        "task_created": False,
        "answer_applied": False,
        "terminal_backlog": False,
    }
    conf["_cycle_activity"] = activity
    overlap_wait_decisions = state.setdefault("overlap_wait_decisions", {})
    if not isinstance(overlap_wait_decisions, dict):
        overlap_wait_decisions = {}
        state["overlap_wait_decisions"] = overlap_wait_decisions
    terminal_retry_ids = state.setdefault("terminal_retry_ids", [])
    if not isinstance(terminal_retry_ids, list):
        terminal_retry_ids = []
        state["terminal_retry_ids"] = terminal_retry_ids
    processed_ids = set(state.get("processed") or ())
    terminal_retry_ids[:] = [
        task_id for task_id in terminal_retry_ids
        if task_id and task_id not in processed_ids
    ]

    tasks = api("/tasks?limit=100").get("tasks") or []
    # The normal cycle only needs a small current snapshot.  Restart recovery
    # is different: its durable set may include an older task past that page.
    # Read each absent ID authoritatively instead of silently losing its handoff.
    recovery_details = load_restart_recovery_tasks(conf, tasks)
    new_terminal = remember_new_terminal_tasks(conf, state, tasks)
    try:
        collect_automation_findings(state, tasks)
    except Exception as e:
        # A transient read or Plan write failure must not mark the run as
        # processed. The next cycle retries it through the durable cursor.
        log("automation_findings_error", repr(e))
    # The first API page is intentionally small and can push the linked root
    # or final stage of an older Plan card out of view.  Reuse the complete
    # history already required by the dashboard and terminal handoffs for all
    # lifecycle reconciliation in this cycle.  Otherwise old cards remain
    # labelled ``in_work`` forever and leave automatic planning with a false
    # picture of its queue.
    complete_tasks = None
    try:
        complete_tasks = all_tasks()
    except Exception as e:
        log("task_history_error", repr(e))
    lifecycle_tasks = complete_tasks if isinstance(complete_tasks, list) else tasks

    # Сначала убрать выполненное из открытого Плана. Автоподбор (когда он
    # включён) ниже по циклу уже не увидит эту карточку как planned.
    try:
        cleanup_completed_plan_cards(lifecycle_tasks, len(stages))
    except Exception as e:
        log("plan_cleanup_error", repr(e))
    try:
        reconcile_stale_plan_cards(lifecycle_tasks)
    except Exception as e:
        log("plan_reconcile_error", repr(e))
    workers = best_workers(api("/workers")["workers"])
    repo_identity_by_id = {r["id"]: r["remote_identity"]
                           for r in (api("/repositories").get("repositories") or [])}
    workflows = {}
    for w in api("/workflows").get("workflows") or []:
        rev = w.get("current_revision") or {}
        workflows[rev.get("title")] = {"workflow_id": w["id"], "revision_id": rev.get("id"),
                                       "enabled": w.get("enabled")}

    # These recoveries deliberately precede the task cursor below.  A Verify
    # task may already be in `processed` when a process stops after gh_merge.
    recover_merge_intents(conf, state)
    poll_delivery_state(conf, state)

    today = time.strftime("%Y-%m-%d", time.gmtime())
    day_start = calendar.timegm(time.strptime(today, "%Y-%m-%d"))
    week_start = time.time() - 7 * 86400
    codex_snapshot = codex_usage_snapshot(day_start, week_start)

    # Снимок для главного экрана. Никогда не должен ломать цикл.
    # The same complete snapshot feeds terminal handoffs below. Looking only
    # at /tasks?limit=100 there loses a completed stage once service traffic
    # pushes it off the first page.
    try:
        write_dashboard(conf, lifecycle_tasks, {w["id"]: w for w in api("/workers")["workers"]},
                        codex_snapshot, (day_start, week_start))
    except Exception as e:
        log("dashboard_error", repr(e))
    # Настоящие проценты подписок — в файл и в уведомления на 80/95.
    try:
        provider_limits_tick(conf)
    except Exception as e:
        log("provider_limits_error", repr(e))

    # Лимиты подписок: понять, свободны ли провайдеры, прежде чем раздавать работу.
    try:
        detect_limits(conf, tasks, {w["id"]: w for w in api("/workers")["workers"]})
    except Exception as e:
        log("limits_error", repr(e))

    # Потолок расхода на задачу — до всего остального, чтобы зациклившийся
    # агент не жёг деньги ещё цикл.
    # Кто поставил работу — записываем до всего остального, пока задача свежая.
    try:
        record_new_works(conf, tasks)
    except Exception as e:
        log("record_works_error", repr(e))

    try:
        budget_guard(conf, tasks, workers)
    except Exception as e:
        log("budget_guard_error", repr(e))

    # Дневной потолок: начатое доигрывается, новое не берётся.
    try:
        if day_budget_blocks(conf, tasks, codex_snapshot[day_start]):
            if recovery_ids:
                conf["_restart_recovery_retry"] = True
            conf.pop("_restart_recovery_ids", None)
            hint = next_poll_hint(conf, tasks, fast=new_terminal)
            conf.pop("_cycle_activity", None)
            return hint
    except Exception as e:
        log("day_cap_error", repr(e))

    # Every automatic handoff in this cycle shares one live work-slot
    # snapshot. Successful creates append to it, so a restart cannot fan an
    # old backlog out past max_parallel_works before the next API poll.
    conf["_active_work_tasks"] = tasks

    # Перегрузка больше не останавливает сторож и весь конвейер. Один запуск
    # гарантирован, затем допускаются только лёгкие стадии; память и диск —
    # аварийные исключения. Снимок используют все create_task ниже по циклу.
    conf.pop("_host_load_snapshot", None)
    conf.pop("_host_load_tasks", None)
    try:
        hb = host_block(workers)
        if conf.get("respect_host_load", True) and hb.get("state") == "over":
            log(f"HOST BUSY: процессор {hb.get('cpu', {}).get('percent')}%, "
                f"память {hb.get('memory', {}).get('percent')}%, "
                f"диск {hb.get('disk', {}).get('percent')}% — действует мягкий допуск")
            conf["_host_load_snapshot"] = hb
            conf["_host_load_tasks"] = list(tasks)
    except Exception as e:
        log("host_load_error", repr(e))

    # A merge conflict is pipeline work, not a reason to hammer GitHub or ask
    # the owner. Return the same branch to Implement, then require Review and
    # Verify again before another immutable merge intent is created.
    try:
        resume_merge_conflicts(conf, state, tasks, workflows, workers)
    except Exception as e:
        log("merge_conflict_resume_error", repr(e))

    # Planner layer runs first, guarded so it can never break the pipeline.
    try:
        handle_epics(conf, state, tasks, workflows, workers, repo_identity_by_id)
    except Exception as e:
        log("epic_error", repr(e))

    # Finish durable repairs even after their original run disappeared from
    # the normal live-task scan.
    try:
        reconcile_diag_repairs(conf, tasks)
    except Exception as e:
        log("diag_repair_reconcile_error", repr(e))

    # Работа, которая крутится дольше порога, разбирается старшей моделью —
    # независимо от того, задавал ли конвейер вопрос.
    try:
        diag_sweep(conf, tasks)
    except Exception as e:
        log("diag_sweep_outer_error", repr(e))

    # Очередь, доставшаяся заболевшему исполнителю, сама не рассосётся.
    try:
        rescue_queued(conf, tasks, workflows, workers)
    except Exception as e:
        log("rescue_error", repr(e))

    # Снять вопросы, повисшие на отменённых задачах, иначе эпик стоит вечно.
    try:
        supersede_stale_questions(tasks)
    except Exception as e:
        log("supersede_error", repr(e))

    # После снятия устаревших вопросов забытая пауза больше не должна
    # блокировать сторож и автоподбор в этом же цикле.
    try:
        cleanup_orphaned_paused_pipelines(conf, tasks)
    except Exception as e:
        log("paused_pipeline_cleanup_outer_error", repr(e))

    # Owner answers resume stopped pipelines.
    try:
        answered = handle_answers(conf, workflows, workers, tasks)
        activity["answer_applied"] = (
            answered is True or (type(answered) is int and answered > 0))
    except Exception as e:
        log("answer_error", repr(e))

    # Sequential epics: start the next subtask once the current one is finished.
    try:
        advance_epics(conf, tasks, workflows, workers)
    except Exception as e:
        log("epic_advance_error", repr(e))

    # Сторож использует тот же снимок цикла после ответов владельца: так
    # потерянный переход возобновляется, но снятая в этом цикле пауза не оживает.
    try:
        pipeline_watch(conf, lifecycle_tasks, workflows, workers)
    except Exception as e:
        log("pipeline_watch_error", repr(e))

    try:
        cleanup_work_archive(conf, lifecycle_tasks)
    except Exception as e:
        log("work_archive_cleanup_error", repr(e))

    terminal_examined = 0
    terminal_limit = max(
        int(conf.get("max_terminal_tasks_per_cycle",
                     MAX_TERMINAL_TASKS_PER_CYCLE)),
        1,
    )
    handoff_tasks = complete_tasks if isinstance(complete_tasks, list) else tasks
    terminal_tasks = recent_terminal_handoff_history(
        handoff_tasks,
        conf.get("terminal_handoff_history_limit",
                 TERMINAL_HANDOFF_HISTORY_LIMIT),
        set(terminal_retry_ids) | set(overlap_wait_decisions) | set(recovery_ids),
    )
    # A full Plan can leave dozens of completed early stages behind. Continue
    # work nearest to delivery first; otherwise a fresh Implement/Review/Verify
    # result waits behind old Triage fragments for many expensive cycles.
    terminal_tasks = prioritize_terminal_handoffs(
        terminal_tasks, state.get("processed"), recovery_ids)
    # Apply the durable cursor after stage priority. Applying it before the
    # sort lets a capacity-deferred late stage jump back to the front on every
    # cycle and starve earlier-stage continuations forever.
    terminal_cursor = state.get("terminal_cursor")
    terminal_tasks = rotate_terminal_handoffs(
        terminal_tasks, terminal_cursor, state.get("processed"), recovery_ids)
    for t in terminal_tasks:
        tid, title, tstate = t["id"], t.get("title", ""), t.get("state")
        if not title.startswith(PREFIX):
            continue
        recovery_detail = None
        if tid in state["processed"]:
            recovery_detail = restart_recovery_detail(
                conf, tasks, t, stages, recovery_details.get(tid))
            if recovery_detail is None:
                continue
        if tstate not in ("succeeded", "failed", "cancelled"):
            if tid in recovery_ids:
                conf["_restart_recovery_retry"] = True
            continue

        closed_reason = work_lifecycle_block(base_title(title), t, handoff_tasks)
        if closed_reason:
            overlap_wait_decisions.pop(tid, None)
            if tid not in state["processed"]:
                state["processed"].append(tid)
            log(f"stage_ended task={tid} — не продолжаю: {closed_reason}")
            continue

        if terminal_examined >= terminal_limit:
            if tid in recovery_ids:
                retry_terminal_task(conf, state, tid)
            activity["terminal_backlog"] = True
            break
        terminal_examined += 1
        # Advance even when this task must wait for capacity. Otherwise the
        # same deferred handoff can starve every terminal task behind it.
        state["terminal_cursor"] = tid

        detail = recovery_detail or api(f"/tasks/{tid}")
        wf = (detail.get("workflow") or {}).get("title")
        if tid not in state["processed"]:
            state["processed"].append(tid)

        if tstate != "succeeded":
            attempts = detail.get("attempts") or []
            err = next((a.get("error") for a in reversed(attempts) if a.get("error")), "") or ""
            res = next((a.get("result") for a in reversed(attempts) if a.get("result")), "") or ""
            base = base_title(title)
            rid = detail["task"].get("repository_id") or ""
            # Отменённая/упавшая задача, которую уже перекрыла другая по той же
            # работе, вопросов не порождает — иначе эпик встанет на пустом месте.
            if is_stopped(conf, base):
                log(f"stage_ended state={tstate} task={tid} — работа остановлена владельцем, вопрос не создаю")
                continue
            newer = live_or_done_at(
                handoff_tasks, t, stage_no_of(title), since=t.get("created_at"))
            if newer and newer["id"] != tid:
                log(f"stage_ended state={tstate} task={tid} stage={wf} "
                    f"— перекрыта задачей {newer['id'][:8]}, вопрос не создаю")
                continue
            # Сбой окружения, а не работы: вход в модель протух, сеть моргнула.
            # Владельцу тут делать нечего — повторяем этап сами.
            if INFRA_SIGNS.search(err or "") and cap_rescues(base, "INFRA") < 3:
                try:
                    create_cap_rescue(base, "INFRA", {
                                 "request_key": str(uuid.uuid4()),
                                 "title": title[:200],
                                 "context": (detail.get("context") or
                                             detail["task"].get("context") or "")[:20000],
                                 "worker_id": detail["task"].get("worker_id") or "",
                                 "repository_id": rid,
                                 "timeout_seconds": conf.get("timeout_seconds", 7200),
                                 "workflow_revision_id": (detail.get("workflow") or {}).get("revision_id")
                                     or (workflows.get(wf, {}) or {}).get("revision_id")},
                                      conf, t, "execution_retry")
                    log(f"INFRA RETRY task={tid} stage={wf}: сбой окружения, повторяю этап")
                    notify(conf, "Повторяю этап: сбой окружения",
                           base + chr(10) + "Вход в модель или сеть подвели — это не ошибка работы. "
                           "Повторяю тот же этап сам, твоего участия не нужно.",
                           tags="repeat", click=f"{UI_BASE}/work")
                    continue
                except Exception as e:
                    retry_terminal_task(conf, state, tid)
                    log("infra_retry_error", repr(e))
                    continue

            done = stage_attempts(handoff_tasks, wf, t)
            if done >= conf.get("max_stage_attempts", 3):
                expl = {"situation_ru": f"Этап «{wf}» уже выполнялся {done} раз(а) и снова упал.",
                        "question_ru": "Что делать: разобраться вручную, поменять подход или отменить задачу?",
                        "options_ru": ["Разберись сам и предложи план", "Отмени эту задачу",
                                       "Пропусти этап", "Покажи подробности"]}
            else:
                expl = explain_failure(conf, wf, base, (err or res))
            route_question(conf, tid, wf, wf, base, rid,
                           expl.get("situation_ru", "Стадия не завершилась."),
                           expl.get("question_ru", "Что делать дальше?"),
                           expl.get("options_ru", []),
                           f"ОШИБКА:\n{squeeze(err, 4000)}\n\nПОСЛЕДНИЙ ВЫВОД:\n{squeeze(res, 8000)}",
                           attempts_so_far=done, repair_task=t)
            attach_question_work_id(t)
            log(f"stage_ended state={tstate} task={tid} stage={wf}")
            continue
        if wf not in stages:
            log(f"succeeded but unknown stage '{wf}' task={tid} -> ignored")
            continue

        idx = stages.index(wf)
        next_stage = stages[idx + 1] if idx + 1 < len(stages) else None
        attempts = detail.get("attempts") or []
        result = next((a.get("result") for a in reversed(attempts) if a.get("result")), "") or ""

        try:
            area_extend(base_title(title), result,
                        detail["task"].get("repository_id") or "")
        except Exception as e:
            log("area_extend_error", repr(e))
        try:
            collect_ideas(result, detail["task"].get("repository_id") or "",
                          base_title(title))
        except Exception as e:
            log("ideas_error", repr(e))
        if wf == "Specification":
            try:
                save_promises(base_title(title), result)
            except Exception as e:
                log("promises_error", repr(e))
        if wf == "Implement + Test":
            try:
                rid_i = detail["task"].get("repository_id") or ""
                record_implementation_artifact(
                    base_title(title), tid, title, result,
                    detail.get("context") or detail["task"].get("context") or "",
                    repo_identity_by_id.get(rid_i, ""))
            except Exception as e:
                # A transport failure must not erase the last proven artifact;
                # the next cycle can safely retry this completed task.
                log("implementation_artifact_error", repr(e))
        verdict = overlap_wait_decisions.pop(tid, None)
        reused_overlap_decision = isinstance(verdict, dict)
        if reused_overlap_decision:
            log(f"decision reuse task={tid} stage={wf} after AREA WAIT")
        else:
            verdict = decide(conf, wf, next_stage, title, result,
                             detail["task"].get("repository_id") or "")
        log(f"decision task={tid} stage={wf} action={verdict['action']} reason={verdict.get('reason','')}")
        if verdict.get("verdict_ru") and not reused_overlap_decision:
            try:
                save_stage_verdict(
                    tid, wf, verdict, result,
                    detail["task"].get("repository_id") or "")
            except Exception as e:
                log("verdict_save_error", repr(e))

        if not next_stage:
            # end of pipeline (Verify): auto-merge on PASS, then optional staging deploy
            if conf.get("auto_merge", True) and verify_passed(result):
                if _intent_has_wait(state, tid):
                    log(f"MERGE SKIP '{base_title(title)}': delivery wait already exists")
                    continue
                branch, implementation_head = selected_delivery(
                    base_title(title), extract_branch(result, detail.get("context", "")))
                rid = detail["task"].get("repository_id") or detail.get("repository", {}).get("id", "")
                repo_identity = repo_identity_by_id.get(rid, "")
                if branch and repo_identity and re.fullmatch(r"[0-9a-f]{40,64}", implementation_head or ""):
                    verify_snapshot = verify_gate(repo_identity, branch)
                    if verify_snapshot.get("blocked"):
                        route_question(
                            conf, tid, "Verify", "Verify", base_title(title), rid,
                            "Проверка не завершена: инфраструктура свежего сравнения веток недоступна.",
                            "Повторить Verify после восстановления доступа к репозиторию?",
                            ["Повтори проверку", "Покажи причину", "Останови работу"],
                            verify_snapshot["note"], attempts_so_far=0, branch=branch)
                        continue
                    link = try_url(result, rid)
                    verified_head = verify_snapshot.get("snapshot", {}).get("candidate_sha", "")
                    if verified_head != implementation_head:
                        route_question(
                            conf, tid, "Verify", "Review", base_title(title), rid,
                            "Ветка поставки изменилась после проверки.",
                            "Повторить Review для нового снимка ветки?",
                            ["Повтори Review", "Останови работу"],
                            "Проверенный снимок больше не совпадает с текущей поставкой.",
                            attempts_so_far=0, branch=branch)
                        continue
                    work_id = detail["task"].get("work_id") or ""
                    prior_conflicts = max(
                        (int(item.get("conflict_count") or 0)
                         for item in state.setdefault("merge_intents", {}).values()
                         if work_id and item.get("work_id") == work_id), default=0)
                    state.setdefault("merge_intents", {})[tid] = {
                        "phase": "intent", "base": base_title(title), "branch": branch,
                        "repository": repo_identity, "commit_sha": verified_head, "link": link or "",
                        "actor_id": None, "work_id": work_id, "base_branch": "main",
                        "conflict_count": prior_conflicts,
                        "rounds": max(1, _merge_rounds(tasks, t))}
                    save(STATE_PATH, state)  # intent must precede external gh_merge
                    recover_merge_intents(conf, state)
                    poll_delivery_state(conf, state)
                    continue
                log(f"auto-merge skipped: missing branch/repo/immutable head (branch={branch!r}, repo={repo_identity!r})")
                continue
            else:
                log(f"pipeline end task={tid}: verify not PASS or auto_merge disabled -> stopped for human")
                # Подзадача эпика НЕ считается сделанной: проверка не прошла.
                mark_final(tid, wf, False)
                base = base_title(title)
                rid = detail["task"].get("repository_id") or ""
                back = "Implement + Test" if "Implement + Test" in stages else wf
                # route_question сам решает, чей это вопрос. Тревогу владельцу
                # поднимаем ТОЛЬКО если он ушёл к нему: иначе владелец получал
                # «конвейер встал», а через минуту «продолжаю сам» — два
                # противоположных сообщения подряд.
                escalated = route_question(
                    conf, tid, wf, back, base, rid,
                    verdict.get("situation_ru") or "Проверка не подтвердила результат — в main ничего не влито.",
                    verdict.get("question_ru") or "Что делать: доделать работу заново или разобраться руками?",
                    verdict.get("options_ru") or ["Доделай сам и проверь заново",
                                                 "Покажи подробности", "Отмени эту задачу"],
                    squeeze(result), attempts_so_far=stage_attempts(handoff_tasks, back, t),
                    branch=selected_delivery(
                        base, extract_branch(result, detail.get("context", "")))[0])
                attach_question_work_id(t)
                if escalated:
                    notify(conf, "Проверка не прошла, нужен ты",
                           f"{base_title(title)}\nПроверка не подтвердила результат, "
                           "в main ничего не влито, и сам я это не решаю.",
                           priority="high", tags="warning", click=f"{UI_BASE}/tasks/{tid}")
            continue
        if verdict["action"] != "advance":
            if wf == "Triage" and close_triage_without_work(t, result):
                continue
            base = base_title(title)
            rid = detail["task"].get("repository_id") or ""
            situation = verdict.get("situation_ru") or ""
            question = verdict.get("question_ru") or ""
            back = resume_stage_for(stages, wf, next_stage)
            route_question(conf, tid, wf, back, base, rid,
                           situation or verdict.get("reason", ""),
                           question or "Что делать дальше?",
                           verdict.get("options_ru") or [], result,
                           attempts_so_far=stage_attempts(handoff_tasks, back, t),
                           branch=selected_delivery(
                               base, extract_branch(result, detail.get("context", "")))[0])
            attach_question_work_id(t)
            continue

        # Замок: не запускаем этап, если тот же файл уже правит другая работа.
        holder = area_busy(tasks, base_title(title), detail.get("context", ""),
                           (detail.get("task") or {}).get("repository_id", ""))
        if holder:
            log(f"AREA WAIT {base_title(title)!r} ждёт: тот же файл правит {holder!r}")
            overlap_wait_decisions[tid] = verdict
            retry_terminal_task(conf, state, tid)
            # The verdict is cached and no handoff was attempted. Do not let
            # this cheap overlap wait consume the cycle's terminal budget;
            # otherwise one blocked late stage monopolizes every fast poll
            # and starves unrelated ready continuations behind it.
            terminal_examined = max(terminal_examined - 1, 0)
            continue
        nw = workflows.get(next_stage)
        complexity = verdict.get("next_complexity", "medium")
        if complexity not in ("low", "medium", "high"):
            complexity = "medium"
        rid = (detail.get("task") or {}).get("repository_id", "")
        worker_name = stage_worker(
            conf, next_stage, complexity, workers, repository_id=rid)
        worker = workers.get(worker_name)
        if not nw or not nw.get("enabled") or not worker:
            retry_terminal_task(conf, state, tid)
            log(f"cannot advance: workflow/worker missing for '{next_stage}' (повторю позже)")
            continue

        # stage marker in the title so the Work list shows progress at a glance
        base = re.sub(r"^\[auto\]\s*(\[\d+/\d+[^\]]*\]\s*)?", "", title).strip()
        next_title = f"[auto] [{idx + 2}/{len(stages)} {next_stage}] {base}"[:200]

        # Idempotency guard: if this work already has a task at the next stage
        # (or beyond) that is live or done, do NOT create another one. Without
        # this, any re-processing of an old task duplicates the whole tail.
        if is_stopped(conf, base):
            log(f"skip: '{base}' остановлена владельцем — дальше не двигаю")
            continue
        dup = live_or_done_at(
            handoff_tasks, t, idx + 2, since=t.get("created_at"))
        if dup:
            log(f"skip: '{base}' уже имеет задачу на стадии {next_stage} или дальше "
                f"({dup['id'][:8]} {dup.get('state')})")
            continue

        handoff = verdict.get("handoff", "")
        branch = extract_branch(result, detail.get("context", ""))
        if wf == "Specification" or next_stage in ("Review", "Verify"):
            try:
                rid_b = detail["task"].get("repository_id") or ""
                cands = branch_candidates(result, detail.get("context", ""))
                picked = pushed_branch(cands, repo_identity_by_id.get(rid_b, ""))
                if picked:
                    branch = picked
            except Exception as e:
                log("branch_pick_error", repr(e))
        if wf == "Review" and next_stage == "Verify" and branch:
            rid_p = detail["task"].get("repository_id") or ""
            try:
                pinned, pin_error = pin_reviewed_delivery(
                    base, repo_identity_by_id.get(rid_p, ""), branch, result)
            except Exception as e:
                retry_terminal_task(conf, state, tid)
                log("review_delivery_pin_error", repr(e))
                continue
            if not pinned:
                route_question(
                    conf, tid, "Review", "Review", base, rid_p,
                    pin_error,
                    "Повторить Review для текущего снимка ветки?",
                    ["Повтори Review", "Останови работу"],
                    pin_error, attempts_so_far=0, branch=branch)
                continue
        branch, implementation_head = selected_delivery(base, branch)
        branch_line = f"Branch: {branch}\n" if branch else ""
        head_line = (f"Implementation head: {implementation_head}\n"
                     if implementation_head else "")
        specification_head = (extract_specification_head(result)
                              if wf == "Specification" else "")
        specification_head_line = (f"Specification head: {specification_head}\n"
                                   if specification_head else "")
        card = extract_card(result, detail.get("context", ""))

        # Спецификация является артефактом поставки, а не только текстом в
        # сокращённом отчёте.  До разработки подтверждаем, что выбранная ветка
        # действительно опубликована и содержит изменения относительно main.
        if wf == "Specification":
            branch_state, branch_files = "", []
            if branch:
                try:
                    rid_s = detail["task"].get("repository_id") or ""
                    branch_state, branch_files = branch_report(
                        repo_identity_by_id.get(rid_s, ""), branch)
                except Exception as e:
                    retry_terminal_task(conf, state, tid)
                    log(f"SPEC BRANCH WAIT {base[:40]!r}: проверка GitHub недоступна: {e}")
                    continue

            branch_missing = not branch or branch_state == "нет"
            branch_empty = branch_state == "есть" and not branch_files
            if branch and branch_state not in ("есть", "нет"):
                retry_terminal_task(conf, state, tid)
                log(f"SPEC BRANCH WAIT {base[:40]!r}: состояние ветки неизвестно")
                continue
            if branch_missing or branch_empty:
                if cap_rescues(base, "SPEC_BRANCH") >= 1:
                    log(f"SPEC BRANCH STOP {base[:40]!r}: возврат уже использован, "
                        "разработку не запускаю")
                    continue
                back_title = f"[auto] [{idx + 1}/{len(stages)} {wf}] {base}"[:200]
                reason = (f"ветки {branch} нет в origin" if branch_missing and branch
                          else "в отчёте и контексте нет имени ветки" if not branch
                          else f"ветка {branch} не содержит отличий от main")
                spec_ctx = (
                    f"Pipeline: {base}\nPrevious stage: {wf}\n{branch_line}\n"
                    f"Спецификацию нельзя передать в разработку: {reason}. "
                    "Сохрани документ в ТЕКУЩЕЙ назначенной ветке: закоммить "
                    "изменения, выполни git push -u origin HEAD и проверь, что "
                    "git diff --name-only origin/main...HEAD показывает файлы задачи. "
                    "Ветку не переключай. Затем сдай Specification повторно.")
                try:
                    create_cap_rescue(base, "SPEC_BRANCH", {
                                 "request_key": str(uuid.uuid4()), "title": back_title,
                                 "context": spec_ctx[:20000],
                                 "worker_id": detail["task"].get("worker_id") or worker["id"],
                                 "repository_id": detail["task"].get("repository_id") or "",
                                 "timeout_seconds": conf.get("timeout_seconds", 7200),
                                 "workflow_revision_id": (detail.get("workflow") or {}).get(
                                     "revision_id") or workflows.get(wf, {}).get("revision_id")
                                     or nw["revision_id"]}, conf, t,
                                      "machine_gate_return")
                    log(f"SPEC BRANCH GATE {base[:40]!r}: {reason} — вернул сохранить")
                    notify(conf, "Вернул сам: спецификация не сохранена",
                           base + chr(10) + reason.capitalize() +
                           ". Вернул закоммитить и загрузить документ; твоего участия не нужно.",
                           tags="wrench", click=f"{UI_BASE}/work")
                    continue
                except Exception as e:
                    retry_terminal_task(conf, state, tid)
                    log("spec_branch_gate_error", repr(e))
                    continue

        # Ворота Спецификации: без машинно проверяемых обещаний дальше нельзя.
        if (wf == "Specification" and not PROMISE_LINE.search(result or "")
                and cap_rescues(base, "SPEC") < 1):
            back_title = f"[auto] [{idx + 1}/{len(stages)} {wf}] {base}"[:200]
            nl = chr(10)
            spec_ctx = nl.join([
                f"Pipeline: {base}",
                f"Previous stage: {wf}",
                branch_line.strip(),
                "",
                "Спецификация принята по содержанию, но в отчёте НЕТ строк "
                "ГОТОВО-КОГДА — без них проверка работы держится на мнении, "
                "а не на фактах. Дополни СУЩЕСТВУЮЩУЮ спецификацию (ветку не "
                "переключай: git fetch origin <ветка> и git reset --hard "
                "FETCH_HEAD) и закончи отчёт строками:",
                "ГОТОВО-КОГДА: файл <путь, который изменится>",
                "ГОТОВО-КОГДА: команда <команда, обязана выйти нулём>",
                "Лучшая команда — новый тест, выражающий суть задачи "
                "(сейчас он красный)."])
            try:
                create_cap_rescue(base, "SPEC", {
                             "request_key": str(uuid.uuid4()), "title": back_title,
                             "context": spec_ctx[:20000],
                             "worker_id": worker["id"],
                             "repository_id": detail["task"].get("repository_id") or "",
                             "timeout_seconds": conf.get("timeout_seconds", 7200),
                             "workflow_revision_id": workflows.get(wf, {}).get("revision_id")
                                 or nw["revision_id"]}, conf, t,
                                  "machine_gate_return")
                log(f"SPEC GATE {base[:40]!r}: нет ГОТОВО-КОГДА — вернул дописать обещания")
                notify(conf, "Вернул сам: спецификация без обещаний",
                       base + chr(10) + "Спецификация не назвала проверяемые признаки "
                       "готовности (ГОТОВО-КОГДА) — вернул дописать. Твоего участия не нужно.",
                       tags="wrench", click=f"{UI_BASE}/work")
                continue
            except Exception as e:
                retry_terminal_task(conf, state, tid)
                log("spec_gate_error", repr(e))
                continue

        # Implement must never start from an unverifiable Specification head.
        # A missing, abbreviated, or malformed HEAD is a hard return to the
        # same stage, so the next stage cannot guess which revision to use.
        if wf == "Specification":
            head_reason = specification_head_gate(result)
            if head_reason and cap_rescues(base, "SPEC_HEAD") >= 1:
                log(f"SPEC HEAD STOP {base[:40]!r}: возврат уже использован, "
                    "разработку не запускаю")
                continue
            if head_reason:
                back_title = f"[auto] [{idx + 1}/{len(stages)} {wf}] {base}"[:200]
                try:
                    create_cap_rescue(base, "SPEC_HEAD", {
                        "request_key": str(uuid.uuid4()), "title": back_title,
                        "context": (f"Pipeline: {base}\nPrevious stage: {wf}\n"
                                     f"{branch_line}\n{head_reason}")[:20000],
                        "worker_id": worker["id"],
                        "repository_id": detail["task"].get("repository_id") or "",
                        "timeout_seconds": conf.get("timeout_seconds", 7200),
                        "workflow_revision_id": workflows.get(wf, {}).get("revision_id")
                            or nw["revision_id"]}, conf, t,
                        "machine_gate_return")
                    log(f"SPEC HEAD GATE {base[:40]!r}: {head_reason}")
                    continue
                except Exception as e:
                    retry_terminal_task(conf, state, tid)
                    log("spec_head_gate_error", repr(e))
                    continue

        # Номер карточки принадлежит опубликованной ветке, а не названию
        # работы. Резерв сохраняется до создания Implement, поэтому два
        # законченных Specification в одном цикле не увидят один номер.
        if wf == "Specification":
            rid_c = detail["task"].get("repository_id") or ""
            card = reserved_card_number(state, repo_identity_by_id.get(rid_c, ""), branch)
            if not card:
                retry_terminal_task(conf, state, tid)
                log(f"SPEC CARD WAIT {base[:40]!r}: каталог карточек недоступен")
                continue
        card_line = f"Card: {card}\n" if card else ""

        # Ворота: дешёвая машинная проверка вместо дорогого круга Ревью.
        gate_note = ""
        if next_stage == "Review" and branch:
            rid_g = detail["task"].get("repository_id") or ""
            g = review_gate(conf, base, branch, repo_identity_by_id.get(rid_g, ""), tasks,
                            area_repo=rid_g, expected_card=card)
            if g and g.get("wait"):
                overlap_wait_decisions[tid] = verdict
                retry_terminal_task(conf, state, tid)
                terminal_examined = max(terminal_examined - 1, 0)
                continue
            if g and g.get("blocked"):
                # A failed authoritative fetch is an infrastructure verdict,
                # not a code defect and never a synthetic REQUEST CHANGES.
                route_question(
                    conf, tid, "Review", "Review", base, rid_g,
                    "Ревью не началось: недоступна инфраструктура свежего сравнения веток.",
                    "Повторить проверку после восстановления доступа к репозиторию?",
                    ["Повтори проверку", "Покажи причину", "Останови работу"],
                    g["note"], attempts_so_far=0, branch=branch)
                continue
            if g and g["back"]:
                back_title = f"[auto] [{idx + 1}/{len(stages)} {wf}] {base}"[:200]
                try:
                    return_body = {"request_key": str(uuid.uuid4()), "title": back_title,
                                 "context": (f"Pipeline: {base}\nPrevious stage: {wf}\n"
                                             f"Branch: {branch}\n{card_line}\n" + g["note"])[:20000],
                                 "worker_id": worker["id"],
                                 "repository_id": rid_g,
                                 "timeout_seconds": conf.get("timeout_seconds", 7200),
                                 "workflow_revision_id": workflows.get(wf, {}).get("revision_id")
                                     or nw["revision_id"]}
                    if g.get("cap_stage"):
                        created_g = create_cap_rescue(
                            base, g["cap_stage"], return_body, conf,
                            t, "machine_gate_return")
                    else:
                        created_g = create_child_task(
                            return_body, t, conf,
                            "machine_gate_return")
                    new_tid = (created_g.get("task") or {}).get("id", "") if isinstance(created_g, dict) else ""
                    notify(conf, g.get("alert") or "Вернул сам: поставка не прошла машинную проверку",
                           base + chr(10) + (g.get("alert_msg") or ""),
                           tags="wrench",
                           click=(f"{UI_BASE}/tasks/{new_tid}" if new_tid else f"{UI_BASE}/work"))
                    continue
                except Exception as e:
                    retry_terminal_task(conf, state, tid)
                    log("gate_return_error", repr(e))
                continue
            elif g:
                if g.get("branch"):
                    branch = g["branch"]
                    record_delivery_artifact(base, branch, g.get("head", ""))
                    branch_line = f"Branch: {branch}\n"
                    head_line = (f"Implementation head: {g['head']}\n"
                                 if g.get("head") else "")
                gate_note = "\n\n" + g["note"]

        context = (f"Pipeline: {base}\nPrevious stage: {wf}\n{branch_line}{head_line}"
                   f"{specification_head_line}{card_line}"
                   f"Orchestrator handoff: {handoff}\n\n"
                   f"Отчёт предыдущей стадии (сокращён):\n{squeeze(result)}"
                   + gate_note)[:20000]
        body = {
            # The control plane atomically replays this request key.  A second
            # Pilot holding the same stale list therefore receives this child
            # rather than creating a duplicate continuation.
            "request_key": continuation_request_key(tid, nw["revision_id"]),
            "title": next_title,
            "context": context,
            "worker_id": worker["id"],
            "repository_id": detail["task"].get("repository_id") or detail.get("repository", {}).get("id", ""),
            "timeout_seconds": conf.get("timeout_seconds", 7200),
            "workflow_revision_id": nw["revision_id"],
        }
        # The decision and delivery gates above can take long enough for
        # another Pilot to create the continuation. Re-check the shared
        # snapshot at the last possible moment before the external write.
        dup = live_or_done_at(
            handoff_tasks, t, idx + 2, since=t.get("created_at"))
        if dup:
            log(f"skip: '{base}' продолжение появилось перед созданием "
                f"({dup['id'][:8]} {dup.get('state')})")
            continue
        try:
            created = create_child_task(body, t, conf)
        except Exception as e:
            # do NOT swallow this task: drop it from 'processed' so the next
            # cycle tries again once a healthy worker is back.
            retry_terminal_task(conf, state, tid)
            log(f"cannot advance '{base}' {wf} -> {next_stage} (повторю позже): {e}")
            continue
        # The task snapshot was loaded before this cycle started.  Keep it
        # current so another completed attempt for this same work sees the
        # newly created next stage through live_or_done_at() below.
        created_task = created.get("task") if isinstance(created, dict) else None
        if (isinstance(created_task, dict)
                and not any(item.get("id") == created_task.get("id")
                            for item in tasks)):
            tasks.append(created_task)
            if handoff_tasks is not tasks:
                handoff_tasks.append(created_task)
        log(f"advanced pipeline='{title}' {wf} -> {next_stage} complexity={complexity} "
            f"worker={worker_name} branch={branch or '-'} "
            f"new_task={created.get('task', {}).get('id')}")

    # Recovery is a bounded startup classification, not a second task cursor.
    # A retryable handoff has already been removed from ``processed`` by
    # retry_terminal_task() and will be handled by the ordinary next cycle.
    conf.pop("_restart_recovery_ids", None)

    # V2 release state was polled before task processing and is the only
    # active delivery mechanism.  Legacy retry flags are audit-only.

    # A terminal handoff may free a slot after the first answer pass. Retry
    # answered continuations before admitting Plan so a full Plan cannot
    # starve an unfinished correction forever.
    try:
        answered = refill_open_work_slots(
            conf, workflows, workers,
            admit_new_plan=not activity["terminal_backlog"],
        )
        activity["answer_applied"] = (
            activity["answer_applied"]
            or answered is True
            or (type(answered) is int and answered > 0)
        )
    except Exception as e:
        log("work_slot_refill_error", repr(e))

    hint = next_poll_hint(
        conf, tasks,
        fast=(new_terminal or activity["task_created"] or activity["answer_applied"]
              or activity["terminal_backlog"]),
    )
    conf.pop("_cycle_activity", None)
    conf.pop("_active_work_tasks", None)
    return hint


def error_poll_hint(conf, failures, error=None):
    """Keep the normal interval on the first failure, then back off safely."""
    base = max(float((conf or {}).get("poll_seconds", 30)), 30)
    seconds = min(base * (2 ** max(int(failures) - 1, 0)),
                  float(ERROR_BACKOFF_MAX_SECONDS))
    try:
        retry_after = float(error.headers.get("Retry-After", 0))
        seconds = max(seconds, retry_after)
    except (AttributeError, TypeError, ValueError):
        pass
    return {"seconds": seconds, "reason": "error_backoff"}


def record_poll_hint(state, hint, now=None):
    """Persist every choice, but log only when the interval or reason changes."""
    previous = state.get("next_poll") or {}
    chosen = {
        "seconds": hint["seconds"],
        "reason": hint["reason"],
        "chosen_at": time.time() if now is None else now,
    }
    state["next_poll"] = chosen
    if (previous.get("seconds"), previous.get("reason")) != (
            chosen["seconds"], chosen["reason"]):
        log(f"next_poll seconds={chosen['seconds']:g} reason={chosen['reason']}")


def normalize_pilot_state(state):
    """Restore required cursors without discarding surviving durable state."""
    if not isinstance(state, dict):
        state = {}
    for key in (
            "processed", "automation_results_processed", "epics_processed",
            "epic_starts_processed", "poll_terminal_seen"):
        if not isinstance(state.get(key), list):
            state[key] = []
    return state


def run_loop(max_cycles=None, sleep_fn=None, clock_fn=None):
    sleep_fn = sleep_fn or time.sleep
    clock_fn = clock_fn or time.time
    failures = 0
    completed = 0
    recovery_ids = None
    recovery_watermark = None
    while max_cycles is None or completed < max_cycles:
        conf = load(CONF_PATH, None)
        state = normalize_pilot_state(load(STATE_PATH, {"processed": []}))
        hint = {"seconds": 60, "reason": "no_config"}
        if conf and conf.get("enabled", True):
            if recovery_ids is None:
                recovery_watermark = state.get("terminal_handoff_watermark")
                recovery_ids = (frozenset(
                    (state.get("processed") or [])[-RESTART_RECOVERY_RETENTION:])
                                if recovery_watermark else frozenset())
                recovery_watermark = recovery_watermark or ""
            else:
                # Recovery is deliberately a startup-only pass.  Failed
                # handoffs remove their ID from ``processed`` and retry via
                # the ordinary terminal cursor, rather than re-reading the
                # whole startup history on every poll.
                recovery_ids = frozenset()
                recovery_watermark = ""
                conf.pop("_restart_recovery_ids", None)
                conf.pop("_restart_recovery_watermark", None)
            if recovery_ids:
                conf["_restart_recovery_ids"] = recovery_ids
                conf["_restart_recovery_watermark"] = recovery_watermark
            else:
                conf.pop("_restart_recovery_ids", None)
                conf.pop("_restart_recovery_watermark", None)
            try:
                hint = cycle(conf, state) or next_poll_hint(conf, [])
                cycle_now = clock_fn()
                failures = 0
                if not conf.get("_restart_recovery_retry"):
                    state["terminal_handoff_watermark"] = (
                        datetime.datetime.fromtimestamp(
                            cycle_now, datetime.timezone.utc).isoformat().replace(
                                "+00:00", "Z"))
                try:
                    write_automation_status(pilot_completed_at=datetime.datetime.fromtimestamp(
                        cycle_now, datetime.timezone.utc).isoformat().replace("+00:00", "Z"))
                except Exception as e:
                    log("automation_status_error", repr(e))
            except Exception as e:
                cycle_now = clock_fn()
                log("cycle_error", repr(e))
                failures += 1
                hint = error_poll_hint(conf, failures, e)
            # This cursor must remain larger than the task history visible to
            # cycle().  Otherwise an old terminal stage falls out, is treated
            # as new again, and can reopen a completed pipeline forever.
            state["processed"] = state["processed"][-PROCESSED_RETENTION:]
            state["automation_results_processed"] = state.get(
                "automation_results_processed", [])[-PROCESSED_RETENTION:]
            state["epics_processed"] = state.get(
                "epics_processed", [])[-PROCESSED_RETENTION:]
            state["epic_starts_processed"] = state.get(
                "epic_starts_processed", [])[-PROCESSED_RETENTION:]
            state["poll_terminal_seen"] = state.get(
                "poll_terminal_seen", [])[-PROCESSED_RETENTION:]
            record_poll_hint(state, hint, cycle_now)
            save(STATE_PATH, state)
        elif conf:
            hint = {"seconds": max(float(conf.get("poll_seconds", 30)), 1),
                    "reason": "disabled"}
        sleep_fn(hint["seconds"])
        completed += 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "cleanup-plan-cards":
        parser = argparse.ArgumentParser(prog="pilot.py cleanup-plan-cards")
        parser.add_argument("--before", required=True)
        parser.add_argument("--apply", action="store_true")
        args = parser.parse_args(argv[1:])
        cleanup_legacy_plan_cards(args.before, apply=args.apply)
        return
    log("factory-pilot started")
    run_loop()


if __name__ == "__main__":
    main()
