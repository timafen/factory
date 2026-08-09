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
import calendar
import io
import json, re, subprocess, time, urllib.request, urllib.error, uuid, sys, os

API = "http://127.0.0.1:7337/api/v1"
HOME = "/opt/factory-data"
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


def api(path, body=None):
    req = urllib.request.Request(API + path)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


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
    "questions": ("Нужен твой ответ", "План эпика готов"),
    "stuck": ("Кручусь по кругу", "Зациклилось", "Не могу продолжить",
              "Проверка не прошла", "Verify PASS, но мёрж", "Эпик НЕ запустился"),
    "money": ("Не влезло в деньги", "Остановил работу", "Дневной потолок",
              "Упёрлись в лимит", "Продлил бюджет"),
    "done": ("Задача выполнена", "Задача завершена", "Эпик завершён", "Задача заведена",
             "Голосовая задача", "Эпик запущен"),
    "escalate": ("Исполнитель повышен",),
    "routine": ("Вернул сам:", "Вернул без Ревью", "Мёрж-конфликт", "Сдвинул застрявшую",
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


HEX_TOKEN = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])")


def no_bare_hashes(text):
    """Хозяин читает пуши на телефоне. Голый хеш ему не говорит ничего,
    поэтому в уведомления он не проходит никогда — это правило кода,
    а не пожелание агентам."""
    return HEX_TOKEN.sub("(служебный код)", str(text or ""))


NOTIFY_LOG_PATH = f"{HOME}/pilot/notifications.jsonl"


