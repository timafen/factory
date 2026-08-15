#!/usr/bin/env python3
"""Экран «План»: предложения и находки, привязанные к проектам.

Ничто найденное по пути не теряется. Исполнитель пишет в отчёте строку
«ПРЕДЛОЖЕНИЕ: ...» или «НАХОДКА: ...» — пилот заводит карточку. Владелец
и помощник вручную заводят только предложения и видят тот же общий список.
"""
import html
import os
import sys
import uuid

sys.path.insert(0, "/opt/factory-data/pilot")
import pilot  # noqa: E402

from fastapi import APIRouter, Form, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402

router = APIRouter()

KIND_RU = {"idea": "Предложение", "finding": "Находка"}
STATE_RU = {"new": "новое", "planned": "в плане", "in_work": "в работе",
            "done": "сделано", "rejected": "отклонено"}
STATE_ORDER = {"in_work": 0, "planned": 1, "new": 2, "done": 3, "rejected": 4}
ORIGIN_RU = {"owner": "хозяин", "assistant": "помощник", "agent": "агент",
             "orchestrator": "фабрика"}


def repos_map():
    out = {}
    try:
        for r in (pilot.api("/repositories").get("repositories") or []):
            out[r["id"]] = r.get("remote_identity") or r.get("name") or r["id"][:8]
    except Exception:
        pass
    return out


def repo_name(rid, rmap):
    if not rid:
        return "без проекта"
    return rmap.get(rid) or ("проект " + rid[:8])


# ------------------------------------------------------------------ JSON ---

@router.get("/ideas")
def ideas_json(repo: str = "", state: str = "", kind: str = ""):
    rmap = repos_map()
    items = []
    for it in pilot.ideas_all():
        if repo and it.get("repo") != repo:
            continue
        if state and it.get("state") != state:
            continue
        if kind and it.get("kind") != kind:
            continue
        d = dict(it)
        d["repo_name"] = repo_name(it.get("repo"), rmap)
        d["state_ru"] = STATE_RU.get(it.get("state"), it.get("state"))
        items.append(d)
    items.sort(key=lambda i: (STATE_ORDER.get(i.get("state"), 9),
                              int(i.get("order") or 0)))
    return {"ideas": items, "repositories": [{"id": k, "name": v}
                                             for k, v in rmap.items()]}


@router.post("/ideas")
def ideas_add(title: str = Form(...), why: str = Form(""), repo: str = Form(""),
              kind: str = Form("idea"), origin: str = Form("owner"),
              state: str = Form("new")):
    rec = pilot.add_idea(kind, title, repo, why, origin=origin, state=state)
    if not rec:
        raise HTTPException(400, "пустой заголовок")
    return rec


# --------------------------------------------------------------- действия ---

def _promote(rec):
    """Заводит задачу из карточки — тем же путём, что и голосовая задача."""
    conf = pilot.load(pilot.CONF_PATH, None)
    if not conf:
        raise HTTPException(500, "нет конфигурации пилота")
    workers = pilot.best_workers(pilot.api("/workers")["workers"])
    workflows = {}
    for w in pilot.api("/workflows").get("workflows") or []:
        rev = w.get("current_revision") or {}
        workflows[rev.get("title")] = {"revision_id": rev.get("id"),
                                       "enabled": w.get("enabled")}
    stage_name, nstages = pilot.first_stage(conf)
    nw = workflows.get(stage_name)
    if not nw or not nw.get("enabled"):
        raise HTTPException(500, "у первого этапа нет включённого сценария")
    worker = workers.get(pilot.stage_worker(conf, stage_name, "medium"))
    if not worker:
        raise HTTPException(500, "нет свободного исполнителя для первого этапа")
    generation_rec = pilot.plan_idea(rec["id"])
    if not generation_rec:
        raise HTTPException(404, "карточка не найдена")
    generation = generation_rec.get("run_generation") or str(uuid.uuid4())
    title = f"[auto] [1/{nstages} {stage_name}] {rec['title']}"[:200]
    why = rec.get("why") or ""
    src = rec.get("source") or ""
    context = (f"Задача выросла из карточки плана ({KIND_RU.get(rec.get('kind'), '')}).\n\n"
               f"Что сделать: {rec['title']}\n\n"
               f"Зачем: {why or 'не записано'}\n\n"
               + (f"Откуда взялось: работа «{src}».\n\n" if src else "")
               + "Ты первый этап конвейера; следующие этапы продолжат на той ветке, "
                 "которую ты (или Implement) запушишь.")[:60000]
    r = pilot.create_task({"request_key": str(uuid.uuid4()), "title": title,
                           "context": context, "worker_id": worker["id"],
                           "repository_id": rec.get("repo") or "",
                           "timeout_seconds": conf.get("timeout_seconds", 7200),
                           "workflow_revision_id": nw["revision_id"]})
    tid = r.get("task", {}).get("id")
    pilot.note_work(rec["title"], pilot.ORIGIN_OWNER, stage_name)
    pilot.set_idea(rec["id"], state="in_work", task_id=tid or "",
                   run_generation=generation)
    return tid


