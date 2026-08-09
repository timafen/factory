#!/usr/bin/env python3
"""factory-intake: voice front door for the Factory.

Flow (all behind the Factory nginx + basic auth, on 127.0.0.1:7338):
  POST /transcribe  audio (webm/opus/wav) -> {"text": "<ru transcription>"}
  POST /dispatch    {"text": ...}         -> Fable classifies into a proposal:
                                             one task, or an epic (N subtasks).
  POST /commit      {"proposal": ...}     -> creates the task, or writes the
                                             epic and fans it out. Returns ids.

The 'brain' (Fable) and routing reuse the pilot's tested helpers, so the model
tiers per stage are identical to the automatic pipeline. Human confirms between
/dispatch and /commit (the UI enforces this).
"""
import json, os, re, subprocess, sys, tempfile, time, uuid

sys.path.insert(0, "/opt/factory-data/pilot")
import pilot  # noqa: E402  (load, api, stage_worker, first_stage, write_epic, start_epic, EPIC_DIR)

from fastapi import FastAPI, UploadFile, File, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

HOME = "/opt/factory-data"
MODEL_DIR = f"{HOME}/intake/models"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
BEAM = int(os.environ.get("WHISPER_BEAM", "1"))
DISPATCH_MODEL = os.environ.get("INTAKE_MODEL", "fable")

app = FastAPI(title="factory-intake")
_model = None


def model():
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8",
                              download_root=MODEL_DIR, cpu_threads=os.cpu_count() or 4)
    return _model


def api(path, body=None):
    return pilot.api(path, body)


