import contextlib
import importlib
import json
import os
import sys
import tempfile
import time
import types
import unittest
import urllib.error
import uuid
from unittest import mock

from pilot import pilot


class AgentRulesScopeTests(unittest.TestCase):
    def test_common_rules_exclude_stage_specific_requirements(self):
        self.assertNotIn("ГОТОВО-КОГДА", pilot.AGENT_RULES)
        self.assertNotIn("Ревью: меряй поставку", pilot.AGENT_RULES)
        self.assertEqual(pilot.AGENT_RULES.count("origin/main...HEAD"), 1)

    def test_common_rules_keep_universal_requirements_and_markers(self):
        required = (
            "=== ПРАВИЛА ДЛЯ АГЕНТА",
            "=== КОНЕЦ ПРАВИЛ ===",
            "Ветка: режь от свежего origin/main",
            "Сдача: сначала перебазируй",
            "ОБЛАСТЬ: <файлы через запятую",
            "первая строка коммита — по-русски",
            "заводи ОТДЕЛЬНУЮ карточку",
            "НЕ гоняй полный набор тестов",
            "Живая проверка на стенде РАЗРЕШЕНА",
        )
        for signature in required:
            with self.subTest(signature=signature):
                self.assertIn(signature, pilot.AGENT_RULES)

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_auto_task_receives_owner_notification_channel(self, _api, _money):
        body = {
            "title": "[auto] [3/5 Implement + Test] Задача",
            "context": "Контекст",
        }
        conf = {
            "ntfy_server": "https://notify.example/",
            "ntfy_owner_topic": "owner alerts",
        }

        pilot.create_task(body, conf)

        self.assertIn(
            "Канал срочных уведомлений владельца: "
            "https://notify.example/owner%20alerts",
            body["context"],
        )

    def test_incomplete_notification_settings_are_not_exposed(self):
        self.assertNotIn(
            "Канал срочных уведомлений владельца",
            pilot.agent_rules({"ntfy_server": "https://notify.example"}),
        )

    def test_long_context_keeps_notification_channel_and_rules(self):
        body = {
            "title": "[auto] [3/5 Implement + Test] Задача",
            "context": "x" * 60000,
        }
        conf = {
            "ntfy_server": "https://notify.example",
            "ntfy_owner_topic": "owner",
        }

        with mock.patch.object(pilot, "money_guard"), \
                mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}}):
            pilot.create_task(body, conf)

        self.assertLessEqual(len(body["context"]), 60000)
        self.assertIn("https://notify.example/owner", body["context"])
        self.assertIn("=== КОНЕЦ ПРАВИЛ ===", body["context"])


class OwnerMessageTests(unittest.TestCase):
    def test_internal_identifiers_become_human_words(self):
        text = (
            "Ветка `factory/6ca72092-cc4f-4a5d-802d-3e376f36e6fc`, "
            "задача 6ca72092-cc4f-4a5d-802d-3e376f36e6fc, "
            "версия `0684f94bd46493d0ec920ed1939323ccbebefe84`."
        )

        result = pilot.no_bare_hashes(text)

        self.assertEqual(
            result,
            "Ветка рабочая ветка, задача внутренняя задача, версия проверенная версия.",
        )
        self.assertNotIn("служебный код", result)

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_auto_task_receives_common_rules_only_once(self, _api, _money):
        body = {"title": "[auto] [3/5 Implement + Test] Задача", "context": "Контекст"}

        pilot.create_task(body)
        pilot.create_task(body)

        self.assertEqual(body["context"].count("ПРАВИЛА ДЛЯ АГЕНТА"), 1)


class DeliveryAreaTests(unittest.TestCase):
    def test_stage_report_extends_delivery_area(self):
        known = {"Счётчик": ["repo::pilot/pilot.py"]}

        with mock.patch.object(pilot, "load", return_value=known), \
                mock.patch.object(pilot, "save") as save:
            added = pilot.area_extend(
                "Счётчик",
                "ОБЛАСТЬ: pilot/pilot.py, web/src/Overview.tsx",
                "repo",
            )

        self.assertEqual(added,
                         {"repo::pilot/pilot.py", "repo::web/src/Overview.tsx"})
        save.assert_called_once_with(
            pilot.AREAS_PATH,
            {"Счётчик": ["repo::pilot/pilot.py", "repo::web/src/Overview.tsx"]},
        )

    def test_review_gate_removes_only_other_area_and_service_noise(self):
        known = {
            "Счётчик": ["repo::pilot/pilot.py", "repo::web/src/Overview.tsx"],
            "Другая работа": ["repo::docs/foreign.md"],
        }
        files = ["pilot/pilot.py", "web/src/Overview.tsx", "docs/extra.md",
                 "docs/foreign.md", "pilot/__pycache__/pilot.pyc"]

        with mock.patch.object(pilot, "branch_report", return_value=("есть", files)), \
                mock.patch.object(pilot, "load", return_value=known), \
                mock.patch.object(pilot, "rebuild_clean_branch",
                                  return_value="task-clean") as rebuild:
            result = pilot.review_gate({}, "Счётчик", "task", "repo")

        self.assertEqual(result["branch"], "task-clean")
        rebuild.assert_called_once_with(
            "repo", "task",
            ["pilot/pilot.py", "web/src/Overview.tsx", "docs/extra.md"],
            "Счётчик",
        )


class CodexUsageTests(unittest.TestCase):
    def setUp(self):
        pilot._codex_rollout_cache.clear()

    def write_rollout(self, events):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = os.path.join(temporary.name, "rollout-test.jsonl")
        with open(path, "w") as fh:
            for event in events:
                fh.write(json.dumps(event) + "\n")
        return path

    @staticmethod
    def event(at, usage, total=None):
        info = {"last_token_usage": usage}
        if total is not None:
            info["total_token_usage"] = total
        return {"timestamp": at, "type": "event_msg",
                "payload": {"type": "token_count", "info": info}}

    def test_codex_rollout_uses_exact_model_and_separate_cached_price(self):
        # Поля ниже взяты из настоящего event_msg/token_count rollout-журнала.
        path = self.write_rollout([
            {"timestamp": "2026-08-09T10:00:00Z", "type": "turn_context",
             "payload": {"model": "gpt-5.6-terra"}},
            self.event("2026-08-09T10:00:01Z",
                       {"input_tokens": 1200, "cached_input_tokens": 200,
                        "cache_write_input_tokens": 100, "output_tokens": 100}),
        ])
        with mock.patch.object(pilot.glob, "glob", side_effect=[[path], []]):
            usage = pilot.codex_usage_since(0)

        self.assertEqual((usage["input"], usage["cache_read"], usage["output"]),
                         (900, 200, 100))
        self.assertEqual(usage["cache_write"], 100)
        self.assertAlmostEqual(usage["cost_usd"], 0.0041125)
        self.assertTrue(usage["cost_defined"])
        self.assertFalse(usage["base_estimate"])

    def test_snapshot_reuses_offsets_and_reads_unchanged_rollout_once(self):
        path = self.write_rollout([
            {"timestamp": "2026-08-09T10:00:00Z", "type": "turn_context",
             "payload": {"model": "gpt-5.6-terra"}},
            self.event("2026-08-09T10:00:01Z",
                       {"input_tokens": 100, "cached_input_tokens": 20,
                        "cache_write_input_tokens": 10, "output_tokens": 5}),
        ])
        real_open = open
        opened = []

        def tracked_open(filename, *args, **kwargs):
            if filename == path:
                opened.append(filename)
            return real_open(filename, *args, **kwargs)

        with mock.patch.object(pilot.glob, "glob",
                               side_effect=[[path], [], [path], []]), \
                mock.patch("builtins.open", side_effect=tracked_open):
            snapshot = pilot.codex_usage_snapshot(0, 1)
            repeated = pilot.codex_usage_since(0)

        self.assertEqual(snapshot[0]["total_tokens"], 105)
        self.assertEqual(snapshot[1], snapshot[0])
        self.assertEqual(repeated, snapshot[0])
        self.assertEqual(opened, [path])

    def test_incomplete_jsonl_line_is_read_after_it_is_finished(self):
        path = self.write_rollout([])
        event = self.event("2026-08-09T10:00:01Z",
                           {"input_tokens": 100, "output_tokens": 5})
        encoded = json.dumps(event)
        split = len(encoded) // 2
        with open(path, "a") as fh:
            fh.write(encoded[:split])

        self.assertEqual(pilot._codex_usage_events(path), [])
        self.assertEqual(pilot._codex_rollout_cache[path]["offset"], 0)

        with open(path, "a") as fh:
            fh.write(encoded[split:] + "\n")

        events = pilot._codex_usage_events(path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input"], 100)
        self.assertEqual(events[0]["output"], 5)

    def test_malformed_json_types_are_skipped_without_stopping_rollout(self):
        malformed = [
            [],
            {"type": "turn_context", "payload": []},
            {"type": "turn_context", "payload": {"model": 56}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": []}},
            self.event("2026-08-09T10:00:01Z", "not-an-object"),
            self.event("2026-08-09T10:00:02Z", {"input_tokens": "100"}),
            self.event("2026-08-09T10:00:03Z", {"input_tokens": True}),
            self.event("2026-08-09T10:00:04Z", {"input_tokens": -1}),
            self.event("2026-08-09T10:00:05Z", {"input_tokens": 10, "model": 56}),
            self.event("2026-08-09T10:00:06Z", None, "not-an-object"),
            self.event("2026-08-09T10:00:07Z", {"input_tokens": 7,
                                                  "output_tokens": 2}),
        ]
        path = self.write_rollout(malformed)

        events = pilot._codex_usage_events(path)

        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]["input"], events[0]["output"]), (7, 2))

    def test_cumulative_counts_are_deltas_and_unknown_price_is_not_zero(self):
        path = self.write_rollout([
            {"timestamp": "2026-08-09T10:00:00Z", "type": "turn_context",
             "payload": {"model": "gpt-future-exact"}},
            self.event("2026-08-09T10:00:01Z", None,
                       {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}),
            self.event("2026-08-09T10:00:02Z", None,
                       {"input_tokens": 150, "cached_input_tokens": 30, "output_tokens": 25}),
        ])
        with mock.patch.object(pilot.glob, "glob", side_effect=[[path], []]):
            usage = pilot.codex_usage_since(0)

        self.assertEqual(usage["total_tokens"], 175)
        self.assertFalse(usage["cost_defined"])
        self.assertTrue(usage["base_estimate"])
        self.assertEqual(usage["unknown_models"], ["gpt-future-exact"])
        self.assertIsNone(pilot.openai_api_cost("gpt-future-exact", 1, 1, 1))

    def test_mixed_last_and_cumulative_usage_does_not_repeat_total(self):
        path = self.write_rollout([
            {"timestamp": "2026-08-09T10:00:00Z", "type": "turn_context",
             "payload": {"model": "gpt-5.6-sol"}},
            self.event("2026-08-09T10:00:01Z",
                       {"input_tokens": 100, "cached_input_tokens": 20,
                        "output_tokens": 10},
                       {"input_tokens": 100, "cached_input_tokens": 20,
                        "output_tokens": 10}),
            self.event("2026-08-09T10:00:02Z", None,
                       {"input_tokens": 150, "cached_input_tokens": 30,
                        "output_tokens": 25}),
        ])

        events = pilot._codex_usage_events(path)

        self.assertEqual([(event["input"], event["cache_read"], event["output"])
                          for event in events], [(80, 20, 10), (40, 10, 15)])

    def test_long_context_and_cache_writes_use_gpt_56_multipliers(self):
        # 273K prompt: input/read/write all use the long-context multiplier;
        # writes additionally cost 1.25x and output costs 1.5x.
        cost = pilot.openai_api_cost("gpt-5.6-sol", 200000, 50000, 23000,
                                     cache_write_tokens=23000)

        self.assertAlmostEqual(cost, 3.3725)

    def test_day_total_adds_global_codex_estimate_without_task_attribution(self):
        with mock.patch.object(pilot, "attempts_of", return_value=["claude-attempt"]), \
                mock.patch.object(pilot, "task_cost_usd", return_value=2.0), \
                mock.patch.object(pilot, "codex_usage_since",
                                  return_value={"cost_usd": 1.25}):
            spent = pilot.day_spent([{"id": "task", "created_at":
                                      time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime()),
                                      "state": "succeeded"}])
        self.assertEqual(spent, 3.25)