@router.post("/ideas/{idea_id}")
def idea_action(idea_id: str, action: str = Form(...), reason: str = Form(""),
                back: str = Form("")):
    rec = next((i for i in pilot.ideas_all() if i.get("id") == idea_id), None)
    if not rec:
        raise HTTPException(404, "карточка не найдена")
    if action == "plan":
        pilot.plan_idea(idea_id)
    elif action == "new":
        pilot.set_idea(idea_id, state="new", reason="")
    elif action == "done":
        close_reason = reason or "Владелец явно закрыл карточку Плана."
        pilot.set_idea(idea_id, state="done", reason=close_reason)
        pilot.close_work(rec.get("title", ""), close_reason)
    elif action == "reject":
        close_reason = reason or "Владелец отклонил карточку; причина не указана."
        pilot.set_idea(idea_id, state="rejected", reason=close_reason)
        pilot.close_work(rec.get("title", ""), close_reason)
    elif action == "up":
        _move(idea_id, -1)
    elif action == "down":
        _move(idea_id, +1)
    elif action == "task":
        _promote(rec)
    else:
        raise HTTPException(400, "неизвестное действие")
    if back:
        return RedirectResponse(back, status_code=303)
    return {"ok": True}


def _move(idea_id, delta):
    items = sorted(pilot.ideas_all(), key=lambda i: int(i.get("order") or 0))
    me = next((i for i in items if i.get("id") == idea_id), None)
    if not me:
        return
    peers = [i for i in items
             if i.get("repo") == me.get("repo") and i.get("state") == me.get("state")]
    idx = peers.index(me)
    j = idx + delta
    if j < 0 or j >= len(peers):
        return
    other = peers[j]
    a, b = int(me.get("order") or 0), int(other.get("order") or 0)
    pilot.set_idea(me["id"], order=b)
    pilot.set_idea(other["id"], order=a)


# ------------------------------------------------------------------ экран ---

CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0a0c11;color:#e8ecf4;
 font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 padding:12px 12px 64px}