# --------------------------------------------------------------- transcribe ---

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    if not data:
        raise HTTPException(400, "empty audio")
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        segments, info = model().transcribe(path, language="ru", vad_filter=True,
                                            beam_size=BEAM, condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "duration": round(getattr(info, "duration", 0.0), 2)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ----------------------------------------------------------------- dispatch ---

class DispatchIn(BaseModel):
    text: str
    proposal: dict | None = None  # set when refining an existing plan by voice
    intent: str = ""              # "edit" | "ask" - explicit, no guessing


def repos_list():
    return [{"id": r["id"], "identity": r.get("remote_identity", "")}
            for r in (api("/repositories").get("repositories") or [])]


def parse_json_block(text):
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = list(blocks) or ([text[text.find("{"):text.rfind("}") + 1]]
                             if "{" in text and "}" in text else [])
    for raw in reversed(cands):
        try:
            return json.loads(raw)
        except Exception:
            continue
    return None


def fable(prompt, timeout=180):
    """Раньше здесь был жёстко зашитый Клод. Теперь та же цепочка движков,
    что и у пилота: кончилась одна подписка — отвечает следующая."""
    conf = pilot.load(pilot.CONF_PATH, {})
    text, eng = pilot.brain(conf, prompt, timeout=timeout)
    if not text:
        raise RuntimeError("ни один движок не ответил")
    return text


@app.post("/dispatch")
def dispatch(inp: DispatchIn):
    text = (inp.text or "").strip()
    if not text:
        raise HTTPException(400, "empty text")
    if inp.proposal:
        return refine(text, inp.proposal, inp.intent)
    repos = repos_list()
    repo_lines = "\n".join(f'- id={r["id"]} :: {r["identity"]}' for r in repos) or "(none)"
    default_repo = next((r["id"] for r in repos
                         if "tarser-operations" in r["identity"]), repos[0]["id"] if repos else "")
    prompt = (
        "You are the intake dispatcher of a software factory. The owner just spoke a "
        "request (transcribed, Russian or English). Decide how to route it.\n\n"
        f"Spoken request:\n---\n{text}\n---\n\n"
        f"Available repositories (pick the most relevant id; default {default_repo}):\n"
        f"{repo_lines}\n\n"
        "Decide:\n"
        "- mode 'task' if this is ONE cohesive change one pipeline run can finish.\n"
        "- mode 'epic' if it needs splitting into several independently shippable "
        "subtasks (broad goal, multiple areas, 'restore/rebuild X').\n"
        "Rate complexity per unit: 'low' (mechanical/config/docs), 'medium' (ordinary), "
        "'high' (subtle logic, migrations, architecture).\n"
        "Write a clear, specific title (imperative). Keep the owner's intent; if the "
        "transcription is rough, infer the obvious meaning. Titles/details in the same "
        "language as the request.\n\n"
        "Reply with ONLY a JSON object, no prose:\n"
        '{"mode":"task"|"epic", "repository_id":"<id>", '
        '"title":"<short name of the whole request>", '
        '"summary":"<one sentence of what you understood>", '
        '"task":{"title":"...","detail":"...","complexity":"low|medium|high"}  // when mode=task, '
        '"subtasks":[{"title":"...","detail":"...","complexity":"low|medium|high"}]  // when mode=epic}'
    )
    try:
        raw = fable(prompt)
    except Exception as e:
        raise HTTPException(502, f"dispatch model failed: {e}")
    data = parse_json_block(raw)
    if not isinstance(data, dict) or data.get("mode") not in ("task", "epic"):
        raise HTTPException(502, "dispatcher returned no valid proposal")
    return _normalize_proposal(data, default_repo, text)


def _normalize_proposal(data, default_repo, transcript):
    """Shared normalisation for fresh and refined proposals."""
    def norm_cx(c):
        c = (c or "medium").lower()
        return c if c in ("low", "medium", "high") else "medium"
    if not data.get("repository_id"):
        data["repository_id"] = default_repo
    if data["mode"] == "task":
        t = data.get("task") or {}
        data["task"] = {"title": (t.get("title") or data.get("title") or "").strip()[:180],
                        "detail": (t.get("detail") or "").strip(),
                        "complexity": norm_cx(t.get("complexity"))}
        if not data["task"]["title"]:
            raise HTTPException(502, "task proposal missing title")
    else:
        subs = []
        for s in data.get("subtasks") or []:
            title = (s.get("title") or "").strip()
            if title:
                subs.append({"title": title[:180], "detail": (s.get("detail") or "").strip(),
                             "complexity": norm_cx(s.get("complexity"))})
        if not subs:
            raise HTTPException(502, "epic proposal has no subtasks")
        data["subtasks"] = subs
    data["transcript"] = transcript
    return data


def refine(text, proposal, intent=""):
    """The owner spoke about an existing plan. Intent is explicit from the UI:
    'ask' answers a question about the plan, 'edit' revises the plan."""
    current = {k: v for k, v in proposal.items() if k in
               ("mode", "repository_id", "title", "summary", "task", "subtasks")}
    plan_json = json.dumps(current, ensure_ascii=False)
    if intent == "ask":
        prompt = (
            "You are the intake dispatcher of a software factory, answering the owner's "
            "question about a plan you proposed. The plan (JSON):\n" + plan_json + "\n\n"
            "Owner's question (transcribed voice):\n---\n" + text + "\n---\n\n"
            "Reply with ONLY: {\"mode\":\"answer\", \"answer\":\"<concrete answer in the "
            "owner's language, referring to specific parts of the plan; if you are unsure "
            "or the plan itself was ambiguous, say so honestly and ask ONE clarifying "
            "question back; do NOT change the plan>\"}"
        )
    else:
        prompt = (
            "You are the intake dispatcher of a software factory. The owner wants CHANGES "
            "to a plan you proposed. The current plan (JSON):\n" + plan_json + "\n\n"
            "Owner's change request (transcribed voice):\n---\n" + text + "\n---\n\n"
            "Reply with ONLY the FULL revised proposal in exactly the same JSON shape "
            "(mode task|epic, repository_id, title, summary, task or subtasks with "
            "complexity). Apply the requested changes, keep everything else intact, keep "
            "the owner's language. If the request is impossible or unclear, reply "
            "{\"mode\":\"answer\",\"answer\":\"<explain the problem and ask one question>\"} instead."
        )
    try:
        raw = fable(prompt)
    except Exception as e:
        raise HTTPException(502, f"refine model failed: {e}")
    data = parse_json_block(raw)
    if not isinstance(data, dict):
        raise HTTPException(502, "refiner returned no valid JSON")
    if data.get("mode") == "answer":
        return {"mode": "answer", "answer": (data.get("answer") or "").strip()[:2000]}
    if data.get("mode") not in ("task", "epic"):
        raise HTTPException(502, "refiner returned unknown mode")
    transcript = (proposal.get("transcript") or "") + f"\n[уточнение]: {text}"
    return _normalize_proposal(data, proposal.get("repository_id", ""), transcript[:4000])


# ------------------------------------------------------------------- commit ---

class CommitIn(BaseModel):
    proposal: dict
    request_key: str = ""
    attachment_ids: list[str] = []


def _workflows_workers():
    workers = pilot.best_workers(api("/workers")["workers"])
    workflows = {}
    for w in api("/workflows").get("workflows") or []:
        rev = w.get("current_revision") or {}
        workflows[rev.get("title")] = {"workflow_id": w["id"], "revision_id": rev.get("id"),
                                       "enabled": w.get("enabled")}
    return workflows, workers


@app.post("/commit")
def commit(inp: CommitIn):
    p = inp.proposal or {}
    mode = p.get("mode")
    repo_id = p.get("repository_id", "")
    conf = pilot.load(pilot.CONF_PATH, None)
    if not conf:
        raise HTTPException(500, "pilot config missing")
    workflows, workers = _workflows_workers()
    stage_name, nstages = pilot.first_stage(conf)
    nw = workflows.get(stage_name)
    if not nw or not nw.get("enabled"):
        raise HTTPException(500, f"first stage '{stage_name}' has no enabled workflow")

    if mode == "task":
        t = p["task"]
        worker = workers.get(pilot.stage_worker(conf, stage_name, t["complexity"]))
        if not worker:
            raise HTTPException(500, "no worker available for the first stage")
        title = f"[auto] [1/{nstages} {stage_name}] {t['title']}"[:200]
        context = (f"Spoken request: {p.get('transcript','')}\n\n"
                   f"Task: {t['title']}\n{t.get('detail','')}\n\n"
                   "You are the first pipeline stage; later stages continue on the branch "
                   "you (or Implement) push.")[:60000]
        try:
            r = pilot.create_task({"request_key": inp.request_key or str(uuid.uuid4()), "title": title,
                                   "context": context, "worker_id": worker["id"],
                                   "repository_id": repo_id,
                                   "timeout_seconds": conf.get("timeout_seconds", 7200),
                                   "workflow_revision_id": nw["revision_id"],
                                   "attachment_ids": inp.attachment_ids})
        except Exception as e:
            detail = getattr(e, "reason", None) or str(e)
            raise HTTPException(502, f"task create failed: {detail}")
        pilot.note_work(t["title"],
                        pilot.ORIGIN_ASSISTANT if p.get("origin") == "assistant"
                        else pilot.ORIGIN_OWNER, stage_name)
        assistant = p.get("origin") == "assistant"
        pilot.notify(conf,
                     "Задача заведена помощником" if assistant
                     else "Голосовая задача заведена",
                     t["title"],
                     tags="robot" if assistant else "studio_microphone")
        return {"mode": "task", "task_id": r.get("task", {}).get("id"), "title": title}

    if mode == "epic":
        epic_id = f"intake-{uuid.uuid4().hex[:10]}"
        epic = pilot.write_epic(epic_id, p.get("title", ""), p.get("transcript", ""),
                                repo_id, p["subtasks"])
        ok, msg = pilot.start_epic(conf, epic, workflows, workers)
        return {"mode": "epic", "epic_id": epic_id, "started": ok, "detail": msg,
                "children": epic.get("children", [])}

    raise HTTPException(400, "unknown proposal mode")


# ---------------------------------------------------------------------- tts ---

from fastapi import Response  # noqa: E402

VOICE_DIR = f"{HOME}/intake/voices"
TTS_VOICES = {"ru": f"{VOICE_DIR}/ru_RU-dmitri-medium.onnx",
              "en": f"{VOICE_DIR}/en_US-lessac-medium.onnx"}
PIPER_BIN = f"{HOME}/intake/venv/bin/piper"


def clean_for_speech(text):
    """Same whitelist as the UI: letters, digits, readable punctuation only."""
    text = re.sub(r"```.*?```", ". Дальше блок кода, пропускаю. ", text, flags=re.S)
    text = re.sub(r"[^\w\s.,!?;:()«»—-]", " ", text, flags=re.U)
    text = re.sub(r"_", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class TTSIn(BaseModel):
    text: str


TTS_CACHE = f"{HOME}/intake/ttscache"


def _tts_cache_cleanup():
    try:
        now = time.time()
        for fn in os.listdir(TTS_CACHE):
            p = os.path.join(TTS_CACHE, fn)
            if now - os.path.getmtime(p) > 900:
                os.unlink(p)
    except Exception:
        pass


@app.post("/tts")
def tts(inp: TTSIn):
    """Synthesize speech; returns an id. The audio is then fetched as a plain
    GET mp3 (iOS refuses blob playback, but streams a normal URL happily)."""
    text = clean_for_speech(inp.text or "")[:4000]
    if not text:
        raise HTTPException(400, "empty text")
    cyr = len(re.findall(r"[а-яё]", text, re.I))
    lat = len(re.findall(r"[a-z]", text))
    model = TTS_VOICES["ru" if cyr >= lat else "en"]
    if not os.path.exists(model):
        raise HTTPException(503, "tts voice not installed")
    os.makedirs(TTS_CACHE, exist_ok=True)
    _tts_cache_cleanup()
    tid = uuid.uuid4().hex
    wav = tempfile.mktemp(suffix=".wav")
    mp3 = os.path.join(TTS_CACHE, f"{tid}.mp3")
    try:
        r = subprocess.run([PIPER_BIN, "--model", model, "--output_file", wav],
                           input=text, capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(wav):
            raise HTTPException(500, f"piper failed: {(r.stderr or '')[:200]}")
        f = subprocess.run(["ffmpeg", "-y", "-i", wav, "-codec:a", "libmp3lame",
                            "-b:a", "64k", mp3], capture_output=True, timeout=120)
        if f.returncode != 0 or not os.path.exists(mp3):
            raise HTTPException(500, "ffmpeg failed")
        return {"id": tid, "bytes": os.path.getsize(mp3)}
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass


@app.get("/tts-audio/{tid}")
def tts_audio(tid: str):
    if not re.fullmatch(r"[0-9a-f]{32}", tid):
        raise HTTPException(400, "bad id")
    path = os.path.join(TTS_CACHE, f"{tid}.mp3")
    if not os.path.exists(path):
        raise HTTPException(404, "expired")
    return Response(content=open(path, "rb").read(), media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"})


class SuggestIn(BaseModel):
    question: str = ""
    situation: str = ""
    title: str = ""
    stage: str = ""
    repository_id: str = ""


@app.post("/suggest-answer")
def suggest_answer(inp: SuggestIn):
    """The owner asked the big model to answer on their behalf."""
    prompt = (
        "Ты — технический директор владельца (непрограммиста). Конвейер разработки "
        f"остановился на этапе '{inp.stage}' задачи '{inp.title}'.\n\n"
        f"Ситуация: {inp.situation}\n"
        f"Вопрос агента к владельцу: {inp.question}\n\n"
        "КОНТЕКСТ ПРОЕКТА:\n" + pilot.project_context() + "\n\n"
        + pilot.repo_brief(inp.repository_id) + "\n\n"
        "Ответь ЗА владельца: короткий, конкретный, исполнимый ответ по-русски (2-5 предложений), "
        "который разблокирует работу. Решай сам, не переспрашивай. Если нужен выбор - выбери "
        "самый безопасный вариант и скажи почему одним придаточным. "
        "Ответь ТОЛЬКО JSON: {\"answer\": \"<текст ответа>\"}"
    )
    try:
        raw = fable(prompt)
    except Exception as e:
        raise HTTPException(502, f"suggest failed: {e}")
    data = parse_json_block(raw)
    if not isinstance(data, dict) or not data.get("answer"):
        raise HTTPException(502, "no suggestion produced")
    return {"answer": str(data["answer"])[:2000]}


class ExplainIn(BaseModel):
    text: str = ""
    title: str = ""


@app.post("/explain-result")
def explain_result(inp: ExplainIn):
    """Turn a raw stage output into a plain-Russian verdict, on demand."""
    raw = (inp.text or "")[:14000]
    if not raw.strip():
        raise HTTPException(400, "empty text")
    prompt = (
        "Ты объясняешь владельцу-непрограммисту результат работы агента над задачей "
        f"'{inp.title}'. Вот его технический отчёт:\n---\n{raw}\n---\n\n"
        "Ответь ТОЛЬКО JSON: {\"verdict\": \"<3-6 предложений по-русски: что конкретно "
        "сделано или найдено, каков итог, и что это значит на практике. Простыми "
        "словами, без жаргона, английских терминов и кода. Если работа не удалась — "
        "честно скажи, что именно не получилось>\"}"
    )
    try:
        raw_out = fable(prompt)
    except Exception as e:
        raise HTTPException(502, f"explain failed: {e}")
    data = parse_json_block(raw_out)
    if not isinstance(data, dict) or not data.get("verdict"):
        raise HTTPException(502, "no verdict produced")
    return {"verdict": str(data["verdict"])[:2000]}


SESSION_ROOT = f"{HOME}/.claude/projects"
PRICE = {"opus": (15.0, 75.0), "fable": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (0.80, 4.0)}


@app.get("/usage/{task_id}")
def task_usage(task_id: str):
    """Token spend for one task: session logs live in a directory whose name
    ends with the attempt id, so the mapping is exact."""
    if not re.fullmatch(r"[0-9a-fA-F-]{10,40}", task_id):
        raise HTTPException(400, "bad task id")
    try:
        detail = api(f"/tasks/{task_id}")
    except Exception as e:
        raise HTTPException(502, f"task lookup failed: {e}")
    attempts = [a.get("id") for a in (detail.get("attempts") or []) if a.get("id")]
    totals = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "messages": 0}
    models = {}
    try:
        dirs = os.listdir(SESSION_ROOT)
    except OSError:
        dirs = []
    for att in attempts:
        for d in dirs:
            if not d.endswith(att):
                continue
            for fn in os.listdir(os.path.join(SESSION_ROOT, d)):
                if not fn.endswith(".jsonl"):
                    continue
                path = os.path.join(SESSION_ROOT, d, fn)
                try:
                    with open(path, errors="ignore") as fh:
                        for line in fh:
                            if '"usage"' not in line:
                                continue
                            try:
                                o = json.loads(line)
                            except Exception:
                                continue
                            msg = o.get("message") or {}
                            u = msg.get("usage") or o.get("usage") or {}
                            if not u:
                                continue
                            totals["input"] += u.get("input_tokens", 0)
                            totals["cache_write"] += u.get("cache_creation_input_tokens", 0)
                            totals["cache_read"] += u.get("cache_read_input_tokens", 0)
                            totals["output"] += u.get("output_tokens", 0)
                            totals["messages"] += 1
                            m = msg.get("model") or "?"
                            models[m] = models.get(m, 0) + u.get("output_tokens", 0)
                except OSError:
                    continue
    model = max(models, key=models.get) if models else ""
    key = next((k for k in PRICE if k in model.lower()), "sonnet")
    pin, pout = PRICE[key]
    cost = ((totals["input"] + totals["cache_write"] * 1.25 + totals["cache_read"] * 0.1) / 1e6 * pin
            + totals["output"] / 1e6 * pout)
    return {**totals, "model": model, "cost_usd": round(cost, 2),
            "total_tokens": totals["input"] + totals["cache_write"] + totals["cache_read"] + totals["output"]}


class LogIn(BaseModel):
    event: str
    detail: str = ""


@app.post("/log")
def uilog(inp: LogIn):
    """Fire-and-forget client telemetry for remote debugging."""
    line = f"{time.strftime('%F %T')} | {inp.event[:60]} | {inp.detail[:400]}\n"
    with open(f"{HOME}/intake/uilog.txt", "a") as f:
        f.write(line)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL_SIZE,
            "tts": {k: os.path.exists(v) for k, v in TTS_VOICES.items()}}


# ------------------------------------------------------------- план ---
from plan import router as plan_router  # noqa: E402
app.include_router(plan_router)