class CreateTaskFallbackTest(unittest.TestCase):
    def test_voice_attachments_keep_request_key_through_fallback(self):
        request_key = "voice-request-with-files"
        body = {
            "request_key": request_key,
            "title": "Создать задачу по голосу",
            "worker_id": "preferred-worker",
            "repository_id": "repo-id",
            "attachment_ids": ["screenshot-id", "document-id"],
        }
        submitted = []

        def fake_api(path, payload=None):
            if path == "/repositories":
                return {"repositories": [{"id": "repo-id", "remote_identity": "github.com/acme/repo"}]}
            submitted.append(payload)
            if len(submitted) < 3:
                raise urllib.error.HTTPError(
                    "/tasks", 409, "repository_not_advertised", None, None
                )
            return {"task": {"worker_id": "fallback-worker"}}

        with mock.patch.object(pilot, "api", side_effect=fake_api), \
                mock.patch.object(pilot, "_http_err", return_value="repository_not_advertised"):
            pilot.create_task(body, {"allow_any_worker": True})

        self.assertEqual(len(submitted), 3)
        for payload in submitted:
            self.assertEqual(payload["request_key"], request_key)
            self.assertEqual(payload["attachment_ids"], ["screenshot-id", "document-id"])


class DiagnosisRepairTests(unittest.TestCase):
    def setUp(self):
        self.repairs = {}
        self.notifications = []
        self.api_calls = []
        self.created = []
        self.conf = {"timeout_seconds": 900}
        self.task = {
            "id": "looping-task",
            "title": "[auto] [3/5 Implement + Test] Починить отчёт",
            "state": "running",
        }

        def load(path, default=None):
            if path == pilot.DIAG_REPAIR_PATH:
                return self.repairs
            return default

        def save(path, value):
            if path == pilot.DIAG_REPAIR_PATH:
                self.repairs = value

        self.patches = [
            mock.patch.object(pilot, "load", side_effect=load),
            mock.patch.object(pilot, "save", side_effect=save),
            mock.patch.object(pilot, "notify",
                              side_effect=lambda *args, **kwargs:
                              self.notifications.append((args, kwargs))),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def detail_api(self, path, body=None):
        self.api_calls.append((path, body))
        if path == "/tasks?limit=200":
            return {"tasks": [self.task], "next_cursor": None}
        if path == "/tasks/looping-task":
            return {
                "task": {
                    "repository_id": "repo-id",
                    "worker_id": "worker-id",
                    "context": "Прошлая работа лежит в ветке factory/old-work",
                },
                "workflow": {"revision_id": "revision-id"},
            }
        if path == "/tasks/looping-task/cancel":
            return {"task": {"id": "looping-task"}}
        raise AssertionError(path)

    def saved_repair(self, status):
        return {
            "status": status,
            "task_id": "looping-task",
            "request_key": "stable-repair-key",
            "title": self.task["title"],
            "context": "Прошлая работа лежит в ветке factory/old-work",
            "branch": "factory/old-work",
            "reason": "исполнитель повторяет один и тот же шаг",
            "solution": "исправить проверку состояния",
            "worker_id": "worker-id",
            "repository_id": "repo-id",
            "workflow_revision_id": "revision-id",
        }

    def test_duplicate_active_id_is_cancelled_once_then_resumed_same_branch(self):
        verdict = {"причина": "исполнитель повторяет один и тот же шаг",
                   "решение": "исправить проверку состояния", "нужен_владелец": False}

        def duplicate_list_api(path, body=None):
            if path == "/tasks?limit=200":
                self.api_calls.append((path, body))
                return {"tasks": [self.task, dict(self.task)], "next_cursor": None}
            return self.detail_api(path, body)

        with mock.patch.object(pilot, "api", side_effect=duplicate_list_api):
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)

        cancels = [call for call in self.api_calls if call[0].endswith("/cancel")]
        self.assertEqual(len(cancels), 1)
        with mock.patch.object(pilot, "create_task",
                               side_effect=lambda body, _conf:
                               self.created.append(body) or {"task": {"id": "repair-task"}}):
            pilot.reconcile_diag_repairs(self.conf, [self.task])
            self.assertEqual(self.created, [])
            stopped = dict(self.task, state="cancelled")
            pilot.reconcile_diag_repairs(self.conf, [stopped])
            pilot.reconcile_diag_repairs(self.conf, [stopped])

        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0]["title"], self.task["title"])
        self.assertIn("factory/old-work", self.created[0]["context"])
        self.assertIn("исправить проверку состояния", self.created[0]["context"])
        self.assertEqual(self.repairs["Починить отчёт"]["status"], "resumed")

    def test_restart_replays_cancel_pending_for_same_task(self):
        self.repairs = {"Починить отчёт": self.saved_repair("cancel_pending")}

        with mock.patch.object(pilot, "api", side_effect=self.detail_api):
            pilot.reconcile_diag_repairs(self.conf, [self.task])

        self.assertEqual(
            [call for call in self.api_calls if call[0].endswith("/cancel")],
            [("/tasks/looping-task/cancel", {})],
        )
        self.assertEqual(
            self.repairs["Починить отчёт"]["status"], "cancellation_requested"
        )

    def test_restart_replays_resume_pending_with_same_request_key(self):
        self.repairs = {"Починить отчёт": self.saved_repair("resume_pending")}

        with mock.patch.object(
                pilot, "create_task",
                side_effect=lambda body, _conf:
                self.created.append(body) or {"task": {"id": "repair-task"}}):
            pilot.reconcile_diag_repairs(self.conf, [])
            pilot.reconcile_diag_repairs(self.conf, [])

        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0]["request_key"], "stable-repair-key")
        self.assertEqual(self.repairs["Починить отчёт"]["status"], "resumed")

    def test_missing_source_in_short_list_is_read_by_saved_id(self):
        self.repairs = {
            "Починить отчёт": self.saved_repair("cancellation_requested")
        }

        def source_api(path, body=None):
            self.api_calls.append((path, body))
            if path == "/tasks/looping-task":
                return {"task": dict(self.task, state="cancelled")}
            raise AssertionError(path)

        with mock.patch.object(pilot, "api", side_effect=source_api), \
                mock.patch.object(
                    pilot, "create_task",
                    side_effect=lambda body, _conf:
                    self.created.append(body) or {"task": {"id": "repair-task"}}):
            pilot.reconcile_diag_repairs(self.conf, [])

        self.assertEqual(self.api_calls, [("/tasks/looping-task", None)])
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.repairs["Починить отчёт"]["status"], "resumed")

    def test_ambiguous_active_runs_are_not_cancelled(self):
        other = dict(self.task, id="other-task", state="queued")
        verdict = {"причина": "цикл", "решение": "починить", "нужен_владелец": False}
        with mock.patch.object(pilot, "api", return_value={
                "tasks": [self.task, other], "next_cursor": None}) as api:
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task, other], self.task)
        api.assert_called_once_with("/tasks?limit=200")
        repair = self.repairs["Починить отчёт"]
        self.assertEqual(repair["status"], "failed")
        self.assertIn("найдено активных запусков — 2", repair["failure"])

    def test_active_run_beyond_first_page_prevents_any_cancellation(self):
        other = dict(self.task, id="older-active-task", state="queued")
        verdict = {"причина": "цикл", "решение": "починить", "нужен_владелец": False}

        def paged_api(path, body=None):
            self.api_calls.append((path, body))
            if path == "/tasks?limit=200":
                return {"tasks": [self.task], "next_cursor": "older/page"}
            if path == "/tasks?limit=200&cursor=older%2Fpage":
                return {"tasks": [other], "next_cursor": None}
            raise AssertionError("cancel must not be called")

        with mock.patch.object(pilot, "api", side_effect=paged_api):
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)

        self.assertEqual([path for path, _ in self.api_calls], [
            "/tasks?limit=200", "/tasks?limit=200&cursor=older%2Fpage",
        ])
        repair = self.repairs["Починить отчёт"]
        self.assertEqual(repair["status"], "failed")
        self.assertIn("найдено активных запусков — 2", repair["failure"])

    def test_missing_branch_fails_before_cancelling(self):
        verdict = {"причина": "цикл", "решение": "починить", "нужен_владелец": False}

        def api_without_branch(path, body=None):
            self.api_calls.append((path, body))
            if path == "/tasks?limit=200":
                return {"tasks": [self.task], "next_cursor": None}
            if path == "/tasks/looping-task":
                return {
                    "task": {"repository_id": "repo-id", "worker_id": "worker-id"},
                    "workflow": {"revision_id": "revision-id"},
                }
            raise AssertionError("cancel must not be called")

        with mock.patch.object(pilot, "api", side_effect=api_without_branch):
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)

        self.assertFalse(any(path.endswith("/cancel") for path, _ in self.api_calls))
        repair = self.repairs["Починить отчёт"]
        self.assertEqual(repair["status"], "failed")
        self.assertIn("прежняя ветка", repair["failure"])

    def test_cancel_failure_stops_without_second_attempt(self):
        verdict = {"причина": "цикл", "решение": "починить", "нужен_владелец": False}
        calls = []

        def failing_api(path, body=None):
            calls.append(path)
            if path in ("/tasks?limit=200", "/tasks/looping-task"):
                return self.detail_api(path, body)
            raise RuntimeError("control plane unavailable")

        with mock.patch.object(pilot, "api", side_effect=failing_api):
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)
            pilot.begin_diag_repair(self.conf, "Починить отчёт", "Implement + Test",
                                    verdict, [self.task], self.task)

        self.assertEqual(calls.count("/tasks/looping-task/cancel"), 1)
        repair = self.repairs["Починить отчёт"]
        self.assertEqual(repair["status"], "failed")
        self.assertIn("control plane unavailable", repair["failure"])

    def test_resume_failure_is_reported_and_never_retried(self):
        self.repairs = {
            "Починить отчёт": {
                "status": "cancellation_requested",
                "task_id": "looping-task",
                "request_key": "stable-repair-key",
                "title": self.task["title"],
            }
        }
        stopped = dict(self.task, state="cancelled")
        with mock.patch.object(pilot, "create_task",
                               side_effect=RuntimeError("worker unavailable")) as create:
            pilot.reconcile_diag_repairs(self.conf, [stopped])
            pilot.reconcile_diag_repairs(self.conf, [stopped])

        create.assert_called_once()
        repair = self.repairs["Починить отчёт"]
        self.assertEqual(repair["status"], "failed")
        self.assertIn("worker unavailable", repair["failure"])

    def test_owner_decision_never_starts_automatic_repair(self):
        answer = '{"причина":"нужен выбор продукта","решение":"спросить",' \
                 '"нужен_владелец":true}'
        with mock.patch.object(pilot, "cap_rescues", return_value=0), \
                mock.patch.object(pilot, "note_cap_rescue"), \
                mock.patch.object(pilot, "brain", return_value=(answer, "brain")), \
                mock.patch.object(pilot, "begin_diag_repair") as begin:
            verdict = pilot.deep_diagnose(
                self.conf, "Починить отчёт", "Implement + Test", 5,
                [self.task], repair_task=self.task)

        self.assertTrue(verdict["нужен_владелец"])
        begin.assert_not_called()

    def test_owner_diagnosis_pauses_pipeline_and_creates_answer_card(self):
        running = dict(
            self.task,
            state="running",
            title="[auto] [3/5 Implement + Test] Починить отчёт",
            repository_id="repo-id",
        )
        verdict = {
            "причина": "нужен выбор контракта",
            "решение": "выбрать допустимую длину имени",
            "нужен_владелец": True,
        }
        conf = dict(self.conf, deep_diag_rounds=5, stages=[
            {"workflow": "Triage"},
            {"workflow": "Specification"},
            {"workflow": "Implement + Test"},
            {"workflow": "Review"},
            {"workflow": "Verify"},
        ])
        with mock.patch.object(pilot, "is_stopped", return_value=False), \
                mock.patch.object(pilot, "stage_attempts", return_value=5), \
                mock.patch.object(pilot, "deep_diagnose", return_value=verdict), \
                mock.patch.object(pilot, "pause_pipeline") as pause, \
                mock.patch.object(pilot, "recent_stage_text", return_value="history"), \
                mock.patch.object(pilot, "write_question", return_value={}) as write, \
                mock.patch.object(pilot, "save") as save:
            pilot.diag_sweep(conf, [running])

        pause.assert_called_once_with(conf, "Починить отчёт")
        self.assertEqual(write.call_args.args[0], "looping-task")
        self.assertEqual(write.call_args.args[2], "Implement + Test")
        save.assert_called_once()

    def test_stopped_pipeline_is_not_diagnosed_again(self):
        running = dict(
            self.task,
            state="running",
            title="[auto] [3/5 Implement + Test] Починить отчёт",
        )
        conf = dict(self.conf, deep_diag_rounds=5)
        with mock.patch.object(pilot, "is_stopped", return_value=True), \
                mock.patch.object(pilot, "deep_diagnose") as diagnose:
            pilot.diag_sweep(conf, [running])

        diagnose.assert_not_called()

    def test_live_sweep_diagnoses_each_work_only_once(self):
        running = dict(
            self.task,
            state="running",
            title="[auto] [3/5 Implement + Test] Починить отчёт",
        )
        conf = dict(self.conf, deep_diag_rounds=5)
        with mock.patch.object(pilot, "is_stopped", return_value=False), \
                mock.patch.object(pilot, "cap_rescues", return_value=1), \
                mock.patch.object(pilot, "deep_diagnose") as diagnose:
            pilot.diag_sweep(conf, [running])

        diagnose.assert_not_called()

    def test_terminal_route_does_not_repeat_spent_diagnosis(self):
        self.repairs["Починить отчёт"] = {"status": "resumed"}
        with mock.patch.object(pilot, "cap_rescues", return_value=1), \
                mock.patch.object(pilot, "brain") as brain, \
                mock.patch.object(pilot, "begin_diag_repair") as begin:
            verdict = pilot.deep_diagnose(
                self.conf, "Починить отчёт", "Review", 6,
                [self.task], repair_task=self.task)

        self.assertIsNone(verdict)
        brain.assert_not_called()
        begin.assert_not_called()

    def test_started_repair_skips_owner_question_and_pipeline_pause_at_limits(self):
        verdict = {"причина": "технический сбой", "решение": "исправить",
                   "нужен_владелец": False, "repair_started": True}
        for attempts, hard_limit in ((5, 99), (8, 8)):
            with self.subTest(attempts=attempts, hard_limit=hard_limit), \
                    mock.patch.object(pilot, "load_tasks_safe", return_value=[self.task]), \
                    mock.patch.object(pilot, "deep_diagnose", return_value=verdict), \
                    mock.patch.object(pilot, "write_question") as write_question, \
                    mock.patch.object(pilot, "pause_pipeline") as pause_pipeline, \
                    mock.patch.object(pilot, "orchestrator_answer") as answer:
                escalated = pilot.route_question(
                    dict(self.conf, deep_diag_rounds=5, max_stage_attempts=3,
                         max_work_rounds=hard_limit),
                    "looping-task", "Implement + Test", "Implement + Test",
                    "Починить отчёт", "repo-id", "снова упало", "Что делать?",
                    [], "", attempts_so_far=attempts, repair_task=self.task)

            self.assertFalse(escalated)
            write_question.assert_not_called()
            pause_pipeline.assert_not_called()
            answer.assert_not_called()

    def test_loop_rescue_does_not_grant_another_full_round_allowance(self):
        rescues = {"LOOP": 0}

        def cap_rescues(_base, stage):
            return rescues.get(stage, 0)

        def note_cap_rescue(_base, stage):
            rescues[stage] = rescues.get(stage, 0) + 1

        conf = dict(self.conf, deep_diag_rounds=99, max_stage_attempts=3,
                    max_work_rounds=8, max_loop_rescues=1)
        with mock.patch.object(pilot, "loop_baseline", return_value=0), \
                mock.patch.object(pilot, "set_loop_baseline") as set_baseline, \
                mock.patch.object(pilot, "cap_rescues", side_effect=cap_rescues), \
                mock.patch.object(pilot, "note_cap_rescue", side_effect=note_cap_rescue), \
                mock.patch.object(pilot, "orchestrator_answer", return_value={
                    "decision": "answer", "answer": "Исправь только найденную гонку"}), \
                mock.patch.object(pilot, "write_question", return_value={}), \
                mock.patch.object(pilot, "pause_pipeline") as pause:
            first = pilot.route_question(
                conf, "looping-task", "Review", "Implement + Test",
                "Починить отчёт", "repo-id", "снова вернулось", "Что делать?",
                [], "", attempts_so_far=8)
            second = pilot.route_question(
                conf, "looping-task-2", "Review", "Implement + Test",
                "Починить отчёт", "repo-id", "снова вернулось", "Что делать?",
                [], "", attempts_so_far=9)

        self.assertFalse(first)
        self.assertTrue(second)
        pause.assert_called_once_with(conf, "Починить отчёт")
        # Отсчёт обновляется только при настоящей остановке. Автоматическое
        # решение не должно незаметно выдавать ещё восемь кругов.
        set_baseline.assert_called_once_with("Починить отчёт", 9)

    def test_cycle_starts_repair_after_repeated_terminal_failure_and_spent_diag(self):
        answer = '{"причина":"повторный технический сбой","решение":"исправить",' \
                 '"нужен_владелец":false}'

        failed = dict(self.task, state="failed")

        def api_for_cycle(path, body=None):
            self.api_calls.append((path, body))
            if path in ("/tasks?limit=100", "/tasks?limit=60",
                        "/tasks?limit=200"):
                return {"tasks": [failed], "next_cursor": None}
            if path == "/workers":
                return {"workers": []}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": []}
            if path == "/tasks/looping-task":
                return {
                    "task": {
                        "repository_id": "repo-id",
                        "worker_id": "worker-id",
                        "context": "Прошлая работа лежит в ветке factory/old-work",
                    },
                    "workflow": {"title": "Implement + Test",
                                 "revision_id": "revision-id"},
                    "attempts": [{"error": "обычный повторный сбой"}],
                }
            raise AssertionError(path)

        conf = dict(self.conf, stages=[{"workflow": "Implement + Test"}],
                    deep_diag_rounds=5, max_stage_attempts=3,
                    max_work_rounds=99, auto_plan=False)
        state = {"processed": [], "epics_processed": []}
        noops = ("cleanup_completed_plan_cards", "write_dashboard",
                 "provider_limits_tick", "detect_limits", "record_new_works",
                 "budget_guard", "handle_epics", "diag_sweep",
                 "rescue_queued", "supersede_stale_questions", "handle_answers",
                 "advance_epics")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=api_for_cycle))
            stack.enter_context(mock.patch.object(pilot, "best_workers", return_value={}))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                                                  return_value={0: 0}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_attempts", return_value=5))
            stack.enter_context(mock.patch.object(
                pilot, "create_task", side_effect=lambda body, _conf:
                self.created.append(body) or {"task": {"id": "repair-task"}}))
            stack.enter_context(mock.patch.object(pilot, "brain", return_value=(answer, "brain")))
            stack.enter_context(mock.patch.object(pilot, "cap_rescues", return_value=1))
            note_diag = stack.enter_context(mock.patch.object(pilot, "note_cap_rescue"))
            stack.enter_context(mock.patch.object(pilot, "orchestrator_answer",
                return_value={"decision": "owner", "reason": "нужен контроль"}))
            stack.enter_context(mock.patch.object(pilot, "write_question", return_value={}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(conf, state)

        note_diag.assert_not_called()
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0]["title"], failed["title"])
        self.assertIn("исправить", self.created[0]["context"])
        self.assertEqual(self.repairs["Починить отчёт"]["status"], "resumed")