def _notify_journal(title, message, group, delivered, click):
    """Каждое уведомление остаётся в журнале — экран «Уведомления» читает его.
    Тихие (выключенная группа) тоже пишутся, с пометкой."""
    try:
        rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "title": title, "message": message[:1500],
               "group": group, "delivered": bool(delivered), "click": click}
        with open(NOTIFY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if os.path.getsize(NOTIFY_LOG_PATH) > 1_500_000:
            lines = io.open(NOTIFY_LOG_PATH, encoding="utf-8").readlines()[-800:]
            io.open(NOTIFY_LOG_PATH, "w", encoding="utf-8").writelines(lines)
    except Exception as e:
        log("notify_journal_error", repr(e))


def notify(conf, title, message, priority="default", tags="", click=""):
    title = no_bare_hashes(title)
    message = no_bare_hashes(message)
    _notify_journal(title, message, notify_group(title),
                    notify_allowed(conf, title), click)
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
2. Сдача: сначала перебазируй на свежий main (git fetch origin main,
   затем git rebase origin/main), потом проверь список файлов командой
   git diff --name-only origin/main...HEAD — именно ТРИ точки, сравнение от
   точки ветвления. В списке ТОЛЬКО твои файлы. Запушь:
   git push --force-with-lease -u origin HEAD. Непушенная работа не существует.
3. Отчёт заканчивай строками:
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
4. Спецификация ДОПОЛНИТЕЛЬНО обязана выдать проверяемые обещания:
   ГОТОВО-КОГДА: файл <путь>            (файл, который изменится)
   ГОТОВО-КОГДА: команда <команда>      (обязана выйти нулём; лучший вариант —
   новый тест, выражающий суть задачи, сейчас красный). Ворота сверят дифф
   с обещаниями; Проверка обязана прогнать команды и показать вывод.
5. Пиши для человека: первая строка коммита — по-русски, что и зачем.
   Голые хеши/ID на экранах и в текстах для владельца запрещены — только
   со словесной подписью. Ревью возвращает работу за голый хеш на экране.
6. Ревью: меряй поставку ТОЛЬКО диффом от точки ветвления
   (git diff origin/main...HEAD, три точки). Файлы, отличающиеся лишь потому,
   что ветка отстала от main, — НЕ замечание, main движется быстро. Возвращай
   только за чужие файлы в ЭТОМ диффе, отсутствие ветки, несделанное или
   сломанное — с конкретным списком. За формулировки не возвращай.
   Побочные идеи — строкой «ПРЕДЛОЖЕНИЕ: что — зачем», не делай их молча.
7. Знания: заводи ОТДЕЛЬНУЮ карточку под свою работу. В общие файлы-журналы
   (CARD-0030 и подобные) НЕ дописывай ни строки: общий файл — магнит для
   конфликтов слияния, когда работы идут параллельно. Всё побочное — строками
   ПРЕДЛОЖЕНИЕ/НАХОДКА в отчёте, карточка заведётся сама.
=== КОНЕЦ ПРАВИЛ ===
"""


def create_task(body, conf=None):
    if conf and str(body.get("title", "")).startswith(PREFIX):
        money_guard(conf, body["title"])
    if str(body.get("title", "")).startswith(PREFIX):
        ctx = body.get("context") or ""
        if "ПРАВИЛА ДЛЯ АГЕНТА" not in ctx:
            body["context"] = (ctx + "\n\n" + AGENT_RULES)[:60000]
    """Create a task robustly. Attempt chain:
    1. exact worker + repository (fast path when already advertised);
    2. route + same worker (lets the worker acquire the repo dynamically);
    3. route without a worker pin (any eligible worker takes it - better a
       different model tier than a dead button).
    Every fallback is logged with the control-plane error that caused it."""
    try:
        return api("/tasks", body)
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
    return out


def gh_merge(repo_identity, branch, title):
    """Open (best-effort) and squash-merge the branch into the default branch."""
    repo = repo_identity.split("github.com/")[-1]
    env = dict(os.environ, HOME=HOME)
    subprocess.run(
        ["gh", "pr", "create", "--repo", repo, "--head", branch,
         "--title", title or branch,
         "--body", "Automated by the Factory pipeline after Verify PASS."],
        capture_output=True, text=True, env=env, timeout=120)
    r = subprocess.run(
        ["gh", "pr", "merge", branch, "--repo", repo, "--squash", "--delete-branch"],
        capture_output=True, text=True, env=env, timeout=180)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


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

# Кто поставил работу. Владельцу важно отличать своё от чужого.
ORIGIN_OWNER = "owner"              # завёл человек: голосом или кнопкой
ORIGIN_ASSISTANT = "assistant"      # завёл помощник из переписки
ORIGIN_ORCHESTRATOR = "orchestrator"  # развернулось из эпика само


def note_work(base, origin, start_stage="", skipped=None, reason=""):
    """Запись о происхождении работы. Пишется один раз, при заведении:
    повторные стадии её не трогают."""
    try:
        rec = load(WORKS_PATH, {})
        if base in rec:
            return
        rec[base] = {
            "origin": origin,
            "start_stage": start_stage or "",
            "skipped": list(skipped or []),
            "reason": reason or "",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        save(WORKS_PATH, rec)
    except Exception as e:
        log("note_work_error", repr(e))


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
    worker = workers.get(stage_worker(conf, stage_name, cx, workers))
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
            if out:
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
                        repo_id=""):
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
        'Ответь ТОЛЬКО JSON: {"decision": "answer" или "escalate", '
        '"answer": "<если answer: конкретный исполнимый ответ агенту по-русски, '
        '2-5 предложений, как будто это сказал владелец>", '
        '"reason": "<если escalate: одной фразой почему это решение владельца>"}'
    )
    try:
        text, _eng = brain(conf, prompt, timeout=240)
        v = json.loads(text[text.find("{"):text.rfind("}") + 1])
        if v.get("decision") == "answer" and (v.get("answer") or "").strip():
            return v
        return {"decision": "escalate", "answer": "",
                "reason": v.get("reason", "оркестратор передал решение владельцу")}
    except Exception as e:
        log("orchestrator_answer_error", repr(e))
        return {"decision": "escalate", "answer": "", "reason": f"сбой авто-ответа: {e}"}


def stage_attempts(tasks, stage, base):
    """How many times this exact work already went through this exact stage."""
    n = 0
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if m and m.group(1).strip() == stage and m.group(2).strip() == base.strip():
            n += 1
    return n


def stage_no_of(title):
    """Номер стадии из заголовка '[auto] [3/5 Implement + Test] ...' -> 3."""
    m = re.match(r"^\[auto\]\s*\[(\d+)/", title or "")
    return int(m.group(1)) if m else 0


def live_or_done_at(tasks, base, stage_no, since=None):
    """Задача по этой же работе на стадии stage_no или дальше, живая либо успешная.
    Единственный источник правды для защиты от дублей: и при продвижении по
    конвейеру, и при возобновлении после ответа владельца.
    since — момент, начиная с которого задача считается «новой»: старый хвост от
    прошлого прогона дублем не считается и не мешает доработке."""
    base = (base or "").strip()
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m or m.group(2).strip() != base:
            continue
        if since and (t.get("created_at") or "") <= since:
            continue
        if stage_no_of(t.get("title")) >= stage_no and t.get("state") in (
                "running", "queued", "preparing", "succeeded"):
            return t
    return None


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
        newer = live_or_done_at(tasks, m.group(2).strip(), stage_no_of(t.get("title")),
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


def area_busy(tasks, base, context="", repo=""):
    """Кто уже занял тот же файл. Возвращает имя работы или пустую строку."""
    mine = area_of(base, context, repo)
    if not mine:
        return ""
    known = load(AREAS_PATH, {}) or {}
    for t in tasks:
        if t.get("state") not in ("running", "queued"):
            continue
        m = STAGE_TITLE_RE.match(t.get("title", ""))
        if not m:
            continue
        other = m.group(2).strip()
        if other == base.strip():
            continue
        if mine & set(known.get(other) or []):
            return other
    return ""


# ------------------------------------------------------------- предложения ---
# Ничто найденное по пути не теряется. Агент пишет в отчёте строку
# «ПРЕДЛОЖЕНИЕ: ...» или «НАХОДКА: ...» — и это становится карточкой
# на экране «План», привязанной к тому же проекту, в котором шла работа.
IDEAS_PATH = f"{HOME}/pilot/ideas.json"
IDEA_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(ПРЕДЛОЖЕНИЕ|НАХОДКА)(?:\*\*)?\s*:\s*(.+?)\s*$", re.M)
IDEA_KINDS = ("idea", "finding")
IDEA_STATES = ("new", "planned", "in_work", "done", "rejected")
IDEA_SKIP = ("нет", "none", "-", "н/д", "нету", "n/a")


def ideas_all():
    d = load(IDEAS_PATH, None)
    return d if isinstance(d, list) else []


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


def add_idea(kind, title, repo="", why="", origin="agent", source="",
             state="new", order=None):
    """Заводит карточку. Повтор в том же проекте не плодится."""
    title = re.sub(r"\s+", " ", (title or "").strip())
    if not title:
        return None
    kind = kind if kind in IDEA_KINDS else "idea"
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
           "source": (source or "")[:200],
           "state": state if state in IDEA_STATES else "new",
           "reason": "", "task_id": "", "order": int(order),
           "created": now, "updated": now}
    items.append(rec)
    save(IDEAS_PATH, items)
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
        if add_idea(kind, title or text, repo_id, why, origin="agent", source=source):
            n += 1
    return n


# --------------------------------------------------------- сторож конвейера ---
# Работа, у которой не бежит ни одна задача, не должна молча умирать.
# Так уже случалось: этап закончился, следующий не создали (замок по области,
# перегрузка, пауза), и повод создать его больше никогда не появлялся.
STALL_PATH = f"{HOME}/pilot/stalled.json"
STALL_WAIT = 600      # сколько ждём, прежде чем толкать: вдруг просто пауза
STALL_NUDGES = 2      # сколько раз толкаем сами, дальше — к хозяину


def stage_names(conf):
    st = conf.get("stages")
    if isinstance(st, list):
        return [x.get("workflow") for x in st if x.get("workflow")]
    return list(st or [])


def work_status_write(mem):
    """Пишем словами, почему работа стоит: экран не должен врать."""
    out = {}
    for base, rec in (mem or {}).items():
        why = rec.get("why")
        if why == "owner":
            out[base] = {"state": "stopped_owner",
                         "text": "остановлена: конвейер по этой работе на паузе"}
        elif why == "give_up":
            out[base] = {"state": "stuck",
                         "text": "не могу сдвинуть сам: этап закончился, "
                                 "следующий не запускается"}
        elif why == "nudged":
            out[base] = {"state": "nudged",
                         "text": "конвейер встал, я запустил следующий этап сам"}
        else:
            out[base] = {"state": "idle",
                         "text": "ничего не бежит, жду следующий этап"}
    save(f"{HOME}/pilot/work_status.json", out)


def pipeline_watch(conf, tasks, workflows, workers):
    stages = stage_names(conf)
    if not stages:
        return
    stopped = set(conf.get("stopped_pipelines") or [])
    groups = {}
    for t in tasks:
        m = STAGE_TITLE_RE.match(t.get("title", "") or "")
        if m:
            groups.setdefault(m.group(2).strip(), []).append((m.group(1).strip(), t))
    mem = load(STALL_PATH, {}) or {}
    now = int(time.time())
    live = ("running", "queued", "pending", "created", "starting")
    for base, lst in groups.items():
        if any(t.get("state") in live for _, t in lst):
            mem.pop(base, None)
            continue
        if base in stopped:
            rec = mem.get(base) or {}
            rec["why"] = "owner"
            rec.setdefault("since", now)
            mem[base] = rec
            continue
        idx = [stages.index(st) for st, t in lst
               if t.get("state") == "succeeded" and st in stages]
        if not idx:
            continue
        far = max(idx)
        if far >= len(stages) - 1:
            mem.pop(base, None)          # дошли до конца конвейера
            continue
        rec = mem.get(base) or {}
        rec.setdefault("since", now)
        rec.setdefault("nudges", 0)
        mem[base] = rec
        if now - int(rec["since"]) < STALL_WAIT:
            continue
        if int(rec["nudges"]) >= STALL_NUDGES:
            if rec.get("why") != "give_up":
                rec["why"] = "give_up"
                notify(conf, "Не могу продолжить сам",
                       base + "\nЭтап «" + stages[far] + "» закончился, "
                       "а следующий не запускается даже после двух попыток.",
                       priority="high", tags="warning")
            continue
        nxt = stages[far + 1]
        nw = workflows.get(nxt)
        wname = stage_worker(conf, nxt, "medium", workers)
        worker = workers.get(wname)
        if not nw or not nw.get("enabled") or not worker:
            continue
        src = next((t for st, t in lst if st == stages[far]), None)
        rid = (src or {}).get("repository_id") or ""
        title = f"[auto] [{far + 2}/{len(stages)} {nxt}] {base}"[:200]
        try:
            create_task({"request_key": str(uuid.uuid4()), "title": title,
                         "context": ("Конвейер встал: предыдущий этап закончился, "
                                     "а следующий никто не создал. Продолжай с того "
                                     "же места, на той же ветке, ничего не начиная "
                                     "заново.\n\nРабота: " + base +
                                     "\nПредыдущий этап: " + stages[far])[:60000],
                         "worker_id": worker["id"], "repository_id": rid,
                         "timeout_seconds": conf.get("timeout_seconds", 7200),
                         "workflow_revision_id": nw["revision_id"]}, conf)
            rec["nudges"] = int(rec["nudges"]) + 1
            rec["since"] = now
            rec["why"] = "nudged"
            log("WATCH сдвинул застрявшую работу " + repr(base[:60]) +
                ": " + stages[far] + " -> " + nxt)
            notify(conf, "Сдвинул застрявшую работу",
                   base + "\n" + stages[far] + " → " + nxt, tags="wrench")
        except Exception as e:
            log("watch_create_error", repr(e))
    save(STALL_PATH, mem)
    try:
        work_status_write(mem)
    except Exception as e:
        log("work_status_error", repr(e))


# ------------------------------------------------------ ворота перед Ревью ---
# Разбор сорока решений показал: Ревью чаще всего отказывает не по сути,
# а по гигиене — ветки нет в хранилище или в диффе чужие файлы. Проверять
# это умеет машина за секунды. Дорогое Ревью получает уже проверенный факт.

def gh_json(args, timeout=30):
    env = dict(os.environ, HOME=HOME)
    r = subprocess.run(["gh"] + args, capture_output=True, text=True,
                       env=env, timeout=timeout)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
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


def branch_report(repo_identity, branch):
    """Что реально лежит в хранилище: ('нет'|'есть', [файлы диффа])."""
    repo = repo_identity.split("github.com/")[-1]
    if not repo or not branch:
        return "", []
    b = gh_json(["api", f"repos/{repo}/branches/{branch}"])
    if b is None:
        return "нет", []
    cmp_ = gh_json(["api", f"repos/{repo}/compare/main...{branch}"])
    files = [f.get("filename") for f in (cmp_ or {}).get("files", [])][:80]
    return "есть", files


def review_gate(conf, base, branch, repo_identity):
    """Перед Ревью: ветка не запушена -> вернуть в разработку без Ревью.
    Ветка есть -> отдать Ревью проверенный список файлов. Ошибки сети
    не блокируют конвейер: тогда ворота просто молчат."""
    try:
        state_, files = branch_report(repo_identity, branch)
    except Exception as e:
        log("gate_error", repr(e))
        return None
    if state_ == "нет":
        note_cap = cap_rescues(base, "GATE")
        if note_cap >= 2:
            return None  # дважды возвращали за то же — пусть решает Ревью
        note_cap_rescue(base, "GATE")
        log(f"GATE '{base}': ветка {branch!r} не запушена — возвращаю в разработку без Ревью")
        return {"back": True,
                "alert": "Вернул сам: разработка не загрузила работу",
                "alert_msg": ("Агент сказал «готово», но не загрузил свою работу "
                              "в хранилище — проверять нечего. Вернул в разработку "
                              "с инструкцией. Твоего участия не нужно."),
                "note": (f"Машинная проверка перед Ревью: ветки {branch} НЕТ в хранилище. "
                         "Работа, которой нет в хранилище, не существует — проверить её нельзя. "
                         "Сделай: git push -u origin " + (branch or "<ветка>") +
                         " и сдай заново. Ничего не переписывай, только запушь и проверь дифф.")}
    if state_ == "есть" and files:
        listing = "\n".join("  - " + f for f in files)

        # Область: файлы вне заявленной зоны — возврат кодом, без Ревью.
        known = load(AREAS_PATH, {}) or {}
        mine = set()
        for p in known.get(base) or []:
            mine.add(p.split("::", 1)[1] if "::" in p else p)
        foreign = sorted(f for f in files if mine and f not in mine)
        if foreign and cap_rescues(base, "DIRT") < 1:
            note_cap_rescue(base, "DIRT")
            log(f"GATE '{base}': {len(foreign)} файлов вне области — возвращаю без Ревью")
            return {"back": True,
                    "alert": "Вернул сам: в поставке чужие файлы",
                    "alert_msg": ("В работе оказались файлы, не относящиеся к задаче "
                                  "(%d шт.) — вернул в разработку с точным списком, "
                                  "что убрать. Твоего участия не нужно." % len(foreign)),
                    "note": ("Машинная проверка перед Ревью: в поставке файлы ВНЕ "
                             "заявленной области работы:\n"
                             + "\n".join("  - " + f for f in foreign)
                             + "\nЗаявленная область:\n"
                             + "\n".join("  - " + f for f in sorted(mine))
                             + "\nУбери чужое из ветки: git checkout origin/main -- <файл>; "
                             "запушь и сдай снова. Если область расширилась осознанно — "
                             "напиши в отчёте новую строку ОБЛАСТЬ: с полным списком и почему.")}

        # Обещания: что Спецификация записала как «готово, когда».
        prom = (load(PROMISES_PATH, {}) or {}).get(base) or {}
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

        return {"back": False,
                "note": (f"Машинная проверка: ветка {branch} в хранилище ЕСТЬ. "
                         f"Файлы в поставке по данным GitHub ({len(files)}):\n{listing}"
                         + prom_note + "\n"
                         "Сверяй записку с этим списком, а не с памятью. "
                         "Возвращай работу только по правилам из инструкций: чужие файлы, "
                         "нет заявленного поведения, сломано работавшее. "
                         "Формулировки в записке — не повод для возврата.")}
    return None


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
        best = max([v for v in (cl.get("percents") or {}).values()
                    if isinstance(v, (int, float)) and 0 <= v <= 100] or [0])
        if best:
            st["alerted"] = limits_alert(conf, "claude", best, None)
            if best >= 95:
                note_limit(conf, "claude",
                           "настоящий счётчик подписки: израсходовано %d%%" % int(best), "")
    st["checked"] = int(time.time())
    save(PROVIDER_LIMITS_PATH, st)


def route_question(conf, task_id, stage, resume_stage, base, repo_id, situation,
                   question, options, prior_result, attempts_so_far=0, branch=""):
    """Try to resolve the question with the orchestrator; escalate if it's the
    owner's call OR if this stage has already been retried too many times."""
    cap = conf.get("max_stage_attempts", 3)
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
        if cap_rescues(base, "LOOP") >= int(conf.get("max_loop_rescues", 2)):
            v = {"decision": "owner",
                 "reason": "orchestrator already broke this loop twice"}
        else:
            v = orchestrator_answer(conf, stage, base,
                                situation + LOOP_NOTE.format(n=attempts_so_far),
                                question, prior_result, repo_id)
        if v["decision"] == "answer" and not looks_like_retry(v.get("answer", "")):
            note_cap_rescue(base, "LOOP")
            set_loop_baseline(base, attempts_so_far)
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
        "prior_result": squeeze(prior_result, 12000),
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
        undone = False
        for i, sub in enumerate(subs):
            # Смотрим и на идущие, и на уже помеченные готовыми: отметка о
            # провале приходит соседним циклом, и раньше «готово» защёлкивалось
            # навсегда — эпик убегал дальше по недоделанной подзадаче.
            if sub.get("status") not in ("running", "done"):
                continue
            since = sub.get("started_at") or epic.get("started_at") or epic.get("created_at") or ""
            state_now = subtask_state(tasks, open_q, last_stage, sub["title"], since)
            if state_now == "done":
                if sub.get("status") != "done":
                    sub["status"] = "done"
                    finished.append(i)
            elif sub.get("status") == "done":
                # «Готово» больше не соответствует правде — разжимаем.
                sub["status"] = "running"
                undone = True
                log("EPIC UNDONE подзадача " + repr(sub["title"][:50])
                    + ": состояние стало " + state_now + ", снимаю «готово»")
        if finished or undone:
            # Снятое «готово» обязано доехать до диска: раньше оно жило только
            # в памяти цикла, и каждые полминуты флаг щёлкал заново — вечный
            # лог и вечно «готовый» на диске эпик, который готов не был.
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
            if not subs[i].get("parallel_ok"):
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
            nxt = next((i for i in pending if i not in started and not subs[i].get("parallel_ok")), None)
            if nxt is not None and any(s.get("status") == "hold" for s in subs[:nxt]):
                held = next(i for i, s in enumerate(subs[:nxt]) if s.get("status") == "hold")
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
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                           time.gmtime(time.time() - max_age_min * 60))
    # самая ранняя стадия каждой работы среди свежих задач
    first = {}
    for t in tasks:
        title = t.get("title") or ""
        if not title.startswith(PREFIX):
            continue
        if (t.get("created_at") or "") < cutoff:
            continue
        base = base_title(title)
        n = stage_no_of(title)
        if not base or not n or base in known:
            continue
        if base not in first or n < first[base][0]:
            first[base] = (n, t.get("created_at") or "")
    for base, (n, _at) in first.items():
        skipped = stages[: n - 1]
        note_work(base, ORIGIN_OWNER, stages[n - 1] if n <= len(stages) else "",
                  skipped,
                  "владелец завёл работу сразу с этого шага" if skipped else "")
        if skipped:
            log(f"WORK ORIGIN base={base!r} владелец начал с {stages[n - 1]}, "
                f"пропущено: {', '.join(skipped)}")


