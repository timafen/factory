#!/usr/bin/env python3
"""Deterministic FastAPI host for the real intake Plan and Alerts router."""

from __future__ import annotations

import atexit
import json
import os
import sys
import tempfile
import types
from pathlib import Path

from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
temporary = tempfile.TemporaryDirectory(prefix="factory-intake-e2e-")
atexit.register(temporary.cleanup)
alerts_path = Path(temporary.name) / "notifications.jsonl"
alerts_path.write_text(
    "\n".join(
        json.dumps(item, ensure_ascii=False)
        for item in [
            {
                "title": "Вопрос владельцу",
                "message": "Нужно подтвердить порядок следующей работы.",
                "at": "2026-08-11T12:03:00Z",
                "group": "questions",
                "delivered": True,
                "click": "/work/question",
            },
            {
                "title": "Работа остановилась",
                "message": "Исполнитель ждёт доступ к репозиторию.",
                "at": "2026-08-11T12:02:00Z",
                "group": "stuck",
                "delivered": False,
                "click": "/work/stuck",
            },
            {
                "title": "Лимит близко",
                "message": "Дневной бюджет израсходован на 80%.",
                "at": "2026-08-11T12:01:00Z",
                "group": "money",
                "delivered": True,
                "click": "/settings",
            },
            {
                "title": "Плановая работа готова",
                "message": "Можно проверить результат этапа.",
                "at": "2026-08-11T12:00:00Z",
                "group": "done",
                "delivered": True,
                "click": "/work/done",
            },
        ]
    )
    + "\nне-json-строка\n",
    encoding="utf-8",
)
os.environ["FACTORY_INTAKE_ALERTS_PATH"] = str(alerts_path)

pilot = types.ModuleType("pilot")
pilot.api = lambda path: {
    "repositories": [
        {
            "id": "repo-factory",
            "name": "factory",
            "remote_identity": "github.com/timafen/factory",
        }
    ]
} if path == "/repositories" else {}
pilot.ideas_all = lambda: [
    {
        "id": "idea-plan-1",
        "title": "Сделать План компактным",
        "why": "Владелец должен видеть обоснование только по своему запросу.",
        "kind": "idea",
        "state": "planned",
        "origin": "owner",
        "created": "2026-08-11T11:00:00Z",
        "repo": "repo-factory",
        "order": 0,
    },
    {
        "id": "idea-plan-2",
        "title": "Проверить уведомления",
        "why": "Группы должны оставаться компактными на телефоне.",
        "kind": "finding",
        "state": "new",
        "origin": "agent",
        "created": "2026-08-11T10:00:00Z",
        "repo": "repo-factory",
        "order": 1,
    },
]
sys.modules["pilot"] = pilot

from intake.plan import router  # noqa: E402


app = FastAPI()
app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("FACTORY_INTAKE_E2E_PORT", "17438")),
        log_level="warning",
    )