class PipelineWatchTests(unittest.TestCase):
    def setUp(self):
        self.now = 10_000
        self.memory = {}
        self.work_status = {}
        self.created = []
        self.notifications = []
        self.conf = {
            "stages": [
                {"workflow": "Specification"},
                {"workflow": "Implement"},
                {"workflow": "Review"},
            ],
            "timeout_seconds": 900,
        }
        self.workflows = {
            "Specification": {"enabled": True, "revision_id": "rev-spec"},
            "Implement": {"enabled": True, "revision_id": "rev-impl"},
            "Review": {"enabled": True, "revision_id": "rev-review"},
        }
        self.workers = {
            "worker": {"id": "worker-id", "online": True, "health": "healthy"}
        }
        self.patches = [
            mock.patch.object(pilot, "load", side_effect=self._load),
            mock.patch.object(pilot, "save", side_effect=self._save),
            mock.patch.object(pilot.time, "time", side_effect=lambda: self.now),
            mock.patch.object(pilot, "stage_worker", return_value="worker"),
            mock.patch.object(pilot, "create_task", side_effect=self._create),
            mock.patch.object(pilot, "notify", side_effect=self._notify),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _load(self, path, default=None):
        if path == pilot.STALL_PATH:
            return self.memory
        return default

    def _save(self, path, value):
        if path == pilot.STALL_PATH:
            self.memory = value
        elif path.endswith("/pilot/work_status.json"):
            self.work_status = value

    def _create(self, body, conf):
        self.created.append(body)
        return {"task": {"id": "new-task"}}

    def _notify(self, conf, title, message, **kwargs):
        self.notifications.append((title, message, kwargs))

    @staticmethod
    def task(stage="Specification", state="succeeded", repository_id="repo-id"):
        return {
            "title": f"[auto] [1/3 {stage}] Встроенный патруль",
            "state": state,
            "repository_id": repository_id,
        }

    def watch(self, tasks=None):
        pilot.pipeline_watch(
            self.conf, tasks or [self.task()], self.workflows, self.workers
        )

    def test_waits_before_resuming_lost_transition(self):
        self.watch()
        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Встроенный патруль"]["since"], self.now)

    def test_resumes_once_after_wait_with_same_repository_and_revision(self):
        self.memory = {
            "Встроенный патруль": {"since": self.now - pilot.STALL_WAIT, "nudges": 0}
        }
        self.watch()

        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0]["repository_id"], "repo-id")
        self.assertEqual(self.created[0]["workflow_revision_id"], "rev-impl")
        self.assertEqual(self.created[0]["worker_id"], "worker-id")
        self.assertIn("[2/3 Implement]", self.created[0]["title"])

        self.watch()
        self.assertEqual(len(self.created), 1)

    def test_live_task_clears_stall_and_prevents_duplicate(self):
        self.memory = {
            "Встроенный патруль": {"since": 1, "nudges": 1, "why": "nudged"}
        }
        self.watch([self.task(state="succeeded"), self.task(stage="Implement", state="running")])

        self.assertNotIn("Встроенный патруль", self.memory)
        self.assertEqual(self.created, [])

    def test_owner_pause_is_not_resumed(self):
        self.conf["stopped_pipelines"] = ["Встроенный патруль"]
        self.watch()

        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Встроенный патруль"]["why"], "owner")
        self.assertEqual(self.work_status["Встроенный патруль"]["state"], "stopped_owner")

    def test_completed_pipeline_is_not_resumed(self):
        self.memory = {"Встроенный патруль": {"since": 1, "nudges": 1}}
        self.watch([self.task(stage="Review")])

        self.assertNotIn("Встроенный патруль", self.memory)
        self.assertEqual(self.created, [])

    def test_ignores_task_without_canonical_pipeline_title(self):
        task = self.task()
        task["title"] = "Implement Встроенный патруль"

        self.watch([task])

        self.assertEqual(self.memory, {})
        self.assertEqual(self.created, [])

    def test_gives_up_after_two_nudges_and_notifies_only_once(self):
        self.memory = {
            "Встроенный патруль": {
                "since": self.now - pilot.STALL_WAIT,
                "nudges": pilot.STALL_NUDGES,
            }
        }
        with mock.patch.object(
            pilot, "orchestrator_answer", side_effect=AssertionError("external helper called")
        ):
            self.watch()
            self.watch()

        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Встроенный патруль"]["why"], "give_up")
        self.assertEqual(self.work_status["Встроенный патруль"]["state"], "stuck")
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("после двух попыток", self.notifications[0][1])

    def test_verify_pass_is_processed_once(self):
        """A restart after a successful Verify must not merge it a second time."""
        self.conf["stages"] = [{"workflow": "Verify"}]
        self.conf["auto_merge"] = True
        verify = {
            "id": "verify-pass",
            "title": "[auto] [1/1 Verify] Идемпотентный финал",
            "state": "succeeded",
            "repository_id": "repo-id",
        }
        detail = {
            "task": {"repository_id": "repo-id"},
            "workflow": {"title": "Verify"},
            "context": "Branch: factory/idempotent-verify",
            "attempts": [{"result": "PASS\nBRANCH: factory/idempotent-verify"}],
        }
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        journal = os.path.join(temporary.name, "merges.jsonl")

        def fake_api(path, payload=None):
            if path == "/tasks?limit=100":
                return {"tasks": [verify]}
            if path == "/tasks/verify-pass":
                return detail
            if path == "/workers":
                return {"workers": []}
            if path == "/repositories":
                return {"repositories": [{"id": "repo-id",
                                           "remote_identity": "github.com/acme/repo"}]}
            if path == "/workflows":
                return {"workflows": [{"id": "verify-workflow", "enabled": True,
                    "current_revision": {"id": "verify-revision", "title": "Verify"}}]}
            raise AssertionError(path)

        noops = ("cleanup_completed_plan_cards", "write_dashboard",
                 "provider_limits_tick", "detect_limits", "record_new_works",
                 "budget_guard", "handle_epics", "rescue_queued",
                 "supersede_stale_questions", "handle_answers", "advance_epics",
                 "autostart_plan")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "best_workers", return_value={}))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                                                  side_effect=lambda day_start, _week_start:
                                                  {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "area_extend"))
            stack.enter_context(mock.patch.object(pilot, "collect_ideas"))
            stack.enter_context(mock.patch.object(pilot, "decide",
                                                  return_value={"action": "stop"}))
            stack.enter_context(mock.patch.object(pilot, "gh_json", return_value={"ahead_by": 1}))
            merge = stack.enter_context(mock.patch.object(pilot, "gh_merge", return_value=(True, "merged")))
            final = stack.enter_context(mock.patch.object(pilot, "mark_final"))
            stack.enter_context(mock.patch.object(pilot, "deploy_after_merge"))
            stack.enter_context(mock.patch.object(pilot, "MERGES_PATH", journal))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(self.conf, {"processed": []})
            pilot.cycle(self.conf, {"processed": []})

        self.assertEqual(merge.call_count, 1)
        final.assert_called_once_with("verify-pass", "Verify", True)
        with open(journal, encoding="utf-8") as entries:
            records = [json.loads(line) for line in entries]
        self.assertEqual([record["task_id"] for record in records], ["verify-pass"])