def handle_answers(conf, workflows, workers, tasks):
    """An answered question resumes its pipeline from resume_stage."""
    stages = [s["workflow"] for s in conf["stages"]]
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
            rounds = stage_attempts(tasks, stage, base_title(q.get("title", "")))
        except Exception:
            rounds = 0
        if rounds >= 2 and cx_hint != "high":
            was = stage_worker(conf, stage, cx_hint, workers)
            cx_hint = "high"
            now_ = stage_worker(conf, stage, cx_hint, workers)
            log(f"ESCALATE '{q.get('title','')[:40]}' {stage}: {rounds} провала — {was} -> {now_}")
            if cap_rescues(q.get("title") or "", "ESCNOTE") < 1:
                note_cap_rescue(q.get("title") or "", "ESCNOTE")
                notify(conf, "Исполнитель повышен",
                       (q.get("title") or "") + "\nЭтап «" + str(stage) + "» провалился "
                       + str(rounds) + " раз(а). Повышаю: " + str(was) + " → " + str(now_) + ".",
                       tags="arrow_double_up", click=f"{UI_BASE}/work")
        worker = workers.get(stage_worker(conf, stage, cx_hint, workers))
        if not nw or not nw.get("enabled") or not worker:
            log(f"answer: no workflow/worker for {stage}")
            continue
        br = (q.get("branch") or extract_branch(q.get("prior_result", ""), "")
              or branch_from_history(tasks, base_title(q.get("title", ""))))
        branch_line = (
            f"Прошлая работа лежит в ветке: {br}\n"
            "ВЕТКУ В РАБОЧЕЙ КОПИИ НЕ ПЕРЕКЛЮЧАЙ — checkout чужой ветки ломает "
            "рабочую копию воркера. Оставайся на своей ветке и забери прошлую "
            f"работу так: `git fetch origin {br} && git reset --hard FETCH_HEAD`. "
            "Продолжай поверх и запушь СВОЮ текущую ветку: `git push -u origin HEAD`.\n\n"
        ) if br else ""
        context = (
            f"Pipeline: {q['title']}\n"
            f"Previous stage: {q['stage']} (остановлена, владелец ответил на вопрос)\n"
            f"{branch_line}"
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

        src_task = next((t for t in tasks if t["id"] == q.get("task_id")), None)
        dup = live_or_done_at(tasks, q["title"], idx + 1,
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
            if q.get("status") != "no_worker":
                q["status"] = "no_worker"
                q["escalation_reason"] = ("ответ есть; жду свободного исполнителя "
                                          "(лимит подписки или воркеры недоступны)")
                save(f"{QUESTION_DIR}/{q['id']}.json", q)
                log(f"answer resume: {q['id']} ждёт свободного исполнителя (после {tries} попыток)")
                notify(conf, "Ответ есть, исполнителей нет — жду",
                       f"{q['title']}\nПродолжу сам, как только освободится исполнитель для {stage}.",
                       tags="hourglass", click=f"{UI_BASE}/work")
            if time.time() - float(q.get("last_resume_try") or 0) < 600:
                continue
            q["last_resume_try"] = time.time()
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
        try:
            r = create_task(body, conf)
            tid = r.get("task", {}).get("id")
            q["status"] = "resolved"
            q["resumed_task_id"] = tid
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"ANSWER APPLIED q={q['id']} -> {stage} new_task={tid}")
            notify(conf, "Ответ принят, работа продолжена",
                   f"{q['title']}\nСтадия: {stage}", tags="arrow_forward",
                   click=f"{UI_BASE}/tasks/{tid}")
        except Exception as e:
            q["resume_tries"] = tries + 1
            save(f"{QUESTION_DIR}/{q['id']}.json", q)
            log(f"answer resume failed for {q['id']} (попытка {tries+1}/5): {e}")


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


def day_spent(tasks):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    atts = []
    for t in tasks:
        if (t.get("created_at") or "")[:10] != today:
            continue
        atts += attempts_of(t["id"], not _live(t))
    return task_cost_usd(atts)


def branch_head(branch):
    """Вершина рабочей ветки на origin — признак того, что работа движется."""
    if not branch:
        return ""
    out = _sh("sudo -n /usr/local/bin/fx repo head " + branch)
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

        spent = task_cost_usd(attempts_of(t["id"], False))
        if spent < cap:
            continue

        branch = branch_from_history(tasks, base)
        head = branch_head(branch)
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


def day_budget_blocks(conf, tasks):
    """Дневной потолок на всё сразу. Начатое доигрывается, новое не берётся."""
    cap = float(conf.get("day_cap_usd") or 0)
    if cap <= 0:
        return False
    spent = day_spent(tasks)
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
    r"upgrade to increase|плат[её]жный лимит|лимит исчерпан)", re.I)
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
        if seen and (time.time() - rec.get("detected_epoch", 0)) > 3600:
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
        if t.get("state") not in ("failed", "succeeded", "cancelled"):
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
        # и ошибка, и отчёт: Codex про исчерпанный лимит часто пишет прямо в вывод
        text = " ".join(str(a.get("error") or "") + " " + str(a.get("result") or "")[-4000:]
                        for a in atts[-2:])
        if not text or not LIMIT_SIGNS.search(text):
            continue
        # Слова «rate limit» в чужом отчёте или в диффе — не лимит подписки.
        # Если настоящий счётчик говорит, что запас есть, а слова нашлись
        # только в тексте отчёта (не в ошибке запуска), — не верим словам.
        err_only = " ".join(str(a.get("error") or "") for a in atts[-2:])
        real = (load(PROVIDER_LIMITS_PATH, {}) or {}).get(prov) or {}
        up = real.get("used_percent")
        fresh = time.time() - (real.get("at") or 0) < 10800
        if (isinstance(up, (int, float)) and up < 80 and fresh
                and not LIMIT_SIGNS.search(err_only)):
            continue
        m = RESET_AT.search(text)
        note_limit(conf, prov, text, m.group(1) if m else "")