h1{font-size:19px;margin:6px 0 2px}
.sub{color:#8b95a8;font-size:13px;margin:0 0 14px}
h2{font-size:15px;margin:22px 0 8px;color:#9fb4d8;
 border-bottom:1px solid #1e2532;padding-bottom:6px}
.card{background:#121722;border:1px solid #1e2532;border-radius:12px;
 padding:11px 12px;margin:8px 0}
.card.done,.card.rejected{opacity:.55}
.t{font-weight:600;margin:0 0 4px}
.why{color:#a8b3c7;font-size:13.5px;margin:0 0 8px;white-space:pre-wrap}
.why-disclosure{background:transparent;border:0;border-radius:0;padding:0;margin:7px 0 9px}
.why-disclosure summary{min-height:36px;display:flex;align-items:center;font-size:13px}
.why-disclosure .why{margin:5px 0 0;overflow-wrap:anywhere}
.meta{color:#7b8699;font-size:12px;margin:0 0 9px}
.badge{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11.5px;
 margin-right:6px;border:1px solid #2a3346;background:#182031;color:#9fb4d8}
.b-finding{background:#2a2119;border-color:#4a3820;color:#e0b877}
.b-in_work{background:#12291c;border-color:#245c39;color:#79d69b}
.b-planned{background:#171f33;border-color:#2c3c63;color:#8fabe6}
.b-rejected{background:#2a1717;border-color:#5c2424;color:#e08b8b}
form.row{display:inline}
button{background:#1b2333;color:#cfe0ff;border:1px solid #2c3648;border-radius:9px;
 padding:7px 11px;font-size:13px;margin:0 5px 5px 0;cursor:pointer}
button.p{background:#1d3a5c;border-color:#2f5c8f;color:#dbeaff}
button.d{background:#2c1c1c;border-color:#5c2c2c;color:#ffd7d7}
input,select,textarea{width:100%;background:#0f141d;color:#e8ecf4;
 border:1px solid #263047;border-radius:9px;padding:9px;font-size:14px;
 margin:0 0 8px;font-family:inherit}
textarea{min-height:64px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.tabs a{text-decoration:none;font-size:13px;padding:6px 11px;border-radius:20px;
 background:#131a26;color:#9aa7bd;border:1px solid #202939}
.tabs a.on{background:#1d3a5c;color:#dbeaff;border-color:#2f5c8f}
details{background:#121722;border:1px solid #1e2532;border-radius:12px;
 padding:10px 12px;margin:18px 0 0}
summary{cursor:pointer;color:#9fb4d8;font-size:14px}
.alert-group{margin:10px 0;padding:0;overflow:hidden}
.alert-group>summary{display:flex;align-items:center;gap:8px;min-height:44px;padding:10px 12px}
.alert-group>summary .freshness{margin-left:auto;color:#7b8699;font-size:12px;text-align:right}
.alert-group .card{margin:0;border-width:1px 0 0;border-radius:0}
.card,.meta,.t,.sub,summary{overflow-wrap:anywhere}
.empty{color:#7b8699;font-size:13.5px;padding:10px 2px}
a.back{color:#8fabe6;text-decoration:none;font-size:13px}
@media(max-width:480px){
 body{padding-left:10px;padding-right:10px}
 .tabs{gap:5px}.tabs a{padding:8px 10px}
 button{min-height:40px}.alert-group>summary{align-items:flex-start;flex-wrap:wrap}
 .alert-group>summary .freshness{width:100%;margin-left:0;text-align:left}
}
"""

HELP = ("Здесь ничего не теряется: предложения добавляешь ты или помощник, "
        "а находки создают исполнители, когда выясняют что-то по ходу работы. "
        "Каждая карточка "
        "привязана к проекту. «В план» — беру в работу позже, «Завести задачу» — "
        "фабрика начинает делать прямо сейчас, «Отклонить» — с причиной, "
        "чтобы через месяц не гадать, почему отказались.")


def esc(x):
    return html.escape(str(x or ""))


def _btn(iid, action, label, cls="", back="", extra=""):
    return (f'<form class="row" method="post" action="ideas/{esc(iid)}">'
            f'<input type="hidden" name="action" value="{action}">'
            f'<input type="hidden" name="back" value="{esc(back)}">'
            f'{extra}<button class="{cls}">{label}</button></form>')


def card_html(it, back):
    st = it.get("state") or "new"
    kind = it.get("kind") or "idea"
    iid = it.get("id")
    bits = [f'<div class="card {st}">']
    bits.append(f'<span class="badge {"b-finding" if kind == "finding" else ""}">'
                f'{KIND_RU.get(kind, kind)}</span>'
                f'<span class="badge b-{st}">{STATE_RU.get(st, st)}</span>')
    bits.append(f'<div class="t">{esc(it.get("title"))}</div>')
    if it.get("why"):
        bits.append('<details class="why-disclosure"><summary>Показать обоснование</summary>'
                    f'<div class="why">{esc(it["why"])}</div></details>')
    meta = f'завёл: {ORIGIN_RU.get(it.get("origin"), it.get("origin"))} · {esc(it.get("created"))}'
    if it.get("source"):
        meta += f' · из работы «{esc(it["source"])}»'
    if it.get("reason"):
        meta += f' · причина отказа: {esc(it["reason"])}'
    if it.get("task_id"):
        meta += (f' · <a class="back" href="/tasks/{esc(it["task_id"])}">'
                 f'открыть задачу</a>')
    bits.append(f'<div class="meta">{meta}</div>')
    if st not in ("done", "rejected"):
        if st != "planned":
            bits.append(_btn(iid, "plan", "В план", back=back))
        if st != "in_work":
            bits.append(_btn(iid, "task", "Завести задачу", "p", back=back))
        bits.append(_btn(iid, "done", "Сделано", back=back))
        bits.append(_btn(iid, "reject", "Отклонить", "d", back=back,
                         extra='<input type="hidden" name="reason" '
                               'value="хозяин отклонил на экране «План»">'))
        if st == "planned":
            bits.append(_btn(iid, "up", "&#8593;", back=back))
            bits.append(_btn(iid, "down", "&#8595;", back=back))
    else:
        bits.append(_btn(iid, "new", "Вернуть в список", back=back))
    bits.append("</div>")
    return "".join(bits)


@router.get("/plan", response_class=HTMLResponse)
def plan_page(repo: str = "", show: str = "open"):
    rmap = repos_map()
    all_items = pilot.ideas_all()
    back = f"/intake/plan?repo={repo}&show={show}"

    items = [i for i in all_items if not repo or i.get("repo") == repo]
    if show == "open":
        items = [i for i in items if i.get("state") not in ("done", "rejected")]
    elif show in ("done", "rejected"):
        items = [i for i in items if i.get("state") == show]

    items.sort(key=lambda i: (STATE_ORDER.get(i.get("state"), 9),
                              int(i.get("order") or 0)))

    used = []
    for i in all_items:
        if i.get("repo") not in used:
            used.append(i.get("repo"))

    tabs = ['<div class="tabs">']
    tabs.append(f'<a class="{"on" if not repo else ""}" href="plan?show={show}">'
                f'Все проекты</a>')
    for rid in used:
        tabs.append(f'<a class="{"on" if repo == rid else ""}" '
                    f'href="plan?repo={esc(rid)}&show={show}">{esc(repo_name(rid, rmap))}</a>')
    tabs.append('</div><div class="tabs">')
    for key, lab in (("open", "В работе и в плане"), ("all", "Всё"),
                     ("done", "Сделанное"), ("rejected", "Отклонённое")):
        tabs.append(f'<a class="{"on" if show == key else ""}" '
                    f'href="plan?repo={esc(repo)}&show={key}">{lab}</a>')
    tabs.append("</div>")

    body = []
    groups = {}
    for it in items:
        groups.setdefault(it.get("repo") or "", []).append(it)
    if not groups:
        body.append('<div class="empty">Пока пусто. Карточки появятся сами, '
                    'когда исполнитель напишет в отчёте «ПРЕДЛОЖЕНИЕ: ...» или '
                    '«НАХОДКА: ...», либо добавь предложение вручную внизу.</div>')
    for rid, lst in groups.items():
        body.append(f"<h2>{esc(repo_name(rid, rmap))} · {len(lst)}</h2>")
        for it in lst:
            body.append(card_html(it, back))

    opts = ['<option value="">без проекта</option>']
    for rid, nm in rmap.items():
        sel = " selected" if rid == repo else ""
        opts.append(f'<option value="{esc(rid)}"{sel}>{esc(nm)}</option>')

    add = (f'<details><summary>Добавить карточку вручную</summary>'
           f'<form method="post" action="plan/add">'
           f'<input type="hidden" name="back" value="{esc(back)}">'
           f'<input name="title" placeholder="Что предлагаешь" required>'
           f'<textarea name="why" placeholder="Зачем это нужно"></textarea>'
           f'<select name="repo">{"".join(opts)}</select>'
           f'<input type="hidden" name="kind" value="idea">'
           f'<button class="p">Добавить</button></form></details>')

    return HTMLResponse(
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>План</title><style>{CSS}</style></head><body>"
        f'<a class="back" href="/work">&#8592; к работам</a>'
        f"<h1>План</h1><p class=sub>{HELP}</p>"
        + "".join(tabs) + "".join(body) + add +
        "</body></html>")


@router.post("/plan/add")
def plan_add(title: str = Form(...), why: str = Form(""), repo: str = Form(""),
             kind: str = Form("idea"), back: str = Form("/intake/plan")):
    pilot.add_idea(kind, title, repo, why, origin="owner")
    return RedirectResponse(back, status_code=303)


# ------------------------------------------------------------- уведомления ---

GROUP_RU = {"questions": "вопрос ко мне", "stuck": "работа встала",
            "money": "деньги и лимиты", "done": "завершения и запуски",
            "escalate": "исполнитель повышен", "routine": "рутина"}


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(group: str = "", n: int = 30):
    import json as _json
    path = os.environ.get(
        "FACTORY_INTAKE_NOTIFICATIONS_PATH",
        "/opt/factory-data/pilot/notifications.jsonl",
    )
    items = []
    try:
        with open(path, encoding="utf-8") as stream:
            lines = stream.readlines()[-800:]
        for line in lines:
            try:
                items.append(_json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    items.reverse()
    if group:
        items = [i for i in items if i.get("group") == group]
    items = items[:max(1, min(n, 30))]

    tabs = ['<div class="tabs">',
            f'<a class="{"on" if not group else ""}" href="alerts">Все</a>']
    for k, v in GROUP_RU.items():
        tabs.append(f'<a class="{"on" if group == k else ""}" href="alerts?group={k}">{v}</a>')
    tabs.append("</div>")

    grouped = {}
    for i in items:
        grouped.setdefault(i.get("group") or "routine", []).append(i)

    body = []
    for group_key, group_items in grouped.items():
        group_name = GROUP_RU.get(group_key, group_key)
        latest = group_items[0].get("at") or "время не указано"
        body.append(
            f'<details class="alert-group"{" open" if group else ""}>'
            f'<summary><span>{esc(group_name)} · {len(group_items)}</span>'
            f'<span class="freshness">последнее: {esc(latest)}</span></summary>')
        for i in group_items:
            quiet = "" if i.get("delivered") else " (тихое: группа выключена)"
            click = i.get("click") or ""
            link = (f'<a class="back" href="{esc(click)}">открыть</a>' if click else "")
            body.append(
                f'<div class="card{"" if i.get("delivered") else " done"}">'
                f'<div class="t">{esc(i.get("title"))}</div>'
                f'<div class="why">{esc(i.get("message"))}</div>'
                f'<div class="meta">{esc(i.get("at"))} · {esc(group_name)}'
                f'{quiet} {link}</div></div>')
        body.append('</details>')
    if not body:
        body.append('<div class="empty">Уведомлений пока нет.</div>')

    return HTMLResponse(
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Уведомления</title><style>{CSS}</style></head><body>"
        '<a class="back" href="/work">&#8592; к работам</a>'
        "<h1>Уведомления</h1><p class=sub>Всё, что фабрика присылала на телефон, "
        "и тихие события из выключенных групп. Настройка групп — на экране "
        "«Настройки».</p>"
        + "".join(tabs) + "".join(body) + "</body></html>")