class PlanCardCleanupTest(unittest.TestCase):
    def setUp(self):
        self.idea = {"id": "idea-1", "state": "in_work", "task_id": "spec-new"}
        self.tasks = [
            {"id": "spec-new", "title": "[auto] [2/5 Specification] Очистить план",
             "state": "succeeded", "created_at": "2026-08-08T10:00:00Z"},
            {"id": "verify-new", "title": "[auto] [5/5 Verify] Очистить план",
             "state": "succeeded", "created_at": "2026-08-08T11:00:00Z"},
        ]

    def run_cleanup(self, final_ok=True, questions=None):
        updates = []
        with mock.patch.object(pilot, "ideas_all", return_value=[self.idea]), \
                mock.patch.object(pilot, "set_idea",
                                  side_effect=lambda idea_id, **fields: updates.append((idea_id, fields))), \
                mock.patch.object(pilot, "load_questions", return_value=questions or []), \
                mock.patch.object(pilot, "final_ok", return_value=final_ok) as verdict:
            closed = pilot.cleanup_completed_plan_cards(self.tasks, 5)
        return closed, updates, verdict

    def test_accepted_final_stage_closes_linked_card(self):
        closed, updates, verdict = self.run_cleanup()

        self.assertEqual(closed, ["idea-1"])
        self.assertEqual(updates, [("idea-1", {"state": "done"})])
        verdict.assert_called_once_with("verify-new", strict=True)

    def test_planned_card_is_removed_from_autostart_candidates(self):
        self.idea["state"] = "planned"
        _, updates, _ = self.run_cleanup()

        self.assertEqual(updates[0][1]["state"], "done")
        candidates = [self.idea | updates[0][1]]
        self.assertEqual([x for x in candidates if x["state"] == "planned"], [])

    def test_intermediate_failure_cancel_or_unaccepted_final_stay_open(self):
        for state, accepted, questions in (
                ("running", True, []),
                ("failed", True, []),
                ("cancelled", True, []),
                ("succeeded", False, []),
                ("succeeded", True, [{"task_id": "verify-new", "status": "open"}])):
            with self.subTest(state=state, accepted=accepted, questions=questions):
                self.tasks[-1]["state"] = state
                closed, updates, _ = self.run_cleanup(accepted, questions)
                self.assertEqual(closed, [])
                self.assertEqual(updates, [])

    def test_success_before_linked_run_does_not_close_card(self):
        self.tasks[-1]["created_at"] = "2026-08-08T09:00:00Z"
        closed, updates, verdict = self.run_cleanup()

        self.assertEqual(closed, [])
        self.assertEqual(updates, [])
        verdict.assert_not_called()

    def test_card_without_linked_task_does_not_close_by_title(self):
        self.idea["task_id"] = ""
        closed, updates, verdict = self.run_cleanup()

        self.assertEqual(closed, [])
        self.assertEqual(updates, [])
        verdict.assert_not_called()


class OrphanedPausedPipelineCleanupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.conf_path = os.path.join(self.temporary.name, "config.json")
        self.conf = {"stopped_pipelines": ["Оплата продавцу"], "untouched": 7}
        pilot.save(self.conf_path, dict(self.conf))

    def cleanup(self, tasks=None, ideas=None, questions=None):
        with mock.patch.object(pilot, "CONF_PATH", self.conf_path), \
                mock.patch.object(pilot, "ideas_all", return_value=ideas or []), \
                mock.patch.object(pilot, "load_questions", return_value=questions or []):
            return pilot.cleanup_orphaned_paused_pipelines(self.conf, tasks or [])

    def disk_config(self):
        return pilot.load(self.conf_path, None)

    def reset_pause(self):
        self.conf["stopped_pipelines"] = ["Оплата продавцу"]
        pilot.save(self.conf_path, dict(self.conf))

    def test_orphan_is_removed_from_memory_and_disk(self):
        self.assertTrue(self.cleanup())
        self.assertEqual(self.conf["stopped_pipelines"], [])
        self.assertEqual(self.disk_config(), {"stopped_pipelines": [], "untouched": 7})

    def test_only_open_plan_states_keep_the_pause(self):
        for state in ("new", "planned", "in_work", "done", "rejected"):
            with self.subTest(state=state):
                self.reset_pause()
                self.cleanup(ideas=[{"title": "  ОПЛАТА ПРОДАВЦУ ", "state": state}])
                expected = ["Оплата продавцу"] if state in (
                    "new", "planned", "in_work") else []
                self.assertEqual(self.conf["stopped_pipelines"], expected)
                self.assertEqual(self.disk_config()["stopped_pipelines"], expected)

    def test_only_exact_open_question_keeps_the_pause(self):
        cases = (
            ({"title": "оплата продавцу", "status": "open"}, True),
            ({"title": "Оплата продавцу", "status": "resolved"}, False),
            ({"title": "Оплата", "status": "open"}, False),
            ({"title": "Оплата продавцу срочно", "status": "open"}, False),
        )
        for question, kept in cases:
            with self.subTest(question=question):
                self.reset_pause()
                self.cleanup(questions=[question])
                self.assertEqual(bool(self.conf["stopped_pipelines"]), kept)

    def test_only_exact_live_task_keeps_the_pause(self):
        for state in ("preparing", "queued", "running", "succeeded", "failed"):
            with self.subTest(state=state):
                self.reset_pause()
                task = {"title": "[auto] [3/5 Implement] ОПЛАТА ПРОДАВЦУ",
                        "state": state}
                self.cleanup(tasks=[task])
                self.assertEqual(bool(self.conf["stopped_pipelines"]), state in (
                    "preparing", "queued", "running"))

    def test_similar_task_name_does_not_keep_the_pause(self):
        task = {"title": "[auto] [1/5 Triage] Оплата", "state": "running"}
        self.assertTrue(self.cleanup(tasks=[task]))
        self.assertEqual(self.conf["stopped_pipelines"], [])

    def test_read_or_write_failure_keeps_memory_and_disk_aligned(self):
        before = dict(self.conf)
        with mock.patch.object(pilot, "CONF_PATH", self.conf_path), \
                mock.patch.object(pilot, "load", return_value=None):
            self.assertFalse(pilot.cleanup_orphaned_paused_pipelines(self.conf, []))
        self.assertEqual(self.conf, before)
        self.assertEqual(self.disk_config(), before)

        with mock.patch.object(pilot, "CONF_PATH", self.conf_path), \
                mock.patch.object(pilot, "ideas_all", return_value=[]), \
                mock.patch.object(pilot, "load_questions", return_value=[]), \
                mock.patch.object(pilot, "save", side_effect=OSError("disk full")):
            self.assertFalse(pilot.cleanup_orphaned_paused_pipelines(self.conf, []))
        self.assertEqual(self.conf, before)
        self.assertEqual(self.disk_config(), before)

    def test_cycle_cleans_after_stale_questions_are_superseded(self):
        questions = [{"title": "Оплата продавцу", "status": "open"}]

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": []}
            if path in ("/workers", "/repositories", "/workflows"):
                return {path.strip("/"): []}
            raise AssertionError(path)

        def supersede(_tasks):
            questions[0]["status"] = "obsolete"

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "handle_answers", "advance_epics", "retry_pending_factory_deploy",
            "autostart_plan",
        )
        conf = dict(self.conf, stages=[{"workflow": "Implement"}], auto_plan=False)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "CONF_PATH", self.conf_path))
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "ideas_all", return_value=[]))
            stack.enter_context(mock.patch.object(pilot, "load_questions",
                                                  return_value=questions))
            stack.enter_context(mock.patch.object(pilot, "supersede_stale_questions",
                                                  side_effect=supersede))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(conf, {"processed": []})

        self.assertEqual(conf["stopped_pipelines"], [])
        self.assertEqual(self.disk_config()["stopped_pipelines"], [])