DASH_PATH = f"{HOME}/pilot/dashboard.json"
_dash_slow = {"at": 0, "data": {}}


def _sh(cmd, timeout=25):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or p.stderr or "").strip()
    except Exception as e:
        return f"ошибка: {e}"


def _repo_dir():
    for root, dirs, _ in os.walk(f"{HOME}/workers"):
        if os.path.basename(root) == "repositories":
            for d in dirs:
                return os.path.join(root, d)
    return ""


def dashboard_slow():
    """Тяжёлая часть: состояние релизов и здоровье стендов. Раз в пять минут."""
    if time.time() - _dash_slow["at"] < 300:
        return _dash_slow["data"]
    out = {}
    # Каталоги стендов пилоту напрямую не видны (и не должны быть) — спрашиваем
    # через того же посредника, что и агенты.
    for key, scope in (("staging", "staging"), ("prod", "prod")):
        info = _sh(f"sudo -n /usr/local/bin/fx {scope} release-info")
        m = re.search(r"current\s*->\s*(\S+)", info)
        if m:
            out[f"{key}_release"] = os.path.basename(m.group(1))
    repo = _repo_dir()
    if repo:
        g = f"git -c safe.directory='*' -C '{repo}'"
        _sh(f"{g} fetch origin --quiet", 40)
        out["main_head"] = _sh(f"{g} rev-parse --short origin/main")[:12]
        out["main_subject"] = _sh(f"{g} log -1 --format=%s origin/main")[:90]
        for key, sha in (("staging", out.get("staging_release", "")),
                         ("prod", out.get("prod_release", ""))):
            if not sha:
                continue
            known = _sh(f"{g} cat-file -e {sha}^{{commit}} && echo yes || echo no").endswith("yes")
            out[f"{key}_commit_known"] = known
            if known:
                # Голый хеш ничего не говорит хозяину. Имя релиза — это дата
                # и что в нём сделано, тем же языком, что у fx factory.
                subj = _sh(f"{g} log -1 --format=%s {sha}")[:80]
                iso = _sh(f"{g} log -1 --format=%cI {sha}")[:16]
                human = ""
                try:
                    M = ["января", "февраля", "марта", "апреля", "мая", "июня",
                         "июля", "августа", "сентября", "октября", "ноября", "декабря"]
                    human = "от %d %s, %s" % (int(iso[8:10]), M[int(iso[5:7]) - 1], iso[11:16])
                except Exception:
                    pass
                out[f"{key}_release_human"] = (human + (" — " + subj if subj else "")).strip()
            out[f"{key}_in_main"] = (
                known and _sh(f"{g} merge-base --is-ancestor {sha} origin/main && echo yes || echo no").endswith("yes"))
    out["staging_health"] = _sh("sudo -n /usr/local/bin/fx staging health")[:60]
    out["prod_health"] = _sh("sudo -n /usr/local/bin/fx prod health")[:60]
    _dash_slow.update({"at": time.time(), "data": out})
    return out


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
                      "state": _verdict(per_core, 0.7, 1.0)}
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


