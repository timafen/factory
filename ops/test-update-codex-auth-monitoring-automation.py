#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SCRIPT = pathlib.Path(__file__).with_name("update-codex-auth-monitoring-automation.py")
SPEC = importlib.util.spec_from_file_location("automation_update", SCRIPT)
assert SPEC and SPEC.loader
automation_update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(automation_update)


class FactoryHandler(BaseHTTPRequestHandler):
    automation = {
        "id": "existing-automation",
        "title": "Патруль Factory",
        "workflow_id": "existing-workflow",
        "context": "Existing patrol policy and history baseline.",
        "timeout_seconds": 1800,
        "enabled": True,
        "version": 7,
        "trigger": {"type": "schedule", "cron": "17 * * * *", "timezone": "America/Chicago"},
    }
    occurrence_ids = ["historical-1", "historical-2"]
    put_count = 0
    enabled_updates = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def send_json(self, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/api/v1/automations?limit=200":
            self.send_json({"automations": [self.automation], "next_cursor": None})
            return
        if self.path.startswith("/api/v1/automations/existing-automation/occurrences"):
            self.send_json({"occurrences": [{"id": item} for item in self.occurrence_ids], "next_cursor": None})
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        if self.path == "/api/v1/automations/existing-automation/enabled":
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.__class__.enabled_updates.append(body["enabled"])
            self.__class__.automation = {**self.automation, "enabled": body["enabled"]}
            self.send_json({"automation": self.automation, "occurrences": []})
            return
        if self.path != "/api/v1/automations/existing-automation":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["expected_version"] != self.automation["version"]:
            self.send_error(409)
            return
        self.__class__.put_count += 1
        self.__class__.automation = {**self.automation, **body, "id": self.automation["id"], "version": self.automation["version"] + 1}
        self.send_json({"automation": self.automation, "occurrences": []})


class UpdateAutomationTest(unittest.TestCase):
    def setUp(self) -> None:
        FactoryHandler.automation = {
            **FactoryHandler.automation,
            "context": "Existing patrol policy and history baseline.",
            "version": 7,
        }
        FactoryHandler.occurrence_ids = ["historical-1", "historical-2"]
        FactoryHandler.put_count = 0
        FactoryHandler.enabled_updates = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FactoryHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.api = automation_update.API(f"http://127.0.0.1:{self.server.server_port}/api/v1")

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_updates_in_place_and_preserves_schedule_and_history(self) -> None:
        evidence = automation_update.update(self.api, "Патруль Factory")

        self.assertEqual(evidence["automation_id"], "existing-automation")
        self.assertEqual(evidence["schedule"]["cron"], "17 * * * *")
        self.assertEqual(evidence["occurrences_before"], 2)
        self.assertEqual(evidence["occurrences_after"], 2)
        self.assertTrue(all(evidence["verification"].values()))
        self.assertEqual(FactoryHandler.put_count, 1)
        self.assertEqual(FactoryHandler.enabled_updates, [False, True])

    def test_second_run_is_idempotent(self) -> None:
        automation_update.update(self.api, "Патруль Factory")
        automation_update.update(self.api, "Патруль Factory")

        self.assertEqual(FactoryHandler.put_count, 1)


if __name__ == "__main__":
    unittest.main()