class BrainFallbackTest(unittest.TestCase):
    """После лимита один провайдер должен оставаться заблокирован до
    следующего вызова brain(), а не тратить попытку снова."""

    def setUp(self):
        self.conf = {"brain_chain": [
            {"cli": "codex", "model": "gpt-5.6-sol", "provider": "codex"},
            {"cli": "claude", "model": "fable", "provider": "claude"},
        ]}
        self.limits_store = {}
        self.note_limit_calls = []

        def fake_note_limit(conf, provider, evidence, resets_at=""):
            self.note_limit_calls.append((conf, provider, evidence))
            self.limits_store[provider] = {
                "manual_off": False, "state": "exhausted", "resets_at": "",
                "detected_at": "2026-08-08T00:00:00Z", "detected_epoch": time.time(),
                "evidence": evidence,
            }

        def fake_run(cmd, **kwargs):
            if cmd[0] == "codex":
                return mock.Mock(stdout="", stderr="rate limit reached, try again later")
            return mock.Mock(stdout="ответ мозга", stderr="")

        self.codex_calls = []
        self.claude_calls = []

        def counting_run(cmd, **kwargs):
            (self.codex_calls if cmd[0] == "codex" else self.claude_calls).append(cmd)
            return fake_run(cmd, **kwargs)

        self.patches = [
            mock.patch.object(pilot, "load_limits", side_effect=lambda: dict(self.limits_store)),
            mock.patch.object(pilot, "note_limit", side_effect=fake_note_limit),
            mock.patch.object(pilot, "engine_down", return_value=False),
            mock.patch.object(pilot, "save"),
            mock.patch.object(pilot.subprocess, "run", side_effect=counting_run),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_expired_provider_is_skipped_on_next_call(self):
        out, eng = pilot.brain(self.conf, "прогони задачу")

        self.assertEqual(out, "ответ мозга")
        self.assertEqual(eng["provider"], "claude")
        self.assertEqual(len(self.note_limit_calls), 1)
        passed_conf, provider, evidence = self.note_limit_calls[0]
        self.assertIs(passed_conf, self.conf)
        self.assertEqual(provider, "codex")
        self.assertIn("rate limit", evidence)
        self.assertEqual(len(self.codex_calls), 1)
        self.assertEqual(len(self.claude_calls), 1)

        out2, eng2 = pilot.brain(self.conf, "вторая задача")

        self.assertEqual(out2, "ответ мозга")
        self.assertEqual(eng2["provider"], "claude")
        self.assertEqual(len(self.note_limit_calls), 1, "codex не должен снова получать запись лимита")
        self.assertEqual(len(self.codex_calls), 1, "codex не должен запускаться повторно, пока блок активен")
        self.assertEqual(len(self.claude_calls), 2)

    def test_expired_provider_is_skipped_later_in_same_chain(self):
        self.conf["brain_chain"] = [
            {"cli": "codex", "model": "gpt-5.6-sol", "provider": "codex"},
            {"cli": "codex", "model": "gpt-5.6-terra", "provider": "codex"},
            {"cli": "claude", "model": "fable", "provider": "claude"},
        ]

        out, eng = pilot.brain(self.conf, "прогони задачу")

        self.assertEqual(out, "ответ мозга")
        self.assertEqual(eng["provider"], "claude")
        self.assertEqual(len(self.note_limit_calls), 1)
        self.assertEqual(len(self.codex_calls), 1,
                         "вторая модель исчерпанного провайдера должна быть пропущена")
        self.assertEqual(len(self.claude_calls), 1)


class PlanAutostartTest(unittest.TestCase):
    def setUp(self):
        self.conf = {
            "stages": [{"workflow": "Triage", "workers": {"medium": "triager"}}],
            "max_parallel_works": 3,
        }
        self.workflows = {"Triage": {"enabled": True, "revision_id": "wf-triage"}}
        self.workers = {"triager": {"id": "worker-triage", "online": True,
                                    "health": "healthy"}}
        self.cards = [
            {"id": "later", "title": "Вторая", "state": "planned", "order": 20,
             "run_generation": "later-run"},
            {"id": "top", "title": "Первая", "why": "важнее", "source": "находка",
             "repo": "repo-1", "origin": "agent", "state": "planned", "order": 10,
             "run_generation": "first-run"},
        ]

    def test_completed_automation_findings_are_added_to_plan_once(self):
        tasks = [
            {"id": "automation-ok", "title": "Patrol: run now",
             "request_key": "automation:patrol:schedule:run:one",
             "state": "succeeded"},
            {"id": "automation-failed", "title": "Patrol: scheduled",
             "request_key": "automation:patrol:schedule:two",
             "state": "failed"},
            {"id": "pipeline", "title": "[auto] [1/1 Triage] Work",
             "request_key": "regular-task", "state": "succeeded"},
        ]
        detail = {
            "task": {"repository_id": "repo-1"},
            "workflow": {"title": "Factory Patrol"},
            "attempts": [{"result": "НАХОДКА: Offline worker - stale worktrees"}],
        }
        state = {}

        with mock.patch.object(pilot, "api", return_value=detail) as api, \
                mock.patch.object(pilot, "collect_ideas", return_value=1) as collect:
            self.assertEqual(pilot.collect_automation_findings(state, tasks), 1)
            self.assertEqual(pilot.collect_automation_findings(state, tasks), 0)

        api.assert_called_once_with("/tasks/automation-ok")
        collect.assert_called_once_with(
            "НАХОДКА: Offline worker - stale worktrees",
            "repo-1",
            "Automation: Factory Patrol",
        )
        self.assertEqual(
            state["automation_results_processed"],
            ["automation-ok", "automation-failed"],
        )

    @mock.patch.object(pilot.uuid, "uuid4", side_effect=["generation-1", "generation-2"])
    @mock.patch.object(pilot, "set_idea")
    def test_each_explicit_planning_gets_a_new_generation(self, set_idea, _uuid):
        pilot.plan_idea("top")
        pilot.plan_idea("top")

        generations = [call.kwargs["run_generation"] for call in set_idea.call_args_list]
        self.assertEqual(generations, ["generation-1", "generation-2"])
        for call in set_idea.call_args_list:
            self.assertEqual(call.kwargs["state"], "planned")
            self.assertEqual(call.kwargs["task_id"], "")

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "new-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_starts_top_planned_card_with_triage_context(self, _limits, _questions,
                                                         ideas, create, set_idea,
                                                         note_work, notify):
        ideas.return_value = self.cards

        result = pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(result, "new-task")
        body, passed_conf = create.call_args.args
        self.assertIs(passed_conf, self.conf)
        self.assertEqual(body["title"], "[auto] [1/1 Triage] Первая")
        self.assertIn("Это этап Triage", body["context"])
        self.assertIn("Зачем: важнее", body["context"])
        set_idea.assert_called_once_with("top", state="in_work", task_id="new-task")
        note_work.assert_called_once()
        notify.assert_called_once()
        self.assertEqual(pilot.notify_group("Взял из Плана"), "routine")

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "new-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    @mock.patch.object(pilot, "api")
    def test_legacy_factory_alias_resolves_to_repository_id(
            self, api, _limits, _questions, ideas, create, set_idea,
            _note_work, _notify):
        self.cards[1]["repo"] = "factory"
        ideas.return_value = self.cards
        api.return_value = {"repositories": [{
            "id": "factory-repo-id",
            "remote_identity": "github.com/timafen/factory",
        }]}

        pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(create.call_args.args[0]["repository_id"], "factory-repo-id")
        set_idea.assert_called_once_with(
            "top", state="in_work", task_id="new-task", repo="factory-repo-id")

    @mock.patch.object(pilot, "create_task")
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions")
    def test_three_unique_active_or_owner_waiting_works_fill_slots(self, questions,
                                                                  ideas, create):
        ideas.return_value = self.cards
        questions.return_value = [{"task_id": "waiting", "status": "open"}]
        tasks = [
            {"id": "a1", "title": "[auto] [1/5 Triage] A", "state": "running"},
            {"id": "a2", "title": "[auto] [2/5 Specification] A", "state": "queued"},
            {"id": "b", "title": "[auto] [1/5 Triage] B", "state": "preparing"},
            {"id": "waiting", "title": "[auto] [2/5 Specification] C", "state": "failed"},
        ]

        self.assertIsNone(pilot.autostart_plan(self.conf, tasks, self.workflows,
                                               self.workers))
        create.assert_not_called()

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "fourth-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_default_limit_starts_a_fourth_independent_work(
            self, _limits, _questions, ideas, _create, _set_idea,
            _note_work, _notify):
        conf = dict(self.conf)
        conf.pop("max_parallel_works")
        ideas.return_value = self.cards
        tasks = [
            {"id": "a", "title": "[auto] [1/5 Triage] A", "state": "running"},
            {"id": "b", "title": "[auto] [2/5 Specification] B", "state": "queued"},
            {"id": "c", "title": "[auto] [3/5 Implement + Test] C", "state": "running"},
        ]

        result = pilot.autostart_plan(conf, tasks, self.workflows, self.workers)

        self.assertEqual(result, "fourth-task")

    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_creation_failure_leaves_card_planned(self, _limits, _questions, ideas,
                                                  set_idea):
        ideas.return_value = self.cards
        with mock.patch.object(pilot, "create_task", side_effect=RuntimeError("day_task_cap")):
            with self.assertRaisesRegex(RuntimeError, "day_task_cap"):
                pilot.autostart_plan(self.conf, [], self.workflows, self.workers)
        set_idea.assert_not_called()

    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_missing_created_task_id_leaves_card_planned(self, _limits, _questions,
                                                         ideas, _create, set_idea):
        ideas.return_value = self.cards

        with self.assertRaisesRegex(RuntimeError, "no task.id"):
            pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        set_idea.assert_not_called()

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_retry_after_uncertain_post_uses_same_card_request_key(
            self, _limits, _questions, ideas, set_idea, _note_work, _notify):
        ideas.return_value = self.cards
        seen_keys = []

        def uncertain_then_idempotent(body, _conf):
            seen_keys.append(body["request_key"])
            if len(seen_keys) == 1:
                raise TimeoutError("response lost after create")
            return {"task": {"id": "created-on-first-post"}}

        with mock.patch.object(pilot, "create_task", side_effect=uncertain_then_idempotent):
            with self.assertRaises(TimeoutError):
                pilot.autostart_plan(self.conf, [], self.workflows, self.workers)
            result = pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(result, "created-on-first-post")
        self.assertEqual(len(set(seen_keys)), 1)
        self.assertTrue(seen_keys[0].startswith("plan-autostart:top:"))
        self.assertEqual(set_idea.call_args_list[-1], mock.call(
            "top", state="in_work", task_id="created-on-first-post"))

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "next-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_card_without_repository_is_explained_and_does_not_block_next(
            self, _limits, _questions, ideas, create, set_idea, _note_work, notify):
        self.cards[0]["order"] = 1
        ideas.return_value = self.cards

        result = pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(result, "next-task")
        self.assertEqual(create.call_args.args[0]["repository_id"], "repo-1")
        self.assertIn(mock.call("later", state="new",
                                reason="Не запущено автоматически: сначала выберите проект."),
                      set_idea.call_args_list)
        self.assertIn("сначала выберите проект", notify.call_args_list[0].kwargs["body"])

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task")
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_invalid_repository_is_explained_and_does_not_block_next(
            self, _limits, _questions, ideas, create, set_idea, _note_work, notify):
        self.cards[0]["repo"] = "repo-2"
        self.cards[0]["order"] = 20
        self.cards[1]["repo"] = "missing-repo"
        create.side_effect = [
            RuntimeError("repository_not_advertised: missing-repo"),
            {"task": {"id": "next-task"}},
        ]
        ideas.return_value = self.cards

        result = pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(result, "next-task")
        self.assertEqual(create.call_args_list[1].args[0]["repository_id"], "repo-2")
        self.assertIn(mock.call(
            "top", state="new",
            reason="Не запущено автоматически: у карточки указан несуществующий проект. Выберите проект заново."),
            set_idea.call_args_list)
        self.assertIn("несуществующий проект", notify.call_args_list[0].kwargs["body"])

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "new-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_new_planning_generation_creates_a_new_request_key(
            self, _limits, _questions, ideas, create, _set_idea, _note_work, _notify):
        card = self.cards[1]
        card["run_generation"] = "second-run"
        ideas.return_value = [card]

        pilot.autostart_plan(self.conf, [], self.workflows, self.workers)

        self.assertEqual(create.call_args.args[0]["request_key"],
                         "plan-autostart:top:second-run")

    def test_cycle_does_not_run_legacy_pipeline_patrol(self):
        tasks = [
            {"id": "a", "title": "[auto] [1/2 Triage] A", "state": "running"},
            {"id": "b", "title": "[auto] [1/2 Triage] B", "state": "running"},
        ]

        def fake_api(path, payload=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path == "/workers":
                return {"workers": list(self.workers.values())}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": [{"id": "workflow", "enabled": True,
                    "current_revision": {"id": "wf-triage", "title": "Triage"}}]}
            raise AssertionError(path)

        noops = ("cleanup_completed_plan_cards", "write_dashboard",
                 "provider_limits_tick", "detect_limits", "record_new_works",
                 "budget_guard", "handle_epics", "rescue_queued",
                 "supersede_stale_questions", "handle_answers", "advance_epics")
        state = {"processed": [], "epics_processed": []}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "best_workers",
                                                  return_value=self.workers))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_overloaded",
                                                  return_value=False))
            watch = stack.enter_context(mock.patch.object(pilot, "pipeline_watch"))
            create = stack.enter_context(mock.patch.object(pilot, "create_task"))
            ideas = stack.enter_context(mock.patch.object(pilot, "ideas_all",
                return_value=self.cards))
            stack.enter_context(mock.patch.object(pilot, "load_questions", return_value=[]))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(self.conf, state)

        watch.assert_not_called()
        self.assertGreaterEqual(ideas.call_count, 1)

    def test_successful_stage_preserves_files_declared_in_report(self):
        report = "ОБЛАСТЬ: pilot/pilot.py, docs/additional.md"
        task = {"id": "done", "title": "[auto] [1/2 Implement] Счётчик",
                "state": "succeeded"}
        detail = {"task": {"repository_id": "repo-1"},
                  "workflow": {"title": "Implement"},
                  "attempts": [{"result": report}]}

        def fake_api(path, payload=None):
            if path == "/tasks?limit=100":
                return {"tasks": [task]}
            if path == "/tasks/done":
                return detail
            if path == "/workers":
                return {"workers": []}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": []}
            raise AssertionError(path)

        conf = {"stages": [{"workflow": "Implement"}, {"workflow": "Review"}],
                "auto_plan": False}
        state = {"processed": [], "epics_processed": []}
        saved = {}
        noops = ("cleanup_completed_plan_cards", "write_dashboard",
                 "provider_limits_tick", "detect_limits", "record_new_works",
                 "budget_guard", "handle_epics", "rescue_queued",
                 "supersede_stale_questions", "handle_answers", "advance_epics",
                 "collect_ideas", "route_question")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "best_workers", return_value={}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_overloaded",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "load", side_effect=lambda path, default=None:
                saved.get(path, default)))
            stack.enter_context(mock.patch.object(
                pilot, "save", side_effect=lambda path, value:
                saved.__setitem__(path, value)))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "stop", "reason": "test"}))
            stack.enter_context(mock.patch.object(pilot, "ideas_all", return_value=[]))
            stack.enter_context(mock.patch.object(pilot, "load_questions", return_value=[]))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)

        self.assertEqual(saved[pilot.AREAS_PATH]["Счётчик"], [
            "repo-1::docs/additional.md", "repo-1::pilot/pilot.py",
        ])


class PlanManualTaskTest(unittest.TestCase):
    def test_task_action_promotes_card_and_creates_task(self):
        fastapi = types.ModuleType("fastapi")
        responses = types.ModuleType("fastapi.responses")

        class Router:
            def get(self, *_args, **_kwargs):
                return lambda func: func

            post = get

        fastapi.APIRouter = Router
        fastapi.Form = lambda default, **_kwargs: default
        fastapi.HTTPException = RuntimeError
        responses.HTMLResponse = object
        responses.RedirectResponse = object
        with mock.patch.dict(sys.modules, {
                "pilot": pilot, "fastapi": fastapi,
                "fastapi.responses": responses}):
            plan = importlib.import_module("intake.plan")

        card = {
            "id": "manual-card",
            "title": "Запустить вручную",
            "why": "владелец выбрал эту работу",
            "kind": "idea",
            "repo": "repo-1",
        }
        conf = {"stages": [{"workflow": "Triage"}], "timeout_seconds": 900}
        created = {"task": {"id": "manual-task"}}
        with mock.patch.object(plan.pilot, "ideas_all", return_value=[card]), \
                mock.patch.object(plan.pilot, "load", return_value=conf), \
                mock.patch.object(plan.pilot, "api", side_effect=[
                    {"workers": [{"id": "worker-1"}]},
                    {"workflows": [{"enabled": True, "current_revision": {
                        "id": "workflow-1", "title": "Triage"}}]},
                ]), \
                mock.patch.object(plan.pilot, "best_workers", return_value={
                    "triager": {"id": "worker-1"}}), \
                mock.patch.object(plan.pilot, "first_stage", return_value=("Triage", 1)), \
                mock.patch.object(plan.pilot, "stage_worker", return_value="triager"), \
                mock.patch.object(plan.pilot, "create_task", return_value=created) as create, \
                mock.patch.object(plan.pilot, "note_work") as note_work, \
                mock.patch.object(plan.pilot, "set_idea") as set_idea:
            result = plan.idea_action("manual-card", action="task")

        self.assertEqual(result, {"ok": True})
        body = create.call_args.args[0]
        self.assertEqual(body["title"], "[auto] [1/1 Triage] Запустить вручную")
        self.assertEqual(body["repository_id"], "repo-1")
        uuid.UUID(body["request_key"])
        note_work.assert_called_once()
        set_idea.assert_called_once_with(
            "manual-card", state="in_work", task_id="manual-task")