def write_dashboard(conf, tasks, workers):
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
             "wasted_usd": 0.0, "worst": None}
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
        "release": dashboard_slow(),
        "janitor": _sh("tail -1 /var/log/factory-janitor.log 2>/dev/null")[:160],
    }
    save(DASH_PATH, data)


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
        if sick and sick.get("online") and sick.get("health") == "healthy":
            continue                      # просто ждёт очереди — это не беда
        try:
            detail = api(f"/tasks/{t['id']}")
            stage = (detail.get("workflow") or {}).get("title") or ""
            nw = workflows.get(stage)
            if not nw or not nw.get("enabled"):
                continue
            cx = complexity_of(conf, stage, (sick or {}).get("name", "")) or "medium"
            name = stage_worker(conf, stage, cx, workers)
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
            created = create_task(body, conf)
            log(f"QUEUE RESCUE task={t['id'][:8]} {stage} "
                f"{(sick or {}).get('name', '?')} (нездоров) -> {name} "
                f"new={created.get('task', {}).get('id', '?')[:8]}")
        except Exception as e:
            log("queue_rescue_error", repr(e))


def stage_worker(conf, stage_name, complexity, workers=None):
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
        return bool(w and w.get("online") and w.get("health") == "healthy")

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
    for name in ordered:
        if name and healthy(name):
            return name
    # Последний резерв — только внутри нашей же конфигурации и от ДЕШЁВЫХ к дорогим,
    # иначе подмена больного воркера сама по себе разоряет (fable/opus в 5 раз дороже).
    pool = []
    for s in conf["stages"]:
        t = s.get("workers")
        pool += (list(t.values()) if isinstance(t, dict) else [s.get("worker")])
    for name in sorted({n for n in pool if n}, key=worker_price_rank):
        if healthy(name):
            log(f"stage_worker: {stage_name}/{complexity} -> подменён на здорового {name}")
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


