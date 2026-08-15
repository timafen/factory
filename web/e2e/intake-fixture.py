#!/usr/bin/env python3
"""Isolated browser fixture for the real intake.plan router."""
import argparse
import json
import os
import sys
import tempfile
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

def fake_pilot():
    module = types.ModuleType("pilot")
    ideas = [{
        "id": "idea-browser",
        "title": "Проверить компактный План",
        "why": "Полное обоснование <должно> открываться только по запросу владельца.",
        "kind": "idea",
        "repo": "repo-browser",
        "state": "new",
        "origin": "owner",
        "created": "2026-08-15T10:00:00Z",
    }]
    module.ideas_all = lambda: ideas
    module.api = lambda path, body=None: {
        "repositories": [{
            "id": "repo-browser",
            "remote_identity": "github.com/example/browser-fixture",
        }],
    } if path == "/repositories" else {}
    module.add_idea = lambda *args, **kwargs: None
    module.set_idea = lambda *args, **kwargs: None
    module.load = lambda: {}
    return module


def fake_fastapi():
    module = types.ModuleType("fastapi")
    responses = types.ModuleType("fastapi.responses")

    class Router:
        def __init__(self):
            self.routes = {}

        def get(self, path, **_kwargs):
            return self._register("GET", path)

        def post(self, path, **_kwargs):
            return self._register("POST", path)

        def _register(self, method, path):
            def decorator(function):
                self.routes[(method, path)] = function
                return function
            return decorator

    class Response:
        def __init__(self, content="", status_code=200, **_kwargs):
            self.body = str(content).encode("utf-8")
            self.status_code = status_code

    module.APIRouter = Router
    module.Form = lambda default, **_kwargs: default
    module.HTTPException = RuntimeError
    responses.HTMLResponse = Response
    responses.RedirectResponse = Response
    return module, responses


def seed_notifications(path):
    records = [
        {"at": "2026-08-15T12:00:00Z", "group": "questions",
         "title": "Нужен ответ", "message": "Выберите вариант продолжения.",
         "delivered": True, "click": "/answer"},
        {"at": "2026-08-15T12:01:00Z", "group": "stuck",
         "title": "Работа остановилась", "message": "Исполнителю нужна помощь владельца.",
         "delivered": False, "click": "/tasks/stuck-browser"},
        {"at": "2026-08-15T12:02:00Z", "group": "stuck",
         "title": "Повтор не помог", "message": "Автоматическое восстановление исчерпано.",
         "delivered": True, "click": "/tasks/retry-browser"},
    ]
    with open(path, "w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="factory-intake-e2e-")
    notifications = os.path.join(temporary.name, "notifications.jsonl")
    seed_notifications(notifications)
    os.environ["FACTORY_INTAKE_NOTIFICATIONS_PATH"] = notifications
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.modules["pilot"] = fake_pilot()
    fastapi, responses = fake_fastapi()
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses

    from intake.plan import router

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            function = router.routes.get(("GET", parsed.path))
            if not function:
                self.send_error(404)
                return
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if "n" in query:
                query["n"] = int(query["n"])
            response = function(**query)
            self.send_response(response.status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, _format, *_args):
            pass

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