class StageWorkerCapacityTests(unittest.TestCase):
    def setUp(self):
        self.conf = {"stages": [{
            "workflow": "Implement + Test",
            "workers": {"low": "preferred", "medium": "preferred", "high": "spare"},
        }]}

    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_saturated_preferred_worker_uses_available_configured_worker(self, _limits):
        workers = {
            "preferred": {"online": True, "health": "healthy", "capacity": 1, "active_count": 1},
            "spare": {"online": True, "health": "healthy", "capacity": 2, "active_count": 0},
        }

        selected = pilot.stage_worker(
            self.conf, "Implement + Test", "medium", workers)

        self.assertEqual(selected, "spare")

    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_all_saturated_workers_keep_preferred_route_queued(self, _limits):
        workers = {
            "preferred": {"online": True, "health": "healthy", "capacity": 1, "active_count": 1},
            "spare": {"online": True, "health": "healthy", "capacity": 1, "active_count": 1},
        }

        selected = pilot.stage_worker(
            self.conf, "Implement + Test", "medium", workers)

        self.assertEqual(selected, "preferred")

    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_retention_full_preferred_worker_uses_spare(self, _limits):
        workers = {
            "preferred": {
                "online": True, "health": "healthy", "capacity": 2,
                "active_count": 0,
                "repositories": [{"id": "factory", "retained_count": 10}],
            },
            "spare": {
                "online": True, "health": "healthy", "capacity": 2,
                "active_count": 0,
                "repositories": [{"id": "factory", "retained_count": 0}],
            },
        }

        selected = pilot.stage_worker(
            self.conf, "Implement + Test", "medium", workers)

        self.assertEqual(selected, "spare")

    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_exact_escalation_queues_on_high_tier_instead_of_falling_back(self, _limits):
        workers = {
            "preferred": {"online": True, "health": "healthy", "capacity": 2, "active_count": 0},
            "spare": {"online": True, "health": "healthy", "capacity": 1, "active_count": 1},
        }

        selected = pilot.stage_worker(
            self.conf, "Implement + Test", "high", workers, exact_tier=True)

        self.assertEqual(selected, "spare")

    def test_capability_rank_orders_reasoning_within_sol(self):
        self.assertLess(pilot.worker_capability_rank("codex-sol-low"),
                        pilot.worker_capability_rank("codex-sol-medium"))
        self.assertLess(pilot.worker_capability_rank("codex-sol-medium"),
                        pilot.worker_capability_rank("codex-sol-high"))


class AnswerEscalationTests(unittest.TestCase):
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_repeated_stage_really_uses_stronger_worker(self, _limits):
        conf = {
            "stages": [{
                "workflow": "Implement + Test",
                "workers": {
                    "low": "codex-terra-medium",
                    "medium": "codex-sol-medium",
                    "high": "codex-sol-high",
                },
            }],
            "timeout_seconds": 900,
        }
        question = {
            "id": "question-id",
            "task_id": "source-task",
            "status": "answered",
            "answer": "Исправь конкретный дефект",
            "resume_stage": "Implement + Test",
            "stage": "Review",
            "title": "Оживить работу",
            "repository_id": "repo-id",
        }
        workers = {
            "codex-terra-medium": {
                "id": "terra", "online": True, "health": "healthy",
                "capacity": 2, "active_count": 0,
            },
            "codex-sol-medium": {
                "id": "sol-medium", "online": True, "health": "healthy",
                "capacity": 2, "active_count": 0,
            },
            # Busy is intentional: a real escalation must queue here instead
            # of silently falling back to sol-medium.
            "codex-sol-high": {
                "id": "sol-high", "online": True, "health": "healthy",
                "capacity": 1, "active_count": 1,
            },
        }
        created = []
        notifications = []

        with mock.patch.object(pilot, "load_questions", return_value=[question]), \
                mock.patch.object(pilot, "load", return_value=dict(question)), \
                mock.patch.object(pilot, "stage_attempts", return_value=2), \
                mock.patch.object(pilot, "cap_rescues", return_value=0), \
                mock.patch.object(pilot, "note_cap_rescue"), \
                mock.patch.object(pilot, "is_stopped", return_value=False), \
                mock.patch.object(pilot, "live_or_done_at", return_value=None), \
                mock.patch.object(
                    pilot, "create_task",
                    side_effect=lambda body, _conf: created.append(body)
                    or {"task": {"id": "new-task"}},
                ), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(
                    pilot, "notify",
                    side_effect=lambda _conf, title, message, **_kwargs:
                    notifications.append((title, message)),
                ):
            pilot.handle_answers(
                conf,
                {"Implement + Test": {"enabled": True, "revision_id": "revision"}},
                workers,
                [],
            )

        self.assertEqual(created[0]["worker_id"], "sol-high")
        raised = [message for title, message in notifications
                  if title == "Исполнитель повышен"]
        self.assertEqual(len(raised), 1)
        self.assertIn("codex-sol-medium → codex-sol-high", raised[0])


class HostLoadAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.cpu_over = {
            "state": "over", "cpu": {"state": "over"},
            "memory": {"state": "ok"}, "disk": {"state": "ok"},
        }

    def test_guaranteed_slot_allows_any_stage(self):
        for stage in ("Triage", "Specification", "Review",
                      "Implement + Test", "Verify", "Unlisted stage"):
            with self.subTest(stage=stage):
                self.assertTrue(pilot.host_load_admits([], stage, self.cpu_over))

    def test_after_guaranteed_slot_only_light_stages_are_allowed(self):
        tasks = [{"state": "running"}]
        for stage in ("Triage", "Specification", "Review"):
            with self.subTest(stage=stage):
                self.assertTrue(pilot.host_load_admits(tasks, stage, self.cpu_over))
        for stage in ("Implement + Test", "Verify", "Unlisted stage", ""):
            with self.subTest(stage=stage):
                self.assertFalse(pilot.host_load_admits(tasks, stage, self.cpu_over))

    def test_all_active_states_count_towards_the_minimum(self):
        for state in ("running", "queued", "pending", "created", "starting"):
            with self.subTest(state=state):
                self.assertFalse(pilot.host_load_admits(
                    [{"state": state}], "Verify", self.cpu_over))

    def test_memory_or_disk_emergency_blocks_even_the_guaranteed_slot(self):
        for resource in ("memory", "disk"):
            load = dict(self.cpu_over)
            load[resource] = {"state": "over"}
            with self.subTest(resource=resource):
                self.assertFalse(pilot.host_load_admits([], "Triage", load))

    def test_normal_load_or_disabled_guard_preserves_previous_admission(self):
        active = [{"state": "running"}]
        self.assertTrue(pilot.host_load_admits(
            active, "Verify", {"state": "tight"}))
        self.assertTrue(pilot.host_load_admits(
            active, "Verify", self.cpu_over, respect_host_load=False))

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "one"}})
    def test_successful_create_consumes_guaranteed_slot(self, api, _money):
        conf = {"_host_load_snapshot": self.cpu_over, "_host_load_tasks": []}
        body = {"title": "[auto] [3/5 Implement + Test] A"}

        pilot.create_task(body, conf)

        with self.assertRaisesRegex(RuntimeError, "stage deferred"):
            pilot.create_task(body, conf)
        api.assert_called_once()

    def test_overload_does_not_stop_cycle_services(self):
        conf = {"stages": [{"workflow": "Triage", "workers": {}}]}
        state = {"processed": [], "epics_processed": [],
                 "epic_starts_processed": []}

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": []}
            if path == "/workers":
                return {"workers": []}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": []}
            raise AssertionError(path)

        noops = ("cleanup_completed_plan_cards", "write_dashboard",
                 "provider_limits_tick", "detect_limits", "record_new_works",
                 "budget_guard", "handle_epics", "rescue_queued",
                 "supersede_stale_questions", "handle_answers", "advance_epics",
                 "autostart_plan")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value=self.cpu_over))
            watch = stack.enter_context(mock.patch.object(pilot, "pipeline_watch"))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)

        watch.assert_not_called()
        self.assertEqual(conf["_host_load_snapshot"], self.cpu_over)

    @mock.patch.object(pilot, "_age_min", return_value=10)
    @mock.patch.object(pilot, "stage_worker", return_value="healthy-worker")
    @mock.patch.object(pilot, "create_task")
    def test_overload_defers_rescue_without_cancelling_original(
            self, create, stage_worker, _age):
        task = {
            "id": "queued-task", "state": "queued", "worker_id": "sick-id",
            "created_at": "2026-08-09T00:00:00", "title": "Pipeline task",
        }
        detail = {
            "workflow": {"title": "Implement + Test"},
            "context": "keep me queued",
            "task": {"repository_id": "repo-id"},
        }
        conf = {"_host_load_snapshot": self.cpu_over}
        workflows = {
            "Implement + Test": {"enabled": True, "revision_id": "revision-id"}
        }
        workers = {
            "sick-worker": {"id": "sick-id", "online": False},
            "healthy-worker": {
                "id": "healthy-id", "online": True, "health": "healthy",
            },
        }

        with mock.patch.object(pilot, "api", return_value=detail) as api:
            pilot.rescue_queued(conf, [task], workflows, workers)

        api.assert_called_once_with("/tasks/queued-task")
        stage_worker.assert_not_called()
        create.assert_not_called()

    @mock.patch.object(pilot, "_age_min", return_value=10)
    @mock.patch.object(pilot, "complexity_of", return_value="low")
    @mock.patch.object(pilot, "stage_worker", return_value="spare-worker")
    @mock.patch.object(
        pilot, "create_task", return_value={"task": {"id": "replacement-task"}})
    def test_retention_full_worker_is_rescued_while_still_healthy(
            self, create, stage_worker, _complexity, _age):
        task = {
            "id": "queued-task", "state": "queued", "worker_id": "full-id",
            "repository_id": "repo-id", "created_at": "2026-08-09T00:00:00",
            "title": "Pipeline task",
        }
        detail = {
            "workflow": {"title": "Specification"}, "context": "preserve me",
            "task": {"repository_id": "repo-id"},
        }
        workflows = {
            "Specification": {"enabled": True, "revision_id": "revision-id"}
        }
        workers = {
            "full-worker": {
                "id": "full-id", "name": "full-worker", "online": True,
                "health": "healthy", "capacity": 2, "active_count": 0,
                "repositories": [{"id": "repo-id", "retained_count": 10}],
            },
            "spare-worker": {
                "id": "spare-id", "name": "spare-worker", "online": True,
                "health": "healthy", "capacity": 2, "active_count": 0,
                "repositories": [{"id": "repo-id", "retained_count": 0}],
            },
        }

        def fake_api(path, body=None):
            if path == "/tasks/queued-task":
                return detail
            if path == "/tasks/queued-task/cancel" and body == {}:
                return {}
            raise AssertionError((path, body))

        with mock.patch.object(pilot, "api", side_effect=fake_api):
            pilot.rescue_queued({}, [task], workflows, workers)

        routed_workers = stage_worker.call_args.args[3]
        self.assertEqual(routed_workers["full-worker"]["health"], "retention_full")
        self.assertEqual(routed_workers["spare-worker"]["health"], "healthy")
        self.assertEqual(create.call_args.args[0]["worker_id"], "spare-id")