def cycle(conf, state):
    stages = [s["workflow"] for s in conf["stages"]]

    tasks = api("/tasks?limit=100").get("tasks") or []
    workers = best_workers(api("/workers")["workers"])
    repo_identity_by_id = {r["id"]: r["remote_identity"]
                           for r in (api("/repositories").get("repositories") or [])}
    workflows = {}
    for w in api("/workflows").get("workflows") or []:
        rev = w.get("current_revision") or {}
        workflows[rev.get("title")] = {"workflow_id": w["id"], "revision_id": rev.get("id"),
                                       "enabled": w.get("enabled")}

    # Снимок для главного экрана. Никогда не должен ломать цикл.
    try:
        write_dashboard(conf, tasks, {w["id"]: w for w in api("/workers")["workers"]})
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
        if day_budget_blocks(conf, tasks):
            return
    except Exception as e:
        log("day_cap_error", repr(e))

    # Перегруженный сервер: начатое доигрывается, новое не берётся. Иначе
    # мы просто замедляем всё сразу и получаем таймауты вместо результата.
    try:
        if host_overloaded(conf, workers):
            hb = host_block(workers)
            log(f"HOST BUSY: процессор {hb.get('cpu', {}).get('percent')}%, "
                f"память {hb.get('memory', {}).get('percent')}%, "
                f"диск {hb.get('disk', {}).get('percent')}% — новую работу не беру")
            return
    except Exception as e:
        log("host_load_error", repr(e))

    # Сторож конвейера: молча умерших работ быть не должно.
    try:
        pipeline_watch(conf, tasks, workflows, workers)
    except Exception as e:
        log("watch_error", repr(e))

    # Planner layer runs first, guarded so it can never break the pipeline.
    try:
        handle_epics(conf, state, tasks, workflows, workers, repo_identity_by_id)
    except Exception as e:
        log("epic_error", repr(e))

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

    # Owner answers resume stopped pipelines.
    try:
        handle_answers(conf, workflows, workers, tasks)
    except Exception as e:
        log("answer_error", repr(e))

    # Sequential epics: start the next subtask once the current one is finished.
    try:
        advance_epics(conf, tasks, workflows, workers)
    except Exception as e:
        log("epic_advance_error", repr(e))

    for t in tasks:
        tid, title, tstate = t["id"], t.get("title", ""), t.get("state")
        if not title.startswith(PREFIX):
            continue
        if tid in state["processed"]:
            continue
        if tstate not in ("succeeded", "failed", "cancelled"):
            continue

        detail = api(f"/tasks/{tid}")
        wf = (detail.get("workflow") or {}).get("title")
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
            newer = live_or_done_at(tasks, base, stage_no_of(title), since=t.get("created_at"))
            if newer and newer["id"] != tid:
                log(f"stage_ended state={tstate} task={tid} stage={wf} "
                    f"— перекрыта задачей {newer['id'][:8]}, вопрос не создаю")
                continue
            done = stage_attempts(tasks, wf, base)
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
                           attempts_so_far=done)
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
            collect_ideas(result, detail["task"].get("repository_id") or "",
                          base_title(title))
        except Exception as e:
            log("ideas_error", repr(e))
        if wf == "Specification":
            try:
                save_promises(base_title(title), result)
            except Exception as e:
                log("promises_error", repr(e))
        verdict = decide(conf, wf, next_stage, title, result,
                         detail["task"].get("repository_id") or "")
        log(f"decision task={tid} stage={wf} action={verdict['action']} reason={verdict.get('reason','')}")
        if verdict.get("verdict_ru"):
            try:
                os.makedirs(VERDICT_DIR, exist_ok=True)
                rec = {"task_id": tid, "stage": wf,
                       "verdict": verdict["verdict_ru"],
                       "action": verdict["action"]}
                # Ссылка живёт рядом с итогом: экран показывает её только там,
                # где написано «сделано».
                seen = try_url(result, detail["task"].get("repository_id") or "")
                if seen and any(u in seen for u in TRY_USELESS):
                    seen = ""     # страница «ok» — не дверь к результату
                if seen:
                    rec["try_url"] = seen
                pf = proof_of(result)
                if pf:
                    rec["proof"] = pf
                save(f"{VERDICT_DIR}/{tid}.json", rec)
            except Exception as e:
                log("verdict_save_error", repr(e))

        if not next_stage:
            # end of pipeline (Verify): auto-merge on PASS, then optional staging deploy
            if conf.get("auto_merge", True) and verify_passed(result):
                mark_final(tid, wf, True)
                branch = extract_branch(result, detail.get("context", ""))
                rid = detail["task"].get("repository_id") or detail.get("repository", {}).get("id", "")
                repo_identity = repo_identity_by_id.get(rid, "")
                if branch and repo_identity:
                    # Замок: если ветка уже в main (второй PASS той же работы),
                    # второй PR не открываем — «Обзор» так влился дважды.
                    repo_short = repo_identity.split("github.com/")[-1]
                    cmp_ = gh_json(["api", f"repos/{repo_short}/compare/main...{branch}"])
                    if cmp_ is not None and cmp_.get("ahead_by") == 0:
                        log(f"MERGE SKIP '{base_title(title)}': ветка {branch} уже в main — дубль не открываю")
                        continue
                    ok, out = gh_merge(repo_identity, branch, base_title(title))
                    log(f"AUTO-MERGE pipeline='{base_title(title)}' branch={branch} ok={ok} :: {out[:200]}")
                    if ok:
                        # Хозяину не нужно знать про main — это кухня. Ему нужно:
                        # задача выполнена, и вот дверь, где потрогать результат.
                        link = try_url(result, rid)
                        if link and any(u in link for u in TRY_USELESS):
                            link = ""
                        pf = proof_of(result)
                        if link:
                            body_txt = "\nПосмотреть: " + link
                        elif pf:
                            body_txt = "\nРезультат не визуальный. Проверено: " + pf
                        else:
                            body_txt = "\nСсылку или доказательство стадия не назвала — открой карточку."
                        notify(conf, "Задача выполнена", base_title(title) + body_txt,
                               tags="white_check_mark",
                               click=link or f"{UI_BASE}/tasks/{tid}")
                    else:
                        # Конфликт слияния — рабочий случай, а не тупик: пока эта
                        # работа шла, в main влилась соседняя. Возвращаем в
                        # разработку с прямым наказом перебазироваться. Один раз:
                        # если и после этого не влилось — зовём хозяина.
                        if "conflict" in out.lower() and cap_rescues(base_title(title), "MERGE") < 1:
                            note_cap_rescue(base_title(title), "MERGE")
                            try:
                                stages_all = [x["workflow"] for x in conf["stages"]]
                                back_st = "Implement + Test" if "Implement + Test" in stages_all else wf
                                bidx = stages_all.index(back_st)
                                bw = workers.get(stage_worker(conf, back_st, "medium", workers))
                                bnw = workflows.get(back_st)
                                if bw and bnw and bnw.get("enabled"):
                                    create_task({"request_key": str(uuid.uuid4()),
                                        "title": f"[auto] [{bidx+1}/{len(stages_all)} {back_st}] {base_title(title)}"[:200],
                                        "context": (f"Pipeline: {base_title(title)}\nBranch: {branch}\n\n"
                                            "Проверка прошла, но ветка НЕ влилась в main: конфликт слияния — "
                                            "пока работа шла, main уехал вперёд. ВЕТКУ НЕ ПЕРЕКЛЮЧАЙ, "
                                            "оставайся на своей. Сделай ровно это: "
                                            f"git fetch origin {branch} && git reset --hard FETCH_HEAD; "
                                            "git rebase origin/main; разреши конфликты, сохранив и свою "
                                            "работу, и то, что уже в main; git push -u origin HEAD; "
                                            "больше ничего не меняй.")[:20000],
                                        "worker_id": bw["id"], "repository_id": rid,
                                        "timeout_seconds": conf.get("timeout_seconds", 7200),
                                        "workflow_revision_id": bnw["revision_id"]}, conf)
                                    notify(conf, "Мёрж-конфликт: отправил на перебазирование",
                                           base_title(title), tags="wrench")
                                else:
                                    raise RuntimeError("нет воркера/сценария")
                            except Exception as e:
                                log("merge_conflict_return_error", repr(e))
                                notify(conf, "Verify PASS, но мёрж не прошёл", f"{base_title(title)}\n{cut(out)}",
                                       priority="high", tags="warning", click=f"{UI_BASE}/tasks/{tid}")
                        else:
                            notify(conf, "Verify PASS, но мёрж не прошёл", f"{base_title(title)}\n{cut(out)}",
                                   priority="high", tags="warning", click=f"{UI_BASE}/tasks/{tid}")
                    cmd = conf.get("deploy_staging_cmd")
                    if ok and cmd:
                        rc, dout = run_shell(cmd)
                        log(f"STAGING-DEPLOY rc={rc} :: {dout[:200]}")
                    elif ok:
                        log("merged to main; no deploy_staging_cmd set -> production deploy is a human one-tap")
                else:
                    log(f"auto-merge skipped: missing branch/repo (branch={branch!r}, repo={repo_identity!r})")
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
                    squeeze(result), attempts_so_far=stage_attempts(tasks, back, base),
                    branch=extract_branch(result, detail.get("context", "")))
                if escalated:
                    notify(conf, "Проверка не прошла, нужен ты",
                           f"{base_title(title)}\nПроверка не подтвердила результат, "
                           "в main ничего не влито, и сам я это не решаю.",
                           priority="high", tags="warning", click=f"{UI_BASE}/tasks/{tid}")
            continue
        if verdict["action"] != "advance":
            base = base_title(title)
            rid = detail["task"].get("repository_id") or ""
            situation = verdict.get("situation_ru") or ""
            question = verdict.get("question_ru") or ""
            back = resume_stage_for(stages, wf, next_stage)
            route_question(conf, tid, wf, back, base, rid,
                           situation or verdict.get("reason", ""),
                           question or "Что делать дальше?",
                           verdict.get("options_ru") or [], result,
                           attempts_so_far=stage_attempts(tasks, back, base),
                           branch=extract_branch(result, detail.get("context", "")))
            continue

        # Замок: не запускаем этап, если тот же файл уже правит другая работа.
        holder = area_busy(tasks, base_title(title), detail.get("context", ""),
                           (detail.get("task") or {}).get("repository_id", ""))
        if holder:
            log(f"AREA WAIT {base_title(title)!r} ждёт: тот же файл правит {holder!r}")
            if tid in state["processed"]:
                state["processed"].remove(tid)
            continue
        nw = workflows.get(next_stage)
        complexity = verdict.get("next_complexity", "medium")
        if complexity not in ("low", "medium", "high"):
            complexity = "medium"
        worker_name = stage_worker(conf, next_stage, complexity, workers)
        worker = workers.get(worker_name)
        if not nw or not nw.get("enabled") or not worker:
            if tid in state["processed"]:
                state["processed"].remove(tid)
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
        dup = live_or_done_at(tasks, base, idx + 2, since=t.get("created_at"))
        if dup:
            log(f"skip: '{base}' уже имеет задачу на стадии {next_stage} или дальше "
                f"({dup['id'][:8]} {dup.get('state')})")
            continue

        handoff = verdict.get("handoff", "")
        branch = extract_branch(result, detail.get("context", ""))
        branch_line = f"Branch: {branch}\n" if branch else ""

        # Ворота Спецификации: без машинно проверяемых обещаний дальше нельзя.
        if (wf == "Specification" and not PROMISE_LINE.search(result or "")
                and cap_rescues(base, "SPEC") < 1):
            note_cap_rescue(base, "SPEC")
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
                create_task({"request_key": str(uuid.uuid4()), "title": back_title,
                             "context": spec_ctx[:20000],
                             "worker_id": worker["id"],
                             "repository_id": detail["task"].get("repository_id") or "",
                             "timeout_seconds": conf.get("timeout_seconds", 7200),
                             "workflow_revision_id": workflows.get(wf, {}).get("revision_id")
                                 or nw["revision_id"]}, conf)
                log(f"SPEC GATE {base[:40]!r}: нет ГОТОВО-КОГДА — вернул дописать обещания")
                notify(conf, "Вернул сам: спецификация без обещаний",
                       base + chr(10) + "Спецификация не назвала проверяемые признаки "
                       "готовности (ГОТОВО-КОГДА) — вернул дописать. Твоего участия не нужно.",
                       tags="wrench", click=f"{UI_BASE}/work")
                continue
            except Exception as e:
                log("spec_gate_error", repr(e))

        # Ворота: дешёвая машинная проверка вместо дорогого круга Ревью.
        gate_note = ""
        if next_stage == "Review" and branch:
            rid_g = detail["task"].get("repository_id") or ""
            g = review_gate(conf, base, branch, repo_identity_by_id.get(rid_g, ""))
            if g and g["back"]:
                back_title = f"[auto] [{idx + 1}/{len(stages)} {wf}] {base}"[:200]
                try:
                    created_g = create_task({"request_key": str(uuid.uuid4()), "title": back_title,
                                 "context": (f"Pipeline: {base}\nPrevious stage: {wf}\n"
                                             f"Branch: {branch}\n\n" + g["note"])[:20000],
                                 "worker_id": worker["id"],
                                 "repository_id": rid_g,
                                 "timeout_seconds": conf.get("timeout_seconds", 7200),
                                 "workflow_revision_id": workflows.get(wf, {}).get("revision_id")
                                     or nw["revision_id"]}, conf)
                    new_tid = (created_g.get("task") or {}).get("id", "") if isinstance(created_g, dict) else ""
                    notify(conf, g.get("alert") or "Вернул сам: поставка не прошла машинную проверку",
                           base + chr(10) + (g.get("alert_msg") or ""),
                           tags="wrench",
                           click=(f"{UI_BASE}/tasks/{new_tid}" if new_tid else f"{UI_BASE}/work"))
                    continue
                except Exception as e:
                    log("gate_return_error", repr(e))
            elif g:
                gate_note = "\n\n" + g["note"]

        context = (f"Pipeline: {base}\nPrevious stage: {wf}\n{branch_line}"
                   f"Orchestrator handoff: {handoff}\n\n"
                   f"Отчёт предыдущей стадии (сокращён):\n{squeeze(result)}"
                   + gate_note)[:20000]
        body = {
            "request_key": str(uuid.uuid4()),
            "title": next_title,
            "context": context,
            "worker_id": worker["id"],
            "repository_id": detail["task"].get("repository_id") or detail.get("repository", {}).get("id", ""),
            "timeout_seconds": conf.get("timeout_seconds", 7200),
            "workflow_revision_id": nw["revision_id"],
        }
        try:
            created = create_task(body, conf)
        except Exception as e:
            # do NOT swallow this task: drop it from 'processed' so the next
            # cycle tries again once a healthy worker is back.
            if tid in state["processed"]:
                state["processed"].remove(tid)
            log(f"cannot advance '{base}' {wf} -> {next_stage} (повторю позже): {e}")
            continue
        log(f"advanced pipeline='{title}' {wf} -> {next_stage} complexity={complexity} "
            f"worker={worker_name} branch={branch or '-'} "
            f"new_task={created.get('task', {}).get('id')}")


def main():
    log("factory-pilot started")
    while True:
        conf = load(CONF_PATH, None)
        state = load(STATE_PATH, {"processed": []})
        if conf and conf.get("enabled", True):
            try:
                cycle(conf, state)
            except Exception as e:
                log("cycle_error", repr(e))
            state["processed"] = state["processed"][-2000:]
            state["epics_processed"] = state.get("epics_processed", [])[-2000:]
            state["epic_starts_processed"] = state.get("epic_starts_processed", [])[-2000:]
            save(STATE_PATH, state)
        time.sleep(conf.get("poll_seconds", 30) if conf else 60)


if __name__ == "__main__":
    main()