class DashboardSnapshotTest(unittest.TestCase):
    def test_shared_snapshot_uses_original_float_windows(self):
        day_start = 100.0
        week_start = 12.345678
        snapshot = {
            day_start: {"total_tokens": 10},
            week_start: {"total_tokens": 70},
        }

        day, week = pilot.codex_snapshot_windows(
            snapshot, (day_start, week_start))

        self.assertEqual(day["total_tokens"], 10)
        self.assertEqual(week["total_tokens"], 70)


class PostMergeDeployTest(unittest.TestCase):
    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(0, "ok"))
    def test_trading_repository_releases_only_trading_staging(self, run_shell, log):
        conf = {
            "deploy_staging_cmd": "fx staging release",
            "deploy_factory_cmd": "fx factory release",
        }

        result = pilot.deploy_after_merge(
            conf, "github.com/timafen/tarser-operations")

        self.assertEqual(result, 0)
        run_shell.assert_called_once_with("fx staging release")
        self.assertIn("AUTOMATION-STAGING-DEPLOY", log.call_args.args[0])

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(0, "ok"))
    def test_factory_repository_never_releases_trading_staging(self, run_shell, log):
        conf = {"deploy_staging_cmd": "fx staging release"}

        result = pilot.deploy_after_merge(conf, "github.com/timafen/factory")

        self.assertIsNone(result)
        run_shell.assert_not_called()
        self.assertIn("deploy_factory_cmd is not configured", log.call_args.args[0])

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(0, "ok"))
    def test_factory_repository_uses_its_own_release_command(self, run_shell, _log):
        conf = {
            "deploy_staging_cmd": "fx staging release",
            "deploy_factory_cmd": "fx factory release",
        }

        result = pilot.deploy_after_merge(conf, "github.com/timafen/factory.git")

        self.assertEqual(result, 0)
        run_shell.assert_called_once_with("fx factory release")

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(8, "another release is running"))
    def test_busy_factory_release_is_coalesced_for_retry(self, run_shell, _log):
        state = {}
        conf = {"deploy_factory_cmd": "fx factory release"}

        result = pilot.deploy_after_merge(
            conf, "github.com/timafen/factory", state, now=100)
        pilot.deploy_after_merge(
            conf, "github.com/timafen/factory", state, now=110)

        self.assertEqual(result, 8)
        self.assertEqual(state["pending_factory_deploy"], {
            "due": 170, "attempts": 0,
        })
        self.assertEqual(run_shell.call_count, 2)

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(0, "released latest main"))
    def test_pending_factory_release_waits_then_clears_on_success(self, run_shell, _log):
        state = {"pending_factory_deploy": {"due": 160, "attempts": 2}}
        conf = {"deploy_factory_cmd": "fx factory release"}

        self.assertIsNone(pilot.retry_pending_factory_deploy(conf, state, now=159))
        self.assertEqual(
            pilot.retry_pending_factory_deploy(conf, state, now=160), 0)

        run_shell.assert_called_once_with("fx factory release")
        self.assertNotIn("pending_factory_deploy", state)

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(8, "still running"))
    def test_pending_factory_release_backs_off_while_lock_is_busy(self, _run_shell, _log):
        state = {"pending_factory_deploy": {"due": 100, "attempts": 0}}

        result = pilot.retry_pending_factory_deploy(
            {"deploy_factory_cmd": "fx factory release"}, state, now=100)

        self.assertEqual(result, 8)
        self.assertEqual(state["pending_factory_deploy"], {
            "due": 160, "attempts": 1,
        })

    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "run_shell", return_value=(5, "tests failed"))
    def test_real_release_failure_is_not_retried_forever(self, _run_shell, _log):
        state = {"pending_factory_deploy": {"due": 100, "attempts": 1}}

        result = pilot.retry_pending_factory_deploy(
            {"deploy_factory_cmd": "fx factory release"}, state, now=100)

        self.assertEqual(result, 5)
        self.assertNotIn("pending_factory_deploy", state)


class DashboardProjectsTest(unittest.TestCase):
    def setUp(self):
        pilot._dash_slow = {"at": 0, "data": {}}

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=["/work/shop"])
    @mock.patch.object(pilot, "_fixed_command", side_effect=[
        (True, "origin/trunk"),
        (True, "updated"),
        (True, "1723200000\x00Свежий коммит из trunk"),
    ])
    def test_project_main_fetches_configured_non_main_branch_before_reading(self, command, _repo):
        result = pilot._project_main("shop")

        self.assertEqual(result, {"main_subject": "Свежий коммит из trunk"})
        self.assertEqual(command.call_args_list[0].args[0][-3:], [
            "symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
        self.assertEqual(command.call_args_list[1].args[0][-3:], ["fetch", "origin", "trunk"])
        self.assertEqual(command.call_args_list[2].args[0][-1], "origin/trunk")

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=["/work/shop"])
    @mock.patch.object(pilot, "_fixed_command", side_effect=[
        (False, ""),
        (True, "ref: refs/heads/develop\tHEAD\nabc\tHEAD"),
        (True, "updated"),
        (True, "1723200000\x00Свежий коммит из develop"),
    ])
    def test_project_main_discovers_remote_default_when_origin_head_is_unset(self, command, _repo):
        result = pilot._project_main("shop")

        self.assertEqual(result, {"main_subject": "Свежий коммит из develop"})
        self.assertEqual(command.call_args_list[1].args[0][-3:], ["--symref", "origin", "HEAD"])
        self.assertEqual(command.call_args_list[2].args[0][-1], "develop")
        self.assertEqual(command.call_args_list[3].args[0][-1], "origin/develop")

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=[])
    @mock.patch.object(pilot, "_fixed_command")
    @mock.patch.object(pilot, "api")
    def test_enabled_projects_keep_api_order_and_use_only_fixed_providers(self, api, command, _repo):
        api.return_value = {"repositories": [
            {"id": "a", "remote_identity": "github.com/acme/shop", "enabled": True},
            {"id": "b", "remote_identity": "github.com/acme/factory", "enabled": True},
            {"id": "c", "remote_identity": "github.com/acme/disabled", "enabled": False},
            {"id": "d", "remote_identity": "github.com/acme/plain", "enabled": True},
        ]}
        command.side_effect = lambda args, timeout=25: (
            (True, "current -> /releases/release-one") if args[-1] == "release-info"
            else (True, "HTTP 200"))
        conf = {"project_providers": [
            {"remote_identity": "github.com/acme/shop", "type": "trade"},
            {"remote_identity": "github.com/acme/factory", "type": "factory"},
        ]}

        projects = pilot.dashboard_slow(conf)

        self.assertEqual([p["id"] for p in projects], ["a", "b", "d"])
        self.assertEqual([e["name"] for e in projects[0]["environments"]], ["Стейдж", "Прод"])
        self.assertEqual([e["name"] for e in projects[1]["environments"]], ["Прод"])
        self.assertEqual(projects[2]["provider_status"], "not_configured")
        scopes = [call.args[0][3] for call in command.call_args_list]
        self.assertEqual(scopes, ["staging", "staging", "prod", "prod", "factory", "factory"])
        self.assertTrue(all(call.args[0][:3] == ["sudo", "-n", "/usr/local/bin/fx"]
                            for call in command.call_args_list))

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=[])
    @mock.patch.object(pilot, "_fixed_command", side_effect=[(True, "current -> release"), (False, "")])
    def test_failed_health_is_unavailable_not_a_false_outage(self, command, _repo):
        snapshot = pilot._environment_snapshot("Прод", "factory", "repo")
        self.assertEqual(snapshot, {"name": "Прод", "status": "unavailable"})
        self.assertNotIn("health", snapshot)
        self.assertEqual(command.call_count, 2)

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=["/work/shop"])
    @mock.patch.object(pilot, "_fixed_command")
    def test_trade_release_path_uses_build_id_for_git_and_fallback(self, command, _repo):
        command.side_effect = [
            (True, "current -> /srv/shop/releases/6f6e2863"),
            (True, "HTTP 200"),
            (True, "Исправить карточку товара"),
            (True, "current -> /srv/shop/releases/a1b2c3d4"),
            (True, "HTTP 200"),
            (False, ""),
        ]

        resolved = pilot._environment_snapshot("Стейдж", "staging", "shop")
        fallback = pilot._environment_snapshot("Прод", "prod", "shop")

        self.assertEqual(resolved["release_label"], "Исправить карточку товара")
        self.assertEqual(fallback["release_label"], "Сборка a1b2c3d4")
        self.assertEqual(command.call_args_list[2], mock.call([
            "git", "-c", "safe.directory=*", "-C", "/work/shop",
            "log", "-1", "--format=%s", "6f6e2863",
        ], 10))
        self.assertEqual(command.call_args_list[5].args[0][-1], "a1b2c3d4")

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=[])
    @mock.patch.object(pilot, "_fixed_command", side_effect=[
        (True, "релиз от 9 августа, 16:22, из main: Исправлен обзор\nточка сборки: abc"),
        (True, "интерфейс: HTTP 200\nданные: HTTP 200"),
    ])
    def test_factory_human_release_format_is_recognized(self, _command, _repo):
        snapshot = pilot._environment_snapshot("Прод", "factory", "repo")
        self.assertEqual(snapshot["status"], "available")
        self.assertEqual(snapshot["release_label"], "релиз от 9 августа, 16:22, из main: Исправлен обзор")

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=[])
    @mock.patch.object(pilot, "_fixed_command", side_effect=[
        (True, "релиз от 9 августа, 16:22, из main: Исправлен обзор"),
        (True, "интерфейс: HTTP 200\nданные: HTTP 500"),
    ])
    def test_environment_is_unhealthy_when_any_required_http_component_fails(self, _command, _repo):
        snapshot = pilot._environment_snapshot("Прод", "factory", "repo")

        self.assertEqual(snapshot["status"], "available")
        self.assertEqual(snapshot["health"], "unhealthy")


if __name__ == "__main__":
    unittest.main()
