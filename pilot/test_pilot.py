import contextlib
import base64
import datetime
import importlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import uuid
from unittest import mock

# A number of tests exercise the real cycle() function, which durably saves
# STATE_PATH.  Redirect every HOME-derived Pilot path before importing the
# production module; subprocess-based tests inherit the same safe root.
_ORIGINAL_FACTORY_DATA_HOME = os.environ.get("FACTORY_DATA_HOME")
_TEST_DATA_HOME = tempfile.TemporaryDirectory(prefix="factory-pilot-tests-")
os.environ["FACTORY_DATA_HOME"] = _TEST_DATA_HOME.name
for _directory in (
        "pilot", "pilot/epics", "pilot/questions", "pilot/verdicts",
        "pilot/rebuild", ".claude/projects", "workers"):
    os.makedirs(os.path.join(_TEST_DATA_HOME.name, _directory), exist_ok=True)

from pilot import pilot


def tearDownModule():
    _TEST_DATA_HOME.cleanup()
    if _ORIGINAL_FACTORY_DATA_HOME is None:
        os.environ.pop("FACTORY_DATA_HOME", None)
    else:
        os.environ["FACTORY_DATA_HOME"] = _ORIGINAL_FACTORY_DATA_HOME


class TestDataIsolationTests(unittest.TestCase):
    def test_pilot_state_is_outside_the_live_data_root(self):
        self.assertEqual(pilot.HOME, _TEST_DATA_HOME.name)
        self.assertTrue(pilot.STATE_PATH.startswith(_TEST_DATA_HOME.name + os.sep))
        self.assertNotEqual(pilot.STATE_PATH, "/opt/factory-data/pilot/state.json")


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

    def test_triage_rules_do_not_require_a_delivery_branch(self):
        rules = pilot.agent_rules({}, "Triage")

        self.assertIn("здесь ещё нет поставки кода", rules)
        self.assertIn("Отсутствующая ветка", rules)
        self.assertIn("не является причиной WAIT на Разборе", rules)
        for forbidden in ("git push", "candidate_sha", "Сдача: сначала", "origin/main...HEAD"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rules)

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_triage_task_replaces_stale_delivery_rules(self, _api, _money):
        body = {
            "title": "[auto] [1/5 Triage] Проверить проблему",
            "context": "Контекст\n\n" + pilot.AGENT_RULES,
        }

        pilot.create_task(body, {})

        self.assertIn("здесь ещё нет поставки кода", body["context"])
        self.assertNotIn("candidate_sha", body["context"])
        self.assertNotIn("git push --force-with-lease", body["context"])
        self.assertEqual(body["context"].count("ПРАВИЛА ДЛЯ АГЕНТА"), 1)

    def test_later_stages_keep_delivery_rules(self):
        rules = pilot.agent_rules({}, "Specification")

        self.assertIn("candidate_sha", rules)
        self.assertIn("git push --force-with-lease", rules)

    def test_verify_cannot_change_the_reviewed_candidate(self):
        rules = pilot.agent_rules({}, "Verify")

        self.assertIn("ФИНАЛЬНАЯ ПРОВЕРКА — ТОЛЬКО ЧТЕНИЕ", rules)
        self.assertIn("запрещено изменять любые файлы", rules)
        self.assertIn("неизменённый снимок", rules)
        self.assertNotIn(
            "ФИНАЛЬНАЯ ПРОВЕРКА — ТОЛЬКО ЧТЕНИЕ",
            pilot.agent_rules({}, "Implement + Test"),
        )

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_verify_task_receives_read_only_override(self, _api, _money):
        body = {
            "title": "[auto] [5/5 Verify] Проверить поставку",
            "context": "Контекст\n\n" + pilot.AGENT_RULES,
        }

        pilot.create_task(body, {})

        self.assertIn("ФИНАЛЬНАЯ ПРОВЕРКА — ТОЛЬКО ЧТЕНИЕ", body["context"])
        self.assertEqual(body["context"].count("ПРАВИЛА ДЛЯ АГЕНТА"), 1)

    def test_stage_verdict_keeps_review_return_reason(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with mock.patch.object(pilot, "VERDICT_DIR", temporary.name), \
                mock.patch.object(pilot, "try_url", return_value=""), \
                mock.patch.object(pilot, "proof_of", return_value=""):
            pilot.save_stage_verdict("review-task", "Review", {
                "action": "stop",
                "reason": "Не проверен повторный сценарий оплаты",
                "verdict_ru": "Работу нужно дополнить.",
            }, "stage result")

        with open(os.path.join(temporary.name, "review-task.json"), encoding="utf-8") as saved:
            record = json.load(saved)
        self.assertEqual(record["reason"], "Не проверен повторный сценарий оплаты")

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

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_repeated_auto_task_replaces_changed_notification_channel(self, _api, _money):
        first = {
            "title": "[auto] [3/5 Implement + Test] Задача",
            "context": "Контекст",
        }
        pilot.create_task(first, {
            "ntfy_server": "https://old.example",
            "ntfy_owner_topic": "old-owner",
        })
        repeated = {"title": first["title"], "context": first["context"]}

        pilot.create_task(repeated, {
            "ntfy_server": "https://new.example",
            "ntfy_owner_topic": "new-owner",
        })

        self.assertNotIn("https://old.example/old-owner", repeated["context"])
        self.assertIn("https://new.example/new-owner", repeated["context"])
        self.assertEqual(repeated["context"].count("ПРАВИЛА ДЛЯ АГЕНТА"), 1)

    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api", return_value={"task": {"id": "task"}})
    def test_repeated_auto_task_removes_stale_channel_for_incomplete_config(
            self, _api, _money):
        first = {
            "title": "[auto] [3/5 Implement + Test] Задача",
            "context": "Контекст",
        }
        pilot.create_task(first, {
            "ntfy_server": "https://old.example",
            "ntfy_owner_topic": "old-owner",
        })
        repeated = {"title": first["title"], "context": first["context"]}

        pilot.create_task(repeated, {"ntfy_server": "https://new.example"})

        self.assertNotIn("https://old.example/old-owner", repeated["context"])
        self.assertNotIn("Канал срочных уведомлений владельца", repeated["context"])
        self.assertEqual(repeated["context"].count("ПРАВИЛА ДЛЯ АГЕНТА"), 1)

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


class ReleaseTrainDashboardTests(unittest.TestCase):
    def block(self, target, tasks=None, now=120):
        state = {pilot.DELIVERY_STATE_KEY: {"version": 2, "targets": {"factory": target}}}
        return pilot.release_train_block(state, tasks or [], now)

    def target(self, generation=None, **extra):
        generations = {generation["id"]: generation} if generation else {}
        return {"id": "factory", "current_generation": generation["id"] if generation else None,
                "generations": generations, **extra}

    def test_unavailable_and_idle_are_distinct(self):
        self.assertIsNone(pilot.release_train_block({}, [], 120))
        self.assertEqual(self.block(self.target()), {"updated_at": "1970-01-01T00:02:00Z", "trains": [{
            "target": "Factory", "state": "idle", "passengers": [],
            "next": {"requested": False, "passengers": []},
        }]})

    def test_reserved_exposes_public_sequence_passengers_and_real_retry_only(self):
        generation = {"id": "private-generation", "sequence": 7, "phase": "reserved",
                      "commit_sha": "secret-sha", "reserved_at": "1970-01-01T00:01:00Z",
                      "next_retry_at": 180, "waits": {"known": {}, "gone": {}}}
        train = self.block(self.target(generation), [{"id": "known", "title": "[auto] [5/5 Verify] Каталог"}])["trains"][0]
        self.assertEqual(train, {
            "target": "Factory", "state": "waiting", "generation": 7,
            "gate": "ожидает broker", "started_at": "1970-01-01T00:01:00Z",
            "elapsed_seconds": 60,
            "passengers": [{"title": "Каталог"}, {"title": "Работа из выпуска (название недоступно)"}],
            "next": {"requested": False, "passengers": [], "retry_at": "1970-01-01T00:03:00Z"},
        })
        self.assertNotIn("commit_sha", str(train))
        self.assertNotIn("private-generation", str(train))

    def test_running_keeps_next_train_separate_without_inventing_a_date(self):
        generation = {"id": "g1", "sequence": 1, "phase": "running",
                      "started_at": "1970-01-01T00:01:30Z", "waits": {"current": {}}}
        train = self.block(self.target(generation, next_requested=True,
                           next_waits={"next": {}}), [
                               {"id": "current", "title": "Текущий пассажир"},
                               {"id": "next", "title": "Следующий пассажир"}])["trains"][0]
        self.assertEqual(train["state"], "running")
        self.assertEqual(train["elapsed_seconds"], 30)
        self.assertEqual(train["next"], {"requested": True,
                                         "passengers": [{"title": "Следующий пассажир"}]})

    def test_projection_uses_explicit_now_without_machine_clock(self):
        generation = {"id": "g1", "sequence": 1, "phase": "running",
                      "started_at": "1970-01-01T00:01:30Z", "waits": {}}
        with mock.patch.object(pilot.time, "time", side_effect=AssertionError("machine clock")):
            snapshot = self.block(self.target(generation), now=120)

        self.assertEqual(snapshot["updated_at"], "1970-01-01T00:02:00Z")
        self.assertEqual(snapshot["trains"][0]["elapsed_seconds"], 30)

    def test_terminal_results_remain_distinct_and_use_durable_finish_time(self):
        for phase, state in (("completed", "succeeded"), ("failed", "failed")):
            with self.subTest(phase=phase):
                generation = {"id": "g1", "sequence": 1, "phase": phase,
                              "finished_at": "1970-01-01T00:01:50Z", "waits": {"work": {}}}
                train = self.block(self.target(generation), [{"id": "work", "title": "Оплата"}])["trains"][0]
                self.assertEqual(train["state"], state)
                self.assertNotIn("previous", train)

    def test_last_failed_train_is_previous_after_successor_arrives(self):
        failed = {"id": "failed-private", "sequence": 1, "phase": "failed",
                  "finished_at": "1970-01-01T00:01:50Z", "waits": {"old": {}}}
        current = {"id": "current-private", "sequence": 2, "phase": "reserved",
                   "reserved_at": "1970-01-01T00:02:00Z", "waits": {"new": {}}}
        target = self.target(current)
        target["generations"][failed["id"]] = failed
        train = self.block(target, [{"id": "old", "title": "Оплата"}])["trains"][0]
        self.assertEqual(train["previous"], {"state": "failed",
            "finished_at": "1970-01-01T00:01:50Z", "passengers": [{"title": "Оплата"}]})
        self.assertNotIn("private", str(train))

    def test_new_delivery_transitions_record_projection_timestamps(self):
        state = {}
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state_path = os.path.join(temporary.name, "state.json")
        with mock.patch.object(pilot, "STATE_PATH", state_path), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", os.path.join(temporary.name, "receipts")), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", os.path.join(temporary.name, "outbox")), \
                mock.patch.object(pilot, "broker_operation", return_value={"status": "succeeded"}), \
                mock.patch.object(pilot, "broker_acceptance", return_value={"status": "passed"}), \
                mock.patch.object(pilot, "mark_final"), mock.patch.object(pilot, "notify"):
            generation = pilot.deploy_after_merge({}, "github.com/timafen/factory", state,
                "a" * 40, {"task_id": "work", "merge_receipt": {}}, now=60)
            self.assertEqual(generation["reserved_at"], "1970-01-01T00:01:00Z")
            pilot.poll_delivery_state({}, state, now=120)
        self.assertEqual(generation["finished_at"], "1970-01-01T00:02:00Z")


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

    def test_review_gate_keeps_finished_other_area_and_removes_service_noise(self):
        known = {
            "Счётчик": ["repo::pilot/pilot.py", "repo::web/src/Overview.tsx"],
            "Другая работа": ["repo::docs/foreign.md"],
        }
        files = ["pilot/pilot.py", "web/src/Overview.tsx", "docs/extra.md",
                 "docs/foreign.md", "pilot/__pycache__/pilot.pyc"]

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "ok", "files": files, "base_sha": "a" * 40, "candidate_sha": "b" * 40, "default_branch": "main"}), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "load", return_value=known), \
                mock.patch.object(pilot, "rebuild_clean_branch",
                                  return_value="task-clean") as rebuild:
            result = pilot.review_gate({}, "Счётчик", "task", "file:///tmp/repo", active_tasks=[])

        self.assertEqual(result["branch"], "task-clean")
        rebuild.assert_called_once_with(
            "file:///tmp/repo", "task",
            ["pilot/pilot.py", "web/src/Overview.tsx", "docs/extra.md",
             "docs/foreign.md"],
            "Счётчик",
        )

    def test_browser_wait_epic_rebuild_keeps_code_despite_finished_claim(self):
        """Regression: a completed epic's old claim must not strip browser code.

        This is the observed AREA WAIT -> automatic rebuild path: only a live
        overlap waits; a finished neighbour cannot leave a knowledge card as
        the sole survivor of a rebuild.
        """
        known = {
            "Браузер после ожидания": ["repo::web/src/Browser.tsx",
                                        "repo::old/obsolete.ts"],
            "Завершённая подзадача эпика": ["repo::web/src/Browser.tsx"],
        }
        files = ["web/src/Browser.tsx", "knowledge/cards/CARD-browser.md",
                 "node_modules/cache.js"]

        def loader(path, default=None):
            if path == pilot.AREAS_PATH:
                return known
            return {}

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "ok", "files": files, "base_sha": "a" * 40, "candidate_sha": "b" * 40, "default_branch": "main"}), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "load", side_effect=loader), \
                mock.patch.object(pilot, "rebuild_clean_branch",
                                  return_value="browser-clean") as rebuild:
            result = pilot.review_gate({}, "Браузер после ожидания", "browser", "file:///tmp/repo",
                                       active_tasks=[])

        self.assertEqual(result["branch"], "browser-clean")
        rebuild.assert_called_once_with(
            "file:///tmp/repo", "browser",
            ["web/src/Browser.tsx", "knowledge/cards/CARD-browser.md"],
            "Браузер после ожидания",
        )

    def test_browser_wait_holds_real_live_overlap(self):
        known = {
            "Браузер после ожидания": ["file:///tmp/repo::web/src/Browser.tsx"],
            "Соседняя подзадача эпика": ["file:///tmp/repo::web/src/Browser.tsx"],
        }
        live = [{"state": "running",
                 "title": "[auto] [2/5 Implement + Test] Соседняя подзадача эпика"}]

        def loader(path, default=None):
            return known if path == pilot.AREAS_PATH else {}

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "ok", "files": ["web/src/Browser.tsx"], "base_sha": "a" * 40, "candidate_sha": "b" * 40, "default_branch": "main"}), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "load", side_effect=loader), \
                mock.patch.object(pilot, "rebuild_clean_branch") as rebuild:
            result = pilot.review_gate({}, "Браузер после ожидания", "browser", "file:///tmp/repo",
                                       active_tasks=live)

        self.assertTrue(result["wait"])
        rebuild.assert_not_called()

    def test_area_replace_clears_stale_paths_after_rebuild(self):
        known = {"Браузер": ["repo::old/obsolete.ts", "repo::web/src/Browser.tsx"]}

        with mock.patch.object(pilot, "load", return_value=known), \
                mock.patch.object(pilot, "save") as save:
            pilot.area_replace("Браузер", ["web/src/Browser.tsx",
                                            "knowledge/cards/CARD-browser.md"], "repo")

        save.assert_called_once_with(
            pilot.AREAS_PATH,
            {"Браузер": ["repo::knowledge/cards/CARD-browser.md",
                          "repo::web/src/Browser.tsx"]},
        )

    def test_knowledge_card_cannot_replace_promised_browser_code(self):
        areas = {"Браузер": ["repo::web/src/Browser.tsx"]}
        promises = {"Браузер": {"files": ["web/src/Browser.tsx"]}}

        def loader(path, default=None):
            if path == pilot.PROMISES_PATH:
                return promises
            if path == pilot.AREAS_PATH:
                return areas
            return default

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "ok", "files": ["knowledge/cards/CARD-browser.md"], "base_sha": "a" * 40, "candidate_sha": "b" * 40, "default_branch": "main"}), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "load", side_effect=loader):
            result = pilot.review_gate({}, "Браузер", "browser", "file:///tmp/repo")

        self.assertTrue(result["back"])
        self.assertIn("документация не заменяет", result["alert_msg"])

    def test_card_commit_gate_accepts_code_commit_before_final_card_commit(self):
        implementation = "a" * 40
        card = ("# CARD-0100\n\n## HEAD\n\n- Status: Implemented\n\nImplementation commit: `" + implementation
                + "` — реализован устойчивый факт.\n")
        responses = [
            {"content": base64.b64encode(card.encode()).decode()},
            {"status": "ahead"},
            {"files": [{"filename": "pilot/pilot.py"}]},
        ]
        with mock.patch.object(pilot, "gh_json", side_effect=responses):
            result = pilot.implementation_commit_gate(
                "github.com/example/repo", "factory/task",
                ["pilot/pilot.py", "knowledge/cards/CARD-0100.md"],
            )
        self.assertIsNone(result)

    def test_card_commit_gate_rejects_old_head_requirement_without_stable_commit(self):
        card = "# CARD-0100\n\n## HEAD\n\n- Status: Implemented\n\nHead commit: git HEAD\n"
        with mock.patch.object(pilot, "gh_json", return_value={
                "content": base64.b64encode(card.encode()).decode()}):
            result = pilot.implementation_commit_gate(
                "github.com/example/repo", "factory/task",
                ["pilot/pilot.py", "knowledge/cards/CARD-0100.md"],
            )
        self.assertTrue(result["back"])
        self.assertIn("Head commit", result["note"])

    def test_card_commit_gate_rejects_invented_or_card_only_commit(self):
        implementation = "b" * 40
        card = ("## HEAD\nStatus: Implemented\nImplementation commit: " + implementation + " — якобы код.\n")
        responses = [
            {"content": base64.b64encode(card.encode()).decode()},
            {"status": "ahead"},
            {"files": [{"filename": "knowledge/cards/CARD-0100.md"}]},
        ]
        with mock.patch.object(pilot, "gh_json", side_effect=responses):
            result = pilot.implementation_commit_gate(
                "github.com/example/repo", "factory/task", ["knowledge/cards/CARD-0100.md"])
        self.assertTrue(result["back"])
        self.assertIn("только карточки", result["note"])


class CardHeadStatusTests(unittest.TestCase):
    def gate(self, status, *, card_path="knowledge/cards/CARD-0127-card-head-implemented-status.md",
             inside_head=True):
        implementation = "a" * 40
        head = f"## HEAD\n\n{status}\n\n" if inside_head else f"{status}\n\n## HEAD\n\n"
        card = (f"# CARD-0127\n\n{head}"
                f"Implementation commit: {implementation} — код.\n")
        responses = [
            {"content": base64.b64encode(card.encode()).decode()},
            {"status": "ahead"},
            {"files": [{"filename": "pilot/pilot.py"}]},
        ]
        with mock.patch.object(pilot, "gh_json", side_effect=responses):
            return pilot.implementation_commit_gate(
                "github.com/example/repo", "factory/task",
                ["pilot/pilot.py", card_path])

    def test_implemented_status_accepts_plain_and_markdown_forms(self):
        for status in ("Status: Implemented", "- Status: IMPLEMENTED — awaiting Review"):
            with self.subTest(status=status):
                self.assertIsNone(self.gate(status))

    def test_old_or_missing_status_returns_to_implement(self):
        for status in ("- Status: Planned", "Implementation is ready", ""):
            with self.subTest(status=status):
                result = self.gate(status)
                self.assertTrue(result["back"])
                self.assertIn("Status: Implemented", result["note"])

    def test_status_outside_head_does_not_pass(self):
        result = self.gate("Status: Implemented", inside_head=False)
        self.assertTrue(result["back"])

    def test_remote_read_failure_is_not_misreported_as_bad_status(self):
        with mock.patch.object(pilot, "gh_json", return_value=None):
            self.assertIsNone(pilot.implementation_commit_gate(
                "github.com/example/repo", "factory/task",
                ["pilot/pilot.py", "knowledge/cards/CARD-0127-card-head-implemented-status.md"]))

    def test_review_rejects_foreign_card_before_review(self):
        snapshot = {"state": "ok", "files": [
            "pilot/pilot.py", "knowledge/cards/CARD-0999-other.md"],
            "base_sha": "a" * 40, "candidate_sha": "b" * 40,
            "default_branch": "main"}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=snapshot):
            result = pilot.review_gate({}, "Работа", "factory/task",
                                       "github.com/example/repo",
                                       expected_card="CARD-0127")
        self.assertTrue(result["back"])
        self.assertIn("CARD-0127", result["note"])


class FreshDefaultBranchSnapshotTests(unittest.TestCase):
    def test_review_range_requires_two_pinned_full_shas(self):
        base = "a" * 40
        candidate = "b" * 40

        self.assertEqual(
            pilot.pinned_review_range(base, candidate),
            base + "..." + candidate,
        )
        for invalid_base, invalid_candidate in (("main", candidate),
                                                  (base, "HEAD"),
                                                  (base.upper(), candidate)):
            with self.subTest(invalid_base=invalid_base, invalid_candidate=invalid_candidate):
                with self.assertRaises(ValueError):
                    pilot.pinned_review_range(invalid_base, invalid_candidate)

    def git(self, cwd, *args):
        rc, out = pilot._git(cwd, *args)
        self.assertEqual(rc, 0, out)
        return out.strip()

    def commit(self, work, name, body):
        path = os.path.join(work, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        self.git(work, "add", name)
        self.git(work, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-qm", name)

    def test_remote_main_advance_keeps_old_candidate_reviewable_without_cache(self):
        """A real bare remote proves scope comes from pinned SHAs, not cached refs."""
        with tempfile.TemporaryDirectory() as tmp:
            remote = os.path.join(tmp, "remote.git")
            author = os.path.join(tmp, "author")
            observer = os.path.join(tmp, "observer")
            self.git(tmp, "init", "--bare", remote)
            self.git(tmp, "init", "-q", author)
            self.git(author, "checkout", "-qb", "main")
            self.git(author, "remote", "add", "origin", remote)
            self.commit(author, "README.md", "root\n")
            self.git(author, "push", "-qu", "origin", "main")
            self.git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
            self.git(author, "checkout", "-qb", "factory/candidate", "origin/main")
            expected = ["delivery/file-%02d.txt" % i for i in range(1, 12)]
            for names, message in ((expected[:6], "first delivery batch"),
                                   (expected[6:], "second delivery batch")):
                for name in names:
                    path = os.path.join(author, name)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(name)
                self.git(author, "add", "delivery")
                self.git(author, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                         "commit", "-qm", message)
            self.git(author, "push", "-qu", "origin", "factory/candidate")

            self.git(author, "checkout", "-q", "main")
            self.commit(author, "foreign-from-advanced-main.txt", "not this delivery\n")
            self.git(author, "push", "-q", "origin", "main")

            self.git(tmp, "clone", "-q", remote, observer)

            self.git(observer, "fetch", "-q", "origin",
                     "factory/candidate:refs/remotes/origin/factory/candidate")
            self.git(observer, "checkout", "-qb", "worker-owned")
            before = self.git(observer, "symbolic-ref", "--short", "HEAD")

            with mock.patch.object(pilot, "_git", wraps=pilot._git) as git_spy:
                snapshot = pilot.fresh_branch_snapshot("file://" + remote, "factory/candidate")

            self.assertEqual(snapshot["state"], "ok")
            self.assertEqual(snapshot["files"], expected)
            self.assertEqual(snapshot["ahead_by"], 2)
            self.assertTrue(snapshot["base_advanced"])
            self.assertEqual(snapshot["base_ahead_by"], 1)
            self.assertRegex(snapshot["base_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(snapshot["candidate_sha"], r"^[0-9a-f]{40}$")
            expected_range = snapshot["base_sha"] + "..." + snapshot["candidate_sha"]
            self.assertTrue(any(
                call.args[1:] == ("diff", "--name-only", expected_range)
                for call in git_spy.call_args_list))
            self.assertEqual(self.git(observer, "symbolic-ref", "--short", "HEAD"), before)

    def test_stale_cached_main_never_defines_review_scope(self):
        """The observer's stale main ref cannot replace the fetched pinned base."""
        with tempfile.TemporaryDirectory() as tmp:
            remote = os.path.join(tmp, "remote.git")
            author = os.path.join(tmp, "author")
            observer = os.path.join(tmp, "observer")
            self.git(tmp, "init", "--bare", remote)
            self.git(tmp, "init", "-q", author)
            self.git(author, "checkout", "-qb", "main")
            self.git(author, "remote", "add", "origin", remote)
            self.commit(author, "README.md", "root\n")
            self.git(author, "push", "-qu", "origin", "main")
            self.git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

            # Clone before candidate publication and main advancement: this is
            # the stale-cache state the production review must survive.
            self.git(tmp, "clone", "-q", remote, observer)
            cached_main = self.git(observer, "rev-parse", "refs/remotes/origin/main")
            self.git(author, "checkout", "-qb", "factory/candidate", "main")
            self.commit(author, "delivery.txt", "candidate\n")
            candidate_sha = self.git(author, "rev-parse", "HEAD")
            self.git(author, "push", "-qu", "origin", "factory/candidate")
            self.git(author, "checkout", "-q", "main")
            self.commit(author, "foreign.txt", "advanced main\n")
            new_main = self.git(author, "rev-parse", "HEAD")
            self.git(author, "push", "-qu", "origin", "main")

            self.git(observer, "fetch", "-q", "origin", "factory/candidate")
            before = self.git(observer, "symbolic-ref", "--short", "HEAD")
            snapshot = pilot.fresh_branch_snapshot("file://" + remote,
                                                   "factory/candidate")

            self.assertEqual(snapshot["state"], "ok")
            self.assertEqual(cached_main, self.git(observer,
                                                   "rev-parse", "refs/remotes/origin/main"))
            self.assertNotEqual(cached_main, new_main)
            self.assertEqual(snapshot["base_sha"], new_main)
            self.assertEqual(snapshot["candidate_sha"], candidate_sha)
            self.assertEqual(snapshot["files"], ["delivery.txt"])
            self.assertEqual(snapshot["base_sha"] + "..." + snapshot["candidate_sha"],
                             new_main + "..." + candidate_sha)
            self.assertTrue(snapshot["base_advanced"])
            self.assertEqual(self.git(observer, "symbolic-ref", "--short", "HEAD"), before)

    def test_stale_candidate_is_merged_with_fresh_main_before_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = os.path.join(tmp, "remote.git")
            author = os.path.join(tmp, "author")
            self.git(tmp, "init", "--bare", remote)
            self.git(tmp, "init", "-q", author)
            self.git(author, "checkout", "-qb", "main")
            self.git(author, "remote", "add", "origin", remote)
            self.commit(author, "README.md", "root\n")
            self.git(author, "push", "-qu", "origin", "main")
            self.git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

            self.git(author, "checkout", "-qb", "factory/candidate", "main")
            self.commit(author, "pilot/change.py", "candidate\n")
            implementation = self.git(author, "rev-parse", "HEAD")
            self.git(author, "push", "-qu", "origin", "factory/candidate")
            self.git(author, "checkout", "-q", "main")
            self.commit(author, "main-only.txt", "advanced\n")
            current_main = self.git(author, "rev-parse", "HEAD")
            self.git(author, "push", "-q", "origin", "main")

            result = pilot.refresh_stale_branch("file://" + remote,
                                                "factory/candidate")

            self.assertEqual(result["state"], "ok")
            self.assertFalse(result["snapshot"]["base_advanced"])
            self.assertEqual(result["snapshot"]["base_sha"], current_main)
            refreshed = result["snapshot"]["candidate_sha"]
            self.git(author, "fetch", "-q", "origin", "factory/candidate")
            self.git(author, "merge-base", "--is-ancestor", implementation,
                     refreshed)
            self.assertEqual(result["branch"], "factory/candidate")

    def test_conflicting_refresh_leaves_remote_candidate_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = os.path.join(tmp, "remote.git")
            author = os.path.join(tmp, "author")
            self.git(tmp, "init", "--bare", remote)
            self.git(tmp, "init", "-q", author)
            self.git(author, "checkout", "-qb", "main")
            self.git(author, "remote", "add", "origin", remote)
            self.commit(author, "shared.txt", "root\n")
            self.git(author, "push", "-qu", "origin", "main")
            self.git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
            self.git(author, "checkout", "-qb", "factory/candidate", "main")
            self.commit(author, "shared.txt", "candidate\n")
            candidate = self.git(author, "rev-parse", "HEAD")
            self.git(author, "push", "-qu", "origin", "factory/candidate")
            self.git(author, "checkout", "-q", "main")
            self.commit(author, "shared.txt", "main\n")
            self.git(author, "push", "-q", "origin", "main")

            result = pilot.refresh_stale_branch("file://" + remote,
                                                "factory/candidate")

            self.assertEqual(result["state"], "conflict")
            self.assertEqual(self.git(tmp, "--git-dir", remote, "rev-parse",
                                      "refs/heads/factory/candidate"), candidate)

    def test_fetch_or_default_resolution_failure_is_blocked_without_cached_fallback(self):
        snapshot = pilot.fresh_branch_snapshot("file:///definitely/not/a/repository", "factory/candidate")
        self.assertEqual(snapshot["state"], "blocked")
        self.assertIn("default branch", snapshot["reason"])

    def test_review_gate_keeps_infrastructure_failure_out_of_request_changes(self):
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={
                "state": "blocked", "reason": "cannot fetch authoritative refs"}):
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo")
        self.assertTrue(result["blocked"])
        self.assertNotIn("REQUEST CHANGES", result["note"])
        self.assertIn("review infrastructure", result["note"])

    def test_review_gate_refreshes_stale_candidate_after_area_is_free(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0163-x.md"]
        stale = {"state": "ok", "default_branch": "main",
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40,
                 "merge_base_sha": "c" * 40, "base_advanced": True,
                 "base_ahead_by": 3, "ahead_by": 2, "files": files}
        fresh = dict(stale, base_sha="d" * 40, candidate_sha="e" * 40,
                     merge_base_sha="d" * 40, base_advanced=False,
                     base_ahead_by=0)
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=stale), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value=[]), \
                mock.patch.object(pilot, "load", return_value={}), \
                mock.patch.object(pilot, "refresh_stale_branch", return_value={
                    "state": "ok", "branch": "factory/candidate", "snapshot": fresh}) as refresh:
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo")

        self.assertFalse(result["back"])
        self.assertEqual(result["head"], "e" * 40)
        refresh.assert_called_once_with("github.com/example/repo", "factory/candidate")
        self.assertNotIn("Основная ветка продвинулась", result["note"])

    def test_review_gate_waits_for_overlap_before_refreshing_stale_branch(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0163-x.md"]
        stale = {"state": "ok", "default_branch": "main",
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40,
                 "merge_base_sha": "c" * 40, "base_advanced": True,
                 "base_ahead_by": 1, "ahead_by": 2, "files": files}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=stale), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value={"pilot/pilot.py"}), \
                mock.patch.object(pilot, "load", return_value={}), \
                mock.patch.object(pilot, "refresh_stale_branch") as refresh:
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo", active_tasks=[])

        self.assertTrue(result["wait"])
        refresh.assert_not_called()

    def test_review_gate_returns_conflicting_refresh_to_implement(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0163-x.md"]
        stale = {"state": "ok", "default_branch": "main",
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40,
                 "merge_base_sha": "c" * 40, "base_advanced": True,
                 "base_ahead_by": 1, "ahead_by": 2, "files": files}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=stale), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value=[]), \
                mock.patch.object(pilot, "load", return_value={}), \
                mock.patch.object(pilot, "refresh_stale_branch", return_value={
                    "state": "conflict", "reason": "content conflict"}):
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo")

        self.assertTrue(result["back"])
        self.assertIn("перед Ревью", result["note"])

    def test_review_gate_blocks_when_stale_refresh_cannot_be_published(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0163-x.md"]
        stale = {"state": "ok", "default_branch": "main",
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40,
                 "merge_base_sha": "c" * 40, "base_advanced": True,
                 "base_ahead_by": 1, "ahead_by": 2, "files": files}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=stale), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value=[]), \
                mock.patch.object(pilot, "load", return_value={}), \
                mock.patch.object(pilot, "refresh_stale_branch", return_value={
                    "state": "blocked", "reason": "push rejected"}):
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo")

        self.assertTrue(result["blocked"])
        self.assertIn("push rejected", result["note"])

    def test_review_gate_returns_empty_pinned_delivery_with_one_message(self):
        snapshot = {
            "state": "ok", "default_branch": "main",
            "base_sha": "a" * 40, "candidate_sha": "b" * 40,
            "merge_base_sha": "a" * 40, "base_advanced": False,
            "base_ahead_by": 0, "ahead_by": 0, "files": [],
        }
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=snapshot):
            result = pilot.review_gate({}, "Работа", "factory/candidate",
                                       "github.com/example/repo")

        self.assertEqual(set(result), {"back", "note"})
        self.assertTrue(result["back"])
        self.assertIn("Поставка пуста", result["note"])
        self.assertIn("a" * 40 + "..." + "b" * 40, result["note"])

    def test_stale_delivery_rebuilds_only_promised_paths_from_artifact(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        works = os.path.join(temporary.name, "works.json")
        promises = os.path.join(temporary.name, "promises.json")
        base, source, clean = "Отставшая поставка", "factory/implementation", "factory/implementation-clean"
        promised = ["pilot/pilot.py", "pilot/test_pilot.py", "internal/controlplane/promises_http.go", "internal/controlplane/http_test.go"]
        pilot.save(works, {base: {"run_generation": "g", "implementation_artifact": {
            "branch": source, "head": "c" * 40, "generation": "g"}}})
        pilot.save(promises, {base: {"files": promised, "commands": ["python3 -m unittest"]}})
        stale = {"state": "ok", "base_advanced": True, "files": ["knowledge/cards/CARD-0163-x.md"],
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40}
        source_snapshot = {"state": "ok", "candidate_sha": "c" * 40, "files": promised}
        rebuilt_snapshot = {"state": "ok", "candidate_sha": "d" * 40, "files": promised}
        with mock.patch.object(pilot, "WORKS_PATH", works), \
                mock.patch.object(pilot, "PROMISES_PATH", promises), \
                mock.patch.object(pilot, "fresh_branch_snapshot", side_effect=[stale, source_snapshot, rebuilt_snapshot]), \
                mock.patch.object(pilot, "rebuild_clean_branch", return_value=clean) as rebuild, \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value=[]):
            result = pilot.review_gate({}, base, "factory/old-delivery", "github.com/acme/repo")
        self.assertFalse(result["back"])
        self.assertEqual(result["branch"], clean)
        self.assertEqual(result["head"], "d" * 40)
        rebuild.assert_called_once_with("github.com/acme/repo", source, sorted(promised), base, area_repo="")
        self.assertEqual(pilot.load(promises, {})[base]["delivery_status"], "пересобрана и заново закреплена")

    def test_stale_delivery_without_verified_source_keeps_safe_return(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        promises = os.path.join(temporary.name, "promises.json")
        base = "Отставшая поставка"
        pilot.save(promises, {base: {"files": ["pilot/pilot.py"]}})
        stale = {"state": "ok", "base_advanced": True, "files": ["knowledge/cards/CARD-0163-x.md"],
                 "base_sha": "a" * 40, "candidate_sha": "b" * 40}
        with mock.patch.object(pilot, "PROMISES_PATH", promises), \
                mock.patch.object(pilot, "fresh_branch_snapshot", return_value=stale), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "other_areas", return_value=[]):
            result = pilot.review_gate({}, base, "factory/old-delivery", "github.com/acme/repo")
        self.assertTrue(result["back"])
        self.assertIn("нет обещанных файлов", result["note"])

    def test_stale_delivery_refetch_failure_blocks_without_rebuild(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        works, promises = os.path.join(temporary.name, "works.json"), os.path.join(temporary.name, "promises.json")
        base = "Отставшая поставка"
        pilot.save(works, {base: {"run_generation": "g", "implementation_artifact": {
            "branch": "factory/source", "head": "c" * 40, "generation": "g"}}})
        pilot.save(promises, {base: {"files": ["pilot/pilot.py"]}})
        stale = {"state": "ok", "base_advanced": True, "files": ["knowledge/cards/CARD-0163-x.md"], "base_sha": "a" * 40, "candidate_sha": "b" * 40}
        with mock.patch.object(pilot, "WORKS_PATH", works), \
                mock.patch.object(pilot, "PROMISES_PATH", promises), \
                mock.patch.object(pilot, "fresh_branch_snapshot", side_effect=[stale, {"state": "blocked", "reason": "fetch failed"}]), \
                mock.patch.object(pilot, "rebuild_clean_branch") as rebuild:
            result = pilot.review_gate({}, base, "factory/old-delivery", "github.com/acme/repo")
        self.assertTrue(result["blocked"])
        self.assertIn("review infrastructure", result["note"])
        rebuild.assert_not_called()

    def test_verify_gate_refreshes_snapshot_and_blocks_before_merge(self):
        snapshot = {
            "state": "ok", "base_sha": "a" * 40,
            "candidate_sha": "b" * 40, "merge_base_sha": "a" * 40,
        }
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=snapshot) as fresh:
            result = pilot.verify_gate("github.com/example/repo", "factory/candidate")
        fresh.assert_called_once_with("github.com/example/repo", "factory/candidate")
        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshot"]["base_sha"], "a" * 40)
        self.assertEqual(result["snapshot"]["candidate_sha"], "b" * 40)

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={
                "state": "blocked", "reason": "cannot fetch authoritative refs"}):
            blocked = pilot.verify_gate("github.com/example/repo", "factory/candidate")
        self.assertTrue(blocked["blocked"])
        self.assertIn("BLOCKED: review infrastructure", blocked["note"])


class SpecificationBranchHandoffTests(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.successful_created = []
        self.state = {"processed": []}
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.rescue_path = os.path.join(self.temporary.name, "cap_rescues.json")
        self.conf = {
            "stages": [
                {"workflow": "Specification"},
                {"workflow": "Implement + Test"},
            ],
            "poll_seconds": 30,
            "auto_plan": False,
        }
        self.task = {
            "id": "specification-done",
            "title": "[auto] [1/2 Specification] Сохранить спецификацию",
            "state": "succeeded",
            "created_at": "2026-08-11T10:00:00Z",
            "repository_id": "repo-id",
        }

    def run_cycle(self, result, branch_result=("есть", ["knowledge/spec.md"]),
                  branch_error=None, published_branches=None, create_effects=None,
                  cycles=1, restart_after_first=False, durable_caps=False,
                  branch_results=None, task_variants=None, result_by_task=None):
        effects = list(create_effects or [])
        tasks = list(task_variants or [self.task])
        results = result_by_task or {task["id"]: result for task in tasks}
        self.log_messages = []

        def fake_api(path, body=None):
            if path in ("/tasks?limit=100", "/tasks?limit=200"):
                return {"tasks": tasks}
            task_id = path.removeprefix("/tasks/")
            if task_id in results:
                return {
                    "task": {
                        "repository_id": "repo-id",
                        "worker_id": "spec-worker-id",
                    },
                    "workflow": {
                        "title": "Specification",
                        "revision_id": "rev-specification",
                    },
                    "context": "",
                    "attempts": [{"id": f"attempt-{task_id}",
                                   "execution_id": f"execution-{task_id}",
                                   "result": results[task_id]}],
                }
            if path == "/workers":
                return {"workers": [{
                    "id": "implement-worker-id", "name": "worker",
                    "online": True, "health": "healthy", "capacity": 1,
                    "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id",
                    "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "implement", "enabled": True,
                    "current_revision": {
                        "id": "rev-implementation", "title": "Implement + Test",
                    },
                }]}
            raise AssertionError(path)

        def create(body, _conf):
            self.created.append(body)
            effect = effects.pop(0) if effects else None
            if isinstance(effect, Exception):
                raise effect
            response = effect or {"task": {
                "id": "created-task", "title": body["title"], "state": "created",
                "repository_id": body["repository_id"],
            }}
            self.successful_created.append(body)
            return response

        def github_branch(args, **_kwargs):
            if "/contents/knowledge/cards?ref=main" in args[-1]:
                return [{"name": "CARD-0041-existing.md"}]
            name = args[-1].split("/branches/", 1)[-1]
            if published_branches is not None and name not in published_branches:
                return None
            return {"name": name}

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas", "save_promises",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "create_task", side_effect=create))
            stack.enter_context(mock.patch.object(pilot, "gh_json", side_effect=github_branch))
            if branch_error:
                branch_report = stack.enter_context(mock.patch.object(
                    pilot, "branch_report", side_effect=branch_error))
            elif branch_results is not None:
                branch_report = stack.enter_context(mock.patch.object(
                    pilot, "branch_report", side_effect=branch_results))
            else:
                branch_report = stack.enter_context(mock.patch.object(
                    pilot, "branch_report", return_value=branch_result))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot", side_effect=lambda day, _week: {day: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", return_value="worker"))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(
                pilot, "work_lifecycle_block", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "live_or_done_at", return_value=None))
            stack.enter_context(mock.patch.object(pilot, "is_stopped", return_value=False))
            if durable_caps:
                stack.enter_context(mock.patch.object(
                    pilot, "RESCUE_PATH", self.rescue_path))
            else:
                stack.enter_context(mock.patch.object(pilot, "cap_rescues", return_value=0))
                stack.enter_context(mock.patch.object(pilot, "note_cap_rescue"))
            self.notify = stack.enter_context(mock.patch.object(pilot, "notify"))
            stack.enter_context(mock.patch.object(
                pilot, "log", side_effect=lambda *args: self.log_messages.append(
                    " ".join(map(str, args)))))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "reason": "готово",
                "next_complexity": "medium", "handoff": "использовать документ",
            }))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            for number in range(cycles):
                pilot.cycle(self.conf, self.state)
                if restart_after_first and number == 0:
                    self.state = {"processed": []}
            self.rescues = pilot.load(self.rescue_path, {}) if durable_caps else {}
        return branch_report

    def test_published_nonempty_branch_starts_implementation(self):
        specification_head = "a" * 40
        report = self.run_cycle(
            "BRANCH: factory/published\n"
            f"HEAD: {specification_head}\n"
            "PUSHED: yes\n"
            "ГОТОВО-КОГДА: файл pilot/pilot.py")

        report.assert_called_once_with("github.com/acme/repo", "factory/published")
        self.assertEqual(len(self.created), 1)
        self.assertIn("Implement + Test", self.created[0]["title"])
        self.assertEqual(self.created[0]["workflow_revision_id"], "rev-implementation")
        self.assertIn("Branch: factory/published", self.created[0]["context"])
        self.assertIn(f"Specification head: {specification_head}\n", self.created[0]["context"])
        self.assertIn("Card: CARD-0042", self.created[0]["context"])

    def test_specification_head_gate_rejects_missing_short_and_malformed(self):
        cases = ("", "HEAD: abc123", "HEAD: " + "g" * 40)
        for result in cases:
            with self.subTest(result=result):
                reason = pilot.specification_head_gate(result)
                self.assertIsNotNone(reason)
                self.assertIn("точный полный SHA", reason)

    def test_specification_head_gate_accepts_exact_full_sha(self):
        self.assertIsNone(pilot.specification_head_gate("HEAD: " + "a" * 40))

    def test_exhausted_head_rescue_hard_stops_a_second_independent_specification(self):
        second_task = {
            "id": "specification-done-second",
            "title": self.task["title"],
            "state": "succeeded",
            "created_at": "2026-08-11T10:01:00Z",
            "repository_id": "repo-id",
        }
        self.run_cycle(
            "BRANCH: factory/published\nHEAD: abc123\nГОТОВО-КОГДА: файл pilot/pilot.py",
            cycles=3,
            durable_caps=True,
            task_variants=[self.task, second_task],
            result_by_task={
                self.task["id"]: "BRANCH: factory/published\nHEAD: abc123\n"
                               "ГОТОВО-КОГДА: файл pilot/pilot.py",
                second_task["id"]: "BRANCH: factory/published\nHEAD: def456\n"
                                      "ГОТОВО-КОГДА: файл pilot/pilot.py",
            },
        )

        self.assertEqual(len(self.successful_created), 1)
        self.assertIn("Specification", self.successful_created[0]["title"])
        self.assertNotIn("Implement + Test", self.successful_created[0]["title"])
        self.assertEqual(self.rescues["Сохранить спецификацию::SPEC_HEAD"], 1)
        self.assertEqual(self.state["processed"], [
            "specification-done", "specification-done-second",
        ])
        self.assertEqual(len(self.created), 1)
        self.assertTrue(any("SPEC HEAD STOP" in message for message in self.log_messages))

    def test_handoff_uses_published_branch_instead_of_stale_first_mention(self):
        report = self.run_cycle(
            "BRANCH: factory/stale\n"
            "Опубликована: factory/published\n"
            "ГОТОВО-КОГДА: файл pilot/pilot.py",
            published_branches={"factory/published"},
        )

        report.assert_called_once_with("github.com/acme/repo", "factory/published")
        self.assertEqual(len(self.created), 1)
        self.assertIn("Branch: factory/published", self.created[0]["context"])

    def test_missing_branch_returns_same_specification(self):
        self.run_cycle(
            "BRANCH: factory/missing\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_result=("нет", []),
        )

        self.assertEqual(len(self.created), 1)
        self.assertIn("Specification", self.created[0]["title"])
        self.assertEqual(self.created[0]["workflow_revision_id"], "rev-specification")
        self.assertEqual(self.created[0]["repository_id"], "repo-id")
        self.assertIn("закоммить", self.created[0]["context"])
        self.assertIn("git push -u origin HEAD", self.created[0]["context"])

    def test_empty_branch_diff_returns_same_specification(self):
        self.run_cycle(
            "BRANCH: factory/empty\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_result=("есть", []),
        )

        self.assertEqual(len(self.created), 1)
        self.assertIn("Specification", self.created[0]["title"])
        self.assertIn("не содержит отличий от main", self.created[0]["context"])

    def test_absent_branch_name_returns_same_specification(self):
        report = self.run_cycle("ГОТОВО-КОГДА: файл pilot/pilot.py")

        report.assert_not_called()
        self.assertEqual(len(self.created), 1)
        self.assertIn("Specification", self.created[0]["title"])
        self.assertIn("нет имени ветки", self.created[0]["context"])

    def test_github_error_retries_without_creating_any_stage(self):
        self.run_cycle(
            "BRANCH: factory/published\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_error=RuntimeError("GitHub unavailable"),
        )

        self.assertEqual(self.created, [])
        self.assertEqual(self.state["processed"], [])

    def test_failed_spec_branch_return_keeps_cap_notification_and_processed_clear(self):
        self.run_cycle(
            "BRANCH: factory/missing\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_result=("нет", []),
            create_effects=[RuntimeError("no_eligible_worker")],
            durable_caps=True,
        )

        self.assertEqual(self.rescues, {})
        self.assertEqual(self.state["processed"], [])
        self.assertEqual(self.successful_created, [])
        self.notify.assert_not_called()

    def test_next_cycle_retries_failed_spec_return_and_records_one_success(self):
        self.run_cycle(
            "BRANCH: factory/published\nHEAD: " + "a" * 40,
            create_effects=[RuntimeError("control plane unavailable"), None],
            cycles=2,
            durable_caps=True,
        )

        self.assertEqual(len(self.created), 2)
        self.assertEqual(len(self.successful_created), 1)
        self.assertEqual(self.rescues["Сохранить спецификацию::SPEC"], 1)
        self.assertEqual(self.state["processed"], ["specification-done"])
        self.notify.assert_called_once()

    def test_restart_retries_failed_branch_return_with_same_durable_cap(self):
        self.run_cycle(
            "BRANCH: factory/missing\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_result=("нет", []),
            create_effects=[RuntimeError("control plane unavailable"), None],
            cycles=2,
            restart_after_first=True,
            durable_caps=True,
        )

        self.assertEqual(len(self.created), 2)
        self.assertEqual(len(self.successful_created), 1)
        self.assertEqual(self.rescues["Сохранить спецификацию::SPEC_BRANCH"], 1)
        self.notify.assert_called_once()

    def test_no_eligible_worker_then_published_branch_starts_implementation(self):
        self.run_cycle(
            "BRANCH: factory/published\nHEAD: " + "a" * 40 + "\nГОТОВО-КОГДА: файл pilot/pilot.py",
            branch_results=[("нет", []), ("есть", ["knowledge/spec.md"])],
            create_effects=[RuntimeError("no_eligible_worker"), None],
            cycles=2,
            durable_caps=True,
        )

        self.assertEqual(len(self.successful_created), 1)
        self.assertIn("Implement + Test", self.successful_created[0]["title"])
        self.assertIn("Branch: factory/published", self.successful_created[0]["context"])
        self.assertEqual(self.rescues, {})
        self.notify.assert_not_called()

    def test_cap_rescue_primitive_records_each_return_only_after_task_id(self):
        with mock.patch.object(pilot, "RESCUE_PATH", self.rescue_path):
            for stage in ("SPEC_BRANCH", "SPEC", "GATE", "DIRT", "INFRA", "MERGE"):
                with self.subTest(stage=stage), \
                        mock.patch.object(pilot, "create_task", side_effect=[
                            RuntimeError("no worker"), {"task": {}}, {"task": {"id": stage}},
                        ]):
                    parent = {"id": "source-" + stage}
                    with self.assertRaises(RuntimeError):
                        pilot.create_cap_rescue("Работа", stage, {}, {}, parent)
                    self.assertEqual(pilot.cap_rescues("Работа", stage), 0)
                    with self.assertRaisesRegex(RuntimeError, "returned no task"):
                        pilot.create_cap_rescue("Работа", stage, {}, {}, parent)
                    self.assertEqual(pilot.cap_rescues("Работа", stage), 0)
                    pilot.create_cap_rescue("Работа", stage, {}, {}, parent)
                    self.assertEqual(pilot.cap_rescues("Работа", stage), 1)

    def test_review_gate_defers_missing_branch_cap_until_return_task_exists(self):
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "missing"}), \
                mock.patch.object(pilot, "cap_rescues", return_value=0), \
                mock.patch.object(pilot, "note_cap_rescue") as note:
            result = pilot.review_gate({}, "Работа", "factory/missing", "file:///tmp/repo")

        self.assertEqual(result["cap_stage"], "GATE")
        note.assert_not_called()

    def test_review_gate_defers_dirty_branch_cap_until_return_task_exists(self):
        def loader(path, default=None):
            if path == pilot.AREAS_PATH:
                return {"Работа": ["repo::pilot/pilot.py"]}
            return default

        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value={"state": "ok", "files": ["pilot/pilot.py", "node_modules/cache.js"], "base_sha": "a" * 40, "candidate_sha": "b" * 40, "default_branch": "main"}), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None), \
                mock.patch.object(pilot, "load", side_effect=loader), \
                mock.patch.object(pilot, "rebuild_clean_branch", return_value=""), \
                mock.patch.object(pilot, "cap_rescues", return_value=0), \
                mock.patch.object(pilot, "note_cap_rescue") as note:
            result = pilot.review_gate({}, "Работа", "factory/dirty", "file:///tmp/repo")

        self.assertEqual(result["cap_stage"], "DIRT")
        note.assert_not_called()

    def test_branch_report_treats_only_http_404_as_missing(self):
        response = types.SimpleNamespace(
            returncode=1, stdout="", stderr="gh: Branch not found (HTTP 404)")
        with mock.patch.object(pilot.subprocess, "run", return_value=response):
            self.assertEqual(
                pilot.branch_report("github.com/acme/repo", "factory/missing"),
                ("нет", []),
            )

    def test_branch_report_raises_on_service_failure(self):
        response = types.SimpleNamespace(
            returncode=1, stdout="", stderr="connection reset by peer")
        with mock.patch.object(pilot.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "connection reset"):
                pilot.branch_report("github.com/acme/repo", "factory/task")


class CardNumberReservationTests(unittest.TestCase):
    def test_parallel_branches_reserve_distinct_numbers_and_retry_keeps_one(self):
        state = {"processed": []}
        cards = [{"name": "CARD-0069-old.md"}]
        with mock.patch.object(pilot, "gh_json", return_value=cards) as github, \
                mock.patch.object(pilot, "save") as save:
            first = pilot.reserved_card_number(state, "github.com/acme/repo", "factory/one")
            second = pilot.reserved_card_number(state, "github.com/acme/repo", "factory/two")
            retry = pilot.reserved_card_number(state, "github.com/acme/repo", "factory/one")

        self.assertEqual((first, second, retry), ("CARD-0070", "CARD-0071", "CARD-0070"))
        self.assertEqual(state[pilot.CARD_RESERVATIONS_KEY], {
            "github.com/acme/repo::factory/one": 70,
            "github.com/acme/repo::factory/two": 71,
        })
        self.assertEqual(save.call_count, 2)
        self.assertEqual(github.call_count, 2)

    def test_unreadable_card_catalogue_does_not_guess_a_number(self):
        state = {"processed": []}
        with mock.patch.object(pilot, "gh_json", return_value=None), \
                mock.patch.object(pilot, "save") as save:
            card = pilot.reserved_card_number(state, "github.com/acme/repo", "factory/one")

        self.assertIsNone(card)
        self.assertNotIn(pilot.CARD_RESERVATIONS_KEY, state)
        save.assert_not_called()

    def test_handoff_keeps_card_from_context_or_stage_report(self):
        self.assertEqual(pilot.extract_card("", "Branch: factory/task\nCard: CARD-0070\n"),
                         "CARD-0070")
        self.assertEqual(pilot.extract_card("Card: CARD-0071\n", "Card: CARD-0070\n"),
                         "CARD-0070")
        self.assertIn("выдана строка `Card: CARD-…`", pilot.AGENT_RULES)

    def test_review_rejects_card_with_other_reserved_number_first(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0071-wrong.md"]
        snapshot = {"state": "ok", "default_branch": "main", "base_sha": "a" * 40,
                    "candidate_sha": "b" * 40, "merge_base_sha": "a" * 40,
                    "base_advanced": False, "base_ahead_by": 0, "ahead_by": 1, "files": files}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=snapshot), \
                mock.patch.object(pilot, "implementation_commit_gate") as implementation:
            result = pilot.review_gate({}, "Работа", "factory/task", "github.com/acme/repo",
                                       expected_card="CARD-0070")

        self.assertTrue(result["back"])
        self.assertIn("CARD-0070", result["note"])
        implementation.assert_not_called()

    def test_review_accepts_matching_card_for_normal_commit_gate(self):
        files = ["pilot/pilot.py", "knowledge/cards/CARD-0070-correct.md"]
        snapshot = {"state": "ok", "default_branch": "main", "base_sha": "a" * 40,
                    "candidate_sha": "b" * 40, "merge_base_sha": "a" * 40,
                    "base_advanced": False, "base_ahead_by": 0, "ahead_by": 1, "files": files}
        with mock.patch.object(pilot, "fresh_branch_snapshot", return_value=snapshot), \
                mock.patch.object(pilot, "implementation_commit_gate", return_value=None) as implementation, \
                mock.patch.object(pilot, "load", return_value={}):
            result = pilot.review_gate({}, "Работа", "factory/task", "github.com/acme/repo",
                                       expected_card="CARD-0070")

        self.assertFalse(result["back"])
        implementation.assert_called_once_with("github.com/acme/repo", "factory/task", files)


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


class CorrectionProvenanceStormTests(unittest.TestCase):
    _SUBPROCESS_DRIVER = r"""
import contextlib
import json
import os
import time
from unittest import mock

from pilot import pilot

request = json.loads(os.environ["PILOT_RESTART_REQUEST"])
action = request["action"]
task = request.get("task")
pilot.WORKS_PATH = request["works_path"]
pilot.DUPLICATE_ROOT_EVENTS_PATH = request["events_path"]
pilot.QUESTION_DIR = request["questions_path"]
pilot.STATE_PATH = request["state_path"]
pilot.MERGES_PATH = request["merges_path"]
pilot.VERDICT_DIR = request["verdicts_path"]
os.makedirs(os.path.join(pilot.HOME, "pilot"), exist_ok=True)
os.makedirs(pilot.QUESTION_DIR, exist_ok=True)
os.makedirs(pilot.VERDICT_DIR, exist_ok=True)


def load_fixture():
    fixture = pilot.load(request["fixture_path"], None)
    if not isinstance(fixture, dict):
        raise AssertionError("missing durable API fixture")
    return fixture


def save_fixture(fixture):
    pilot.save(request["fixture_path"], fixture)


def set_succeeded(fixture, task_id, result):
    task = next(item for item in fixture["tasks"] if item["id"] == task_id)
    task["state"] = "succeeded"
    fixture["details"][task_id]["task"] = task
    fixture["details"][task_id]["attempts"] = [{"result": result}]
    save_fixture(fixture)


def latest_stage(fixture, stage):
    return next(item for item in reversed(fixture["tasks"])
                if fixture["details"].get(item["id"], {}).get(
                    "workflow", {}).get("title") == stage)


def run_full_cycle(fixture):
    # Run one real cycle against a JSON-only control-plane fixture.
    state = pilot.load(pilot.STATE_PATH, {"processed": []})
    day_start = pilot.calendar.timegm(time.strptime(
        time.strftime("%Y-%m-%d", time.gmtime()), "%Y-%m-%d"))

    def fake_api(path, body=None):
        if path == "/tasks?limit=100":
            return {"tasks": list(fixture["tasks"])}
        if path.startswith("/tasks/"):
            return fixture["details"][path.rsplit("/", 1)[-1]]
        if path == "/workers":
            return {"workers": list(fixture["workers"].values())}
        if path == "/repositories":
            return {"repositories": [{"id": "repo-id",
                                      "remote_identity": "github.com/acme/repo"}]}
        if path == "/workflows":
            return {"workflows": [{"id": stage, "enabled": True,
                "current_revision": {"id": data["revision_id"], "title": stage}}
                for stage, data in fixture["workflows"].items()]}
        raise AssertionError(path)

    def create(body, _conf=None):
        parent = next(item for item in fixture["tasks"]
                      if item["id"] == body["parent_task_id"])
        task_id = "created-%d" % (len(fixture["created"]) + 1)
        task = {
            "id": task_id, "work_id": parent["work_id"],
            "parent_task_id": parent["id"],
            "correction_kind": body.get("correction_kind", ""),
            "title": body["title"], "state": "queued",
            "created_at": "2026-08-11T20:%02d:00Z" % (len(fixture["created"]) + 2),
            "repository_id": "repo-id",
        }
        stage = next(stage for stage in fixture["workflows"]
                     if " " + stage + "]" in task["title"])
        fixture["tasks"].append(task)
        fixture["details"][task_id] = {
            "task": task, "workflow": {"title": stage},
            "context": body.get("context", ""), "attempts": [],
        }
        fixture["created"].append({"id": task_id, "body": dict(body)})
        save_fixture(fixture)
        return {"task": task}

    noops = (
        "collect_automation_findings", "cleanup_completed_plan_cards",
        "write_dashboard", "provider_limits_tick", "detect_limits",
        "budget_guard", "handle_epics", "reconcile_diag_repairs", "diag_sweep",
        "rescue_queued", "supersede_stale_questions",
        "cleanup_orphaned_paused_pipelines", "advance_epics", "pipeline_watch",
        "cleanup_work_archive", "area_extend", "collect_ideas",
        "record_implementation_artifact", "save_stage_verdict",
        "retry_pending_factory_deploy", "autostart_plan",
    )
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
        stack.enter_context(mock.patch.object(
            pilot, "all_tasks", side_effect=lambda: list(fixture["tasks"])))
        stack.enter_context(mock.patch.object(
            pilot, "codex_usage_snapshot", return_value={day_start: {}}))
        stack.enter_context(mock.patch.object(pilot, "day_budget_blocks", return_value=False))
        stack.enter_context(mock.patch.object(pilot, "host_block", return_value={"state": "ok"}))
        stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block", return_value=""))
        stack.enter_context(mock.patch.object(pilot, "stage_worker", return_value="worker"))
        stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
        stack.enter_context(mock.patch.object(pilot, "decide", return_value={
            "action": "advance", "reason": "готово", "handoff": "",
            "next_complexity": "medium"}))
        stack.enter_context(mock.patch.object(pilot, "create_task", side_effect=create))
        stack.enter_context(mock.patch.object(pilot, "review_gate", return_value={
            "back": False, "branch": "factory/correction", "note": "ok"}))
        stack.enter_context(mock.patch.object(pilot, "verify_gate", return_value={
            "state": "ok", "snapshot": {"candidate_sha": "a" * 40}}))
        stack.enter_context(mock.patch.object(
            pilot, "selected_delivery", return_value=("factory/correction", "a" * 40)))
        stack.enter_context(mock.patch.object(
            pilot, "pushed_branch", return_value="factory/correction"))
        stack.enter_context(mock.patch.object(pilot, "merge_recorded", return_value=False))
        stack.enter_context(mock.patch.object(pilot, "gh_json", return_value={
            "ahead_by": 1, "commit": {"sha": "a" * 40}}))
        stack.enter_context(mock.patch.object(
            pilot, "broker_operation", return_value={"status": "succeeded"}))
        stack.enter_context(mock.patch.object(
            pilot, "gh_merge", return_value=(True, "merged")))
        stack.enter_context(mock.patch.object(pilot, "notify"))
        for name in noops:
            stack.enter_context(mock.patch.object(pilot, name))
        pilot.cycle(fixture["conf"], state)
    save_fixture(fixture)
    pilot.save(pilot.STATE_PATH, state)


if action == "discover":
    pilot.record_new_works(request["conf"], request["tasks"],
                           max_age_min=10_000_000)
elif action == "crash":
    boundary = request["boundary"]

    def terminate_at_boundary(name):
        if name == boundary:
            os._exit(86)

    pilot._duplicate_root_crash_boundary = terminate_at_boundary
    pilot.note_duplicate_root_prevented(task)
elif action == "recover":
    pilot.note_duplicate_root_prevented(task)
    pilot.note_duplicate_root_prevented(task)
elif action == "full_cycle_before_restart":
    fixture = load_fixture()
    run_full_cycle(fixture)
    correction = latest_stage(fixture, "Implement + Test")
    if not correction.get("correction_kind"):
        raise AssertionError("first process did not create correction")
    correction["title"] = "[auto] [1/5 Triage] Изменённое человеком имя"
    set_succeeded(fixture, correction["id"],
                  "BRANCH: factory/correction\nHEAD: " + "a" * 40 + "\nCard: CARD-0086")
    fixture["restart"] = {"first_pid": os.getpid(),
                          "correction_id": correction["id"]}
    save_fixture(fixture)
elif action == "full_cycle_after_restart":
    if any(key in request for key in ("tasks", "details", "state", "created")):
        raise AssertionError("restart received in-memory pipeline objects")
    fixture = load_fixture()
    restart = fixture.get("restart") or {}
    if not restart.get("first_pid") or restart["first_pid"] == os.getpid():
        raise AssertionError("second process did not restore after a real restart")
    if not pilot.load(pilot.STATE_PATH, None):
        raise AssertionError("restart lost durable Pilot state")
    run_full_cycle(fixture)
    review = latest_stage(fixture, "Review")
    set_succeeded(fixture, review["id"], "APPROVE\nHEAD: " + "a" * 40)
    run_full_cycle(fixture)
    verify = latest_stage(fixture, "Verify")
    set_succeeded(fixture, verify["id"], "PASS\nTRY: none")
    run_full_cycle(fixture)
    fixture["restart"].update({"second_pid": os.getpid(),
                               "terminal_task_id": verify["id"]})
    save_fixture(fixture)
else:
    raise AssertionError(action)
"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.works_path = os.path.join(self.temporary.name, "works.json")
        self.events_path = os.path.join(
            self.temporary.name, "duplicate-root-prevented.json")
        self.questions_path = os.path.join(self.temporary.name, "questions")
        self.state_path = os.path.join(self.temporary.name, "state.json")
        self.tasks_path = os.path.join(self.temporary.name, "tasks.json")
        self.merges_path = os.path.join(self.temporary.name, "merges.jsonl")
        self.fixture_path = os.path.join(self.temporary.name, "api-fixture.json")
        self.verdicts_path = os.path.join(self.temporary.name, "verdicts")
        os.makedirs(self.questions_path)
        self.patches = (
            mock.patch.object(pilot, "WORKS_PATH", self.works_path),
            mock.patch.object(
                pilot, "DUPLICATE_ROOT_EVENTS_PATH", self.events_path),
            mock.patch.object(pilot, "QUESTION_DIR", self.questions_path),
            mock.patch.object(pilot, "STATE_PATH", self.state_path),
            mock.patch.object(pilot, "MERGES_PATH", self.merges_path),
            mock.patch.object(pilot, "VERDICT_DIR", self.verdicts_path),
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conf = {"stages": [
            {"workflow": "Triage"}, {"workflow": "Specification"},
            {"workflow": "Implement + Test"}, {"workflow": "Review"},
            {"workflow": "Verify"},
        ]}
        self.root = {
            "id": "root-work", "work_id": "root-work",
            "title": "[auto] [1/5 Triage] Исправить корзину",
            "state": "succeeded", "created_at": "2026-08-11T20:00:00Z",
        }

    def correction(self, kind):
        source = "review-task" if kind == "review_return" else "verify-task"
        return {
            "id": kind, "work_id": self.root["id"],
            "parent_task_id": source, "correction_kind": kind,
            "title": "[auto] [3/5 Implement + Test] Исправить корзину",
            "state": "queued", "created_at": "2026-08-11T20:01:00Z",
        }

    def run_pilot_process(self, request, expected_returncode=0):
        request = dict(request, works_path=self.works_path,
                       events_path=self.events_path,
                       questions_path=self.questions_path,
                       state_path=self.state_path,
                       merges_path=self.merges_path,
                       verdicts_path=self.verdicts_path,
                       fixture_path=self.fixture_path)
        env = os.environ.copy()
        env["FACTORY_DATA_HOME"] = self.temporary.name
        env["PILOT_RESTART_REQUEST"] = json.dumps(request)
        result = subprocess.run(
            [sys.executable, "-c", self._SUBPROCESS_DRIVER],
            cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
            text=True, capture_output=True, timeout=30, check=False)
        self.assertEqual(
            result.returncode, expected_returncode,
            "stdout=%r stderr=%r" % (result.stdout, result.stderr))

    def assert_storm_is_single_pipeline(self, kind):
        correction = self.correction(kind)
        tasks = [self.root, correction]
        self.run_pilot_process({
            "action": "discover", "conf": self.conf, "tasks": [self.root],
        })
        # The first interpreter has exited. A newly imported Pilot process
        # reads the durable files and rediscovers the correction snapshot.
        self.run_pilot_process({
            "action": "discover", "conf": self.conf,
            "tasks": list(reversed(tasks)),
        })
        works = pilot.load(self.works_path, {})
        outbox = pilot.load(self.events_path, {})
        events = outbox["events"]
        event_id = "pilot_duplicate_root_prevented:" + correction["id"]
        self.assertEqual(list(works), [self.root["id"]])
        self.assertEqual(len({pilot.task_work_id(task) for task in tasks}), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[event_id]["payload"], {
            "task_id": correction["id"], "work_id": self.root["id"],
            "parent_task_id": correction["parent_task_id"],
            "correction_kind": kind,
        })
        self.assertEqual(outbox["acknowledged"], {event_id: True})

    def assert_full_cycle_survives_restart(self, kind):
        for path in (self.works_path, self.events_path, self.state_path,
                     self.tasks_path, self.merges_path, self.fixture_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        for directory in (self.questions_path, self.verdicts_path):
            if os.path.isdir(directory):
                for name in os.listdir(directory):
                    os.unlink(os.path.join(directory, name))

        base = "Исправить корзину"
        source_stage = "Review" if kind == "review_return" else "Verify"
        root = dict(self.root, repository_id="repo-id")
        source = {
            "id": source_stage.lower() + "-failed", "work_id": root["id"],
            "parent_task_id": "implement-original", "correction_kind": "",
            "title": f"[auto] [{'4' if source_stage == 'Review' else '5'}/5 {source_stage}] {base}",
            "state": "succeeded", "created_at": "2026-08-11T20:01:00Z",
            "repository_id": "repo-id",
        }
        question = {
            "id": "answer-" + kind, "status": "answered", "answer": "Исправь",
            "title": base, "stage": source_stage,
            "resume_stage": "Implement + Test", "task_id": source["id"],
            "repository_id": "repo-id", "question": "Исправлять?",
            "prior_result": "REQUEST CHANGES",
        }
        workflows = {stage: {"enabled": True, "revision_id": "rev-" + stage}
                     for stage in ("Triage", "Specification", "Implement + Test",
                                   "Review", "Verify")}
        workers = {"worker": {"id": "worker-id", "name": "worker",
                               "online": True, "health": "healthy",
                               "capacity": 1, "active_count": 0}}
        fixture = {
            "conf": self.conf, "tasks": [root, source],
            "details": {source["id"]: {
                "task": source, "workflow": {"title": source_stage},
                "attempts": [{"result": "REQUEST CHANGES"}],
            }},
            "workflows": workflows, "workers": workers, "created": [],
        }
        # The only hand-off between the two interpreters is these files.
        pilot.save(self.fixture_path, fixture)
        pilot.save(self.works_path, {root["id"]: {
            "origin": pilot.ORIGIN_OWNER, "base_title": base,
        }})
        pilot.save(self.state_path, {"processed": [source["id"], root["id"]]})
        pilot.save(os.path.join(self.questions_path, question["id"] + ".json"), question)

        self.run_pilot_process({"action": "full_cycle_before_restart"})
        # This request deliberately contains paths only, never task objects.
        self.run_pilot_process({"action": "full_cycle_after_restart"})

        fixture = pilot.load(self.fixture_path, {})
        correction = next(task for task in fixture["tasks"]
                          if task.get("correction_kind") == kind)
        review = next(task for task in fixture["tasks"]
                      if fixture["details"].get(task["id"], {}).get(
                          "workflow", {}).get("title") == "Review"
                      and task["id"] != source["id"])
        verify = next(task for task in fixture["tasks"]
                      if fixture["details"].get(task["id"], {}).get(
                          "workflow", {}).get("title") == "Verify"
                      and task["id"] != source["id"])
        restart = fixture["restart"]
        self.assertNotEqual(restart["first_pid"], restart["second_pid"])
        self.assertEqual(restart["correction_id"], correction["id"])
        self.assertEqual(restart["terminal_task_id"], verify["id"])
        self.assertEqual(correction["title"],
                         "[auto] [1/5 Triage] Изменённое человеком имя")
        self.assertEqual(len([task for task in fixture["tasks"]
                              if task["id"] == task["work_id"]]), 1)
        self.assertEqual({task["work_id"] for task in fixture["tasks"]}, {root["id"]})
        self.assertFalse(any(" Triage]" in item["body"]["title"]
                             or " Specification]" in item["body"]["title"]
                             for item in fixture["created"]))
        self.assertEqual([item["body"].get("correction_kind", "")
                          for item in fixture["created"]], [kind, "", ""])
        self.assertEqual(pilot.load(self.works_path, {})[root["id"]]["base_title"], base)
        self.assertTrue(pilot.load(
            os.path.join(self.verdicts_path, verify["id"] + ".json"),
            {}).get("final_pass"))
        with open(self.merges_path, encoding="utf-8") as stream:
            merged = [json.loads(line)["task_id"] for line in stream if line.strip()]
        self.assertEqual(merged, [verify["id"]])
        state = pilot.load(self.state_path, {})
        target_key, adapter = pilot._delivery_target("github.com/acme/repo")
        self.assertEqual(adapter, "external-merge")
        delivery = state[pilot.DELIVERY_STATE_KEY]["targets"][target_key]
        generation = delivery["generations"][delivery["current_generation"]]
        self.assertEqual(generation["phase"], "completed")
        self.assertEqual(set(generation["completed_waits"]), {verify["id"]})
        self.assertEqual(
            state[pilot.DELIVERY_STATE_KEY]["outbox"][generation["id"] + ":done"]["status"],
            "sent")

    def test_review_and_verify_discovery_survives_real_process_restart(self):
        for kind in ("review_return", "verify_return"):
            with self.subTest(kind=kind):
                for path in (self.works_path, self.events_path):
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass
                self.assert_storm_is_single_pipeline(kind)

    def test_review_and_verify_corrections_complete_one_pipeline_after_restart(self):
        for kind in ("review_return", "verify_return"):
            with self.subTest(kind=kind):
                self.assert_full_cycle_survives_restart(kind)

    def test_explicit_provenance_wins_over_auto_title(self):
        correction = self.correction("review_return")
        correction["title"] = "[auto] [1/5 Triage] Изменённое человеком имя"
        pilot.record_new_works(
            self.conf, [correction], max_age_min=10_000_000)
        self.assertEqual(pilot.load(self.works_path, {}), {})
        self.assertEqual(
            len(pilot.load(self.events_path, {})["events"]), 1)

    def test_duplicate_root_outbox_converges_at_every_crash_boundary(self):
        correction = self.correction("review_return")
        boundaries = (
            "before_journal_append", "after_journal_append",
            "before_acknowledgement", "after_acknowledgement",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                try:
                    os.unlink(self.events_path)
                except FileNotFoundError:
                    pass
                self.run_pilot_process({
                    "action": "crash", "boundary": boundary,
                    "task": correction,
                }, expected_returncode=86)
                # The crashing interpreter is gone. A new Pilot process
                # replays the idempotent event from the durable outbox.
                self.run_pilot_process({
                    "action": "recover", "task": correction,
                })
                outbox = pilot.load(self.events_path, {})
                event_id = "pilot_duplicate_root_prevented:" + correction["id"]
                self.assertEqual(list(outbox["events"]), [event_id])
                self.assertEqual(list(outbox["acknowledged"]), [event_id])
                self.assertEqual(
                    outbox["events"][event_id]["event_type"],
                    "pilot_duplicate_root_prevented")

    def test_child_builder_always_sends_parent_and_correction(self):
        sent = []
        with mock.patch.object(
                pilot, "create_task",
                side_effect=lambda body, _conf: sent.append(body)
                or {"task": {"id": "child"}}):
            pilot.create_child_task(
                {"title": "[auto] correction"}, self.root, {},
                "review_return")
        self.assertEqual(sent[0]["parent_task_id"], self.root["id"])
        self.assertEqual(sent[0]["correction_kind"], "review_return")

    def test_identical_titles_with_distinct_work_ids_remain_distinct(self):
        first = dict(self.root, state="running")
        other = dict(first, id="other-work", work_id="other-work")
        tasks = [first, other, self.correction("review_return")]
        self.assertEqual(len(pilot.active_auto_works(tasks)), 2)
        self.assertEqual(pilot.stage_attempts(tasks, "Triage", first), 1)
        self.assertEqual(pilot.stage_attempts(tasks, "Triage", other), 1)
        self.assertIs(
            pilot.live_or_done_at(tasks, other, 1), other)

    def test_archived_attempt_does_not_spend_current_retry_limit(self):
        old = dict(
            self.correction("review_return"), id="old-attempt", state="failed")
        current = dict(
            self.correction("verify_return"), id="current-attempt", state="running")
        receipt = {
            "task_id": old["id"], "closed": "2026-08-11T20:02:00Z",
            "closed_reason": "Попытку заменила более новая попытка этой работы.",
        }
        pilot.save(self.works_path, {self.root["id"]: {
            "base_title": "Исправить корзину", "archived_attempts": [receipt],
        }})

        self.assertEqual(
            pilot.stage_attempts([old, current], "Implement + Test", current), 1)
        self.assertEqual(
            pilot.load(self.works_path, {})[self.root["id"]]["archived_attempts"],
            [receipt])

    def test_merge_rounds_include_archived_attempts_of_current_generation_only(self):
        archived = dict(
            self.correction("review_return"), id="archived-implement",
            state="succeeded")
        current = dict(
            self.correction("verify_return"), id="current-implement",
            state="succeeded")
        verify = {
            "id": "current-verify", "work_id": self.root["id"],
            "title": "[auto] [5/5 Verify] Исправить корзину",
            "state": "succeeded", "created_at": "2026-08-11T20:03:00Z",
        }
        previous_generation = [dict(
            archived, id=f"previous-{number}", work_id="previous-root")
            for number in range(3)
        ]
        pilot.save(self.works_path, {self.root["id"]: {
            "base_title": "Исправить корзину",
            "archived_attempts": [{"task_id": archived["id"]}],
        }})

        self.assertEqual(
            pilot._merge_rounds(
                previous_generation + [archived, current, verify], verify),
            2)

    def test_unarchived_terminal_attempt_still_spends_retry_limit(self):
        old = dict(
            self.correction("review_return"), id="old-attempt", state="failed")
        current = dict(
            self.correction("verify_return"), id="current-attempt", state="running")
        pilot.save(self.works_path, {self.root["id"]: {
            "base_title": "Исправить корзину",
        }})

        self.assertEqual(
            pilot.stage_attempts([old, current], "Implement + Test", current), 2)

    def test_archive_isolated_between_identically_titled_work_ids(self):
        old = dict(
            self.correction("review_return"), id="old-attempt", state="failed")
        current = dict(
            self.correction("verify_return"), id="current-attempt", state="running")
        pilot.save(self.works_path, {"other-work": {
            "base_title": "Исправить корзину",
            "archived_attempts": [{"task_id": old["id"]}],
        }})

        self.assertEqual(
            pilot.stage_attempts([old, current], "Implement + Test", current), 2)

    def test_missing_or_malformed_work_archive_keeps_attempt_count(self):
        old = dict(
            self.correction("review_return"), id="old-attempt", state="failed")
        current = dict(
            self.correction("verify_return"), id="current-attempt", state="running")
        tasks = [old, current]

        self.assertEqual(
            pilot.stage_attempts(tasks, "Implement + Test", current), 2)
        pilot.save(self.works_path, {self.root["id"]: {
            "base_title": "Исправить корзину", "archived_attempts": 42,
        }})
        self.assertEqual(
            pilot.stage_attempts(tasks, "Implement + Test", current), 2)

    @mock.patch.object(pilot, "load_questions", return_value=[{
        "task_id": "waiting-work", "status": "open",
    }])
    def test_question_waiting_for_owner_does_not_consume_executor_slot(self, _questions):
        waiting = dict(
            self.root, id="waiting-work", work_id="waiting-work",
            state="succeeded")

        self.assertEqual(pilot.active_auto_works([waiting]), set())


class PipelineWatchTests(unittest.TestCase):
    def setUp(self):
        self.now = 10_000
        self.memory = {}
        self.works = {}
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
        if path == pilot.WORKS_PATH:
            return self.works
        return default

    def _save(self, path, value):
        if path == pilot.STALL_PATH:
            self.memory = value
        elif path == pilot.WORKS_PATH:
            self.works = value
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
            "id": "source-task",
            "title": f"[auto] [1/3 {stage}] Встроенный патруль",
            "state": state,
            "repository_id": repository_id,
        }

    def watch(self, tasks=None):
        pilot.pipeline_watch(
            self.conf, tasks or [self.task()], self.workflows, self.workers
        )

    def test_waits_before_resuming_lost_transition(self):
        self.assertEqual(pilot.STALL_WAIT, 450)
        self.watch()
        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Встроенный патруль"]["since"], self.now)

        self.now += pilot.STALL_WAIT - 1
        self.watch()
        self.assertEqual(self.created, [])

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

    def test_watch_carries_canonical_implementation_and_updates_snapshot(self):
        head = "a" * 40
        self.works["Встроенный патруль"] = {
            "implementation_artifact": {
                "branch": "factory/real-implementation", "head": head,
                "task_id": "implement-task", "recorded_at": "2026-08-11T12:00:00Z",
                "generation": "",
            }
        }
        self.memory = {
            "Встроенный патруль": {"since": self.now - pilot.STALL_WAIT, "nudges": 0}
        }
        tasks = [self.task()]

        self.watch(tasks)

        self.assertIn("Branch: factory/real-implementation", self.created[0]["context"])
        self.assertIn(f"Implementation head: {head}", self.created[0]["context"])
        self.assertEqual(tasks[-1]["state"], "created")
        self.assertIn("[2/3 Implement]", tasks[-1]["title"])
        self.assertEqual(tasks[-1]["repository_id"], "repo-id")
        self.assertEqual(
            pilot.live_or_done_at(
                tasks, "Встроенный патруль", 1,
                since="1970-01-01T00:00:00Z")["id"],
            "new-task")

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

    def test_failed_nudge_costs_attempt_backs_off_and_keeps_reason(self):
        self.memory = {
            "Встроенный патруль": {"since": self.now - pilot.STALL_WAIT, "nudges": 0}
        }

        def boom(body, conf):
            raise urllib.error.HTTPError(
                "http://panel/api/v1/tasks", 400, "Bad Request", None,
                io.BytesIO(b'{"error":{"code":"work_closed"}}'))

        with mock.patch.object(pilot, "create_task", side_effect=boom):
            self.watch()
            self.watch()   # то же мгновение: окно ожидания уже сдвинуто

        rec = self.memory["Встроенный патруль"]
        self.assertEqual(rec["nudges"], 1)
        self.assertEqual(rec["since"], self.now)
        self.assertEqual(rec["why"], "nudge_failed")
        self.assertIn("work_closed", rec["reason"])
        self.assertEqual(self.created, [])
        self.assertEqual(self.work_status["Встроенный патруль"]["state"], "stuck")
        self.assertIn("work_closed",
                      self.work_status["Встроенный патруль"]["text"])

        self.now += pilot.STALL_WAIT
        with mock.patch.object(pilot, "create_task", side_effect=boom):
            self.watch()   # вторая неудача тратит последнюю попытку
        self.now += pilot.STALL_WAIT
        with mock.patch.object(pilot, "create_task", side_effect=boom):
            self.watch()   # попытки кончились — сдаёмся
            self.watch()   # и молчим, а не сдаёмся второй раз

        self.assertEqual(self.memory["Встроенный патруль"]["why"], "give_up")
        self.assertEqual(len(self.notifications), 1)
        self.assertIn("после двух попыток", self.notifications[0][1])

    def test_slot_deferral_pauses_without_burning_attempts(self):
        self.memory = {
            "Встроенный патруль": {"since": self.now - pilot.STALL_WAIT, "nudges": 0}
        }
        with mock.patch.object(
            pilot, "create_task",
            side_effect=pilot.ParallelWorkLimit("parallel_work_limit: stage deferred"),
        ):
            self.watch()

        rec = self.memory["Встроенный патруль"]
        self.assertEqual(rec["nudges"], 0)
        self.assertEqual(rec["since"], self.now)
        self.assertNotEqual(rec.get("why"), "nudge_failed")
        self.assertEqual(self.notifications, [])

    def test_full_capacity_defers_without_requesting_each_stalled_work(self):
        self.conf["max_parallel_works"] = 2
        self.conf["_active_work_tasks"] = [
            {
                "id": "active-one", "work_id": "active-one",
                "title": "[auto] [2/3 Implement] Первая занятая работа",
                "state": "running",
            },
            {
                "id": "active-two", "work_id": "active-two",
                "title": "[auto] [2/3 Implement] Вторая занятая работа",
                "state": "running",
            },
        ]
        self.memory = {
            "Встроенный патруль": {
                "since": self.now - pilot.STALL_WAIT,
                "nudges": 0,
            }
        }

        self.watch()

        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Встроенный патруль"]["since"], self.now)
        self.assertEqual(self.memory["Встроенный патруль"]["nudges"], 0)
        self.assertEqual(self.notifications, [])

    def test_full_capacity_does_not_scan_task_history(self):
        self.conf["max_parallel_works"] = 1
        self.conf["_active_work_tasks"] = [{
            "id": "active", "work_id": "active",
            "title": "[auto] [2/3 Implement] Busy work", "state": "running",
        }]
        self.memory = {
            "Waiting work": {"since": self.now - pilot.STALL_WAIT, "nudges": 0}
        }
        tasks = [self.task()]
        tasks.extend({
            "id": f"history-{index}", "work_id": f"history-{index}",
            "title": f"[auto] [1/3 Triage] Historical work {index}",
            "state": "succeeded",
        } for index in range(500))

        with mock.patch.object(
            pilot, "work_lifecycle_block",
            side_effect=AssertionError("full-capacity watch scanned task history"),
        ):
            self.watch(tasks)

        self.assertEqual(self.created, [])
        self.assertEqual(self.memory["Waiting work"]["since"], self.now)
        self.assertEqual(self.memory["Waiting work"]["nudges"], 0)

    def test_records_for_vanished_works_are_purged(self):
        self.memory = {
            "Призрак давно закрытой работы": {"since": 1, "nudges": 2, "why": "give_up"}
        }
        self.watch()

        self.assertNotIn("Призрак давно закрытой работы", self.memory)
        self.assertEqual(self.created, [])
        self.assertEqual(self.notifications, [])

    def test_gives_up_after_two_nudges_and_notifies_only_once(self):
        self.memory = {
            "Встроенный патруль": {
                "since": self.now - pilot.STALL_WAIT,
                "nudges": pilot.STALL_NUDGES,
                "stage": "Specification",
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

    def test_nudge_attempts_reset_after_work_reaches_the_next_stage(self):
        self.memory = {
            "Встроенный патруль": {
                "since": self.now - pilot.STALL_WAIT,
                "nudges": pilot.STALL_NUDGES,
                "why": "give_up",
                "stage": "Specification",
            }
        }

        self.watch([self.task(stage="Implement")])

        self.assertEqual(len(self.created), 0)
        rec = self.memory["Встроенный патруль"]
        self.assertEqual(rec["stage"], "Implement")
        self.assertEqual(rec["nudges"], 0)
        self.assertNotEqual(rec.get("why"), "give_up")

        self.now += pilot.STALL_WAIT
        self.watch([self.task(stage="Implement")])
        self.assertEqual(len(self.created), 1)
        self.assertIn("[3/3 Review]", self.created[0]["title"])

    def test_legacy_give_up_record_is_retried_after_upgrade(self):
        self.memory = {
            "Встроенный патруль": {
                "since": self.now - pilot.STALL_WAIT,
                "nudges": pilot.STALL_NUDGES,
                "why": "give_up",
            }
        }

        self.watch()

        self.assertEqual(len(self.created), 1)
        self.assertIn("[2/3 Implement]", self.created[0]["title"])
        self.assertEqual(
            self.memory["Встроенный патруль"]["stage"], "Specification")
        self.assertNotEqual(
            self.memory["Встроенный патруль"].get("why"), "give_up")


class CanonicalImplementationBranchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.works_path = os.path.join(self.temporary.name, "works.json")
        self.questions_path = os.path.join(self.temporary.name, "questions")
        os.makedirs(self.questions_path)
        self.path_patches = [
            mock.patch.object(pilot, "WORKS_PATH", self.works_path),
            mock.patch.object(pilot, "QUESTION_DIR", self.questions_path),
        ]
        for patcher in self.path_patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        pilot.save(self.works_path, {
            "Настоящая работа": {"run_generation": "generation-1"}
        })

    @staticmethod
    def github(branch="factory/implementation", head=None, files=None):
        head = head or "b" * 40
        files = [{"filename": "pilot/pilot.py"}] if files is None else files

        def response(args, strict=False):
            path = args[-1]
            if "/branches/" in path:
                return {"name": branch, "commit": {"sha": head}}
            if "/compare/" in path:
                return {"files": files}
            raise AssertionError(path)

        return response

    def test_successful_implementation_is_recorded_with_full_identity(self):
        with mock.patch.object(pilot, "gh_json", side_effect=self.github()):
            artifact = pilot.record_implementation_artifact(
                "Настоящая работа", "task-implement",
                "[auto] [3/5 Implement + Test] Настоящая работа",
                "BRANCH: factory/implementation", "", "github.com/timafen/factory")

        self.assertEqual(artifact["branch"], "factory/implementation")
        self.assertEqual(artifact["head"], "b" * 40)
        self.assertEqual(artifact["task_id"], "task-implement")
        self.assertEqual(artifact["generation"], "generation-1")
        self.assertRegex(artifact["recorded_at"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(pilot.implementation_artifact("Настоящая работа"), artifact)

    def test_unproven_and_service_candidates_do_not_replace_artifact(self):
        existing = {
            "branch": "factory/real", "head": "c" * 40,
            "task_id": "real-task", "recorded_at": "2026-08-11T10:00:00Z",
            "generation": "generation-1",
        }
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1", "implementation_artifact": existing,
        }})
        with mock.patch.object(
                pilot, "gh_json", side_effect=self.github(
                    branch="factory/empty-review", files=[])):
            self.assertEqual(pilot.record_implementation_artifact(
                "Настоящая работа", "empty-task",
                "[auto] [3/5 Implement + Test] Настоящая работа",
                "BRANCH: factory/empty-review", "", "github.com/timafen/factory"), {})
        with mock.patch.object(pilot, "gh_json") as github:
            self.assertEqual(pilot.record_implementation_artifact(
                "helper debug", "service-task",
                "[auto] [3/5 Implement + Test] helper debug",
                "BRANCH: factory/service", "", "github.com/timafen/factory"), {})
            github.assert_not_called()
        self.assertEqual(pilot.implementation_artifact("Настоящая работа"), existing)

    def test_canonical_identity_overrides_review_text_and_is_cleared_on_reopen(self):
        artifact = {
            "branch": "factory/real", "head": "d" * 40,
            "task_id": "real-task", "recorded_at": "2026-08-11T10:00:00Z",
            "generation": "generation-1",
        }
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1", "implementation_artifact": artifact,
        }})

        self.assertEqual(
            pilot.canonical_implementation("Настоящая работа", "factory/empty-review"),
            ("factory/real", "d" * 40))
        question = pilot.write_question(
            "review-task", "Review", "Implement + Test", "Настоящая работа",
            "repo-id", "Нужна доработка", "Продолжить?", [], "",
            branch="factory/empty-review")
        self.assertEqual(question["branch"], "factory/real")
        self.assertEqual(question["implementation_head"], "d" * 40)

        with mock.patch.object(pilot, "CONF_PATH", os.path.join(self.temporary.name, "missing.json")), \
                mock.patch.object(pilot, "HOME", self.temporary.name):
            pilot.reopen_work("Настоящая работа", "generation-2")
        self.assertEqual(pilot.implementation_artifact("Настоящая работа"), {})

    def test_reprocessing_same_implementation_keeps_delivery_branch(self):
        implementation = {
            "branch": "factory/real", "head": "e" * 40,
            "task_id": "implement-task", "recorded_at": "2026-08-11T10:00:00Z",
            "generation": "generation-1",
        }
        delivery = {
            "branch": "factory/real-clean", "head": "e" * 40,
            "selected_at": "2026-08-11T10:01:00Z",
            "generation": "generation-1",
        }
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1",
            "implementation_artifact": implementation,
            "delivery_artifact": delivery,
        }})

        with mock.patch.object(pilot, "gh_json", side_effect=self.github(
                branch="factory/real", head="e" * 40)):
            artifact = pilot.record_implementation_artifact(
                "Настоящая работа", "implement-task",
                "[auto] [3/5 Implement + Test] Настоящая работа",
                "BRANCH: factory/real", "", "github.com/timafen/factory")

        self.assertEqual(artifact["branch"], "factory/real")
        self.assertEqual(pilot.delivery_artifact("Настоящая работа"), delivery)

    def test_refreshed_head_from_same_implementation_keeps_delivery_pin(self):
        original_head = "a" * 40
        refreshed_head = "b" * 40
        delivery = {
            "branch": "factory/real", "head": refreshed_head,
            "selected_at": "2026-08-11T10:01:00Z",
            "generation": "generation-1",
        }
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1",
            "implementation_artifact": {
                "branch": "factory/real", "head": original_head,
                "task_id": "implement-task",
                "recorded_at": "2026-08-11T10:00:00Z",
                "generation": "generation-1",
            },
            "delivery_artifact": delivery,
        }})

        with mock.patch.object(pilot, "gh_json", side_effect=self.github(
                branch="factory/real", head=refreshed_head)):
            artifact = pilot.record_implementation_artifact(
                "Настоящая работа", "implement-task",
                "[auto] [3/5 Implement + Test] Настоящая работа",
                "BRANCH: factory/real", "", "github.com/timafen/factory")

        self.assertEqual(artifact["head"], refreshed_head)
        self.assertEqual(pilot.delivery_artifact("Настоящая работа"), delivery)

    def test_completed_review_restores_missing_delivery_pin(self):
        reviewed_head = "b" * 40
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1",
            "implementation_artifact": {
                "branch": "factory/real", "head": "a" * 40,
                "task_id": "implement-task",
                "recorded_at": "2026-08-11T10:00:00Z",
                "generation": "generation-1",
            },
        }})

        with mock.patch.object(pilot, "gh_json", side_effect=self.github(
                branch="factory/real", head=reviewed_head)):
            artifact, reason = pilot.pin_reviewed_delivery(
                "Настоящая работа", "github.com/timafen/factory",
                "factory/real", f"APPROVE\nHEAD: {reviewed_head}")

        self.assertEqual(reason, "")
        self.assertEqual(artifact["head"], reviewed_head)
        self.assertEqual(pilot.delivery_artifact("Настоящая работа"), artifact)

    def test_changed_branch_cannot_be_pinned_by_old_review(self):
        with mock.patch.object(pilot, "gh_json", side_effect=self.github(
                branch="factory/real", head="c" * 40)):
            artifact, reason = pilot.pin_reviewed_delivery(
                "Настоящая работа", "github.com/timafen/factory",
                "factory/real", "HEAD: " + "b" * 40)

        self.assertEqual(artifact, {})
        self.assertIn("изменилась после Review", reason)
        self.assertEqual(pilot.delivery_artifact("Настоящая работа"), {})

    def test_new_implementation_invalidates_delivery_branch(self):
        pilot.save(self.works_path, {"Настоящая работа": {
            "run_generation": "generation-1",
            "implementation_artifact": {
                "branch": "factory/old", "head": "a" * 40,
                "task_id": "old-task", "recorded_at": "2026-08-11T10:00:00Z",
                "generation": "generation-1",
            },
            "delivery_artifact": {
                "branch": "factory/old-clean", "head": "b" * 40,
                "selected_at": "2026-08-11T10:01:00Z",
                "generation": "generation-1",
            },
        }})

        with mock.patch.object(pilot, "gh_json", side_effect=self.github(
                branch="factory/new", head="f" * 40)):
            pilot.record_implementation_artifact(
                "Настоящая работа", "new-task",
                "[auto] [3/5 Implement + Test] Настоящая работа",
                "BRANCH: factory/new", "", "github.com/timafen/factory")

        self.assertEqual(pilot.delivery_artifact("Настоящая работа"), {})


class RebuiltDeliveryBranchPipelineTests(unittest.TestCase):
    def test_review_gate_rebuild_reaches_review_verify_and_merge(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        works_path = os.path.join(temporary.name, "works.json")
        merges_path = os.path.join(temporary.name, "merges.jsonl")
        base = "Чистая поставка"
        original = "factory/original-implementation"
        rebuilt = "factory/original-implementation-clean"
        implementation_head = "e" * 40
        delivery_head = "d" * 40
        card = "CARD-0070"
        pilot.save(works_path, {base: {
            "run_generation": "generation-1",
            "implementation_artifact": {
                "branch": original, "head": implementation_head, "task_id": "implement",
                "recorded_at": "2026-08-11T10:00:00Z",
                "generation": "generation-1",
            },
        }})
        conf = {
            "stages": [
                {"workflow": "Implement + Test"},
                {"workflow": "Review"},
                {"workflow": "Verify"},
            ],
            "auto_merge": True,
            "poll_seconds": 30,
        }
        state = {"processed": []}
        tasks = [{
            "id": "implement", "title": f"[auto] [1/3 Implement + Test] {base}",
            "state": "succeeded", "created_at": "2026-08-11T10:00:00Z",
            "repository_id": "repo-id",
        }]
        details = {
            "implement": {
                "task": {"repository_id": "repo-id"},
                "workflow": {"title": "Implement + Test"},
                "context": f"Card: {card}",
                "attempts": [{"result": (
                    f"BRANCH: {original}\nCard: {card}\nГотово")}],
            },
        }
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path.startswith("/tasks/"):
                return details[path.rsplit("/", 1)[-1]]
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 1, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": stage.lower(), "enabled": True,
                    "current_revision": {"id": "rev-" + stage.lower(),
                                         "title": stage},
                } for stage in ("Implement + Test", "Review", "Verify")]}
            raise AssertionError(path)

        def create(body, _conf):
            stage = next(stage for stage in
                         ("Implement + Test", "Review", "Verify")
                         if f" {stage}]" in body["title"])
            task_id = ("implement-rescue" if stage == "Implement + Test"
                       else stage.lower())
            task = {
                "id": task_id, "title": body["title"], "state": "created",
                "created_at": "2026-08-11T10:0%d:00Z" % (len(created) + 1),
                "repository_id": "repo-id", "context": body["context"],
            }
            tasks.append(task)
            details[task_id] = {
                "task": {"repository_id": "repo-id", "context": body["context"]},
                "workflow": {"title": stage}, "context": body["context"],
                "attempts": [],
            }
            created.append(body)
            return {"task": task}

        verdict = {
            "action": "advance", "reason": "готово",
            "next_complexity": "medium", "handoff": "",
        }
        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "cleanup_work_archive", "retry_pending_factory_deploy",
            "autostart_plan", "area_extend", "collect_ideas", "all_tasks",
            "save_stage_verdict", "mark_final",
            "deploy_after_merge", "notify",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "WORKS_PATH", works_path))
            stack.enter_context(mock.patch.object(pilot, "MERGES_PATH", merges_path))
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", return_value="worker"))
            stack.enter_context(mock.patch.object(
                pilot, "work_lifecycle_block", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value=verdict))
            stack.enter_context(mock.patch.object(pilot, "create_task", side_effect=create))
            gate = stack.enter_context(mock.patch.object(
                pilot, "review_gate",
                return_value={"back": False, "branch": rebuilt,
                              "head": delivery_head, "note": "rebuilt"}))
            stack.enter_context(mock.patch.object(
                pilot, "pushed_branch", side_effect=lambda candidates, _repo:
                candidates[0] if candidates else ""))
            stack.enter_context(mock.patch.object(
                pilot, "merge_recorded", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "cap_rescues", return_value=0))
            stack.enter_context(mock.patch.object(pilot, "note_cap_rescue"))
            def github(args, strict=False):
                path = args[-1]
                if "/branches/" in path:
                    if path.endswith(rebuilt):
                        return {"name": rebuilt, "commit": {"sha": delivery_head}}
                    return {"name": original, "commit": {"sha": implementation_head}}
                if "/pulls?" in path:
                    return []
                if "/compare/main..." in path:
                    return {"files": [{"filename": "pilot/pilot.py"}], "ahead_by": 1}
                raise AssertionError(path)
            stack.enter_context(mock.patch.object(pilot, "gh_json", side_effect=github))
            merge = stack.enter_context(mock.patch.object(
                pilot, "gh_merge", return_value=(False, "merge conflict")))
            snapshot = {
                "state": "ok", "default_branch": "main",
                "base_sha": "a" * 40, "candidate_sha": delivery_head,
                "merge_base_sha": "a" * 40, "base_advanced": False,
                "base_ahead_by": 0, "ahead_by": 1,
                "files": ["pilot/pilot.py"],
            }
            fresh = stack.enter_context(mock.patch.object(
                pilot, "fresh_branch_snapshot", return_value=snapshot))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)
            self.assertIn(f"Branch: {rebuilt}", created[0]["context"])
            self.assertEqual(pilot.delivery_artifact(base)["branch"], rebuilt)
            self.assertEqual(pilot.delivery_artifact(base)["head"], delivery_head)
            self.assertEqual(pilot.implementation_artifact(base)["branch"], original)
            self.assertNotEqual(delivery_head, implementation_head)

            # A watcher restart reprocesses the terminal Implement task before
            # Review completes.  Recording the same implementation must not
            # discard the rebuilt branch selected by review_gate.
            state["processed"] = []
            pilot.cycle(conf, state)
            self.assertEqual(len(created), 1)
            self.assertEqual(pilot.delivery_artifact(base)["branch"], rebuilt)

            tasks[-1]["state"] = "succeeded"
            details["review"]["attempts"] = [{
                "result": f"PASS\nHEAD: {delivery_head}",
            }]
            pilot.cycle(conf, state)
            self.assertIn(f"Branch: {rebuilt}", created[1]["context"])

            tasks[-1]["state"] = "succeeded"
            details["verify"]["attempts"] = [{"result": "PASS"}]
            pilot.cycle(conf, state)

            # The immutable attempt is retained, but a content conflict is
            # handed to the next cycle instead of hammering GitHub forever.
            self.assertEqual(len(created), 2)
            self.assertEqual(state["merge_intents"]["verify"]["branch"], rebuilt)
            self.assertEqual(state["merge_intents"]["verify"]["commit_sha"], delivery_head)
            self.assertEqual(state["merge_intents"]["verify"]["phase"], "conflict")
            fresh.assert_called_once_with("github.com/acme/repo", rebuilt)

        gate.assert_called_once_with(
            conf, base, original, "github.com/acme/repo", mock.ANY,
            area_repo="repo-id", expected_card=card)
        merge.assert_called_once_with("github.com/acme/repo", rebuilt, base, delivery_head)


class ImmutableMergeTests(unittest.TestCase):
    def test_force_push_after_verify_blocks_merge(self):
        with mock.patch.object(pilot, "gh_json", return_value={
                "commit": {"sha": "f" * 40}}), \
                mock.patch("subprocess.run") as run:
            ok, message = pilot.gh_merge("github.com/acme/repo", "factory/candidate",
                                         "Работа", "a" * 40)
        self.assertFalse(ok)
        self.assertIn("changed after Verify", message)
        run.assert_not_called()

    def test_force_push_during_merge_is_rejected_atomically(self):
        expected = "a" * 40
        current = {"commit": {"sha": expected}}
        created = subprocess.CompletedProcess([], 0, "", "")
        changed = subprocess.CompletedProcess([], 1, "", "head commit changed")
        with mock.patch.object(pilot, "gh_json", return_value=current), \
                mock.patch("subprocess.run", side_effect=[created, changed]) as run:
            ok, message = pilot.gh_merge(
                "github.com/acme/repo", "factory/candidate", "Работа", expected)

        self.assertFalse(ok)
        self.assertIn("head commit changed", message)
        self.assertEqual(run.call_args_list[1].args[0][-2:],
                         ["--match-head-commit", expected])


class ClosedWorkLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = self.temporary.name
        os.makedirs(os.path.join(self.root, "pilot", "questions"))
        self.paths = {
            "HOME": self.root,
            "WORKS_PATH": os.path.join(self.root, "pilot", "works.json"),
            "IDEAS_PATH": os.path.join(self.root, "pilot", "ideas.json"),
            "CONF_PATH": os.path.join(self.root, "pilot", "config.json"),
            "STALL_PATH": os.path.join(self.root, "pilot", "stalled.json"),
            "DIAG_REPAIR_PATH": os.path.join(self.root, "pilot", "diag_repairs.json"),
            "QUESTION_DIR": os.path.join(self.root, "pilot", "questions"),
        }
        self.patches = [mock.patch.object(pilot, name, value)
                        for name, value in self.paths.items()]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        pilot.save(pilot.CONF_PATH, {"stopped_pipelines": []})
        pilot.save(pilot.IDEAS_PATH, [])
        self.conf = {
            "stages": [{"workflow": "Triage"}, {"workflow": "Specification"}],
            "timeout_seconds": 900,
        }
        self.workflows = {
            "Triage": {"enabled": True, "revision_id": "triage-rev"},
            "Specification": {"enabled": True, "revision_id": "spec-rev"},
        }
        self.workers = {"worker": {"id": "worker-id"}}
        self.old = {
            "id": "old-triage", "title": "[auto] [1/2 Triage] Закрытая работа",
            "state": "succeeded", "repository_id": "repo-id",
            "created_at": "2026-08-10T10:00:00Z",
        }

    def watch(self, tasks, created):
        with mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                mock.patch.object(pilot, "create_task",
                                  side_effect=lambda body, _conf: created.append(body) or
                                  {"task": {"id": "spec"}}), \
                mock.patch.object(pilot, "notify"):
            pilot.pipeline_watch(self.conf, tasks, self.workflows, self.workers)

    def test_closed_triage_stays_closed_across_two_cycles_and_restart(self):
        reason = "Владелец закрыл работу как заменённую новой карточкой."
        pilot.close_work("Закрытая работа", reason)
        created = []

        with mock.patch.object(pilot.time, "time", return_value=20_000):
            self.watch([self.old], created)
            self.watch([self.old], created)
            os.remove(pilot.STALL_PATH)
            self.watch([self.old], created)

        self.assertEqual(created, [])
        self.assertEqual(pilot.load(pilot.CONF_PATH, {})["stopped_pipelines"], [])
        status = pilot.load(os.path.join(self.root, "pilot", "work_status.json"), {})
        self.assertEqual(status["Закрытая работа"]["state"], "archived")
        self.assertEqual(status["Закрытая работа"]["text"], reason)

    def test_done_plan_card_blocks_old_success_and_answer(self):
        pilot.save(pilot.IDEAS_PATH, [{
            "id": "card", "title": "Закрытая работа", "state": "done",
            "reason": "Карточка закрыта после замены.",
        }])
        question = {
            "id": "question", "task_id": "old-triage", "title": "Закрытая работа",
            "stage": "Triage", "resume_stage": "Specification", "status": "answered",
            "answer": "Продолжай", "repository_id": "repo-id",
        }
        pilot.save(os.path.join(pilot.QUESTION_DIR, "question.json"), question)
        created = []
        with mock.patch.object(pilot, "load_questions", return_value=[question]), \
                mock.patch.object(pilot, "create_task",
                                  side_effect=lambda body, _conf: created.append(body)):
            self.assertEqual(pilot.handle_answers(
                self.conf, self.workflows, self.workers, [self.old]), 0)

        self.watch([self.old], created)
        self.assertEqual(created, [])
        resolved = pilot.load(os.path.join(pilot.QUESTION_DIR, "question.json"), {})
        self.assertEqual(resolved["status"], "resolved")
        self.assertIn("Карточка закрыта после замены", resolved["escalation_reason"])

    def test_completed_stage_handler_cannot_advance_old_triage_after_restart(self):
        pilot.save(pilot.IDEAS_PATH, [{
            "id": "card", "title": "Закрытая работа", "state": "done",
            "reason": "Карточка уже завершена.",
        }])
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": [self.old]}
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 1, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "spec", "enabled": True,
                    "current_revision": {"id": "spec-rev", "title": "Specification"},
                }]}
            if path == "/tasks" and body is not None:
                created.append(body)
                return {"task": {"id": "unexpected"}}
            raise AssertionError("old terminal task detail must not be read: " + path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "cleanup_work_archive",
            "retry_pending_factory_deploy", "autostart_plan",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot",
                side_effect=lambda day, _week: {day: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(self.conf, {"processed": []})
            pilot.cycle(self.conf, {"processed": []})

        self.assertEqual(created, [])

    def test_restart_repair_is_retired_instead_of_recreating_closed_work(self):
        pilot.close_work("Закрытая работа", "Работа архивирована владельцем.")
        pilot.save(pilot.DIAG_REPAIR_PATH, {"Закрытая работа": {
            "status": "resume_pending", "task_id": "old-triage",
            "title": self.old["title"], "request_key": "stable-repair",
        }})
        with mock.patch.object(pilot, "create_task") as create:
            pilot.reconcile_diag_repairs(self.conf, [self.old])

        create.assert_not_called()
        repair = pilot.load(pilot.DIAG_REPAIR_PATH, {})["Закрытая работа"]
        self.assertEqual(repair["status"], "closed")
        self.assertEqual(repair["closed_reason"], "Работа архивирована владельцем.")

    def test_explicit_reopen_creates_new_generation_and_allows_it_only(self):
        pilot.save(pilot.IDEAS_PATH, [{
            "id": "card", "title": "Закрытая работа", "state": "done",
            "reason": "Старое поколение завершено.",
        }])
        pilot.close_work("Закрытая работа", "Старое поколение завершено.")
        reopened = pilot.plan_idea("card")
        created = []
        with mock.patch.object(pilot.time, "time", return_value=20_000):
            self.watch([self.old], created)
        self.assertEqual(created, [])

        current = dict(self.old, id="new-triage", created_at="2026-08-10T12:00:00Z")
        pilot.set_idea("card", state="in_work", task_id="new-triage",
                       run_generation=reopened["run_generation"])
        pilot.save(pilot.STALL_PATH, {
            "Закрытая работа": {"since": 1, "nudges": 0},
        })
        with mock.patch.object(pilot.time, "time", return_value=20_000):
            self.watch([self.old, current], created)

        self.assertEqual([body["title"] for body in created], [
            "[auto] [2/2 Specification] Закрытая работа",
        ])
        work = pilot.load(pilot.WORKS_PATH, {})["Закрытая работа"]
        self.assertNotIn("closed", work)
        self.assertEqual(work["closed_generations"][0]["closed_reason"],
                         "Старое поколение завершено.")

    def test_linked_descendant_survives_when_plan_root_left_task_page(self):
        pilot.save(pilot.IDEAS_PATH, [{
            "id": "card", "title": "Долгая работа", "state": "in_work",
            "task_id": "current-root", "run_generation": "current-run",
        }])
        current = {
            "id": "current-review",
            "title": "[auto] [4/5 Review] Долгая работа",
            "state": "succeeded",
            "created_at": "2026-08-14T20:17:55Z",
            "work_id": "current-root",
        }
        stale = dict(current, id="stale-review", work_id="previous-root")

        self.assertEqual(
            pilot.work_lifecycle_block("Долгая работа", current, [current]), "")
        self.assertIn(
            "до явного повторного запуска",
            pilot.work_lifecycle_block("Долгая работа", stale, [stale]),
        )

    def test_owner_created_live_task_after_close_is_a_new_generation(self):
        pilot.save(pilot.IDEAS_PATH, [{
            "id": "card", "title": "Закрытая работа", "state": "done",
            "reason": "Старое поколение завершено.",
        }])
        with mock.patch.object(pilot.time, "time", return_value=1_786_359_600):
            pilot.close_work("Закрытая работа", "Старое поколение завершено.")
        current = dict(
            self.old, id="owner-restart", state="queued",
            created_at="2026-08-10T12:00:00Z",
        )

        with mock.patch.object(pilot.time, "time", return_value=1_786_366_800):
            pilot.record_new_works(self.conf, [self.old, current], max_age_min=10_000)

        card = pilot.ideas_all()[0]
        self.assertEqual((card["state"], card["task_id"]),
                         ("in_work", "owner-restart"))
        self.assertTrue(pilot.work_lifecycle_block(
            "Закрытая работа", self.old, [self.old, current]))
        self.assertEqual(pilot.work_lifecycle_block(
            "Закрытая работа", current, [self.old, current]), "")


class WorkOriginAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.works_path = os.path.join(self.temporary.name, "works.json")
        self.ideas_path = os.path.join(self.temporary.name, "ideas.json")
        self.patches = [
            mock.patch.object(pilot, "WORKS_PATH", self.works_path),
            mock.patch.object(pilot, "IDEAS_PATH", self.ideas_path),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        pilot.save(self.works_path, {})
        pilot.save(self.ideas_path, [])
        self.conf = {"stages": [{"workflow": "Triage"}, {"workflow": "Review"}]}

    @staticmethod
    def task(base, request_key="regular-task"):
        return {
            "id": request_key,
            "title": f"[auto] [1/2 Triage] {base}",
            "state": "queued",
            "request_key": request_key,
            "created_at": "2026-08-12T03:00:00Z",
        }

    def test_new_work_inherits_assistant_origin_from_plan(self):
        pilot.save(self.ideas_path, [{
            "id": "proposal", "title": "Assistant proposal",
            "origin": "assistant", "state": "in_work",
        }])

        pilot.record_new_works(
            self.conf, [self.task("Assistant proposal")], max_age_min=10_000,
        )

        work = pilot.load(self.works_path, {})["Assistant proposal"]
        self.assertEqual(work["origin"], "assistant")

    def test_automation_task_is_not_attributed_to_owner(self):
        pilot.save(self.ideas_path, [{
            "id": "old-owner-card", "title": "Scheduled patrol",
            "origin": "owner", "state": "in_work",
        }])

        pilot.record_new_works(
            self.conf,
            [self.task("Scheduled patrol", "automation:patrol:schedule:one")],
            max_age_min=10_000,
        )

        work = pilot.load(self.works_path, {})["Scheduled patrol"]
        self.assertEqual(work["origin"], "orchestrator")


class WorkArchiveCleanupTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_786_320_000
        self.works = {}
        self.statuses = {}
        self.saved = []
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.merges = os.path.join(self.temporary.name, "merges.jsonl")
        open(self.merges, "w", encoding="utf-8").close()

        # Production writes legacy merge receipts in the server's time.Local.
        self.old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Chicago"
        if hasattr(time, "tzset"):
            time.tzset()
        self.addCleanup(self.restore_timezone)

    def restore_timezone(self):
        if self.old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.old_tz
        if hasattr(time, "tzset"):
            time.tzset()

    @staticmethod
    def task(task_id, base, state, minute=0, stage="Review", request_key="",
             created_at=""):
        return {
            "id": task_id, "title": f"[auto] [4/5 {stage}] {base}",
            "state": state, "request_key": request_key,
            "created_at": created_at or f"2026-08-10T18:{minute:02d}:00Z",
        }

    def remember(self, base, origin="owner", start_stage="Review", skipped=None):
        self.works[base] = {
            "origin": origin,
            "start_stage": start_stage,
            "skipped": (["Triage", "Specification", "Implement + Test"]
                        if skipped is None else skipped),
        }

    def add_merge(self, base, at):
        with open(self.merges, "a", encoding="utf-8") as journal:
            journal.write(json.dumps({"base": base, "at": at}) + "\n")

    def load(self, path, default=None):
        if path == pilot.WORKS_PATH:
            return self.works
        if path.endswith("/pilot/work_status.json"):
            return self.statuses
        return default

    def save(self, path, value):
        self.saved.append(path)
        if path == pilot.WORKS_PATH:
            self.works = value
        elif path.endswith("/pilot/work_status.json"):
            self.statuses = value

    def run_cleanup(self, tasks, questions=None, stopped=None):
        conf = {
            "stopped_pipelines": stopped or [],
            "stages": [
                {"workflow": "Triage"}, {"workflow": "Specification"},
                {"workflow": "Implement + Test"}, {"workflow": "Review"},
                {"workflow": "Verify"},
            ],
        }
        with mock.patch.object(pilot, "load", side_effect=self.load), \
                mock.patch.object(pilot, "save", side_effect=self.save), \
                mock.patch.object(pilot, "load_questions", return_value=questions or []), \
                mock.patch.object(pilot, "MERGES_PATH", self.merges), \
                mock.patch.object(pilot.time, "time", return_value=self.now):
            pilot.cleanup_work_archive(conf, tasks)

    def assert_archived(self, base):
        self.assertIn("closed", self.works[base])
        self.assertEqual(self.statuses[base]["state"], "archived")
        self.assertEqual(self.works[base]["retention_until"], "2026-11-08T00:00:00Z")

    # Nine production regressions: a real merge, the Russian patrol, a product
    # schedule, two independent-check origins, required gates, owner questions,
    # explicit/dead-end stops, and live/replaced generations.
    def test_01_production_legacy_merge_time_uses_local_instant(self):
        self.add_merge("Уже влито", "2026-08-10 13:30:26")
        self.add_merge("Ещё не влито", "2026-08-10 13:30:26")
        tasks = [
            self.task("merged", "Уже влито", "succeeded", stage="Verify",
                      created_at="2026-08-10T18:30:25.900Z"),
            self.task("newer", "Ещё не влито", "succeeded", stage="Verify",
                      created_at="2026-08-10T18:30:27Z"),
        ]

        self.run_cleanup(tasks)

        self.assert_archived("Уже влито")
        self.assertNotIn("closed", self.works["Ещё не влито"])
        merged_at = pilot._work_time("2026-08-10 13:30:26")
        self.assertIsNotNone(merged_at.tzinfo)
        self.assertEqual(merged_at.isoformat(), "2026-08-10T18:30:26+00:00")

    def test_02_cancelled_russian_factory_patrol_is_archived(self):
        patrol = {
            "id": "patrol", "title": "Патруль Factory: scheduled 2026-08-10T18:00:00Z",
            "state": "cancelled",
            "request_key": "automation:4f3a:schedule:scheduled:2026-08-10T18:00:00Z",
            "created_at": "2026-08-10T18:00:00Z",
        }

        self.run_cleanup([patrol])

        self.assert_archived(patrol["title"])
        self.assertEqual(self.works[patrol["title"]]["origin"], "orchestrator")

    def test_03_cancelled_product_schedule_is_not_patrol(self):
        product = {
            "id": "prices", "title": "Сверка продуктовых цен: scheduled 2026-08-10",
            "state": "cancelled",
            "request_key": "automation:pricing:schedule:scheduled:2026-08-10",
            "created_at": "2026-08-10T18:01:00Z",
        }

        self.run_cleanup([product])

        self.assertEqual(self.works[product["title"]]["origin"], "orchestrator")
        self.assertNotIn("closed", self.works[product["title"]])
        self.assertNotIn("archived_attempts", self.works[product["title"]])

    def test_04_assistant_independent_review_is_archived(self):
        self.remember("Review помощника", origin="assistant")
        self.run_cleanup([self.task("assistant-review", "Review помощника", "succeeded")])
        self.assert_archived("Review помощника")

    def test_05_orchestrator_independent_verify_is_archived(self):
        self.remember(
            "Verify оркестратора", origin="orchestrator", start_stage="Verify",
            skipped=["Triage", "Specification", "Implement + Test", "Review"],
        )
        self.run_cleanup([
            self.task("orchestrator-verify", "Verify оркестратора", "failed", stage="Verify")
        ])
        self.assert_archived("Verify оркестратора")

    def test_06_unfinished_or_required_gates_are_not_archived(self):
        self.remember("Обязательная проверка", start_stage="Triage", skipped=[])
        self.remember("Без skipped", skipped=[])
        self.remember("Незавершённый Review")
        tasks = [
            self.task("required", "Обязательная проверка", "succeeded"),
            self.task("no-skips", "Без skipped", "succeeded"),
            self.task("unfinished", "Незавершённый Review", "blocked"),
        ]
        self.run_cleanup(tasks)
        for base in ("Обязательная проверка", "Без skipped", "Незавершённый Review"):
            self.assertNotIn("closed", self.works[base])

    def test_07_open_question_is_not_archived(self):
        self.remember("Открытый вопрос")
        self.run_cleanup(
            [self.task("question", "Открытый вопрос", "failed")],
            questions=[{"task_id": "question", "status": "open"}],
        )
        self.assertNotIn("closed", self.works["Открытый вопрос"])

    def test_08_owner_stop_and_genuine_stuck_are_not_archived(self):
        self.remember("Пауза владельца")
        self.remember("Настоящий тупик")
        self.statuses["Пауза владельца"] = {"state": "stopped_owner"}
        self.statuses["Настоящий тупик"] = {"state": "stuck"}
        tasks = [
            self.task("paused", "Пауза владельца", "failed"),
            self.task("stuck", "Настоящий тупик", "failed"),
        ]
        self.run_cleanup(tasks, stopped=["Пауза владельца"])
        for base in ("Пауза владельца", "Настоящий тупик"):
            self.assertNotIn("closed", self.works[base])

    def test_09_live_generation_stays_open_and_old_attempt_is_idempotent(self):
        tasks = [
            self.task("old", "Новое поколение", "failed", 1),
            self.task("queued", "Новое поколение", "queued", 2),
            self.task("running", "Работа выполняется", "running", 3),
        ]
        self.run_cleanup(tasks)

        self.assertNotIn("closed", self.works["Новое поколение"])
        self.assertNotIn("closed", self.works["Работа выполняется"])
        self.assertEqual(
            [item["task_id"] for item in self.works["Новое поколение"]["archived_attempts"]],
            ["old"],
        )
        writes_after_first_run = len(self.saved)
        self.run_cleanup(tasks)
        self.assertEqual(len(self.saved), writes_after_first_run)


class MergeConflictRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = os.path.join(self.temporary.name, "state.json")
        self.intent = {
            "phase": "intent", "base": "Resolve once", "branch": "factory/topic",
            "repository": "github.com/acme/repo", "commit_sha": "a" * 40,
            "link": "",
        }
        self.conf = {
            "stages": [{"workflow": name} for name in
                       ("Triage", "Specification", "Implement + Test", "Review", "Verify")],
            "timeout_seconds": 7200,
        }
        self.workflows = {
            "Implement + Test": {"enabled": True, "revision_id": "implement-revision"},
        }
        self.workers = {"worker": {"id": "worker-id"}}
        self.parent = {
            "id": "verify-1", "title": "[auto] [5/5 Verify] Resolve once",
            "state": "succeeded", "repository_id": "repo-id", "work_id": "work-1",
        }

    def conflict_state(self):
        intent = dict(self.intent)
        intent.update({"phase": "conflict", "merge_error": "merge conflict details"})
        return {"merge_intents": {"verify-1": intent}}

    def test_content_conflict_is_journaled_and_not_retried_each_cycle(self):
        state = {"merge_intents": {"verify-1": dict(self.intent)}}
        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "a" * 40}}
            if "/pulls?" in args[-1]:
                return []
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(
                    pilot, "gh_merge",
                    return_value=(False, "Pull request is not mergeable: merge conflicts")) as merge:
            pilot.recover_merge_intents({}, state)
            pilot.recover_merge_intents({}, state)

        self.assertEqual(merge.call_count, 1)
        self.assertEqual(state["merge_intents"]["verify-1"]["phase"], "conflict")
        self.assertIn("merge conflicts", state["merge_intents"]["verify-1"]["merge_error"])

    def test_second_conflict_closes_current_pr_when_same_work_was_merged(self):
        """A second conflict must not leave a duplicate PR after equivalent delivery."""
        state = {"merge_intents": {"verify-1": dict(
            self.intent, work_id="work-1", base_branch="main", conflict_count=1)}}
        current = {"number": 11, "state": "open", "body": "<!-- factory-work-id:work-1 -->",
                   "head": {"ref": "factory/topic"}, "base": {"ref": "main"}}
        merged = {"number": 12, "merged_at": "2026-08-15T12:00:00Z",
                  "body": "<!-- factory-work-id:work-1 -->", "html_url": "https://example/pr/12",
                  "base": {"ref": "main"}}

        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "a" * 40}}
            if "state=open&head=" in args[-1]:
                return [current]
            if "state=all&per_page=100" in args[-1]:
                return [current, merged]
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(pilot, "_verified_merge_result", return_value=False), \
                mock.patch.object(pilot, "gh_merge", return_value=(False, "merge conflicts")), \
                mock.patch.object(pilot, "gh_close_pr", return_value=(True, "closed")) as close:
            pilot.recover_merge_intents({}, state)
            pilot.recover_merge_intents({}, state)

        intent = state["merge_intents"]["verify-1"]
        close.assert_called_once_with("acme/repo", 11, 12)
        self.assertEqual(intent["phase"], "superseded")
        self.assertEqual(intent["superseded_by"], 12)
        self.assertIn("same work already merged", intent["supersede_reason"])

    def test_failed_stale_pr_close_remains_recoverable(self):
        """A GitHub close failure must leave the conflict eligible for repair."""
        state = {"merge_intents": {"verify-1": dict(
            self.intent, work_id="work-1", base_branch="main", conflict_count=1)}}
        current = {"number": 11, "state": "open", "body": "<!-- factory-work-id:work-1 -->",
                   "head": {"ref": "factory/topic"}, "base": {"ref": "main"}}
        merged = {"number": 12, "merged_at": "2026-08-15T12:00:00Z",
                  "body": "<!-- factory-work-id:work-1 -->", "html_url": "https://example/pr/12",
                  "base": {"ref": "main"}}

        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "a" * 40}}
            if "state=open&head=" in args[-1]:
                return [current]
            if "state=all&per_page=100" in args[-1]:
                return [current, merged]
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(pilot, "_verified_merge_result", return_value=False), \
                mock.patch.object(pilot, "gh_merge", return_value=(False, "merge conflicts")), \
                mock.patch.object(pilot, "gh_close_pr", return_value=(False, "GitHub unavailable")), \
                mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                mock.patch.object(
                    pilot, "create_child_task",
                    return_value={"task": {"id": "repair-after-close-failure"}}) as create:
            pilot.recover_merge_intents({}, state)
            intent = state["merge_intents"]["verify-1"]
            self.assertEqual(intent["phase"], "conflict")
            self.assertNotIn("superseded_by", intent)
            self.assertEqual(pilot.resume_merge_conflicts(
                self.conf, state, [self.parent], self.workflows, self.workers), 1)

        create.assert_called_once()
        self.assertEqual(intent["phase"], "repairing")
        self.assertEqual(intent["repair_task_id"], "repair-after-close-failure")

    def test_force_push_before_recovery_blocks_merge_and_delivery(self):
        state = {"merge_intents": {"verify-1": dict(self.intent)}}

        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "b" * 40}}
            if "/pulls?" in args[-1]:
                return []
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(pilot, "gh_merge") as merge, \
                mock.patch.object(pilot, "deploy_after_merge") as deploy:
            pilot.recover_merge_intents({}, state)

        intent = state["merge_intents"]["verify-1"]
        self.assertEqual(intent["phase"], "stale")
        self.assertIn("changed after Verify", intent["merge_error"])
        merge.assert_not_called()
        deploy.assert_not_called()

    def test_recovery_does_not_accept_merge_of_another_head(self):
        state = {"merge_intents": {"verify-1": dict(self.intent)}}

        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "a" * 40}}
            if "/pulls?" in args[-1]:
                return [{"merged_at": "2026-08-12T10:00:00Z",
                         "head": {"sha": "b" * 40}}]
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(
                    pilot, "gh_merge", return_value=(False, "head commit changed")) as merge, \
                mock.patch.object(pilot, "deploy_after_merge") as deploy:
            pilot.recover_merge_intents({}, state)

        merge.assert_called_once_with(
            "github.com/acme/repo", "factory/topic", "Resolve once", "a" * 40)
        deploy.assert_not_called()

    def test_conflict_returns_same_work_to_implement_once(self):
        state = self.conflict_state()
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                mock.patch.object(
                    pilot, "create_child_task",
                    return_value={"task": {"id": "repair-1"}}) as create:
            self.assertEqual(pilot.resume_merge_conflicts(
                self.conf, state, [self.parent], self.workflows, self.workers), 1)
            self.assertEqual(pilot.resume_merge_conflicts(
                self.conf, state, [self.parent], self.workflows, self.workers), 0)

        create.assert_called_once()
        body, source, passed_conf, correction_kind = create.call_args.args
        self.assertEqual(body["title"],
                         "[auto] [3/5 Implement + Test] Resolve once")
        self.assertIn("Branch: factory/topic", body["context"])
        self.assertIn("Previous verified head: " + "a" * 40, body["context"])
        self.assertIn("Fetch origin/main", body["context"])
        self.assertIn("rebase or merge", body["context"])
        self.assertIn("full required test set", body["context"])
        self.assertIn("push the updated branch", body["context"])
        self.assertIn("merge conflict details", body["context"])
        self.assertEqual(body["request_key"],
                         "merge-conflict-return:verify-1:" + "a" * 40)
        self.assertEqual(body["repository_id"], "repo-id")
        self.assertEqual(body["worker_id"], "worker-id")
        self.assertEqual(body["workflow_revision_id"], "implement-revision")
        self.assertEqual(source, self.parent)
        self.assertIs(passed_conf, self.conf)
        self.assertEqual(correction_kind, "merge_conflict_return")
        self.assertEqual(state["merge_intents"]["verify-1"]["phase"], "repairing")
        self.assertEqual(state["merge_intents"]["verify-1"]["repair_task_id"], "repair-1")

    def test_restart_links_existing_correction_without_duplicate(self):
        state = self.conflict_state()
        correction = {
            "id": "repair-existing", "parent_task_id": "verify-1",
            "correction_kind": "merge_conflict_return",
        }
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "create_child_task") as create, \
                mock.patch.object(pilot, "api") as api_call:
            created = pilot.resume_merge_conflicts(
                self.conf, state, [correction], self.workflows, self.workers)

        self.assertEqual(created, 0)
        create.assert_not_called()
        api_call.assert_not_called()
        self.assertEqual(state["merge_intents"]["verify-1"]["phase"], "repairing")
        self.assertEqual(state["merge_intents"]["verify-1"]["repair_task_id"],
                         "repair-existing")

    def test_missing_parent_is_loaded_from_detail_api(self):
        state = self.conflict_state()
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(
                    pilot, "api", return_value={"task": dict(self.parent)}) as api_call, \
                mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                mock.patch.object(
                    pilot, "create_child_task",
                    return_value={"task": {"id": "repair-detail"}}) as create:
            created = pilot.resume_merge_conflicts(
                self.conf, state, [], self.workflows, self.workers)

        self.assertEqual(created, 1)
        api_call.assert_called_once_with("/tasks/verify-1")
        self.assertEqual(create.call_args.args[1]["work_id"], "work-1")

    def test_unavailable_routes_and_create_error_keep_conflict_for_retry(self):
        cases = (
            ("workflow", {"Implement + Test": {"enabled": False,
                                                 "revision_id": "implement-revision"}},
             [self.parent], self.workers, None),
            ("repository", self.workflows,
             [dict(self.parent, repository_id="")], self.workers, None),
            ("branch", self.workflows, [self.parent], self.workers, ""),
            ("worker", self.workflows, [self.parent], {}, None),
            ("api", self.workflows, [self.parent], self.workers, None),
        )
        for name, workflows, tasks, workers, branch in cases:
            with self.subTest(name=name):
                state = self.conflict_state()
                if branch is not None:
                    state["merge_intents"]["verify-1"]["branch"] = branch
                error = (urllib.error.URLError("control plane unavailable")
                         if name == "api" else AssertionError("must not create"))
                with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                        mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                        mock.patch.object(pilot, "create_child_task", side_effect=error):
                    created = pilot.resume_merge_conflicts(
                        self.conf, state, tasks, workflows, workers)
                self.assertEqual(created, 0)
                self.assertEqual(state["merge_intents"]["verify-1"]["phase"],
                                 "conflict")

    def test_only_new_verify_intent_can_merge_after_repair(self):
        state = {"merge_intents": {
            "verify-old": dict(self.intent, phase="repairing",
                               repair_task_id="repair-1"),
            "verify-new": dict(self.intent, phase="intent", commit_sha="b" * 40),
        }}

        def github(args):
            if "/branches/" in args[-1]:
                return {"commit": {"sha": "b" * 40}}
            if "/pulls?" in args[-1]:
                return []
            raise AssertionError(args)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "gh_json", side_effect=github), \
                mock.patch.object(pilot, "gh_merge", return_value=(False, "pending")) as merge:
            pilot.recover_merge_intents({}, state)

        merge.assert_called_once_with(
            "github.com/acme/repo", "factory/topic", "Resolve once", "b" * 40)


class PipelineWatchMergeTests(unittest.TestCase):
    def setUp(self):
        self.conf = {
            "stages": [{"workflow": "Specification"}, {"workflow": "Implement"},
                       {"workflow": "Review"}],
            "timeout_seconds": 900,
        }

    def _recover_merge(self, intent, already_merged=False, merge_ok=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        journal = os.path.join(temporary.name, "merges.jsonl")
        state = {"merge_intents": {"verify-1": dict(intent)}}
        with mock.patch.object(pilot, "MERGES_PATH", journal), \
                mock.patch.object(pilot, "STATE_PATH", os.path.join(temporary.name, "state.json")), \
                mock.patch.object(pilot, "gh_json", return_value={"commit": {"sha": "a" * 40}}), \
                mock.patch.object(pilot, "_verified_merge_result", return_value=already_merged), \
                mock.patch.object(pilot, "gh_merge", return_value=(merge_ok, "merged")) as merge, \
                mock.patch.object(pilot, "deploy_after_merge", return_value=None):
            pilot.recover_merge_intents({}, state)
        with open(journal, encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        return state, records, merge

    def test_merge_journal_records_rounds_and_automatic_actor(self):
        _, records, merge = self._recover_merge({
            "phase": "intent", "base": "Круги", "branch": "factory/rounds",
            "repository": "github.com/acme/repo", "commit_sha": "a" * 40,
            "rounds": 3, "actor_id": None,
        })

        merge.assert_called_once()
        self.assertEqual(records, [{"task_id": "verify-1", "base": "Круги",
            "at": records[0]["at"], "actor": "automatic", "actor_id": None,
            "rounds": 3}])

    def test_owner_merge_records_owner_and_preserves_rounds(self):
        _, records, merge = self._recover_merge({
            "phase": "intent", "base": "Круги", "branch": "factory/rounds",
            "repository": "github.com/acme/repo", "commit_sha": "a" * 40,
            "rounds": 2, "actor_id": None,
        }, already_merged=True)

        merge.assert_not_called()
        self.assertEqual((records[0]["actor"], records[0]["actor_id"], records[0]["rounds"]),
                         ("owner", None, 2))

    def test_merge_recovery_preserves_actor_and_rounds(self):
        state, records, merge = self._recover_merge({
            "phase": "merging", "base": "Круги", "branch": "factory/rounds",
            "repository": "github.com/acme/repo", "commit_sha": "a" * 40,
            "rounds": 4, "actor": "automatic", "actor_id": None,
        }, already_merged=True)

        merge.assert_not_called()
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]["actor"], records[0]["rounds"]), ("automatic", 4))
        self.assertEqual(state["merge_intents"]["verify-1"]["phase"], "journaled")

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
                 "autostart_plan", "cleanup_work_archive")
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

        # A V2 delivery requires the immutable implementation SHA.  A legacy
        # Verify report with only a branch must not merge or falsely complete.
        self.assertEqual(merge.call_count, 0)
        final.assert_not_called()
        self.assertFalse(os.path.exists(journal))

    def test_merge_conflict_keeps_context_card_despite_verify_report_to_review(self):
        self.conf["stages"] = [
            {"workflow": "Implement + Test"},
            {"workflow": "Review"},
            {"workflow": "Verify"},
        ]
        self.conf["auto_merge"] = True
        created = []
        phase = {"value": "verify"}
        verify = {
            "id": "verify-conflict",
            "title": "[auto] [3/3 Verify] Сохранить номер карточки",
            "state": "succeeded", "repository_id": "repo-id",
            "created_at": "2026-08-11T10:00:00Z",
        }
        implement = {
            "id": "implement-after-conflict",
            "title": "[auto] [1/3 Implement + Test] Сохранить номер карточки",
            "state": "succeeded", "repository_id": "repo-id",
            "created_at": "2026-08-11T10:01:00Z",
        }

        def fake_api(path, payload=None):
            if path in ("/tasks?limit=100", "/tasks?limit=200"):
                return {"tasks": [verify] if phase["value"] == "verify" else [implement]}
            if path == "/tasks/verify-conflict":
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Verify", "revision_id": "verify-revision"},
                    "context": "Branch: factory/card-conflict\nCard: CARD-0070\n",
                    "attempts": [{"result": "PASS\nBRANCH: factory/card-conflict\nHEAD: " + "d" * 40 + "\nCard: CARD-0071"}],
                }
            if path == "/tasks/implement-after-conflict":
                return {
                    "task": {"repository_id": "repo-id", "worker_id": "implement-worker"},
                    "workflow": {"title": "Implement + Test", "revision_id": "implement-revision"},
                    "context": created[0]["context"],
                    "attempts": [{"result": "BRANCH: factory/card-conflict\nГотово"}],
                }
            if path == "/workers":
                return {"workers": []}
            if path == "/repositories":
                return {"repositories": [{"id": "repo-id",
                    "remote_identity": "github.com/acme/repo"}]}
            if path == "/workflows":
                return {"workflows": [{"id": name, "enabled": True,
                    "current_revision": {"id": name + "-revision", "title": title}}
                    for name, title in (("implement", "Implement + Test"),
                                        ("review", "Review"), ("verify", "Verify"))]}
            raise AssertionError(path)

        def create(body, _conf):
            created.append(body)
            return {"task": {"id": "created-" + str(len(created)),
                "title": body["title"], "state": "created",
                "repository_id": body["repository_id"]}}

        noops = ("collect_automation_findings", "cleanup_completed_plan_cards",
                 "write_dashboard", "provider_limits_tick", "detect_limits",
                 "record_new_works", "budget_guard", "money_guard", "handle_epics",
                 "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
                 "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
                 "handle_answers", "advance_epics", "pipeline_watch",
                 "cleanup_work_archive", "retry_pending_factory_deploy",
                 "autostart_plan", "area_extend", "collect_ideas", "save_promises")
        workers = {"implement-worker": {"id": "implement-worker"},
                   "review-worker": {"id": "review-worker"}}
        state = {"processed": []}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "create_task", side_effect=create))
            stack.enter_context(mock.patch.object(pilot, "best_workers", return_value=workers))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", side_effect=lambda _conf, stage, *_args:
                "review-worker" if stage == "Review" else "implement-worker"))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot", side_effect=lambda day, _week: {day: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "is_stopped", return_value=False))
            stack.enter_context(mock.patch.object(pilot, "live_or_done_at", return_value=None))
            stack.enter_context(mock.patch.object(pilot, "cap_rescues", return_value=0))
            stack.enter_context(mock.patch.object(pilot, "note_cap_rescue"))
            stack.enter_context(mock.patch.object(pilot, "notify"))
            stack.enter_context(mock.patch.object(pilot, "mark_final"))
            stack.enter_context(mock.patch.object(pilot, "gh_merge",
                                                  return_value=(False, "merge conflict")))
            stack.enter_context(mock.patch.object(
                pilot, "gh_json", side_effect=lambda args, **_kwargs:
                {"ahead_by": 1} if "/compare/" in args[-1]
                else {"name": "factory/card-conflict"}))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "reason": "готово", "next_complexity": "medium",
                "handoff": "проверить исправление",
            }))
            review_gate = stack.enter_context(mock.patch.object(
                pilot, "review_gate", return_value={"back": False, "note": "Карточка принята"}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(self.conf, state)
            # Merge failure is retried from the durable intent, rather than
            # creating a fake new pipeline stage without accepted delivery.
            # This legacy fixture has no persisted implementation artifact,
            # so V2 correctly refuses even to create an external intent.
            self.assertEqual(created, [])
            self.assertNotIn("verify-conflict", state.get("merge_intents", {}))

        review_gate.assert_not_called()


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


class StalePlanRevalidationTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 8, 14, 20, 0,
                                     tzinfo=datetime.timezone.utc).timestamp()
        self.idea = {
            "id": "idea-stale", "state": "in_work", "task_id": "triage-old",
            "title": "Проверить старую проблему", "created": "2026-08-13 10:00",
            "updated": "2026-08-13 10:00",
        }
        self.tasks = [{
            "id": "triage-old", "work_id": "triage-old",
            "title": "[auto] [1/5 Triage] Проверить старую проблему",
            "state": "succeeded", "created_at": "2026-08-13T15:00:00Z",
        }]

    def reconcile(self, ideas=None, questions=None):
        saved = []
        with mock.patch.object(pilot, "ideas_all",
                               return_value=ideas or [self.idea]), \
                mock.patch.object(pilot, "load_questions",
                                  return_value=questions or []), \
                mock.patch.object(pilot, "save",
                                  side_effect=lambda path, value: saved.append((path, value))):
            queued = pilot.reconcile_stale_plan_cards(self.tasks, now=self.now)
        return queued, saved

    def test_old_generation_returns_to_triage_with_new_generation(self):
        queued, saved = self.reconcile()

        self.assertEqual(queued, ["idea-stale"])
        self.assertEqual(self.idea["state"], "planned")
        self.assertEqual(self.idea["task_id"], "")
        self.assertTrue(self.idea["run_generation"])
        self.assertTrue(self.idea["revalidation"])
        self.assertEqual(len(saved), 1)

    def test_live_recent_or_question_blocked_generation_is_not_requeued(self):
        cases = (
            ({"state": "running"}, [], self.now),
            ({"updated_at": "2026-08-14T19:30:00Z"}, [], self.now),
            ({}, [{"status": "open", "task_id": "triage-old"}], self.now),
        )
        for task_update, questions, now in cases:
            with self.subTest(task_update=task_update, questions=questions):
                self.idea["state"] = "in_work"
                self.idea["task_id"] = "triage-old"
                self.tasks[0].pop("updated_at", None)
                self.tasks[0].pop("completed_at", None)
                self.tasks[0].update({"state": "succeeded"})
                self.tasks[0].update(task_update)
                queued, saved = self.reconcile(questions=questions)
                self.assertEqual(queued, [])
                self.assertEqual(saved, [])

    def test_revalidation_queue_is_bounded(self):
        ideas = []
        tasks = []
        for index in range(15):
            task_id = f"old-{index}"
            ideas.append({
                "id": f"idea-{index}", "state": "in_work", "task_id": task_id,
                "title": f"Старая проблема {index}",
                "created": "2026-08-13 10:00", "updated": "2026-08-13 10:00",
            })
            tasks.append({
                "id": task_id, "work_id": task_id,
                "title": f"[auto] [1/5 Triage] Старая проблема {index}",
                "state": "succeeded", "created_at": "2026-08-13T15:00:00Z",
            })
        self.tasks = tasks
        queued, _ = self.reconcile(ideas=ideas)

        self.assertEqual(len(queued), pilot.PLAN_REVALIDATION_QUEUE)
        self.assertEqual(sum(i.get("state") == "planned" for i in ideas),
                         pilot.PLAN_REVALIDATION_QUEUE)


class LegacyPlanCardCleanupTest(unittest.TestCase):
    cutoff = "2026-08-10T12:00:00Z"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = os.path.join(self.temporary.name, "ideas.json")
        self.idea = {"id": "idea-1", "title": "Старая работа", "state": "in_work",
                     "task_id": "root", "reason": "", "kept": 7}
        pilot.save(self.path, [dict(self.idea)])

    def task(self, task_id="root", state="succeeded", created="2026-08-10T09:00:00Z",
             stage="5/5 Verify", work_id="work-1", title="Старая работа"):
        return {"id": task_id, "title": f"[auto] [{stage}] {title}", "state": state,
                "created_at": created, "repository_id": "repo-1", "work_id": work_id}

    def bytes_on_disk(self):
        with open(self.path, "rb") as stream:
            return stream.read()

    def run_cleanup(self, tasks, apply=False, detail_time="2026-08-10T11:00:00Z",
                    api_error=None):
        def fake_api(path, _body=None):
            if api_error:
                raise api_error
            return {"execution": {"updated_at": detail_time}}
        with mock.patch.object(pilot, "IDEAS_PATH", self.path), \
                mock.patch.object(pilot, "all_tasks", return_value=tasks), \
                mock.patch.object(pilot, "api", side_effect=fake_api), \
                mock.patch.object(pilot, "final_ok", return_value=True), \
                mock.patch.object(pilot, "log"):
            return pilot.cleanup_legacy_plan_cards(
                self.cutoff, apply=apply,
                now_fn=lambda: datetime.datetime(2026, 8, 12, tzinfo=datetime.timezone.utc))

    def test_dry_run_finds_old_final_failure_and_missing_link_without_writing(self):
        cases = (
            ([self.task()], "root"),
            ([self.task(state="failed", stage="3/5 Implement + Test")], "root"),
            ([], "deleted"),
        )
        for tasks, task_id in cases:
            with self.subTest(task_id=task_id, state=tasks[0]["state"] if tasks else "missing"):
                data = dict(self.idea, task_id=task_id)
                pilot.save(self.path, [data])
                before = self.bytes_on_disk()
                self.assertEqual(self.run_cleanup(tasks), 1)
                self.assertEqual(self.bytes_on_disk(), before)

    def test_apply_preserves_record_and_marks_exact_reason_idempotently(self):
        self.assertEqual(self.run_cleanup([self.task()], apply=True), 1)
        record = pilot.load(self.path, [])[0]
        self.assertEqual(record["state"], "done")
        self.assertEqual(record["reason"], "закрыто уборкой")
        self.assertEqual(record["cleanup_reason"], "terminal_before_cutoff")
        self.assertEqual(record["cleanup_at"], "2026-08-12T00:00:00Z")
        self.assertEqual((record["task_id"], record["kept"]), ("root", 7))
        after = self.bytes_on_disk()
        self.assertEqual(self.run_cleanup([self.task()], apply=True), 0)
        self.assertEqual(self.bytes_on_disk(), after)

        pilot.save(self.path, [dict(self.idea, task_id="deleted")])
        self.assertEqual(self.run_cleanup([], apply=True), 1)
        missing = pilot.load(self.path, [])[0]
        self.assertEqual(missing["cleanup_reason"], "linked_task_missing")
        self.assertEqual(missing["task_id"], "deleted")

    def test_protective_cases_stay_byte_identical(self):
        cases = (
            ([self.task(state="running")], {}, "active"),
            ([self.task(state="cancelled")], {}, "cancelled"),
            ([self.task(stage="3/5 Implement + Test")], {}, "intermediate"),
            ([self.task()], {"detail_time": self.cutoff}, "at_cutoff"),
            ([self.task(), self.task("new", "running", "2026-08-10T10:00:00Z")], {}, "new_active"),
        )
        for tasks, kwargs, label in cases:
            with self.subTest(label=label):
                pilot.save(self.path, [dict(self.idea)])
                before = self.bytes_on_disk()
                self.assertEqual(self.run_cleanup(tasks, apply=True, **kwargs), 0)
                self.assertEqual(self.bytes_on_disk(), before)

    def test_empty_link_closed_states_and_ambiguous_legacy_stay_open(self):
        for state, task_id, tasks in (
                ("in_work", "", []), ("new", "root", []), ("done", "root", []),
                ("rejected", "root", []),
                ("in_work", "root", [self.task(work_id="") | {"repository_id": ""}])):
            with self.subTest(state=state, task_id=task_id):
                pilot.save(self.path, [dict(self.idea, state=state, task_id=task_id)])
                before = self.bytes_on_disk()
                self.assertEqual(self.run_cleanup(tasks, apply=True), 0)
                self.assertEqual(self.bytes_on_disk(), before)

    def test_invalid_cutoff_or_detail_error_never_writes(self):
        before = self.bytes_on_disk()
        with mock.patch.object(pilot, "IDEAS_PATH", self.path):
            with self.assertRaises(ValueError):
                pilot.cleanup_legacy_plan_cards("not-a-date", apply=True)
        self.assertEqual(self.bytes_on_disk(), before)
        with self.assertRaises(RuntimeError):
            self.run_cleanup([self.task()], apply=True, api_error=RuntimeError("detail failed"))
        self.assertEqual(self.bytes_on_disk(), before)

    def test_all_tasks_rejects_unfinished_pagination(self):
        with mock.patch.object(pilot, "api", return_value={"tasks": [], "next_cursor": "more"}):
            with self.assertRaises(RuntimeError):
                pilot.all_tasks()


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

    def test_external_pause_removal_refreshes_current_cycle_memory(self):
        pilot.save(self.conf_path, {"stopped_pipelines": [], "untouched": 7})

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
            ({"title": "Оплата продавцу", "status": "resolved",
              "machine_action": "wait"}, True),
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


class ProviderLimitDetectionTest(unittest.TestCase):
    def setUp(self):
        self.conf = {"name": "test"}
        self.workers = {"worker-claude": {"name": "claude-1"}}
        self.details = {}
        self.note_limit_calls = []

        def fake_api(path):
            task_id = path.removeprefix("/tasks/")
            return self.details[task_id]

        self.api_patch = mock.patch.object(pilot, "api", side_effect=fake_api)
        self.note_patch = mock.patch.object(
            pilot, "note_limit",
            side_effect=lambda *args: self.note_limit_calls.append(args),
        )
        self.provider_limits_patch = mock.patch.object(pilot, "load")
        self.api_mock = self.api_patch.start()
        self.note_patch.start()
        self.provider_limits_mock = self.provider_limits_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.addCleanup(self.note_patch.stop)
        self.addCleanup(self.provider_limits_patch.stop)

    @staticmethod
    def task(task_id, state):
        return {"id": task_id, "state": state, "worker_id": "worker-claude"}

    def test_succeeded_report_never_blocks_regardless_of_limit_snapshot(self):
        markers = "rate limit; quota exceeded; usage limit reached"
        self.details["patrol"] = {"attempts": [{"error": "", "result": markers}]}

        for snapshot in ({}, {"claude": {"used_percent": 99, "at": time.time()}}):
            with self.subTest(snapshot=snapshot):
                self.provider_limits_mock.return_value = snapshot
                pilot.detect_limits(
                    self.conf, [self.task("patrol", "succeeded")], self.workers)

        self.assertEqual(self.note_limit_calls, [])
        self.api_mock.assert_not_called()
        self.provider_limits_mock.assert_not_called()

    def test_result_only_markers_do_not_block_failed_or_cancelled_task(self):
        report = "Проверены rate limit и quota exceeded; это только отчёт."
        self.details["failed"] = {"attempts": [{"error": "", "result": report}]}
        self.details["cancelled"] = {"attempts": [{"error": "", "result": report}]}

        pilot.detect_limits(
            self.conf,
            [self.task("failed", "failed"), self.task("cancelled", "cancelled")],
            self.workers,
        )

        self.assertEqual(self.note_limit_calls, [])
        self.api_mock.assert_called_once_with("/tasks/failed")

    def test_successful_retry_does_not_reuse_previous_limit_error(self):
        self.details["retried"] = {"attempts": [
            {"state": "failed", "error": "rate limit reached"},
            {"state": "succeeded", "error": "", "result": "Готово"},
        ]}

        pilot.detect_limits(
            self.conf, [self.task("retried", "succeeded")], self.workers)

        self.assertEqual(self.note_limit_calls, [])
        self.api_mock.assert_not_called()

    def test_only_latest_attempt_error_is_considered(self):
        self.details["failed"] = {"attempts": [
            {"state": "failed", "error": "rate limit reached"},
            {"state": "failed", "error": "обычная ошибка"},
        ]}

        pilot.detect_limits(self.conf, [self.task("failed", "failed")], self.workers)

        self.assertEqual(self.note_limit_calls, [])

    def test_latest_failed_error_blocks_provider_with_reset_time(self):
        error = "usage limit reached; resets at 2026-08-16T07:30:00Z"
        self.details["failed"] = {"attempts": [
            {"state": "failed", "error": "обычная ошибка"},
            {"state": "failed", "error": error, "result": "rate limit в отчёте"},
        ]}

        pilot.detect_limits(self.conf, [self.task("failed", "failed")], self.workers)

        self.assertEqual(
            self.note_limit_calls,
            [(self.conf, "claude", error, "2026-08-16T07:30:00Z")],
        )

    def test_infrastructure_error_is_not_a_subscription_limit(self):
        self.details["failed"] = {"attempts": [{
            "state": "failed",
            "error": "rate limit reached after 401 Unauthorized",
        }]}

        pilot.detect_limits(self.conf, [self.task("failed", "failed")], self.workers)

        self.assertEqual(self.note_limit_calls, [])


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


class PlanTerminologyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ideas_path = os.path.join(self.temporary.name, "ideas.json")
        self.conf_path = os.path.join(self.temporary.name, "config.json")
        self.patches = [
            mock.patch.object(pilot, "IDEAS_PATH", self.ideas_path),
            mock.patch.object(pilot, "CONF_PATH", self.conf_path),
            mock.patch.object(pilot, "notify"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        pilot.save(self.ideas_path, [])
        pilot.save(self.conf_path, {})

    def test_owner_and_assistant_can_only_add_proposals(self):
        owner = pilot.add_idea("finding", "Проверить очередь", origin="owner")
        assistant = pilot.add_idea(
            "finding", "Добавить понятный статус", origin="assistant"
        )

        self.assertEqual(owner["kind"], "idea")
        self.assertEqual(assistant["kind"], "idea")

    def test_only_worker_result_with_source_can_be_a_finding(self):
        finding = pilot.add_idea(
            "finding",
            "Воркер завис после тестов",
            origin="worker",
            source="Работа: проверка выпуска",
        )
        missing_source = pilot.add_idea(
            "finding", "Нет источника", origin="worker"
        )

        self.assertEqual(finding["kind"], "finding")
        self.assertEqual(missing_source["kind"], "idea")

    def test_existing_manual_findings_are_migrated_to_proposals(self):
        pilot.save(self.ideas_path, [{
            "id": "old",
            "key": "finding||old",
            "kind": "finding",
            "title": "Поставил помощник",
            "origin": "assistant",
            "source": "",
        }])

        migrated = pilot.ideas_all()[0]

        self.assertEqual(migrated["kind"], "idea")
        self.assertTrue(migrated["key"].startswith("idea|"))


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
        set_idea.assert_called_once_with(
            "top", state="in_work", task_id="new-task", work_id="new-task")
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
            "top", state="in_work", task_id="new-task", work_id="new-task",
            repo="factory-repo-id")

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "new-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions")
    def test_owner_waiting_work_does_not_block_free_executor_slot(
            self, questions, ideas, create, _set_idea, _note_work, _notify):
        ideas.return_value = self.cards
        questions.return_value = [{"task_id": "waiting", "status": "open"}]
        tasks = [
            {"id": "a1", "title": "[auto] [1/5 Triage] A", "state": "running"},
            {"id": "a2", "title": "[auto] [2/5 Specification] A", "state": "queued"},
            {"id": "b", "title": "[auto] [1/5 Triage] B", "state": "preparing"},
            {"id": "waiting", "title": "[auto] [2/5 Specification] C", "state": "failed"},
        ]

        self.assertEqual(pilot.autostart_plan(
            self.conf, tasks, self.workflows, self.workers), "new-task")
        create.assert_called_once()

    @mock.patch.object(pilot, "create_task")
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    def test_owner_paused_planned_card_is_not_started(self, _questions, ideas,
                                                       create):
        paused = self.cards[1]
        ideas.return_value = [paused]
        conf = dict(self.conf, stopped_pipelines=[paused["title"]])

        self.assertIsNone(pilot.autostart_plan(
            conf, [], self.workflows, self.workers))
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

    def test_replenishment_promotes_new_cards_and_fills_every_free_slot(self):
        cards = [
            {"id": "one", "title": "One", "repo": "repo-1", "state": "new",
             "order": 10, "origin": "owner"},
            {"id": "two", "title": "Two", "repo": "repo-1", "state": "new",
             "order": 20, "origin": "assistant"},
            {"id": "three", "title": "Three", "repo": "repo-1", "state": "new",
             "order": 30, "origin": "worker"},
        ]
        conf = {
            "stages": [{"workflow": "Triage", "workers": {
                "low": "first", "medium": "second", "high": "third",
            }}],
            "max_parallel_works": 3,
        }
        workers = {
            "first": {"id": "worker-1", "online": True, "health": "healthy",
                      "capacity": 1, "active_count": 0},
            "second": {"id": "worker-2", "online": True, "health": "healthy",
                       "capacity": 1, "active_count": 0},
            "third": {"id": "worker-3", "online": True, "health": "healthy",
                      "capacity": 1, "active_count": 0},
        }
        created = []

        def update_card(idea_id, **fields):
            card = next(card for card in cards if card["id"] == idea_id)
            card.update(fields)
            return card

        def create(body, _conf):
            task_id = f"task-{len(created) + 1}"
            created.append(dict(body, id=task_id))
            return {"task": {"id": task_id, "title": body["title"],
                             "state": "queued"}}

        with mock.patch.object(pilot, "ideas_all", side_effect=lambda: cards), \
                mock.patch.object(pilot, "set_idea", side_effect=update_card), \
                mock.patch.object(pilot, "create_task", side_effect=create), \
                mock.patch.object(pilot, "work_lifecycle_block", return_value=""), \
                mock.patch.object(pilot, "load_limits", return_value={}), \
                mock.patch.object(pilot, "note_work"), \
                mock.patch.object(pilot, "notify"):
            tasks = []
            started = pilot.replenish_plan(conf, tasks, self.workflows, workers)

        self.assertEqual(started, ["task-1", "task-2", "task-3"])
        self.assertEqual(len(pilot.active_auto_works(tasks)), 3)
        self.assertEqual([body["worker_id"] for body in created],
                         ["worker-2", "worker-3", "worker-1"])
        self.assertTrue(all(card["state"] == "in_work" for card in cards))
        self.assertTrue(all(card.get("run_generation") for card in cards))

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "next-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "work_lifecycle_block", return_value="")
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_new_duplicate_is_linked_to_live_work_before_next_card_starts(
            self, _limits, _lifecycle, ideas, create, set_idea,
            _note_work, _notify):
        ideas.return_value = [
            {"id": "duplicate", "title": "Already running", "repo": "repo-1",
             "state": "new", "order": 1},
            {"id": "next", "title": "Useful next work", "repo": "repo-1",
             "state": "new", "order": 2},
        ]
        tasks = [{"id": "live-task", "title": "[auto] [2/5 Specification] Already running",
                  "state": "running"}]

        result = pilot.autostart_plan(self.conf, tasks, self.workflows, self.workers)

        self.assertEqual(result, "next-task")
        self.assertIn(mock.call("duplicate", state="in_work", task_id="live-task",
                                reason="Не запущено повторно: эта работа уже идёт."),
                      set_idea.call_args_list)
        self.assertEqual(create.call_count, 1)

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "next-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "work_lifecycle_block",
                       side_effect=["работа уже закрыта", ""])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_closed_new_card_is_rejected_before_next_card_starts(
            self, _limits, _lifecycle, ideas, create, set_idea,
            _note_work, _notify):
        ideas.return_value = [
            {"id": "closed", "title": "Closed", "repo": "repo-1",
             "state": "new", "order": 1},
            {"id": "next", "title": "Next", "repo": "repo-1",
             "state": "new", "order": 2},
        ]

        self.assertEqual(pilot.autostart_plan(
            self.conf, [], self.workflows, self.workers), "next-task")
        self.assertIn(mock.call("closed", state="rejected",
                                reason="Не запущено повторно: работа уже закрыта"),
                      set_idea.call_args_list)
        create.assert_called_once()

    @mock.patch.object(pilot, "create_task")
    @mock.patch.object(pilot, "ideas_all")
    def test_automatic_selection_can_be_disabled_without_blocking_manual_plan(
            self, ideas, create):
        ideas.return_value = [{"id": "new", "title": "New", "repo": "repo-1",
                               "state": "new", "order": 1}]

        self.assertIsNone(pilot.autostart_plan(
            dict(self.conf, auto_plan=False), [], self.workflows, self.workers))
        create.assert_not_called()

    @mock.patch.object(pilot, "notify")
    @mock.patch.object(pilot, "note_work")
    @mock.patch.object(pilot, "set_idea")
    @mock.patch.object(pilot, "create_task", return_value={"task": {"id": "fourth-task"}})
    @mock.patch.object(pilot, "ideas_all")
    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "load_limits", return_value={})
    def test_four_work_limit_and_free_worker_distribution(
            self, _limits, _questions, ideas, create, _set_idea,
            _note_work, _notify):
        conf = {
            "stages": [{"workflow": "Triage", "workers": {
                "medium": "preferred", "high": "spare",
            }}],
        }
        workflows = {"Triage": {"enabled": True, "revision_id": "wf-triage"}}
        workers = {
            "preferred": {"id": "worker-busy", "online": True,
                           "health": "healthy", "capacity": 1, "active_count": 1},
            "spare": {"id": "worker-free", "online": True,
                      "health": "healthy", "capacity": 1, "active_count": 0},
        }
        ideas.return_value = [self.cards[1]]
        three_active = [
            {"id": "a", "title": "[auto] [1/5 Triage] A", "state": "running"},
            {"id": "b", "title": "[auto] [2/5 Specification] B", "state": "queued"},
            {"id": "c", "title": "[auto] [3/5 Implement + Test] C", "state": "running"},
        ]

        result = pilot.autostart_plan(conf, three_active, workflows, workers)

        self.assertEqual(result, "fourth-task")
        self.assertEqual(create.call_args.args[0]["worker_id"], "worker-free")
        self.assertIsNone(pilot.autostart_plan(
            conf, three_active + [{"id": "d", "title": "[auto] [1/5 Triage] D",
                                   "state": "running"}], workflows, workers))
        self.assertEqual(create.call_count, 1)

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
            "top", state="in_work", task_id="created-on-first-post",
            work_id="created-on-first-post"))

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

    def test_cycle_runs_pipeline_watch_with_current_snapshot(self):
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

        watch.assert_called_once()
        self.assertIs(watch.call_args.args[0], self.conf)
        self.assertEqual(watch.call_args.args[1], tasks)
        self.assertEqual(watch.call_args.args[2]["Triage"]["revision_id"], "wf-triage")
        self.assertIs(watch.call_args.args[3], self.workers)
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
        self.assertEqual(set_idea.call_count, 2)
        generation = set_idea.call_args_list[0].kwargs["run_generation"]
        self.assertEqual(set_idea.call_args_list[0].args, ("manual-card",))
        self.assertEqual(set_idea.call_args_list[0].kwargs["state"], "planned")
        set_idea.assert_called_with(
            "manual-card", state="in_work", task_id="manual-task",
            run_generation=generation)


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
    def test_worker_without_repository_uses_repository_ready_spare(self, _limits):
        workers = {
            "preferred": {
                "online": True, "health": "healthy", "capacity": 2,
                "active_count": 0,
                "repositories": [{"id": "other"}],
            },
            "spare": {
                "online": True, "health": "healthy", "capacity": 2,
                "active_count": 0,
                "repositories": [{"id": "factory"}],
            },
        }

        selected = pilot.stage_worker(
            self.conf, "Implement + Test", "medium", workers,
            repository_id="factory")

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


class TriageCloseTests(unittest.TestCase):
    def test_close_or_duplicate_finishes_linked_plan_card(self):
        task = {"id": "triage-task", "title": "[auto] [1/5 Triage] Old work"}
        cards = [
            {"id": "linked", "task_id": "triage-task", "state": "in_work"},
            {"id": "other", "task_id": "other-task", "state": "in_work"},
        ]

        with mock.patch.object(pilot, "ideas_all", return_value=cards), \
                mock.patch.object(pilot, "close_work") as close, \
                mock.patch.object(pilot, "set_idea") as set_idea:
            closed = pilot.close_triage_without_work(
                task, "CLOSE / DUPLICATE — already shipped in CARD-0030")

        self.assertTrue(closed)
        close.assert_called_once_with(
            "Old work",
            "Разбор закрыл работу: она уже выполнена или дублирует существующую.",
        )
        set_idea.assert_called_once_with(
            "linked", state="done",
            reason="Разбор закрыл работу: она уже выполнена или дублирует существующую.",
        )

    def test_ready_report_is_not_closed(self):
        with mock.patch.object(pilot, "close_work") as close:
            closed = pilot.close_triage_without_work(
                {"id": "triage-task", "title": "[auto] [1/5 Triage] New work"},
                "READY TO SPECIFY\nProblem: still reproducible",
            )

        self.assertFalse(closed)
        close.assert_not_called()


class CertainDecisionTests(unittest.TestCase):
    def test_exact_positive_verdicts_do_not_call_the_model_again(self):
        cases = (
            ("Triage", "READY TO SPECIFY\nProblem: reproduced", "advance"),
            ("Review", "# APPROVE\nNo blocking findings.", "advance"),
            ("Verify", "PASS.\nAll release checks are green.", "stop"),
        )
        for stage, result, action in cases:
            with self.subTest(stage=stage), \
                    mock.patch.object(
                        pilot, "brain",
                        side_effect=AssertionError("model must not be called")):
                decision = pilot.decide(
                    {}, stage, "next", "Work", result, "repo")
            self.assertEqual(decision["action"], action)
            self.assertEqual(decision["next_complexity"], "medium")
            self.assertTrue(decision["verdict_ru"])

    def test_ambiguous_or_negative_verdict_still_uses_the_model(self):
        answer = json.dumps({
            "action": "stop", "reason": "needs context", "handoff": "",
            "next_complexity": "medium", "verdict_ru": "Нужны подробности.",
        })
        for result in ("Result: APPROVE", "BLOCKED\nDNS is unavailable"):
            with self.subTest(result=result), \
                    mock.patch.object(
                        pilot, "brain", return_value=(answer, "test")) as brain:
                decision = pilot.decide(
                    {}, "Review", "Verify", "Work", result, "repo")
            self.assertEqual(decision["action"], "stop")
            brain.assert_called_once()


class TerminalHandoffPriorityTests(unittest.TestCase):
    def test_late_existing_work_precedes_new_triage_backlog(self):
        tasks = [
            {"id": "triage-new", "title": "[auto] [1/5 Triage] New",
             "state": "succeeded", "created_at": "2026-08-14T20:10:00Z"},
            {"id": "spec", "title": "[auto] [2/5 Specification] Existing",
             "state": "succeeded", "created_at": "2026-08-14T20:09:00Z"},
            {"id": "implement", "title": "[auto] [3/5 Implement + Test] Existing",
             "state": "succeeded", "created_at": "2026-08-14T20:08:00Z"},
            {"id": "live", "title": "[auto] [5/5 Verify] Live",
             "state": "running", "created_at": "2026-08-14T20:11:00Z"},
        ]

        ordered = pilot.prioritize_terminal_handoffs(tasks, [])

        self.assertEqual([task["id"] for task in ordered],
                         ["implement", "spec", "triage-new", "live"])

    def test_processed_task_stays_out_of_urgent_prefix_unless_recovering(self):
        tasks = [
            {"id": "processed", "title": "[auto] [5/5 Verify] Old",
             "state": "succeeded", "created_at": "2026-08-14T20:00:00Z"},
            {"id": "fresh", "title": "[auto] [1/5 Triage] Fresh",
             "state": "succeeded", "created_at": "2026-08-14T20:01:00Z"},
        ]

        ordinary = pilot.prioritize_terminal_handoffs(tasks, ["processed"])
        recovery = pilot.prioritize_terminal_handoffs(
            tasks, ["processed"], ["processed"])

        self.assertEqual([task["id"] for task in ordinary],
                         ["fresh", "processed"])
        self.assertEqual([task["id"] for task in recovery],
                         ["processed", "fresh"])

    def test_round_robin_cursor_never_demotes_verify_behind_earlier_stage(self):
        tasks = [
            {"id": "verify-new", "title": "[auto] [5/5 Verify] Ready",
             "state": "succeeded"},
            {"id": "verify-cursor", "title": "[auto] [5/5 Verify] Previous",
             "state": "succeeded"},
            {"id": "implement", "title": "[auto] [3/5 Implement + Test] Old",
             "state": "succeeded"},
            {"id": "spec", "title": "[auto] [2/5 Specification] Old",
             "state": "succeeded"},
        ]
        ordered = pilot.prioritize_terminal_handoffs(tasks, [])

        rotated = pilot.rotate_terminal_handoffs(
            ordered, "verify-cursor", processed=[])

        self.assertEqual([task["id"] for task in rotated],
                         ["verify-new", "verify-cursor", "implement", "spec"])


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
                "repositories": [{"id": "repo-id"}],
            },
            "codex-sol-medium": {
                "id": "sol-medium", "online": True, "health": "healthy",
                "capacity": 2, "active_count": 0,
                "repositories": [{"id": "repo-id"}],
            },
            # Busy is intentional: a real escalation must queue here instead
            # of silently falling back to sol-medium.
            "codex-sol-high": {
                "id": "sol-high", "online": True, "health": "healthy",
                "capacity": 1, "active_count": 1,
                "repositories": [{"id": "repo-id"}],
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
        self.assertEqual(created[0]["parent_task_id"], "source-task")
        self.assertEqual(created[0]["correction_kind"], "review_return")
        raised = [message for title, message in notifications
                  if title == "Исполнитель повышен"]
        self.assertEqual(len(raised), 1)
        self.assertIn("codex-sol-medium → codex-sol-high", raised[0])

    def test_parallel_limit_defers_answer_without_counting_a_failed_retry(self):
        question = {
            "id": "question-id", "task_id": "source-task",
            "status": "answered", "answer": "Продолжай",
            "resume_stage": "Specification", "stage": "Triage",
            "title": "Работа", "repository_id": "repo-id",
        }
        conf = {
            "stages": [{"workflow": "Specification", "workers": {
                "medium": "worker",
            }}],
            "timeout_seconds": 900,
        }
        workflows = {
            "Specification": {"enabled": True, "revision_id": "revision"},
        }
        workers = {"worker": {"id": "worker-id"}}

        with mock.patch.object(pilot, "load_questions", return_value=[question]), \
                mock.patch.object(pilot, "load", return_value=dict(question)), \
                mock.patch.object(pilot, "work_lifecycle_block", return_value=""), \
                mock.patch.object(pilot, "stage_attempts", return_value=0), \
                mock.patch.object(pilot, "stage_worker", return_value="worker"), \
                mock.patch.object(pilot, "selected_delivery", return_value=("", "")), \
                mock.patch.object(pilot, "branch_from_history", return_value=""), \
                mock.patch.object(pilot, "is_stopped", return_value=False), \
                mock.patch.object(pilot, "live_or_done_at", return_value=None), \
                mock.patch.object(
                    pilot, "create_child_task",
                    side_effect=pilot.ParallelWorkLimit("parallel_work_limit"),
                ) as create, \
                mock.patch.object(pilot, "save") as save:
            applied = pilot.handle_answers(conf, workflows, workers, [])

        self.assertEqual(applied, 0)
        create.assert_called_once()
        save.assert_not_called()

    def test_newly_opened_slot_resumes_answer_before_plan(self):
        conf = {"max_parallel_works": 4}
        fresh_tasks = [
            {"id": str(index), "title": f"[auto] [1/5 Triage] Work {index}",
             "state": "running"}
            for index in range(3)
        ]
        order = []

        def resume(_conf, _workflows, _workers, tasks):
            order.append("answer")
            tasks.append({"id": "correction",
                          "title": "[auto] [3/5 Implement + Test] Correction",
                          "state": "queued"})
            return 1

        def plan(_conf, tasks, _workflows, _workers):
            order.append("plan")
            self.assertEqual(len(pilot.active_auto_works(tasks)), 4)
            return []

        with mock.patch.object(
                pilot, "api", return_value={"tasks": fresh_tasks}), \
                mock.patch.object(pilot, "handle_answers", side_effect=resume), \
                mock.patch.object(pilot, "replenish_plan", side_effect=plan):
            applied = pilot.refill_open_work_slots(conf, {}, {})

        self.assertEqual(applied, 1)
        self.assertEqual(order, ["answer", "plan"])
        self.assertIs(conf["_active_work_tasks"], fresh_tasks)

    def test_terminal_backlog_reserves_open_slot_before_new_plan_work(self):
        conf = {"max_parallel_works": 4}
        fresh_tasks = [{
            "id": "running", "title": "[auto] [1/5 Triage] Existing",
            "state": "running",
        }]

        with mock.patch.object(
                pilot, "api", return_value={"tasks": fresh_tasks}), \
                mock.patch.object(pilot, "handle_answers", return_value=0), \
                mock.patch.object(pilot, "replenish_plan") as replenish:
            pilot.refill_open_work_slots(
                conf, {}, {}, admit_new_plan=False)

        replenish.assert_not_called()
        self.assertIs(conf["_active_work_tasks"], fresh_tasks)


class OrchestratorWaitActionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.question_dir = os.path.join(self.temporary.name, "questions")
        self.conf_path = os.path.join(self.temporary.name, "config.json")
        self.patches = (
            mock.patch.object(pilot, "QUESTION_DIR", self.question_dir),
            mock.patch.object(pilot, "CONF_PATH", self.conf_path),
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conf = {
            "stages": [{"workflow": "Specification", "worker": "worker"}],
            "stopped_pipelines": [],
            "timeout_seconds": 900,
            "deep_diag_rounds": 5,
            "max_stage_attempts": 3,
            "max_work_rounds": 8,
        }
        pilot.save(self.conf_path, dict(self.conf))
        self.workflows = {
            "Specification": {"enabled": True, "revision_id": "revision"},
        }
        self.workers = {
            "worker": {"id": "worker-id", "online": True,
                       "health": "healthy", "capacity": 1, "active_count": 0},
        }

    def route(self, verdict, task_id="question-id"):
        with mock.patch.object(pilot, "orchestrator_answer", return_value=verdict), \
                mock.patch.object(pilot, "notify"), \
                mock.patch.object(pilot, "load_limits", return_value={}):
            return pilot.route_question(
                self.conf, task_id, "Triage", "Specification", "Новая работа",
                "repo-id", "вердикт WAIT", "Что делать дальше?", [],
                "WAIT до трёх зелёных циклов")

    def apply_answers_twice(self):
        created = []
        with mock.patch.object(pilot, "load_limits", return_value={}), \
                mock.patch.object(pilot, "notify"), \
                mock.patch.object(
                    pilot, "create_task",
                    side_effect=lambda body, _conf: created.append(body)
                    or {"task": {"id": "created-task"}},
                ):
            pilot.handle_answers(self.conf, self.workflows, self.workers, [])
            pilot.handle_answers(self.conf, self.workflows, self.workers, [])
        return created

    def test_wait_resolves_question_pauses_pipeline_and_never_creates_task(self):
        self.assertFalse(self.route({
            "decision": "wait",
            "reason": "Отложить до трёх подряд зелёных полных циклов",
        }))

        question = pilot.load(os.path.join(self.question_dir, "question-id.json"), {})
        self.assertEqual(question["status"], "resolved")
        self.assertEqual(question["machine_action"], "wait")
        self.assertEqual(question["answered_by"], "orchestrator")
        self.assertIn("трёх подряд зелёных", question["answer"])
        self.assertEqual(self.conf["stopped_pipelines"], ["Новая работа"])
        self.assertEqual(
            pilot.load(self.conf_path, {})["stopped_pipelines"], ["Новая работа"])
        self.assertEqual(self.apply_answers_twice(), [])

    def test_transient_infrastructure_wait_retries_same_stage_after_backoff(self):
        verdict = {
            "decision": "wait",
            "reason": "GitHub недоступен: Could not resolve host: github.com",
        }
        with mock.patch.object(pilot, "orchestrator_answer", return_value=verdict), \
                mock.patch.object(pilot, "notify"), \
                mock.patch.object(pilot, "load_limits", return_value={}):
            self.assertFalse(pilot.route_question(
                self.conf, "dns-question", "Specification", "Specification",
                "Сетевая проверка", "repo-id", "BLOCKED: review infrastructure",
                "Что делать дальше?", [],
                "Could not resolve host: github.com", attempts_so_far=1,
                branch="factory/network-check"))

        path = os.path.join(self.question_dir, "dns-question.json")
        question = pilot.load(path, {})
        self.assertEqual(question["status"], "answered")
        self.assertEqual(question["machine_action"], "retry_infrastructure")
        self.assertEqual(question["resume_stage"], "Specification")
        self.assertNotIn("Сетевая проверка", self.conf["stopped_pipelines"])
        self.assertEqual(self.apply_answers_twice(), [])

        question["retry_not_before"] = "2000-01-01T00:00:00Z"
        pilot.save(path, question)
        created = self.apply_answers_twice()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"],
                         "[auto] [1/1 Specification] Сетевая проверка")
        self.assertIn("автоматический повтор того же снимка", created[0]["context"])
        self.assertNotIn("ОТВЕТ ВЛАДЕЛЬЦА", created[0]["context"])

    def test_russian_dns_wait_is_also_an_infrastructure_retry(self):
        self.conf["stages"] = [{"workflow": "Review", "worker": "worker"}]
        self.workflows["Review"] = {
            "enabled": True, "revision_id": "review-revision",
        }
        pilot.save(self.conf_path, dict(self.conf))
        verdict = {
            "decision": "wait",
            "reason": (
                "Проверку нужно оставить до восстановления DNS-доступа к GitHub; "
                "без свежего origin продолжать нельзя."
            ),
        }
        with mock.patch.object(pilot, "orchestrator_answer", return_value=verdict), \
                mock.patch.object(pilot, "notify"), \
                mock.patch.object(pilot, "load_limits", return_value={}):
            self.assertFalse(pilot.route_question(
                self.conf, "russian-dns-question", "Review", "Review",
                "Сетевая проверка", "repo-id", "Проверка временно остановлена",
                "Что делать дальше?", [], "GitHub сейчас недоступен",
                attempts_so_far=1, branch="factory/network-check"))

        question = pilot.load(
            os.path.join(self.question_dir, "russian-dns-question.json"), {})
        self.assertEqual(question["status"], "answered")
        self.assertEqual(question["machine_action"], "retry_infrastructure")
        self.assertEqual(question["resume_stage"], "Review")
        self.assertNotIn("Сетевая проверка", self.conf["stopped_pipelines"])

        question["retry_not_before"] = "2000-01-01T00:00:00Z"
        pilot.save(
            os.path.join(self.question_dir, "russian-dns-question.json"), question)
        created = self.apply_answers_twice()
        self.assertEqual(len(created), 1)
        self.assertIn("Branch: factory/network-check\n", created[0]["context"])
        self.assertNotIn("Прошлая работа лежит в ветке", created[0]["context"])

    def test_continue_creates_exactly_one_task_across_repeated_cycles(self):
        self.assertFalse(self.route({
            "decision": "answer",
            "answer": "Исправь найденную гонку и повтори проверку",
        }))

        created = self.apply_answers_twice()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"],
                         "[auto] [1/1 Specification] Новая работа")
        question = pilot.load(os.path.join(self.question_dir, "question-id.json"), {})
        self.assertEqual(question["status"], "resolved")
        self.assertEqual(question["resumed_task_id"], "created-task")

    def test_manual_wait_word_is_not_reinterpreted_as_machine_action(self):
        question = pilot.write_question(
            "manual-question", "Triage", "Specification", "Ручная работа",
            "repo-id", "нужен выбор", "Продолжать?", [], "", status="answered")
        self.assertRegex(question["asked_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        question["answer"] = "Отложить и сначала исправить окружение"
        question["answered_by"] = "owner"
        pilot.save(os.path.join(self.question_dir, "manual-question.json"), question)

        created = self.apply_answers_twice()

        self.assertEqual(len(created), 1)
        self.assertIn("ОТВЕТ ВЛАДЕЛЬЦА", created[0]["context"])

    def test_orchestrator_contract_accepts_explicit_wait_decision(self):
        reply = json.dumps({
            "decision": "wait",
            "reason": "Условие продолжения ещё не выполнено",
        })
        with mock.patch.object(pilot, "brain", return_value=(reply, "test")):
            verdict = pilot.orchestrator_answer(
                {"auto_answer": True}, "Triage", "Работа", "WAIT", "Дальше?", "")

        self.assertEqual(verdict["decision"], "wait")
        self.assertEqual(verdict["reason"], "Условие продолжения ещё не выполнено")

    def test_wait_survives_repeated_cleanup_and_pipeline_watch_cycles(self):
        self.conf["stages"] = [
            {"workflow": "Triage", "worker": "worker"},
            {"workflow": "Specification", "worker": "worker"},
        ]
        pilot.save(self.conf_path, dict(self.conf))
        self.assertFalse(self.route({
            "decision": "wait",
            "reason": "Владелец явно снимет паузу после проверки",
        }))
        task = {
            "id": "question-id",
            "title": "[auto] [1/2 Triage] Новая работа",
            "state": "succeeded",
            "repository_id": "repo-id",
        }
        worker = {
            "id": "worker-id", "name": "worker", "online": True,
            "health": "healthy", "capacity": 1, "active_count": 0,
        }
        workflows = [
            {"id": "triage", "enabled": True,
             "current_revision": {"title": "Triage", "id": "rev-triage"}},
            {"id": "spec", "enabled": True,
             "current_revision": {
                 "title": "Specification", "id": "rev-spec"}},
        ]

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": [task]}
            if path == "/workers":
                return {"workers": [worker]}
            if path == "/repositories":
                return {"repositories": []}
            if path == "/workflows":
                return {"workflows": workflows}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "advance_epics",
            "retry_pending_factory_deploy", "autostart_plan",
        )
        created = []
        state = {"processed": ["question-id"]}
        stall_path = os.path.join(self.temporary.name, "pipeline_stalls.json")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "STALL_PATH", stall_path))
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "ideas_all", return_value=[]))
            stack.enter_context(mock.patch.object(pilot, "load_limits", return_value={}))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "work_status_write"))
            stack.enter_context(mock.patch.object(
                pilot, "create_task", side_effect=lambda body, _conf:
                created.append(body) or {"task": {"id": "unexpected"}}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(self.conf, state)
            pilot.cycle(self.conf, state)

        self.assertEqual(created, [])
        self.assertEqual(self.conf["stopped_pipelines"], ["Новая работа"])
        self.assertEqual(
            pilot.load(self.conf_path, {})["stopped_pipelines"], ["Новая работа"])
        self.assertEqual(pilot.load(stall_path, {})["Новая работа"]["why"], "owner")


class AdaptivePollingTests(unittest.TestCase):
    def _restart_handoff_fixture(self, create_effects, cycles,
                                 area_busy_effect="", restart_after_first=False,
                                 shared_task_store=None, stale_snapshot=False,
                                 request_log=None):
        conf = {
            "stages": [{"workflow": "Triage"}, {"workflow": "Specification"}],
            "poll_seconds": 30,
            "_restart_recovery_ids": frozenset(("triage-done",)),
            "_restart_recovery_watermark": "2026-08-10T10:00:00Z",
        }
        state = {"processed": ["triage-done"]}
        tasks = [{
            "id": "triage-done",
            "title": "[auto] [1/2 Triage] Восстановить передачу",
            "state": "succeeded",
            "created_at": "2026-08-10T09:00:00Z",
            "repository_id": "repo-id",
        }]
        created = []
        task_store = shared_task_store if shared_task_store is not None else {}
        initial_tasks = list(tasks)
        effects = iter(create_effects)

        def fake_api(path, body=None):
            if request_log is not None:
                request_log.append(path)
            if path == "/tasks?limit=100":
                return {"tasks": list(initial_tasks if stale_snapshot else tasks)}
            if path == "/tasks/triage-done":
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Triage"},
                    "context": "",
                    "execution": {"updated_at": "2026-08-10T10:01:00Z"},
                    "attempts": [{"result": "READY"}],
                }
            if path == "/tasks" and body is not None:
                existing = task_store.get(body["request_key"])
                if existing:
                    return {"task": existing}
                effect = next(effects)
                if isinstance(effect, Exception):
                    raise effect
                child = {
                    "id": f"spec-{len(created)}", "title": body["title"],
                    "state": "created", "created_at": "2026-08-10T11:00:00Z",
                    "repository_id": "repo-id",
                }
                created.append(child)
                tasks.append(child)
                task_store[body["request_key"]] = child
                return {"task": child}
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 2, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "spec", "enabled": True,
                    "current_revision": {"id": "rev-spec", "title": "Specification"},
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "dashboard_slow", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "autostart_plan", "area_extend", "collect_ideas", "all_tasks",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", return_value="worker"))
            stack.enter_context(mock.patch.object(
                pilot, "area_busy", side_effect=area_busy_effect
                if callable(area_busy_effect) or isinstance(area_busy_effect, list)
                else None, return_value=area_busy_effect))
            stack.enter_context(mock.patch.object(
                pilot, "work_lifecycle_block", return_value=""))
            decide = stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            for cycle_number in range(cycles):
                pilot.cycle(conf, state)
                if restart_after_first and cycle_number == 0:
                    state["terminal_handoff_watermark"] = (
                        conf["_restart_recovery_watermark"]
                        if conf.get("_restart_recovery_retry")
                        else "2026-08-10T12:00:00Z")
                    state_path = os.path.join(
                        _TEST_DATA_HOME.name,
                        f"restart-recovery-state-{uuid.uuid4()}.json")
                    pilot.save(state_path, state)
                    state = pilot.load(state_path, {})
                    conf = {key: value for key, value in conf.items()
                            if key != "_restart_recovery_retry"}
                    conf["_restart_recovery_ids"] = frozenset(state["processed"])
                    conf["_restart_recovery_watermark"] = state[
                        "terminal_handoff_watermark"]

        return state, tasks, created, decide

    def test_restart_recovers_processed_success_with_missing_next_stage(self):
        state, tasks, created, decide = self._restart_handoff_fixture([None], 2)

        # A second process receives the same durable startup boundary. The
        # already-created Specification must suppress both decision and create.
        conf = {
            "_restart_recovery_ids": frozenset(("triage-done",)),
            "_restart_recovery_watermark": "2026-08-10T10:00:00Z",
        }
        with mock.patch.object(pilot, "api") as api, \
                mock.patch.object(pilot, "work_lifecycle_block", return_value=""):
            detail = pilot.restart_recovery_detail(
                conf, tasks, tasks[0], ["Triage", "Specification"])

        self.assertIsNone(detail)
        api.assert_called_once_with("/tasks/triage-done")
        self.assertEqual(len(created), 1)
        self.assertEqual(decide.call_count, 1)
        self.assertEqual(state["processed"], ["triage-done"])

    def test_restart_recovery_is_consumed_after_first_cycle(self):
        requests = []
        state, _tasks, created, decide = self._restart_handoff_fixture(
            [None], 2, request_log=requests)

        self.assertEqual(len(created), 1)
        self.assertEqual(decide.call_count, 1)
        self.assertEqual(requests.count("/tasks/triage-done"), 1)
        self.assertEqual(state["processed"], ["triage-done"])

    def test_restart_recovery_retries_temporary_create_failure(self):
        state, _tasks, created, decide = self._restart_handoff_fixture([
            pilot.ParallelWorkLimit("busy"), None,
        ], 2)

        self.assertEqual(len(created), 1)
        self.assertEqual(decide.call_count, 2)
        self.assertEqual(state["processed"], ["triage-done"])

    def test_restart_recovery_loads_saved_id_beyond_first_hundred_tasks(self):
        conf = {
            "_restart_recovery_ids": frozenset(("old-terminal",)),
            "_restart_recovery_watermark": "2026-08-10T10:00:00Z",
        }
        tasks = [{"id": f"new-{number}"} for number in range(100)]
        detail = {
            "task": {
                "id": "old-terminal",
                "title": "[auto] [1/2 Triage] Старая работа",
                "state": "succeeded", "created_at": "2026-08-10T09:00:00Z",
            },
            "workflow": {"title": "Triage"},
            "execution": {"updated_at": "2026-08-10T10:01:00Z"},
        }
        with mock.patch.object(pilot, "api", return_value=detail) as api, \
                mock.patch.object(pilot, "work_lifecycle_block", return_value=""):
            details = pilot.load_restart_recovery_tasks(conf, tasks)
            recovered = tasks[-1]
            self.assertIs(pilot.restart_recovery_detail(
                conf, tasks, recovered, ["Triage", "Specification"],
                details["old-terminal"]), detail)

        self.assertEqual(len(tasks), 101)
        api.assert_called_once_with("/tasks/old-terminal")

    def test_normal_cycle_advances_terminal_task_beyond_first_page(self):
        conf = {
            "stages": [{"workflow": "Triage"}, {"workflow": "Specification"}],
            "poll_seconds": 30,
        }
        state = {"processed": []}
        recent = [{
            "id": f"recent-{number}", "title": f"service task {number}",
            "state": "succeeded", "created_at": "2026-08-10T11:00:00Z",
        } for number in range(100)]
        hidden = {
            "id": "hidden-triage",
            "title": "[auto] [1/2 Triage] Hidden continuation",
            "state": "succeeded", "created_at": "2026-08-10T09:00:00Z",
            "repository_id": "repo-id",
        }
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(recent)}
            if path == "/tasks/hidden-triage":
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Triage"},
                    "context": "",
                    "attempts": [{"result": "READY"}],
                }
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 1, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "spec", "enabled": True,
                    "current_revision": {
                        "id": "rev-spec", "title": "Specification",
                    },
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "autostart_plan", "area_extend",
            "collect_ideas",
        )
        plan_cleanup_histories = []
        archive_cleanup_histories = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(
                pilot, "all_tasks", return_value=recent + [hidden]))
            stack.enter_context(mock.patch.object(
                pilot, "cleanup_completed_plan_cards",
                side_effect=lambda tasks, _stages:
                plan_cleanup_histories.append(list(tasks))))
            stack.enter_context(mock.patch.object(
                pilot, "cleanup_work_archive",
                side_effect=lambda _conf, tasks:
                archive_cleanup_histories.append(list(tasks))))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", return_value="worker"))
            stack.enter_context(mock.patch.object(
                pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(
                pilot, "work_lifecycle_block", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            stack.enter_context(mock.patch.object(
                pilot, "create_task", side_effect=lambda body, _conf:
                created.append(body) or {"task": {
                    "id": "spec-created", "title": body["title"],
                    "state": "created", "repository_id": "repo-id",
                }}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)

        self.assertEqual(len(plan_cleanup_histories), 1)
        self.assertEqual(len(archive_cleanup_histories), 1)
        self.assertIn(hidden, plan_cleanup_histories[0])
        self.assertIn(hidden, archive_cleanup_histories[0])
        self.assertEqual([body["title"] for body in created], [
            "[auto] [2/2 Specification] Hidden continuation",
        ])
        self.assertIn("hidden-triage", state["processed"])

    def test_terminal_handoff_history_keeps_second_page_without_replaying_archive(self):
        tasks = [{"id": f"task-{number}"} for number in range(350)]

        bounded = pilot.recent_terminal_handoff_history(
            tasks, pinned_ids={"task-300"})

        self.assertEqual(len(bounded), 201)
        self.assertEqual(bounded[100]["id"], "task-100")
        self.assertEqual(bounded[199]["id"], "task-199")
        self.assertEqual(bounded[-1]["id"], "task-300")
        self.assertNotIn("task-200", {task["id"] for task in bounded})

    def test_retry_terminal_task_keeps_deferred_handoff_pinned(self):
        state = {"processed": ["deferred"]}

        pilot.retry_terminal_task({}, state, "deferred")
        pilot.retry_terminal_task({}, state, "deferred")

        self.assertEqual(state["processed"], [])
        self.assertEqual(state["terminal_retry_ids"], ["deferred"])

    def test_restart_recovery_skips_unavailable_ids_individually(self):
        conf = {
            "_restart_recovery_ids": frozenset(("gone", "broken", "available")),
            "_restart_recovery_watermark": "2026-08-10T10:00:00Z",
        }
        tasks = []
        available_detail = {
            "task": {
                "id": "available",
                "title": "[auto] [1/2 Triage] Доступная старая работа",
                "state": "succeeded",
            },
        }

        def fake_api(path):
            if path == "/tasks/gone":
                raise urllib.error.HTTPError(
                    path, 404, "not found", {}, io.BytesIO(b"gone"))
            if path == "/tasks/broken":
                raise RuntimeError("temporary detail failure")
            if path == "/tasks/available":
                return available_detail
            raise AssertionError(path)

        with mock.patch.object(pilot, "api", side_effect=fake_api):
            details = pilot.load_restart_recovery_tasks(conf, tasks)

        self.assertEqual(set(details), {"available"})
        self.assertEqual([task["id"] for task in tasks], ["available"])

    def test_two_pilots_replay_one_atomic_continuation_request(self):
        # Both processes see the same stale task page.  The storage-backed
        # request key must return the first child to the second process.
        task_store = {}
        first = self._restart_handoff_fixture(
            [None], 1, shared_task_store=task_store, stale_snapshot=True)
        second = self._restart_handoff_fixture(
            [None], 1, shared_task_store=task_store, stale_snapshot=True)

        self.assertEqual(len(task_store), 1)
        self.assertEqual(len(first[2]), 1)
        self.assertEqual(second[2], [])
        self.assertEqual(next(iter(task_store)), pilot.continuation_request_key(
            "triage-done", "rev-spec"))

    def test_restart_recovery_survives_area_wait_and_second_restart(self):
        state, _tasks, created, decide = self._restart_handoff_fixture(
            [None], 2, area_busy_effect=["другая работа", ""],
            restart_after_first=True)

        self.assertEqual(len(created), 1)
        self.assertEqual(decide.call_count, 1)
        self.assertEqual(state["processed"], ["triage-done"])

    def test_restart_recovery_rejects_unsafe_or_completed_candidates(self):
        source = {
            "id": "done", "title": "[auto] [1/2 Triage] Работа",
            "state": "succeeded", "created_at": "2026-08-10T09:00:00Z",
        }
        conf = {
            "_restart_recovery_ids": frozenset(("done",)),
            "_restart_recovery_watermark": "2026-08-10T10:00:00Z",
        }
        detail = {"workflow": {"title": "Triage"}}
        tails = [dict(
            source, id=f"tail-{task_state}",
            title="[auto] [2/2 Specification] Работа", state=task_state,
            created_at="2026-08-10T10:02:00Z",
        ) for task_state in ("created", "queued", "preparing", "running", "succeeded")]

        for tail in tails:
            with self.subTest(tail=tail["state"]), \
                    mock.patch.object(pilot, "api", return_value=detail), \
                    mock.patch.object(pilot, "work_lifecycle_block", return_value=""):
                self.assertIsNone(pilot.restart_recovery_detail(
                    conf, [source, tail], source, ["Triage", "Specification"]))

        rejected = (
            (dict(source, state="failed"), conf, detail, ""),
            (dict(source, state="cancelled"), conf, detail, ""),
            (source, conf, dict(detail, execution={}), ""),
            (source, dict(conf, _restart_recovery_watermark=""), detail, ""),
            (source, conf, {"workflow": {"title": "Unknown"}}, ""),
            (source, conf, {"workflow": {"title": "Specification"}}, ""),
            (source, conf, detail, "archived"),
        )
        for task, candidate_conf, candidate_detail, blocked in rejected:
            with self.subTest(task=task.get("state"), blocked=blocked,
                              workflow=candidate_detail["workflow"]["title"]), \
                    mock.patch.object(pilot, "api", return_value=candidate_detail), \
                    mock.patch.object(
                        pilot, "work_lifecycle_block", return_value=blocked):
                self.assertIsNone(pilot.restart_recovery_detail(
                    candidate_conf, [task], task, ["Triage", "Specification"]))

        with mock.patch.object(pilot, "api", return_value=detail), \
                mock.patch.object(pilot, "work_lifecycle_block", return_value=""):
            self.assertIsNone(pilot.restart_recovery_detail(
                dict(conf, stopped_pipelines=["Работа"]), [source], source,
                ["Triage", "Specification"]))

        with mock.patch.object(pilot, "api", return_value={
                "workflow": {"title": "Triage"},
                "attempts": [{"completed_at": "2026-08-10T10:01:00Z"}],
        }), mock.patch.object(pilot, "work_lifecycle_block", return_value=""):
            self.assertIsNotNone(pilot.restart_recovery_detail(
                conf, [source], source, ["Triage", "Specification"]))

    def test_loop_moves_recovery_watermark_only_after_success(self):
        conf = {"enabled": True, "poll_seconds": 30}
        state = {
            "processed": ["done"],
            "terminal_handoff_watermark": "2026-08-10T10:00:00Z",
        }

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        recovery_seen = []

        def fake_cycle(cycle_conf, _state):
            recovery_seen.append(cycle_conf.get("_restart_recovery_ids"))
            if len(recovery_seen) == 1:
                return {"seconds": 30, "reason": "idle"}
            raise RuntimeError("boom")

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "write_automation_status"), \
                mock.patch.object(pilot, "cycle", side_effect=fake_cycle):
            pilot.run_loop(max_cycles=2, sleep_fn=lambda _seconds: None,
                           clock_fn=iter((100.0, 200.0)).__next__)

        self.assertEqual(
            state["terminal_handoff_watermark"], "1970-01-01T00:01:40Z")
        self.assertEqual(recovery_seen,
                         [frozenset(("done",)), None])

    def test_restart_recovery_is_bounded_to_recent_terminal_tasks(self):
        conf = {"enabled": True, "poll_seconds": 30}
        ids = [
            f"terminal-{number}"
            for number in range(pilot.RESTART_RECOVERY_RETENTION + 1)
        ]
        state = {
            "processed": ids,
            "terminal_handoff_watermark": "2026-08-10T10:00:00Z",
        }
        recovery_seen = []

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        def fake_cycle(cycle_conf, _state):
            recovery_seen.append(cycle_conf.get("_restart_recovery_ids"))
            return {"seconds": 30, "reason": "idle"}

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "write_automation_status"), \
                mock.patch.object(pilot, "cycle", side_effect=fake_cycle):
            pilot.run_loop(max_cycles=1, sleep_fn=lambda _seconds: None,
                           clock_fn=lambda: 100.0)

        self.assertEqual(len(recovery_seen[0]), pilot.RESTART_RECOVERY_RETENTION)
        self.assertNotIn(ids[0], recovery_seen[0])
        self.assertIn(ids[-1], recovery_seen[0])

    def test_loop_keeps_recovery_watermark_when_handoff_is_pending(self):
        conf = {"enabled": True, "poll_seconds": 30}
        state = {
            "processed": ["done"],
            "terminal_handoff_watermark": "2026-08-10T10:00:00Z",
        }

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        def pending_cycle(cycle_conf, _state):
            cycle_conf["_restart_recovery_retry"] = True
            return {"seconds": 30, "reason": "idle"}

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "write_automation_status"), \
                mock.patch.object(pilot, "cycle", side_effect=pending_cycle):
            pilot.run_loop(max_cycles=1, sleep_fn=lambda _seconds: None,
                           clock_fn=lambda: 100.0)

        self.assertEqual(
            state["terminal_handoff_watermark"], "2026-08-10T10:00:00Z")

    def test_loop_retains_more_than_two_thousand_terminal_task_ids(self):
        conf = {"enabled": True, "poll_seconds": 30}
        ids = [f"terminal-{number}" for number in range(2501)]
        state = {
            "processed": list(ids),
            "automation_results_processed": list(ids),
            "epics_processed": list(ids),
            "epic_starts_processed": list(ids),
            "poll_terminal_seen": list(ids),
        }

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "cycle", return_value={
                    "seconds": 30, "reason": "idle",
                }):
            pilot.run_loop(max_cycles=1, sleep_fn=lambda _seconds: None,
                           clock_fn=lambda: 100.0)

        for key in (
                "processed", "automation_results_processed", "epics_processed",
                "epic_starts_processed", "poll_terminal_seen"):
            self.assertEqual(state[key], ids)

    def test_loop_restores_missing_required_cursors_without_losing_state(self):
        conf = {"enabled": True, "poll_seconds": 30}
        state = {"delivery_state_v2": {"targets": {"factory": {}}}}
        observed = []

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        def fake_cycle(_conf, cycle_state):
            observed.append(cycle_state)
            return {"seconds": 30, "reason": "idle"}

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "write_automation_status"), \
                mock.patch.object(pilot, "cycle", side_effect=fake_cycle):
            pilot.run_loop(max_cycles=1, sleep_fn=lambda _seconds: None,
                           clock_fn=lambda: 100.0)

        self.assertIs(observed[0], state)
        self.assertEqual(state["delivery_state_v2"], {"targets": {"factory": {}}})
        for key in (
                "processed", "automation_results_processed", "epics_processed",
                "epic_starts_processed", "poll_terminal_seen"):
            self.assertEqual(state[key], [])

    def test_fully_idle_pipeline_keeps_thirty_second_interval(self):
        self.assertEqual(pilot.next_poll_hint({"poll_seconds": 30}, []), {
            "seconds": 30, "reason": "idle",
        })

    def test_loop_uses_fast_handoff_then_idle_hint_with_fake_clock_and_sleep(self):
        conf = {"enabled": True, "poll_seconds": 30}
        state = {"processed": []}
        sleeps = []
        clock = iter((100.0, 102.0))

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "cycle", side_effect=[
                    {"seconds": 2, "reason": "handoff"},
                    {"seconds": 30, "reason": "idle"},
                ]):
            pilot.run_loop(max_cycles=2, sleep_fn=sleeps.append,
                           clock_fn=lambda: next(clock))

        self.assertEqual(sleeps, [2, 30])
        self.assertEqual(state["next_poll"], {
            "seconds": 30, "reason": "idle", "chosen_at": 102.0,
        })

    def test_network_errors_back_off_and_success_resets_interval(self):
        conf = {"enabled": True, "poll_seconds": 30}
        state = {"processed": []}
        sleeps = []

        def fake_load(path, default):
            return conf if path == pilot.CONF_PATH else state

        with mock.patch.object(pilot, "load", side_effect=fake_load), \
                mock.patch.object(pilot, "save"), \
                mock.patch.object(pilot, "cycle", side_effect=[
                    urllib.error.URLError("network down"),
                    urllib.error.URLError("network still down"),
                    {"seconds": 10, "reason": "active"},
                ]):
            pilot.run_loop(max_cycles=3, sleep_fn=sleeps.append,
                           clock_fn=iter((100.0, 130.0, 190.0)).__next__)

        self.assertEqual(sleeps, [30, 60, 10])
        self.assertEqual(state["next_poll"]["reason"], "active")

    def test_rate_limit_retry_after_never_shortens_error_backoff(self):
        error = urllib.error.HTTPError(
            "https://factory.invalid", 429, "rate limited",
            {"Retry-After": "75"}, None,
        )

        self.assertEqual(pilot.error_poll_hint(
            {"poll_seconds": 30}, 1, error), {
                "seconds": 75, "reason": "error_backoff",
            })

    def test_stopped_owner_work_does_not_select_fast_or_active_poll(self):
        conf = {"poll_seconds": 30, "stopped_pipelines": ["Пауза владельца"]}
        tasks = [{
            "id": "stopped", "state": "succeeded",
            "title": "[auto] [2/5 Specification] Пауза владельца",
        }]
        state = {}

        self.assertFalse(pilot.remember_new_terminal_tasks(conf, state, tasks))
        self.assertEqual(pilot.next_poll_hint(conf, tasks), {
            "seconds": 30, "reason": "idle",
        })
        self.assertEqual(state["poll_terminal_seen"], ["stopped"])

    def test_poll_choice_is_logged_only_when_choice_changes(self):
        state = {}
        with mock.patch.object(pilot, "log") as log:
            pilot.record_poll_hint(state, {"seconds": 10, "reason": "active"}, 1)
            pilot.record_poll_hint(state, {"seconds": 10, "reason": "active"}, 2)
            pilot.record_poll_hint(state, {"seconds": 30, "reason": "idle"}, 3)

        self.assertEqual(log.call_count, 2)
        self.assertEqual(state["next_poll"]["chosen_at"], 3)

    def _assert_overlap_wait_reuses_decision(self, next_stage, result,
                                             area_busy_results,
                                             review_gate_results=None):
        conf = {
            "stages": [
                {"workflow": "Triage"},
                {"workflow": next_stage},
            ],
            "poll_seconds": 30,
        }
        state = {"processed": []}
        completed = {
            "id": "triage-done",
            "title": "[auto] [1/2 Triage] Пересекающаяся работа",
            "state": "succeeded",
            "created_at": "2026-08-10T10:00:00Z",
            "repository_id": "repo-id",
        }
        tasks = [completed]
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path == "/tasks/triage-done":
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Triage"},
                    "context": "",
                    "attempts": [{"result": result}],
                }
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 1, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "next", "enabled": True,
                    "current_revision": {"id": "rev-next", "title": next_stage},
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "dashboard_slow", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas", "all_tasks",
        )
        verdict = {
            "action": "advance", "reason": "готово",
            "next_complexity": "medium", "handoff": "",
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_worker",
                                                  return_value="worker"))
            area_busy = stack.enter_context(mock.patch.object(
                pilot, "area_busy", side_effect=area_busy_results))
            review_gate = None
            if review_gate_results is not None:
                review_gate = stack.enter_context(mock.patch.object(
                    pilot, "review_gate", side_effect=review_gate_results))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block",
                                                  return_value=""))
            decide = stack.enter_context(mock.patch.object(
                pilot, "decide", return_value=verdict))
            stack.enter_context(mock.patch.object(
                pilot, "create_task", side_effect=lambda body, _conf:
                created.append(body) or {"task": {
                    "id": "spec-created", "title": body["title"], "state": "created",
                    "repository_id": "repo-id",
                }}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)
            pilot.cycle(conf, state)
            self.assertEqual(state["overlap_wait_decisions"], {
                "triage-done": verdict,
            })
            pilot.cycle(conf, state)

        self.assertEqual(decide.call_count, 1)
        self.assertEqual(area_busy.call_count, 3)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"],
                         f"[auto] [2/2 {next_stage}] Пересекающаяся работа")
        self.assertEqual(state["overlap_wait_decisions"], {})
        if review_gate is not None:
            self.assertEqual(review_gate.call_count, 3)

    def test_overlap_wait_reuses_decision_across_poll_cycles(self):
        self._assert_overlap_wait_reuses_decision(
            "Specification", "READY",
            ["Соседняя работа", "Соседняя работа", ""],
        )

    def test_review_gate_wait_reuses_decision_until_overlap_clears(self):
        self._assert_overlap_wait_reuses_decision(
            "Review", "BRANCH: factory/task",
            ["", "", ""],
            [{"wait": True}, {"wait": True}, None],
        )

    def test_area_wait_does_not_starve_unrelated_terminal_handoff(self):
        conf = {
            "stages": [
                {"workflow": "Implement + Test"},
                {"workflow": "Review"},
                {"workflow": "Verify"},
            ],
            "poll_seconds": 30,
            "max_terminal_tasks_per_cycle": 1,
        }
        blocked = {
            "id": "review-wait", "state": "succeeded",
            "title": "[auto] [2/3 Review] Занятая область",
            "created_at": "2026-08-10T10:00:00Z",
            "repository_id": "repo-id",
        }
        ready = {
            "id": "implement-ready", "state": "succeeded",
            "title": "[auto] [1/3 Implement + Test] Свободная работа",
            "created_at": "2026-08-10T10:01:00Z",
            "repository_id": "repo-id",
        }
        tasks = [ready, blocked]
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path in ("/tasks/review-wait", "/tasks/implement-ready"):
                task = blocked if path.endswith("review-wait") else ready
                stage = "Review" if task is blocked else "Implement + Test"
                result = "APPROVE" if task is blocked else (
                    "PASS\nBRANCH: factory/ready\n"
                    "HEAD: " + "a" * 40 + "\nPUSHED: yes"
                )
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": stage},
                    "context": "",
                    "attempts": [{"result": result}],
                }
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 2, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": stage, "enabled": True,
                    "current_revision": {"id": "rev-" + stage, "title": stage},
                } for stage in ("Review", "Verify")]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas", "all_tasks", "record_implementation_artifact",
        )
        verdict = {
            "action": "advance", "reason": "готово",
            "next_complexity": "medium", "handoff": "",
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(
                pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(
                pilot, "day_budget_blocks", return_value=False))
            stack.enter_context(mock.patch.object(
                pilot, "host_block", return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(
                pilot, "stage_worker", return_value="worker"))
            stack.enter_context(mock.patch.object(
                pilot, "work_lifecycle_block", return_value=""))
            stack.enter_context(mock.patch.object(
                pilot, "decide", return_value=verdict))
            stack.enter_context(mock.patch.object(
                pilot, "area_busy",
                side_effect=lambda _tasks, base, _context, _repo: (
                    "другая работа" if base == "Занятая область" else "")))
            stack.enter_context(mock.patch.object(
                pilot, "review_gate", return_value=None))
            stack.enter_context(mock.patch.object(
                pilot, "create_task", side_effect=lambda body, _conf:
                created.append(body) or {"task": {
                    "id": "review-created", "title": body["title"],
                    "state": "created", "repository_id": "repo-id",
                }}))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, {"processed": []})

        self.assertEqual([body["title"] for body in created], [
            "[auto] [2/3 Review] Свободная работа",
        ])

    def test_duplicate_terminal_attempts_start_one_heavy_next_stage(self):
        conf = {
            "stages": [
                {"workflow": "Specification"},
                {"workflow": "Implement + Test"},
                {"workflow": "Verify"},
            ],
            "poll_seconds": 30,
        }
        state = {"processed": []}
        tasks = [{
            "id": f"implement-{number}",
            "title": "[auto] [2/3 Implement + Test] Одна работа",
            "state": "succeeded", "created_at": f"2026-08-10T10:0{number}:00Z",
            "repository_id": "repo-id", "work_id": "one-work",
        } for number in range(2)]
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path.startswith("/tasks/implement-"):
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Implement + Test"},
                    "context": "",
                    "attempts": [{"result": "READY"}],
                }
            if path == "/tasks" and body is not None:
                task = {
                    "id": "review", "title": body["title"], "state": "created",
                    "created_at": "2026-08-10T11:00:00Z", "repository_id": "repo-id",
                }
                created.append(task)
                tasks.append(task)
                return {"task": task}
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 4, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "verify", "enabled": True,
                    "current_revision": {"id": "rev-verify", "title": "Verify"},
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_worker",
                                                  return_value="worker"))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block",
                                                  return_value=""))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)
            pilot.cycle(conf, state)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"],
                         "[auto] [3/3 Verify] Одна работа")
        self.assertEqual(state["processed"], ["implement-0", "implement-1"])

    def test_four_parallel_handoffs_create_each_next_stage_once(self):
        conf = {
            "stages": [{"workflow": "Triage"}, {"workflow": "Specification"}],
            "poll_seconds": 30,
        }
        state = {"processed": []}
        tasks = [{
            "id": f"done-{number}",
            "title": f"[auto] [1/2 Triage] Работа {number}",
            "state": "succeeded", "created_at": f"2026-08-10T10:0{number}:00Z",
            "repository_id": "repo-id",
        } for number in range(4)]
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path.startswith("/tasks/done-"):
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Triage"},
                    "context": "",
                    "attempts": [{"result": "READY"}],
                }
            if path == "/tasks" and body is not None:
                new_task = {
                    "id": f"next-{len(created)}", "title": body["title"],
                    "state": "created", "created_at": "2026-08-10T11:00:00Z",
                    "repository_id": "repo-id",
                }
                created.append(new_task)
                tasks.append(new_task)
                return {"task": new_task}
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 4, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "spec", "enabled": True,
                    "current_revision": {"id": "rev-spec", "title": "Specification"},
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_worker",
                                                  return_value="worker"))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block",
                                                  return_value=""))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            handoff_hint = pilot.cycle(conf, state)
            settled_hint = pilot.cycle(conf, state)

        self.assertEqual(handoff_hint, {"seconds": 2, "reason": "handoff"})
        self.assertEqual(settled_hint, {"seconds": 10, "reason": "active"})
        self.assertEqual(len(created), 4)
        self.assertEqual(len({task["title"] for task in created}), 4)

    def test_terminal_backlog_is_bounded_to_four_decisions_per_cycle(self):
        conf = {
            "stages": [{"workflow": "Triage"}, {"workflow": "Specification"}],
            "poll_seconds": 30,
            "max_parallel_works": 10,
        }
        state = {"processed": []}
        tasks = [{
            "id": f"done-{number}",
            "title": f"[auto] [1/2 Triage] Work {number}",
            "state": "succeeded", "created_at": f"2026-08-10T10:0{number}:00Z",
            "repository_id": "repo-id",
        } for number in range(6)]
        created = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path.startswith("/tasks/done-"):
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": "Triage"},
                    "context": "",
                    "attempts": [{"result": "READY"}],
                }
            if path == "/tasks" and body is not None:
                new_task = {
                    "id": f"next-{len(created)}", "title": body["title"],
                    "state": "created", "created_at": "2026-08-10T11:00:00Z",
                    "repository_id": "repo-id",
                }
                created.append(new_task)
                tasks.append(new_task)
                return {"task": new_task}
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 10, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [{
                    "id": "spec", "enabled": True,
                    "current_revision": {"id": "rev-spec", "title": "Specification"},
                }]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_worker",
                                                  return_value="worker"))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block",
                                                  return_value=""))
            decide = stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            refill = stack.enter_context(mock.patch.object(
                pilot, "refill_open_work_slots", return_value=0))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            hint = pilot.cycle(conf, state)

        self.assertEqual(hint, {"seconds": 2, "reason": "handoff"})
        self.assertEqual(decide.call_count, 4)
        self.assertEqual(len(created), 4)
        self.assertEqual(len(state["processed"]), 4)
        refill.assert_called_once()
        self.assertFalse(refill.call_args.kwargs["admit_new_plan"])

    def test_deferred_terminal_handoff_does_not_starve_next_terminal(self):
        conf = {
            "stages": [
                {"workflow": "Triage"},
                {"workflow": "Specification"},
                {"workflow": "Implement + Test"},
            ],
            "poll_seconds": 30,
        }
        state = {"processed": []}
        tasks = [
            {
                "id": "triage-done",
                "title": "[auto] [1/3 Triage] Earlier stage",
                "state": "succeeded", "created_at": "2026-08-10T10:01:00Z",
                "repository_id": "repo-id",
            },
            {
                "id": "spec-done",
                "title": "[auto] [2/3 Specification] Later stage",
                "state": "succeeded", "created_at": "2026-08-10T10:00:00Z",
                "repository_id": "repo-id",
            },
        ]
        details_read = []

        def fake_api(path, body=None):
            if path == "/tasks?limit=100":
                return {"tasks": list(tasks)}
            if path in ("/tasks/triage-done", "/tasks/spec-done"):
                details_read.append(path)
                stage = "Specification" if path.endswith("spec-done") else "Triage"
                return {
                    "task": {"repository_id": "repo-id"},
                    "workflow": {"title": stage},
                    "context": "",
                    "attempts": [{"result": "READY"}],
                }
            if path == "/workers":
                return {"workers": [{
                    "id": "worker-id", "name": "worker", "online": True,
                    "health": "healthy", "capacity": 4, "active_count": 0,
                }]}
            if path == "/repositories":
                return {"repositories": [{
                    "id": "repo-id", "remote_identity": "github.com/acme/repo",
                }]}
            if path == "/workflows":
                return {"workflows": [
                    {
                        "id": "spec", "enabled": True,
                        "current_revision": {
                            "id": "rev-spec", "title": "Specification",
                        },
                    },
                    {
                        "id": "implement", "enabled": True,
                        "current_revision": {
                            "id": "rev-implement", "title": "Implement + Test",
                        },
                    },
                ]}
            raise AssertionError(path)

        noops = (
            "collect_automation_findings", "cleanup_completed_plan_cards",
            "write_dashboard", "provider_limits_tick", "detect_limits",
            "record_new_works", "budget_guard", "money_guard", "handle_epics",
            "reconcile_diag_repairs", "diag_sweep", "rescue_queued",
            "supersede_stale_questions", "cleanup_orphaned_paused_pipelines",
            "handle_answers", "advance_epics", "pipeline_watch",
            "retry_pending_factory_deploy", "autostart_plan", "area_extend",
            "collect_ideas",
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            stack.enter_context(mock.patch.object(pilot, "codex_usage_snapshot",
                side_effect=lambda day_start, _week_start: {day_start: {}}))
            stack.enter_context(mock.patch.object(pilot, "day_budget_blocks",
                                                  return_value=False))
            stack.enter_context(mock.patch.object(pilot, "host_block",
                                                  return_value={"state": "ok"}))
            stack.enter_context(mock.patch.object(pilot, "stage_worker",
                                                  return_value="worker"))
            stack.enter_context(mock.patch.object(pilot, "area_busy", return_value=""))
            stack.enter_context(mock.patch.object(pilot, "work_lifecycle_block",
                                                  return_value=""))
            stack.enter_context(mock.patch.object(pilot, "decide", return_value={
                "action": "advance", "next_complexity": "medium", "handoff": "",
            }))
            stack.enter_context(mock.patch.object(
                pilot, "create_child_task",
                side_effect=pilot.ParallelWorkLimit("parallel_work_limit")))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))

            pilot.cycle(conf, state)

        self.assertEqual(details_read, ["/tasks/spec-done", "/tasks/triage-done"])
        self.assertEqual(state["terminal_cursor"], "triage-done")


class BudgetGuardTests(unittest.TestCase):
    def test_branch_head_rejects_malicious_branch_without_running_command(self):
        """BRANCH из отчёта не может превратиться в запуск команды."""
        with mock.patch.object(pilot, "_fixed_command") as command:
            head = pilot.branch_head("factory/valid; touch /tmp/pilot-owned")

        self.assertEqual(head, "")
        command.assert_not_called()

    def test_branch_head_uses_validated_branch_as_argv(self):
        expected = "a" * 40
        with mock.patch.object(pilot, "_fixed_command", return_value=(True, expected)) as command:
            head = pilot.branch_head("factory/valid-branch")

        self.assertEqual(head, expected)
        command.assert_called_once_with(
            ["sudo", "-n", "/usr/local/bin/fx", "repo", "head", "factory/valid-branch"])

    def test_unchanged_branch_downgrades_on_first_overrun(self):
        """Первый перерасход не получает продления за старый коммит ветки."""
        task = {
            "id": "run-1", "state": "running", "worker_id": "worker-1",
            "title": "[auto] [3/5 Implement + Test] Неизменная работа",
        }
        workers = [{"id": "worker-1", "name": "terra-worker"}]
        budget = {}
        saved = []

        def fake_api(path, body=None):
            if path == "/tasks/run-1/cancel":
                return {}
            if path == "/tasks/run-1":
                return {"task": {"repository_id": "repo-1"}}
            raise AssertionError(path)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "load", return_value=budget))
            stack.enter_context(mock.patch.object(pilot, "save",
                side_effect=lambda path, value: saved.append((path, value.copy()))))
            stack.enter_context(mock.patch.object(pilot, "branch_from_history",
                return_value="factory/unchanged"))
            stack.enter_context(mock.patch.object(pilot, "branch_head",
                return_value="a" * 40))
            stack.enter_context(mock.patch.object(pilot, "attempts_of", return_value=[]))
            cost = stack.enter_context(mock.patch.object(pilot, "task_cost_usd",
                side_effect=[0.0, 8.0]))
            stack.enter_context(mock.patch.object(pilot, "work_spent", return_value=8.0))
            stack.enter_context(mock.patch.object(pilot, "api", side_effect=fake_api))
            retry = stack.enter_context(mock.patch.object(pilot, "write_budget_retry"))
            stack.enter_context(mock.patch.object(pilot, "notify"))

            pilot.budget_guard({}, [task], workers)
            pilot.budget_guard({}, [task], workers)

        self.assertEqual(budget["Неизменная работа"]["last_head"], "a" * 40)
        self.assertEqual(budget["Неизменная работа"]["extensions"], 0)
        self.assertEqual(budget["Неизменная работа"]["downgrades"], 1)
        self.assertEqual(cost.call_count, 2)
        retry.assert_called_once()
        self.assertTrue(saved)

    def test_new_commit_still_earns_an_extension(self):
        task = {
            "id": "run-1", "state": "running", "worker_id": "worker-1",
            "title": "[auto] [3/5 Implement + Test] Движущаяся работа",
        }
        budget = {"Движущаяся работа": {
            "extensions": 0, "downgrades": 0, "last_head": "a" * 40,
            "stopped": "",
        }}

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pilot, "load", return_value=budget))
            stack.enter_context(mock.patch.object(pilot, "save"))
            stack.enter_context(mock.patch.object(pilot, "branch_from_history",
                return_value="factory/moving"))
            stack.enter_context(mock.patch.object(pilot, "branch_head",
                return_value="b" * 40))
            stack.enter_context(mock.patch.object(pilot, "attempts_of", return_value=[]))
            stack.enter_context(mock.patch.object(pilot, "task_cost_usd", return_value=8.0))
            stack.enter_context(mock.patch.object(pilot, "work_spent", return_value=8.0))
            retry = stack.enter_context(mock.patch.object(pilot, "write_budget_retry"))

            pilot.budget_guard({}, [task], [{"id": "worker-1", "name": "terra"}])

        self.assertEqual(budget["Движущаяся работа"]["extensions"], 1)
        self.assertEqual(budget["Движущаяся работа"]["last_head"], "b" * 40)
        retry.assert_not_called()


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
                    [{"id": state, "work_id": "work-1", "state": state}],
                    "Verify", self.cpu_over))

    def test_handoffs_for_one_work_share_one_reservation(self):
        tasks = [
            {"id": "implement", "work_id": "work-1", "state": "running"},
            {"id": "verify", "work_id": "work-1", "state": "created"},
        ]

        self.assertFalse(pilot.host_load_admits(
            tasks, "Implement + Test", self.cpu_over))

    def test_equally_named_works_keep_independent_reservations(self):
        tasks = [
            {"id": "first", "work_id": "work-1", "state": "running",
             "title": "[auto] [3/5 Implement + Test] Одинаковое имя"},
            {"id": "second", "work_id": "work-2", "state": "running",
             "title": "[auto] [3/5 Implement + Test] Одинаковое имя"},
        ]

        self.assertEqual(pilot.active_auto_works(tasks), {"work-1", "work-2"})
        self.assertFalse(pilot.host_load_admits(
            tasks, "Verify", self.cpu_over))

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
        self.assertEqual(conf["_host_load_tasks"][0]["work_id"], "one")

    def test_finished_work_releases_reservation_on_fresh_snapshot(self):
        finished = [{"id": "one", "work_id": "work-1", "state": "succeeded"}]

        self.assertTrue(pilot.host_load_admits(
            finished, "Implement + Test", self.cpu_over))

    @mock.patch.object(pilot, "load_questions", return_value=[])
    @mock.patch.object(pilot, "money_guard")
    @mock.patch.object(pilot, "api")
    def test_all_handoffs_share_the_four_work_limit(self, api, _money, _questions):
        api.side_effect = [
            {"task": {"id": f"task-{index}"}} for index in range(4)
        ]
        conf = {"max_parallel_works": 4, "_active_work_tasks": []}

        for index in range(4):
            pilot.create_task({
                "title": f"[auto] [2/5 Specification] Work {index}",
            }, conf)

        with self.assertRaisesRegex(pilot.ParallelWorkLimit,
                                    "parallel_work_limit"):
            pilot.create_task({
                "title": "[auto] [2/5 Specification] Work 5",
            }, conf)

        self.assertEqual(api.call_count, 4)
        self.assertEqual(len(pilot.active_auto_works(
            conf["_active_work_tasks"])), 4)

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

        watch.assert_called_once_with(conf, [], {}, {})
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


@unittest.skip("superseded by delivery_state_v2")
class PostMergeDeployTest(unittest.TestCase):
    @mock.patch.object(pilot.subprocess, "Popen")
    @mock.patch.object(pilot, "log")
    def test_release_is_started_in_background_and_saved_for_next_cycle(self, log, popen):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        popen.return_value.pid = 123
        state = {}
        state_path = os.path.join(temporary.name, "state.json")
        with mock.patch.object(pilot, "DEPLOY_DIR", temporary.name), \
                mock.patch.object(pilot, "STATE_PATH", state_path):
            pilot.deploy_after_merge({"deploy_factory_cmd": "fx factory release"},
                                     "github.com/timafen/factory", state)

        release = state[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]
        self.assertEqual(release["pid"], 123)
        self.assertEqual(release["generation"], 1)
        self.assertTrue(release["status"].endswith(".status"))
        self.assertIn("started generation=1", log.call_args.args[0])
        self.assertIn("fx factory release", popen.call_args.args[0])
        self.assertEqual(pilot.load(state_path, {}), state)

    @mock.patch.object(pilot.subprocess, "Popen")
    @mock.patch.object(pilot, "log")
    def test_restart_from_state_file_resumes_release_saved_before_process_start(self, _log, popen):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state_path = os.path.join(temporary.name, "state.json")
        conf = {"deploy_factory_cmd": "fx factory release"}

        def stop_pilot(*_args, **_kwargs):
            saved = pilot.load(state_path, {})
            release = saved[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]
            self.assertTrue(release["queued"])
            self.assertNotIn("pid", release)
            raise SystemExit("Pilot stopped after durable reservation")

        popen.side_effect = stop_pilot
        with mock.patch.object(pilot, "DEPLOY_DIR", temporary.name), \
                mock.patch.object(pilot, "STATE_PATH", state_path):
            with self.assertRaises(SystemExit):
                pilot.deploy_after_merge(conf, "github.com/timafen/factory", {})

            restored = pilot.load(state_path, {})
            popen.side_effect = None
            popen.return_value.pid = 456
            pilot.poll_post_merge_deploys(conf, restored)

        release = restored[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]
        self.assertEqual(release["pid"], 456)
        self.assertFalse(release["queued"])
        self.assertEqual(pilot.load(state_path, {}), restored)

    @mock.patch.object(pilot, "log")
    def test_completed_release_logs_exit_code_and_output(self, log):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        status = os.path.join(temporary.name, "done.status")
        output = os.path.join(temporary.name, "done.log")
        with open(status, "w", encoding="utf-8") as f:
            f.write("7\n")
        with open(output, "w", encoding="utf-8") as f:
            f.write("health check failed — возвращаю предыдущие сервер и воркер\n")
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "generation": 3, "status": status, "output": output, "queued": False}}}

        events = os.path.join(temporary.name, "release-events.jsonl")
        with mock.patch.object(pilot, "RELEASE_EVENTS_PATH", events):
            pilot.poll_post_merge_deploys({"deploy_factory_cmd": "fx factory release"}, state)

        self.assertNotIn("deploy_factory_cmd", state[pilot.DEPLOY_STATE_KEY])
        self.assertIn("completed generation=3 rc=7 :: " +
                      pilot.RELEASE_DIAGNOSTICS_OMITTED,
                      log.call_args.args[0])
        with open(events, encoding="utf-8") as event_file:
            recorded = [json.loads(line) for line in event_file]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["id"], "deploy_factory_cmd:3")
        self.assertEqual(recorded[0]["kind"], "failed_release")
        self.assertTrue(recorded[0]["rollback"])

        # Re-observing a durable status after a restart cannot double-count it.
        state[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"] = {
            "generation": 3, "status": status, "output": output, "queued": False}
        with mock.patch.object(pilot, "RELEASE_EVENTS_PATH", events):
            pilot.poll_post_merge_deploys({"deploy_factory_cmd": "fx factory release"}, state)
        with open(events, encoding="utf-8") as event_file:
            self.assertEqual(len(event_file.readlines()), 1)

    @mock.patch.object(pilot, "log")
    def test_completed_release_keeps_only_allowlisted_diagnostics(self, log):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        status = os.path.join(temporary.name, "failed.status")
        output = os.path.join(temporary.name, "failed.log")
        with open(status, "w", encoding="utf-8") as f:
            f.write("7\n")
        with open(output, "w", encoding="utf-8") as f:
            f.write("build output " + ("x" * 400) + "\n")
            f.write("Chromium sandbox smoke failed: No usable sandbox\n")
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "generation": 4, "status": status, "output": output, "queued": False}}}

        pilot.poll_post_merge_deploys({"deploy_factory_cmd": "fx factory release"}, state)

        message = log.call_args.args[0]
        self.assertIn("Chromium sandbox smoke failed: No usable sandbox", message)
        self.assertNotIn("build output", message)

    def test_release_output_rejects_adversarial_secret_lines(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = os.path.join(temporary.name, "failed.log")
        secrets = {
            "aws": "AWS_SECRET_ACCESS_KEY=aws-secret-value",
            "client_secret": "client_secret=oauth-secret-value",
            "url_credentials": "postgres://dbuser:dbpass@db.example/factory",
            "cookie": "Cookie: factory_session=cookie-secret-value",
            "session": "session=session-secret-value",
        }
        with open(output, "w", encoding="utf-8") as f:
            f.write("Chromium sandbox smoke failed: No usable sandbox\n")
            for secret in secrets.values():
                f.write(secret + "\n")
                f.write("Chromium sandbox smoke failed: No usable sandbox " + secret + "\n")

        result = pilot._release_output({"output": output})

        self.assertEqual(result, "Chromium sandbox smoke failed: No usable sandbox")
        for label, secret in secrets.items():
            with self.subTest(label=label):
                self.assertNotIn(secret, result)

    @mock.patch.object(pilot.subprocess, "Popen")
    @mock.patch.object(pilot, "log")
    def test_external_release_lock_is_saved_then_retried_after_delay(self, _log, popen):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state_path = os.path.join(temporary.name, "state.json")
        status = os.path.join(temporary.name, "external-lock.status")
        with open(status, "w", encoding="utf-8") as f:
            f.write("8\n")
        popen.return_value.pid = 789
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "generation": 1, "status": status, "output": "/missing", "queued": False}}}
        conf = {"deploy_factory_cmd": "fx factory release"}

        with mock.patch.object(pilot, "DEPLOY_DIR", temporary.name), \
                mock.patch.object(pilot, "STATE_PATH", state_path):
            pilot.poll_post_merge_deploys(conf, state, now=100)
            deferred = state[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]
            self.assertTrue(deferred["queued"])
            self.assertEqual(deferred["due"], 160)
            self.assertNotIn("pid", deferred)
            self.assertEqual(pilot.load(state_path, {}), state)

            pilot.poll_post_merge_deploys(conf, state, now=159)
            popen.assert_not_called()
            pilot.poll_post_merge_deploys(conf, state, now=160)

        release = state[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]
        self.assertEqual(release["pid"], 789)
        self.assertFalse(release["queued"])
        popen.assert_called_once()

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_trading_repository_releases_only_trading_staging(self, log, start):
        conf = {
            "deploy_staging_cmd": "fx staging release",
            "deploy_factory_cmd": "fx factory release",
        }

        result = pilot.deploy_after_merge(conf, "github.com/timafen/tarser-operations", {})

        self.assertIsNone(result)
        start.assert_called_once_with("deploy_staging_cmd", "AUTOMATION-STAGING-DEPLOY",
                                      "fx staging release", mock.ANY)

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_factory_repository_never_releases_trading_staging(self, log, start):
        conf = {"deploy_staging_cmd": "fx staging release"}

        result = pilot.deploy_after_merge(conf, "github.com/timafen/factory")

        self.assertIsNone(result)
        start.assert_not_called()
        self.assertIn("deploy_factory_cmd is not configured", log.call_args.args[0])

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_factory_repository_uses_its_own_release_command(self, _log, start):
        conf = {
            "deploy_staging_cmd": "fx staging release",
            "deploy_factory_cmd": "fx factory release",
        }

        result = pilot.deploy_after_merge(conf, "github.com/timafen/factory.git", {})

        self.assertIsNone(result)
        start.assert_called_once_with("deploy_factory_cmd", "FACTORY-DEPLOY",
                                      "fx factory release", mock.ANY)

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    @mock.patch.object(pilot, "save")
    def test_busy_factory_release_is_coalesced_for_retry(self, save, _log, start):
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "generation": 1, "pid": 42, "queued": False}}}
        conf = {"deploy_factory_cmd": "fx factory release"}

        pilot.deploy_after_merge(
            conf, "github.com/timafen/factory", state, now=110)

        self.assertTrue(state[pilot.DEPLOY_STATE_KEY]["deploy_factory_cmd"]["queued"])
        save.assert_called_once_with(pilot.STATE_PATH, state)
        start.assert_not_called()

    @mock.patch.object(pilot, "_release_running", return_value=True)
    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_restart_keeps_running_release_until_durable_status(self, _log, start, _running):
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "pid": 42, "generation": 2, "status": "/not-yet", "queued": False}}}
        conf = {"deploy_factory_cmd": "fx factory release"}

        pilot.poll_post_merge_deploys(conf, state)

        start.assert_not_called()
        self.assertIn("deploy_factory_cmd", state[pilot.DEPLOY_STATE_KEY])

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_completed_release_starts_one_coalesced_successor(self, _log, start):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        status = os.path.join(temporary.name, "done")
        with open(status, "w", encoding="utf-8") as f:
            f.write("0\n")
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "generation": 1, "status": status, "queued": True, "output": "/missing"}}}

        pilot.poll_post_merge_deploys({"deploy_factory_cmd": "fx factory release"}, state)

        start.assert_called_once_with("deploy_factory_cmd", "FACTORY-DEPLOY",
                                      "fx factory release", mock.ANY)

    @mock.patch.object(pilot, "_start_post_merge_deploy")
    @mock.patch.object(pilot, "log")
    def test_lost_release_after_restart_is_restarted(self, _log, start):
        state = {pilot.DEPLOY_STATE_KEY: {"deploy_factory_cmd": {
            "pid": 999999, "generation": 1, "status": "/not-yet", "queued": False}}}

        pilot.poll_post_merge_deploys({"deploy_factory_cmd": "fx factory release"}, state)

        start.assert_called_once_with("deploy_factory_cmd", "FACTORY-DEPLOY",
                                      "fx factory release", mock.ANY)


class MergeReleaseDeliveryStateMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.broker_build = tempfile.TemporaryDirectory()
        cls.broker_executable = os.path.join(cls.broker_build.name, "factory-release-broker")
        subprocess.run(["go", "build", "-o", cls.broker_executable,
                        "./cmd/factory-release-broker"], check=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))

    @classmethod
    def tearDownClass(cls):
        cls.broker_build.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.broker_processes = {}
        self.state_path = os.path.join(self.temporary.name, "state.json")
        self.receipts = os.path.join(self.temporary.name, "receipts.jsonl")
        self.outbox = os.path.join(self.temporary.name, "outbox.jsonl")
        self.sha = "a" * 40

    def wait(self, task="verify-1"):
        return {"task_id": task, "base": "Единый выпуск", "link": "",
                "merge_receipt": {"task_id": task, "base": "Единый выпуск"}}

    def _stop_process(self, process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _start_process_broker(self, locked=False, outcome="succeeded"):
        """Run the real Go Unix broker against a blocking physical FX fixture."""
        socket_path = os.path.join(self.temporary.name, uuid.uuid4().hex + ".sock")
        state_dir = os.path.join(self.temporary.name, uuid.uuid4().hex + "-broker")
        fx = os.path.join(self.temporary.name, uuid.uuid4().hex + "-fx")
        attempts = fx + ".attempts"
        success = fx + ".success"
        started = fx + ".started"
        pid = fx + ".pid"
        release_gate = fx + ".release"
        lock_once = fx + ".lock-once"
        acceptance = fx + ".acceptance"
        with open(fx, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nset -eu\n"
                         "printf '%s\\n' \"$FACTORY_DELIVERY_ID\" >> \"" + attempts + "\"\n"
                         "if [ -f \"" + lock_once + "\" ]; then rm -f \"" + lock_once + "\"; exit 8; fi\n"
                         "printf '%s\\n' \"$$\" > \"" + pid + "\"\n"
                         ": > \"" + started + "\"\n"
                         "while [ ! -f \"" + release_gate + "\" ]; do sleep 0.01; done\n"
                         "case \"" + outcome + "\" in\n"
                         "  succeeded) printf '%s\\n' \"$FACTORY_DELIVERY_ID\" >> \"" + success + "\"; exit 0 ;;\n"
                         "  rollback_failed) exit 1 ;;\n"
                         "  *) exit 7 ;;\n"
                         "esac\n")
        os.chmod(fx, 0o700)
        with open(acceptance, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nprintf '%s\\n' '{\"status\":\"passed\"}'\n")
        os.chmod(acceptance, 0o700)
        if locked:
            with open(lock_once, "w", encoding="utf-8") as stream:
                stream.write("locked once\n")
        broker = subprocess.Popen([self.broker_executable, "-socket", socket_path,
                                   "-state-dir", state_dir, "-factory-release-executable", fx,
                                   "-live-acceptance-executable", acceptance],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.broker_processes[socket_path] = broker
        self.addCleanup(self._stop_process, broker)
        for _ in range(100):
            if os.path.exists(socket_path):
                return {"socket": socket_path, "broker_state": state_dir,
                        "fx": fx, "acceptance": acceptance,
                        "attempts": attempts, "success": success, "fx_started": started,
                        "fx_pid": pid, "release_gate": release_gate}
            if broker.poll() is not None:
                self.fail("built release broker stopped before opening its Unix socket")
            time.sleep(.02)
        self.fail("built release broker did not open its Unix socket")

    def _restart_process_broker(self, paths):
        """Replace a stopped broker while retaining its durable state and FX."""
        process = subprocess.Popen([self.broker_executable, "-socket", paths["socket"],
                                    "-state-dir", paths["broker_state"],
                                    "-factory-release-executable", paths["fx"],
                                    "-live-acceptance-executable", paths["acceptance"]],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.broker_processes[paths["socket"]] = process
        self.addCleanup(self._stop_process, process)
        for _ in range(100):
            if os.path.exists(paths["socket"]):
                return process
            if process.poll() is not None:
                self.fail("restarted release broker stopped before opening its Unix socket")
            time.sleep(.02)
        self.fail("restarted release broker did not open its Unix socket")

    def _pilot_process(self, action, paths, boundary="", now=0, sha=""):
        """Run or abruptly stop an independent real Pilot interpreter."""
        invocation = {"action": action, "boundary": boundary, "now": now, "sha": sha,
                      **paths}
        config = os.path.join(self.temporary.name, uuid.uuid4().hex + ".json")
        with open(config, "w", encoding="utf-8") as stream:
            json.dump(invocation, stream)
        script = r'''
import json, os, sys, time
from pilot import pilot
d = json.load(open(sys.argv[1], encoding="utf-8"))
for name, key in (("STATE_PATH", "state"), ("MERGES_PATH", "merges"),
                  ("DELIVERY_RECEIPTS_PATH", "receipts"), ("DELIVERY_OUTBOX_PATH", "outbox"),
                  ("NOTIFY_LOG_PATH", "notifications")):
    setattr(pilot, name, d[key])
def event(name, *values):
    with open(d["events"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps([name, *values]) + "\n")
def generation(state):
    target = state.get(pilot.DELIVERY_STATE_KEY, {}).get("targets", {}).get("factory", {})
    return target.get("generations", {}).get(target.get("current_generation"), {})
original_save = pilot.save
def save_then_crash(path, state):
    original_save(path, state)
    if d["action"] != "crash":
        return
    phase = generation(state).get("phase")
    boundary = d["boundary"]
    if ((boundary in ("post", "wrapper_status") and phase == "launching") or
            (boundary == "running" and phase == "running") or
            (boundary == "terminal" and phase == "completed")):
        event("crash", boundary, phase)
        os._exit(0)
pilot.save = save_then_crash
pilot.mark_final = lambda *args: event("mark_final", *args)
pilot.notify = lambda _conf, title, *_args, **_kw: event("owner_done", title)
conf = {"release_broker_socket": d["socket"]}
def wait(task, sha):
    return {"task_id": task, "base": "Единый выпуск", "link": "",
            "merge_receipt": {"task_id": task, "base": "Единый выпуск", "sha": sha}}
state = pilot.load(pilot.STATE_PATH, {})
if not generation(state):
    intent = {"phase": "merged", "base": "Единый выпуск", "branch": "topic",
              "repository": "github.com/timafen/factory", "commit_sha": d["sha"], "link": ""}
    state = {"merge_intents": {"verify-1": intent}}
    pilot.save(pilot.STATE_PATH, state)
    pilot.recover_merge_intents(conf, state)
if d["action"] == "seed":
    raise SystemExit(0)
if d["action"] == "join":
    pilot.deploy_after_merge(conf, "github.com/timafen/factory", state, d["sha"], wait("verify-2", d["sha"]))
    raise SystemExit(0)
pilot.recover_merge_intents(conf, state)
if d["action"] == "poll_once":
    pilot.poll_delivery_state(conf, state, now=d["now"])
    pilot.save(pilot.STATE_PATH, state)
    raise SystemExit(0)
if d["action"] == "recover":
    with open(d["release_gate"], "w", encoding="utf-8"):
        pass
if d["action"] == "crash" and d["boundary"] == "pid":
    pilot.poll_delivery_state(conf, state, now=d["now"])
    operation = generation(state)
    path = os.path.join(d["broker_state"], operation["id"] + ".json")
    for _ in range(250):
        try:
            with open(path, encoding="utf-8") as stream:
                if json.load(stream).get("pid"):
                    event("crash", "pid", operation["id"])
                    os._exit(0)
        except (OSError, ValueError):
            pass
        time.sleep(.02)
    raise SystemExit("physical FX PID was not persisted")
released = d["action"] == "recover"
for _ in range(250):
    pilot.poll_delivery_state(conf, state, now=d["now"])
    phase = generation(state).get("phase")
    if d["action"] == "crash" and d["boundary"] == "terminal" and phase == "running" and not released:
        with open(d["release_gate"], "w", encoding="utf-8"):
            pass
        released = True
    if d["action"] != "crash" and phase in ("completed", "failed", "reserved"):
        break
    time.sleep(.02)
if d["action"] == "crash":
    raise SystemExit("crash boundary was not reached: " + d["boundary"])
pilot.save(pilot.STATE_PATH, state)
'''
        subprocess.run([sys.executable, "-c", script, config], check=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)))

    def _process_paths(self, broker):
        prefix = os.path.join(self.temporary.name, uuid.uuid4().hex)
        return {**broker, "state": prefix + ".state.json", "merges": prefix + ".merges.jsonl",
                "receipts": prefix + ".receipts.jsonl", "outbox": prefix + ".outbox.jsonl",
                "notifications": prefix + ".notifications.jsonl", "events": prefix + ".events.jsonl"}

    def _events(self, path, name):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if json.loads(line)[0] == name]

    def _read_json(self, path):
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def test_state_file_crash_boundaries_recover_in_fresh_pilot_processes(self):
        boundaries = ("post", "wrapper_status", "pid", "running", "terminal")
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                paths = self._process_paths(self._start_process_broker())
                # The subprocess calls production recovery/polling and exits
                # with os._exit immediately after its actual durable boundary.
                self._pilot_process("crash", paths, boundary, sha=self.sha)
                self.assertEqual(len(self._events(paths["events"], "crash")), 1)
                crashed = self._read_json(paths["state"])
                crashed_target = crashed[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
                crashed_generation = crashed_target["generations"][crashed_target["current_generation"]]
                if boundary in ("post", "wrapper_status"):
                    self.assertEqual(crashed_generation["phase"], "launching")
                elif boundary == "running":
                    self.assertEqual(crashed_generation["phase"], "running")
                elif boundary == "terminal":
                    self.assertEqual(crashed_generation["phase"], "completed")
                    self.assertFalse(os.path.exists(paths["receipts"]))
                    self.assertFalse(os.path.exists(paths["outbox"]))
                    self.assertEqual(self._events(paths["events"], "mark_final"), [])
                    self.assertEqual(self._events(paths["events"], "owner_done"), [])
                else:
                    broker_before_recovery = self._read_json(os.path.join(
                        paths["broker_state"], crashed_generation["id"] + ".json"))
                    self.assertGreater(broker_before_recovery.get("pid", 0), 0)
                self._pilot_process("recover", paths, boundary, sha=self.sha)
                state = self._read_json(paths["state"])
                target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
                generation = target["generations"][target["current_generation"]]
                broker_state = self._read_json(os.path.join(paths["broker_state"], generation["id"] + ".json"))
                with open(paths["attempts"], encoding="utf-8") as stream:
                    physical = [line.strip() for line in stream if line.strip()]
                self.assertEqual(broker_state["posts"], 1)
                self.assertGreater(broker_state.get("pid", 0), 0)
                self.assertEqual(physical, [generation["id"]])
                with open(paths["success"], encoding="utf-8") as stream:
                    self.assertEqual([line.strip() for line in stream if line.strip()], [generation["id"]])
                self.assertEqual(len(self._events(paths["events"], "mark_final")), 1)
                self.assertEqual(len(self._events(paths["events"], "owner_done")), 1)
                with open(paths["receipts"], encoding="utf-8") as stream:
                    self.assertEqual(len(stream.readlines()), 1)
                with open(paths["outbox"], encoding="utf-8") as stream:
                    self.assertEqual(len(stream.readlines()), 1)
                self.assertEqual(generation["phase"], "completed")
                self.assertEqual(generation["waits"]["verify-1"]["task_id"], "verify-1")

    def test_real_rollback_failure_never_completes_waits(self):
        paths = self._process_paths(self._start_process_broker(outcome="rollback_failed"))
        self._pilot_process("seed", paths, sha=self.sha)
        self._pilot_process("recover", paths, sha=self.sha)
        state = self._read_json(paths["state"])
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        generation = target["generations"][target["current_generation"]]
        broker_state = self._read_json(os.path.join(paths["broker_state"], generation["id"] + ".json"))
        self.assertEqual(broker_state["status"], "rollback_failed")
        self.assertEqual(generation["phase"], "failed")
        self.assertFalse(os.path.exists(paths["receipts"]))
        with open(paths["outbox"], encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 1)
        self.assertEqual(self._events(paths["events"], "mark_final"), [])
        self.assertEqual(len(self._events(paths["events"], "owner_done")), 1)

    def test_terminal_write_failure_survives_real_broker_restart_without_false_done(self):
        paths = self._process_paths(self._start_process_broker())
        self._pilot_process("seed", paths, sha=self.sha)
        self._pilot_process("poll_once", paths, sha=self.sha)
        for _ in range(250):
            if os.path.exists(paths["fx_started"]):
                break
            time.sleep(.02)
        else:
            self.fail("physical FX did not start")

        # Hold the physical command at its gate until the broker has durably
        # recorded the running state.  Corrupting the state directory before
        # this point tests a startup-write failure instead and legitimately
        # lets the broker terminate the child, which made this terminal-write
        # scenario depend on process scheduling.
        state = self._read_json(paths["state"])
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        operation_id = target["current_generation"]
        broker_path = os.path.join(paths["broker_state"], operation_id + ".json")
        for _ in range(750):
            try:
                if self._read_json(broker_path).get("status") == "running":
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.02)
        else:
            self.fail("broker did not durably record the running delivery")

        saved_state = paths["broker_state"] + ".saved"
        os.rename(paths["broker_state"], saved_state)
        with open(paths["broker_state"], "w", encoding="utf-8") as stream:
            stream.write("injected terminal write failure\n")
        with open(paths["release_gate"], "w", encoding="utf-8"):
            pass
        for _ in range(250):
            if os.path.exists(paths["success"]):
                break
            time.sleep(.02)
        else:
            self.fail("physical delivery did not finish")

        # The live broker must retain its last durable, non-terminal view.  A
        # Pilot process therefore cannot create completion artifacts.
        self._pilot_process("poll_once", paths, sha=self.sha)
        state = self._read_json(paths["state"])
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        generation = target["generations"][target["current_generation"]]
        # Both accepted broker states are durable and non-terminal.  Under
        # load the physical command can finish before the broker's launching
        # record advances to running; neither state may create completion
        # receipts, which is the invariant exercised below.
        self.assertIn(generation["phase"], ("launching", "running"))
        self.assertFalse(os.path.exists(paths["receipts"]))
        self.assertFalse(os.path.exists(paths["outbox"]))
        self.assertEqual(self._events(paths["events"], "mark_final"), [])
        self.assertEqual(self._events(paths["events"], "owner_done"), [])

        old_broker = self.broker_processes[paths["socket"]]
        self._stop_process(old_broker)
        os.remove(paths["broker_state"])
        os.rename(saved_state, paths["broker_state"])
        self._restart_process_broker(paths)
        self._pilot_process("recover", paths, sha=self.sha)

        state = self._read_json(paths["state"])
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        generation = target["generations"][target["current_generation"]]
        broker_state = self._read_json(os.path.join(
            paths["broker_state"], generation["id"] + ".json"))
        with open(paths["attempts"], encoding="utf-8") as stream:
            attempts = [line.strip() for line in stream if line.strip()]
        with open(paths["success"], encoding="utf-8") as stream:
            successful = [line.strip() for line in stream if line.strip()]
        self.assertEqual(generation["phase"], "failed")
        self.assertEqual(broker_state["status"], "failed")
        self.assertEqual(attempts, [generation["id"]])
        self.assertEqual(successful, [generation["id"]])
        self.assertFalse(os.path.exists(paths["receipts"]))
        with open(paths["outbox"], encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 1)
        self.assertEqual(self._events(paths["events"], "mark_final"), [])
        self.assertEqual(len(self._events(paths["events"], "owner_done")), 1)

    def test_failed_broker_terminal_never_completes_waits(self):
        state = {}
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", self.receipts), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", self.outbox), \
                mock.patch.object(pilot, "NOTIFY_LOG_PATH", os.path.join(self.temporary.name, "notifications.jsonl")), \
                mock.patch.object(pilot, "broker_operation", return_value={"status": "failed"}), \
                mock.patch.object(pilot, "mark_final") as mark_final, \
                mock.patch.object(pilot, "notify") as owner_done:
            pilot.deploy_after_merge({}, "github.com/timafen/factory", state, self.sha, self.wait())
            pilot.poll_delivery_state({}, state)
            pilot.poll_delivery_state({}, pilot.load(self.state_path, {}))
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        generation = target["generations"][target["current_generation"]]
        self.assertEqual(generation["phase"], "failed")
        self.assertFalse(os.path.exists(self.receipts))
        with open(self.outbox, encoding="utf-8") as stream:
            journal = [json.loads(line) for line in stream]
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["category"], "failed")
        self.assertNotIn(self.sha, str(journal[0]))
        mark_final.assert_not_called()
        owner_done.assert_called_once()

    def test_lock_join_and_successor_are_distinct(self):
        state = {}
        with mock.patch.object(pilot, "STATE_PATH", self.state_path):
            first = pilot.deploy_after_merge({}, "github.com/timafen/factory", state, self.sha, self.wait("a"))
            joined = pilot.deploy_after_merge({}, "github.com/timafen/factory", state, self.sha, self.wait("b"))
        self.assertEqual(first["id"], joined["id"])
        first["phase"] = "launching"
        with mock.patch.object(pilot, "STATE_PATH", self.state_path):
            pilot.deploy_after_merge({}, "github.com/timafen/factory", state, "b" * 40, self.wait("c"))
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        self.assertTrue(target["next_requested"])
        with mock.patch.object(pilot, "broker_operation", return_value={"status": "succeeded"}), \
                mock.patch.object(pilot, "broker_acceptance", return_value={"status": "passed"}), \
                mock.patch.object(pilot, "mark_final"), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", self.receipts), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", self.outbox):
            pilot.poll_delivery_state({}, state)
        self.assertEqual(len(target["generations"]), 2)

    def test_locked_retry_uses_same_real_broker_operation_after_second_merge(self):
        paths = self._process_paths(self._start_process_broker(locked=True))
        self._pilot_process("seed", paths, sha=self.sha)
        self._pilot_process("poll", paths, now=0, sha=self.sha)  # first physical FX exits rc=8
        self._pilot_process("join", paths, sha="b" * 40)  # second merge arrives in another Pilot process
        self._pilot_process("recover", paths, now=pilot.DELIVERY_RETRY_DELAY, sha="b" * 40)
        state = self._read_json(paths["state"])
        target = state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]
        self.assertEqual(len(target["generations"]), 1, "reserved N must not create N+1")
        generation = target["generations"][target["current_generation"]]
        broker_state = self._read_json(os.path.join(paths["broker_state"], generation["id"] + ".json"))
        with open(paths["attempts"], encoding="utf-8") as stream:
            physical = [line.strip() for line in stream if line.strip()]
        with open(paths["success"], encoding="utf-8") as stream:
            successful = [line.strip() for line in stream if line.strip()]
        self.assertEqual(generation["commit_sha"], "b" * 40)
        self.assertEqual(set(generation["waits"]), {"verify-1", "verify-2"})
        self.assertEqual(generation["phase"], "completed")
        self.assertEqual(broker_state["posts"], 2, "every real POST was persisted by the broker")
        self.assertEqual(physical, [generation["id"], generation["id"]])
        self.assertEqual(successful, [generation["id"]], "only retry installs successfully")
        self.assertEqual(len(self._events(paths["events"], "owner_done")), 1)
        self.assertEqual(len(self._events(paths["events"], "mark_final")), 2)

    def test_pilot_uses_real_unix_broker_routes(self):
        """A built Go broker receives the Unix API request and runs fixed FX once."""
        socket_path = os.path.join(self.temporary.name, "broker.sock")
        state_dir = os.path.join(self.temporary.name, "broker-state")
        executable = os.path.join(self.temporary.name, "factory-release-broker")
        fx = os.path.join(self.temporary.name, "fx")
        calls = os.path.join(self.temporary.name, "fx-calls")
        acceptance = os.path.join(self.temporary.name, "acceptance")
        with open(fx, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nprintf '%s %s\\n' \"$FACTORY_DELIVERY_ID\" \"$*\" >> \"" + calls + "\"\n")
        os.chmod(fx, 0o700)
        with open(acceptance, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\nprintf '%s\\n' '{\"status\":\"passed\"}'\n")
        os.chmod(acceptance, 0o700)
        subprocess.run(["go", "build", "-o", executable, "./cmd/factory-release-broker"],
                       check=True, cwd=os.path.dirname(os.path.dirname(__file__)))
        process = subprocess.Popen([executable, "-socket", socket_path, "-state-dir", state_dir,
                                    "-factory-release-executable", fx,
                                    "-live-acceptance-executable", acceptance],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (process.terminate() if process.poll() is None else None, process.wait(timeout=2) if process.poll() is None else None))
        for _ in range(100):
            if os.path.exists(socket_path):
                break
            if process.poll() is not None:
                self.fail("built release broker stopped before opening its Unix socket")
            time.sleep(.02)
        self.assertTrue(os.path.exists(socket_path))
        state = {}
        broker_calls = []
        real_broker_operation = pilot.broker_operation

        def counting_broker(*args, **kwargs):
            broker_calls.append(args[1])
            return real_broker_operation(*args, **kwargs)

        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", self.receipts), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", self.outbox), \
                mock.patch.object(pilot, "NOTIFY_LOG_PATH", os.path.join(self.temporary.name, "notifications.jsonl")), \
                mock.patch.object(pilot, "mark_final") as owner_done, \
                mock.patch.object(pilot, "broker_operation", side_effect=counting_broker):
            pilot.deploy_after_merge({"release_broker_socket": socket_path}, "github.com/timafen/factory",
                                     state, self.sha, self.wait())
            for _ in range(100):
                pilot.poll_delivery_state({"release_broker_socket": socket_path}, state)
                if state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]["generations"][
                        state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]["current_generation"]]["phase"] == "completed":
                    break
                time.sleep(.02)
        self.assertEqual(broker_calls.count("POST"), 1)
        self.assertGreaterEqual(broker_calls.count("GET"), 1)
        with open(calls, encoding="utf-8") as stream:
            physical = stream.readlines()
        self.assertEqual(len(physical), 1)
        self.assertIn(self.sha, physical[0])
        owner_done.assert_called_once_with("verify-1", "Verify", True)

    def test_recovery_journals_before_wait_without_second_merge(self):
        state = {"merge_intents": {"verify-1": {
            "phase": "merged", "base": "Единый выпуск", "branch": "topic",
            "repository": "github.com/timafen/factory", "commit_sha": self.sha, "link": ""}}}
        journal = os.path.join(self.temporary.name, "merges.jsonl")
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "MERGES_PATH", journal), \
                mock.patch.object(pilot, "gh_merge") as merge:
            pilot.save(self.state_path, state)
            restored = pilot.load(self.state_path, {})
            pilot.recover_merge_intents({}, restored)
            pilot.recover_merge_intents({}, pilot.load(self.state_path, {}))
        merge.assert_not_called()
        with open(journal, encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 1)
        self.assertTrue(pilot._intent_has_wait(restored, "verify-1"))

    def test_outbox_and_notification_journals_are_immutable(self):
        state = {}
        notifications = os.path.join(self.temporary.name, "notifications.jsonl")
        wait = self.wait()
        wait["merge_receipt"].update({
            "actor": "owner", "actor_id": None, "rounds": 3,
        })
        with mock.patch.object(pilot, "STATE_PATH", self.state_path), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", self.receipts), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", self.outbox), \
                mock.patch.object(pilot, "NOTIFY_LOG_PATH", notifications), \
                mock.patch.object(pilot, "mark_final"), \
                mock.patch.object(pilot, "broker_operation", return_value={"status": "succeeded"}), \
                mock.patch.object(pilot, "broker_acceptance", return_value={"status": "passed"}):
            pilot.deploy_after_merge({}, "github.com/timafen/factory", state, self.sha, wait)
            pilot.poll_delivery_state({}, state)
            restored = pilot.load(self.state_path, {})
            pilot.poll_delivery_state({}, restored)
        with open(self.receipts, encoding="utf-8") as stream:
            receipts = [json.loads(line) for line in stream]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(
            (receipts[0]["actor"], receipts[0]["actor_id"], receipts[0]["rounds"]),
            ("owner", None, 3),
        )
        with open(self.outbox, encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 1)
        with open(notifications, encoding="utf-8") as stream:
            self.assertEqual(len(stream.readlines()), 1)

    def test_legacy_is_audit_only_and_never_done(self):
        state = {"post_merge_deploys": {"deploy_factory_cmd": {"pid": 99, "queued": True}}}
        durable = pilot._delivery_state(state)
        self.assertNotIn("post_merge_deploys", state)
        self.assertIn("legacy_post_merge_deploys", durable["audit"])
        self.assertEqual(durable["targets"], {})


class RecentDoneTest(unittest.TestCase):
    def test_ignores_succeeded_intermediate_triage(self):
        task = {
            "id": "triage",
            "title": "[auto] [1/5 Triage] Оплата картой",
            "state": "succeeded",
            "updated_at": "2026-08-10T14:00:00Z",
        }
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        with mock.patch.object(
                pilot, "MERGES_PATH", os.path.join(temporary.name, "merges.jsonl")), \
                mock.patch.object(
                    pilot, "NOTIFY_LOG_PATH", os.path.join(temporary.name, "notifications.jsonl")), \
                mock.patch.object(pilot, "api") as api:
            recent = pilot.recent_done_block([task])

        self.assertEqual(recent, [])
        api.assert_not_called()

    def test_excludes_successful_progress_and_unmerged_verify(self):
        tasks = [
            {"id": "triage", "title": "[auto] [1/5 Triage] Оплата картой",
             "state": "succeeded", "updated_at": "2026-08-10T14:00:00Z"},
            {"id": "unmerged", "title": "[auto] [5/5 Verify] Новая витрина",
             "state": "succeeded", "updated_at": "2026-08-10T13:00:00Z"},
            {"id": "merged", "title": "[auto] [5/5 Verify] Поиск товаров",
             "state": "succeeded", "updated_at": "2026-08-10T12:00:00Z"},
            {"id": "failed", "title": "[auto] [4/5 Review] Оплата картой",
             "state": "failed", "updated_at": "2026-08-10T11:00:00Z"},
        ]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipts = os.path.join(temporary.name, "receipts.jsonl")
        with open(receipts, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"task_id": "merged"}) + "\n")

        with mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", receipts), \
                mock.patch.object(pilot, "api", return_value={"attempts": []}):
            recent = pilot.recent_done_block(tasks)

        self.assertEqual([item["title"] for item in recent],
                         ["Поиск товаров", "Оплата картой"])
        self.assertEqual([item["status"] for item in recent], ["delivered", "failed"])

    def test_keeps_real_pipeline_results_and_excludes_five_service_finals(self):
        tasks = [
            {"id": f"service-{i}", "title": f"[auto] [5/5 Verify] {name}",
             "state": "succeeded", "updated_at": f"2026-08-10T10:0{i}:00Z"}
            for i, name in enumerate(("Smoke check", "Helper cleanup", "Debug probe",
                                       "Idempotency final", "Идемпотентный финал"))
        ] + [
            {"id": "merged", "title": "[auto] [5/5 Verify] Новая витрина",
             "state": "succeeded", "updated_at": "2026-08-10T11:00:00Z"},
            {"id": "failed", "title": "[auto] [4/5 Review] Оплата картой",
             "state": "failed", "updated_at": "2026-08-10T12:00:00Z"},
        ]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipts = os.path.join(temporary.name, "receipts.jsonl")
        with open(receipts, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"task_id": "merged"}) + "\n")

        def detail(path, body=None):
            return {"attempts": [{"result": "ПРОВЕРКА: браузерный сценарий прошёл."}]}

        with mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", receipts), \
                mock.patch.object(pilot, "api", side_effect=detail):
            recent = pilot.recent_done_block(tasks)

        self.assertEqual([item["title"] for item in recent], ["Оплата картой", "Новая витрина"])
        self.assertEqual(recent[0]["status"], "failed")
        self.assertIn("в main не влито", recent[0]["detail"])
        self.assertEqual(recent[1]["status"], "delivered")
        self.assertIn("Выпуск принят", recent[1]["detail"])

    def test_old_notification_is_filtered_and_success_without_merge_is_honest(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        notifications = os.path.join(temporary.name, "notifications.jsonl")
        with open(notifications, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"title": "Задача выполнена", "message": "Идемпотентный финал"}) + "\n")
            stream.write(json.dumps({"title": "Задача выполнена", "message": "Старый настоящий результат\nПроверено вручную"}) + "\n")
        with mock.patch.object(pilot, "NOTIFY_LOG_PATH", notifications), \
                mock.patch.object(pilot, "MERGES_PATH", os.path.join(temporary.name, "none")), \
                mock.patch.object(pilot, "api", return_value={"attempts": []}):
            recent = pilot.recent_done_block([], n=3)

        self.assertEqual([item["title"] for item in recent], ["Старый настоящий результат"])
        self.assertEqual(recent[0]["status"], "legacy")

    def test_reads_every_task_page(self):
        pages = [
            {"tasks": [{"id": "new"}], "next_cursor": "older"},
            {"tasks": [{"id": "old"}], "next_cursor": None},
        ]
        with mock.patch.object(pilot, "api", side_effect=pages) as api:
            self.assertEqual([task["id"] for task in pilot.all_tasks()], ["new", "old"])
        self.assertEqual(api.call_args_list[0].args[0], "/tasks?limit=200")
        self.assertEqual(api.call_args_list[1].args[0], "/tasks?limit=200&cursor=older")


class DashboardProjectsTest(unittest.TestCase):
    def setUp(self):
        pilot._dash_slow = {"at": 0, "data": {}}

    @mock.patch.object(pilot, "_project_repo_dirs", return_value=["/work/shop"])
    @mock.patch.object(pilot, "_fixed_command")
    @mock.patch.object(pilot, "api")
    def test_readiness_uses_all_nine_safe_sources_without_exposing_values(
            self, api, command, _repo):
        api.side_effect = lambda path: ({"routing_ready": True, "workers": []}
                                        if path.endswith("/readiness") else {
                                            "attempts": [{
                                                "state": "succeeded", "result": "PASS — verified",
                                                "completed_at": "2026-08-10T11:30:00Z",
                                            }],
                                        })
        command.side_effect = lambda args, timeout=25: (
            (True, "HTTP 200") if args[-1] == "health" else
            (True, "DATABASE_URL\nAPI_TOKEN\nSECRET=value\narbitrary output"))
        tasks = [{
            "id": "verify-1", "title": "[auto] [5/5 Verify] Shop",
            "repository_id": "shop", "state": "succeeded",
            "created_at": "2026-08-10T11:00:00Z",
        }]
        environments = [{
            "name": "Стейдж", "status": "available",
            "release_label": "Летний выпуск", "health": "healthy",
        }]
        browser = pilot._readiness_check("browser", "ready", "Smoke прошёл.")

        readiness = pilot._project_readiness(
            {"id": "shop"}, "trade", environments, tasks,
            [{"key": "staging", "enabled": True},
             {"key": "production-write", "enabled": False}], browser,
            now=1_754_824_000,
        )

        self.assertEqual([check["key"] for check in readiness["checks"]],
                         [key for key, _title in pilot.PROJECT_READINESS_CHECKS])
        self.assertEqual([check["state"] for check in readiness["checks"]], ["ready"] * 9)
        self.assertEqual(readiness["verdict"], "ready")
        secret_reason = readiness["checks"][7]["reason"]
        self.assertEqual(secret_reason, "Доступны имена секретов: 2.")
        self.assertNotIn("SECRET=value", repr(readiness))
        self.assertNotIn("arbitrary output", repr(readiness))
        self.assertEqual(command.call_args_list, [
            mock.call(["sudo", "-n", "/usr/local/bin/fx", "staging", "health"]),
            mock.call(["sudo", "-n", "/usr/local/bin/fx", "staging", "env-names"]),
        ])
        rollback_argv = pilot.PROJECT_PROVIDER_CATALOG["trade"]["rollback_argv"]
        self.assertNotIn(mock.call(list(rollback_argv)), command.call_args_list)

    def test_readiness_verdict_is_order_independent_and_unknown_is_not_ready(self):
        ready = [pilot._readiness_check(key, "ready", "ok")
                 for key, _title in pilot.PROJECT_READINESS_CHECKS]
        self.assertEqual(pilot._readiness_verdict(list(reversed(ready))), "ready")
        unknown = [dict(check) for check in ready]
        unknown[0]["state"] = "unknown"
        self.assertEqual(pilot._readiness_verdict(unknown), "needs_configuration")
        blocked = [dict(check) for check in unknown]
        blocked[-1]["state"] = "blocked"
        self.assertEqual(pilot._readiness_verdict(blocked), "blocked")

    def test_browser_readiness_requires_fresh_valid_smoke_marker(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        marker = os.path.join(temporary.name, "browser-readiness.json")
        now = datetime.datetime(2026, 8, 10, 12, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(pilot._browser_readiness(now, marker)["state"], "unknown")
        with open(marker, "w", encoding="utf-8") as marker_file:
            json.dump({"passed_at": "2026-08-10T11:00:00Z",
                       "browser_fingerprint": "a" * 64}, marker_file)
        self.assertEqual(pilot._browser_readiness(now, marker)["state"], "ready")
        with open(marker, "w", encoding="utf-8") as marker_file:
            json.dump({"passed_at": "2026-08-08T11:00:00Z",
                       "browser_fingerprint": "a" * 64}, marker_file)
        self.assertEqual(pilot._browser_readiness(now, marker)["state"], "unknown")
        with open(marker, "w", encoding="utf-8") as marker_file:
            marker_file.write("not-json")
        self.assertEqual(pilot._browser_readiness(now, marker)["state"], "blocked")

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
        self.assertEqual(scopes, [
            "staging", "staging", "prod", "prod", "staging", "staging",
            "factory", "factory",
        ])
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


class EpicCompletionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.epic_dir = os.path.join(self.temp.name, "epics")
        os.makedirs(self.epic_dir)
        self.merges_path = os.path.join(self.temp.name, "merges.jsonl")
        self.patches = [
            mock.patch.object(pilot, "EPIC_DIR", self.epic_dir),
            mock.patch.object(pilot, "MERGES_PATH", self.merges_path),
            mock.patch.object(pilot, "load_questions", return_value=[]),
        ]
        for patch in self.patches:
            patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: [patch.stop() for patch in reversed(self.patches)])
        self.conf = {"stages": [{"workflow": "Implement + Test"},
                                {"workflow": "Verify"}]}

    def write_epic(self, subtasks):
        epic = {"id": "epic-1", "name": "Receipt test", "status": "running",
                "created_at": "2026-08-10T09:00:00Z", "subtasks": subtasks,
                "children": []}
        pilot.save(os.path.join(self.epic_dir, "epic-1.json"), epic)
        return epic

    def read_epic(self):
        return pilot.load(os.path.join(self.epic_dir, "epic-1.json"), {})

    def advance(self, tasks=(), final_ok=True):
        with mock.patch.object(pilot, "final_ok", return_value=final_ok), \
                mock.patch.object(pilot, "notify"), \
                mock.patch.object(pilot, "launch_subtask", return_value=(None, "test")) as launch:
            pilot.advance_epics(self.conf, list(tasks), {}, {})
        return launch

    def test_done_subtask_keeps_task_history_receipt_after_cleanup(self):
        self.write_epic([
            {"title": "Подготовить sandbox", "status": "running",
             "task_id": "verify-1", "started_at": "2026-08-10T10:00:00Z"},
            {"title": "Купить ключ", "status": "pending", "hold_reason": "ждём ключ владельца"},
        ])
        final_task = {"id": "verify-1", "state": "succeeded",
                      "created_at": "2026-08-10T10:01:00Z",
                      "title": "[auto] [2/2 Verify] Подготовить sandbox"}

        self.advance([final_task])
        saved = self.read_epic()["subtasks"][0]
        self.assertEqual(saved["status"], "done")
        self.assertEqual(saved["completion_source"], "task_history")
        self.assertEqual(saved["completion_receipt"]["task_id"], "verify-1")
        self.assertTrue(saved["completed_at"])

        self.advance([])
        self.assertEqual(self.read_epic()["subtasks"][0], saved)

    def test_running_subtask_recovers_only_from_matching_new_merge_receipt(self):
        self.write_epic([
            {"title": "Подготовить sandbox", "status": "running",
             "started_at": "2026-08-10T10:00:00Z"},
            {"title": "Купить ключ", "status": "pending", "hold_reason": "ждём ключ владельца"},
        ])
        with open(self.merges_path, "w", encoding="utf-8") as merges:
            merges.write(json.dumps({"task_id": "near-match", "base": "Подготовить sandbox extra",
                                     "at": "2026-08-10T10:03:00Z"}) + "\n")
            merges.write(json.dumps({"task_id": "verify-1", "base": "Подготовить sandbox",
                                     "at": "2026-08-10T10:02:00Z"}) + "\n")

        self.advance([])
        saved = self.read_epic()["subtasks"][0]
        self.assertEqual(saved["status"], "done")
        self.assertEqual(saved["completed_at"], "2026-08-10T10:02:00Z")
        self.assertEqual(saved["completion_source"], "merge_journal")
        self.assertEqual(saved["completion_receipt"], {
            "task_id": "verify-1", "base": "Подготовить sandbox", "at": "2026-08-10T10:02:00Z"})

    def test_old_merge_cannot_complete_restarted_generation(self):
        self.write_epic([
            {"title": "Подготовить sandbox", "status": "running",
             "started_at": "2026-08-10T11:00:00Z"},
            {"title": "Следующий шаг", "status": "pending"},
        ])
        with open(self.merges_path, "w", encoding="utf-8") as merges:
            merges.write(json.dumps({"task_id": "old-verify", "base": "Подготовить sandbox",
                                     "at": "2026-08-10T10:02:00Z"}) + "\n")

        launch = self.advance([])
        self.assertEqual(self.read_epic()["subtasks"][0]["status"], "running")
        launch.assert_not_called()

    def test_live_restart_rejects_old_receipt_after_history_is_cleaned(self):
        self.write_epic([
            {"title": "Подготовить sandbox", "status": "done",
             "started_at": "2026-08-10T09:00:00Z", "completed_at": "2026-08-10T10:02:00Z",
             "completion_source": "merge_journal",
             "completion_receipt": {"task_id": "old", "base": "Подготовить sandbox",
                                    "at": "2026-08-10T10:02:00Z"}},
            {"title": "Купить ключ", "status": "pending", "hold_reason": "ждём ключ владельца"},
        ])
        with open(self.merges_path, "w", encoding="utf-8") as merges:
            merges.write(json.dumps({"task_id": "old", "base": "Подготовить sandbox",
                                     "at": "2026-08-10T10:02:00Z"}) + "\n")
        live = {"id": "restart-1", "state": "running", "created_at": "2026-08-10T11:00:00Z",
                "title": "[auto] [1/2 Implement + Test] Подготовить sandbox"}

        self.advance([live])
        self.assertEqual(self.read_epic()["subtasks"][0]["started_at"], "2026-08-10T11:00:00Z")
        self.advance([])
        self.assertEqual(self.read_epic()["subtasks"][0]["status"], "running")

    def test_failed_or_stuck_restart_keeps_generation_boundary_after_history_cleanup(self):
        for state in ("failed", "stuck"):
            with self.subTest(state=state):
                self.write_epic([
                    {"title": "Подготовить sandbox", "status": "done",
                     "started_at": "2026-08-10T09:00:00Z", "completed_at": "2026-08-10T10:02:00Z",
                     "completion_source": "merge_journal",
                     "completion_receipt": {"task_id": "old", "base": "Подготовить sandbox",
                                            "at": "2026-08-10T10:02:00Z"}},
                    {"title": "Следующий шаг", "status": "pending"},
                ])
                with open(self.merges_path, "w", encoding="utf-8") as merges:
                    merges.write(json.dumps({"task_id": "old", "base": "Подготовить sandbox",
                                             "at": "2026-08-10T10:02:00Z"}) + "\n")
                restart = {"id": f"restart-{state}", "state": state,
                           "created_at": "2026-08-10T11:00:00Z",
                           "title": "[auto] [1/2 Implement + Test] Подготовить sandbox"}

                self.advance([restart])
                saved = self.read_epic()["subtasks"][0]
                self.assertEqual(saved["started_at"], "2026-08-10T11:00:00Z")
                self.assertEqual(saved["task_id"], f"restart-{state}")

                self.advance([])
                self.assertEqual(self.read_epic()["subtasks"][0]["status"], "running")

    def test_hold_reason_does_not_create_a_pending_subtask(self):
        self.write_epic([
            {"title": "Купить ключ", "status": "pending", "parallel_ok": True,
             "hold_reason": "ждём ключ владельца"},
            {"title": "Seed", "status": "pending"},
        ])

        launch = self.advance([])
        launch.assert_not_called()

    def test_parallel_subtask_starts_beside_running_sequential_subtask(self):
        self.write_epic([
            {"title": "Последовательная", "status": "running",
             "started_at": "2026-08-10T10:00:00Z"},
            {"title": "Независимая", "status": "pending", "parallel_ok": True},
            {"title": "После последовательной", "status": "pending"},
        ])
        live = {"id": "serial-1", "state": "running", "created_at": "2026-08-10T10:01:00Z",
                "title": "[auto] [1/2 Implement + Test] Последовательная"}

        launch = self.advance([live])
        launch.assert_called_once_with(self.conf, mock.ANY, 1, {}, {})


class AreaLockArbitrationTests(unittest.TestCase):
    """Замок областей решает споры детерминированно, а не взаимным ожиданием."""

    AREAS = {
        "Старшая работа": ["repo::pilot/pilot.py"],
        "Младшая работа": ["repo::pilot/pilot.py"],
    }

    def _loader(self, path, default=None):
        return dict(self.AREAS) if path == pilot.AREAS_PATH else (default or {})

    def _busy(self, tasks, base):
        with mock.patch.object(pilot, "load", side_effect=self._loader), \
                mock.patch.object(pilot, "area_of",
                                  return_value={"repo::pilot/pilot.py"}):
            return pilot.area_busy(tasks, base)

    def test_running_holder_still_blocks_unconditionally(self):
        tasks = [{"state": "running", "created_at": "2026-08-13T10:00:00Z",
                  "title": "[auto] [2/5 Implement + Test] Младшая работа"}]
        self.assertEqual(self._busy(tasks, "Старшая работа"), "Младшая работа")

    def test_mutual_queued_contention_has_exactly_one_winner(self):
        tasks = [
            {"state": "queued", "created_at": "2026-08-13T10:00:00Z",
             "title": "[auto] [4/5 Review] Старшая работа"},
            {"state": "queued", "created_at": "2026-08-13T09:00:00Z",
             "title": "[auto] [2/5 Specification] Младшая работа"},
        ]
        self.assertEqual(self._busy(tasks, "Старшая работа"), "")
        self.assertEqual(self._busy(tasks, "Младшая работа"), "Старшая работа")

    def test_equal_stage_earlier_start_wins(self):
        tasks = [
            {"state": "queued", "created_at": "2026-08-13T08:00:00Z",
             "title": "[auto] [3/5 Implement + Test] Старшая работа"},
            {"state": "queued", "created_at": "2026-08-13T11:00:00Z",
             "title": "[auto] [3/5 Implement + Test] Младшая работа"},
        ]
        self.assertEqual(self._busy(tasks, "Старшая работа"), "")
        self.assertEqual(self._busy(tasks, "Младшая работа"), "Старшая работа")


class AutomationStatusSnapshotTests(unittest.TestCase):
    def test_allowlist_and_partial_failure_remain_visible(self):
        target = os.path.join(_TEST_DATA_HOME.name, "pilot", "automation-status-test.json")
        old = pilot.AUTOMATION_STATUS_PATH
        pilot.AUTOMATION_STATUS_PATH = target

        def fake_run(argv, **_kwargs):
            if "factory-pilot.service" in argv:
                return types.SimpleNamespace(returncode=0, stdout=(
                    "ActiveState=active\nActiveEnterTimestamp=Thu 2026-08-13 10:00:00 UTC\n"))
            return types.SimpleNamespace(returncode=1, stdout="")

        try:
            pilot.write_automation_status(fake_run, os.path.join(_TEST_DATA_HOME.name, "missing.log"))
            with open(target, encoding="utf-8") as handle:
                rows = json.load(handle)["automations"]
        finally:
            pilot.AUTOMATION_STATUS_PATH = old
        self.assertEqual(["factory-pilot", "factory-release-broker", "factory-intake", "factory-janitor"],
                         [row["id"] for row in rows])
        self.assertEqual("ok", rows[0]["data_status"])
        self.assertTrue(all(row["data_status"] == "no_data" for row in rows[1:]))

    def test_snapshot_uses_completed_pilot_cycle_and_converts_local_systemd_time(self):
        target = os.path.join(_TEST_DATA_HOME.name, "pilot", "automation-status-test.json")
        old = pilot.AUTOMATION_STATUS_PATH
        pilot.AUTOMATION_STATUS_PATH = target

        def fake_run(_argv, **_kwargs):
            return types.SimpleNamespace(returncode=0, stdout=(
                "ActiveState=active\nActiveEnterTimestamp=Thu 2026-08-13 10:00:00 CDT\n"))

        try:
            pilot.write_automation_status(fake_run, os.path.join(_TEST_DATA_HOME.name, "missing.log"),
                                          "2026-08-13T16:00:00Z")
            with open(target, encoding="utf-8") as handle:
                snapshot = json.load(handle)
        finally:
            pilot.AUTOMATION_STATUS_PATH = old
        self.assertIn("observed_at", snapshot)
        self.assertEqual("2026-08-13T16:00:00Z", snapshot["automations"][0]["last_activity_at"])
        self.assertEqual("2026-08-13T15:00:00Z", snapshot["automations"][1]["last_activity_at"])

    def test_invalid_janitor_calendar_date_remains_no_data(self):
        target = os.path.join(_TEST_DATA_HOME.name, "pilot", "automation-status-test.json")
        log_path = os.path.join(_TEST_DATA_HOME.name, "janitor-invalid-date.log")
        old = pilot.AUTOMATION_STATUS_PATH
        pilot.AUTOMATION_STATUS_PATH = target
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("completed at 2026-99-99T10:00:00Z\\n")

        try:
            pilot.write_automation_status(lambda *_args, **_kwargs: types.SimpleNamespace(returncode=1, stdout=""), log_path)
            with open(target, encoding="utf-8") as handle:
                janitor = json.load(handle)["automations"][-1]
        finally:
            pilot.AUTOMATION_STATUS_PATH = old
        self.assertEqual("no_data", janitor["data_status"])
        self.assertNotIn("last_activity_at", janitor)

    def test_future_host_activity_remains_no_data(self):
        target = os.path.join(_TEST_DATA_HOME.name, "pilot", "automation-status-test.json")
        log_path = os.path.join(_TEST_DATA_HOME.name, "janitor-future-date.log")
        old = pilot.AUTOMATION_STATUS_PATH
        pilot.AUTOMATION_STATUS_PATH = target
        future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write(f"completed at {future}\\n")

        def fake_run(_argv, **_kwargs):
            return types.SimpleNamespace(returncode=0, stdout=(
                f"ActiveState=active\\nActiveEnterTimestamp={future}\\n"))

        try:
            pilot.write_automation_status(fake_run, log_path)
            with open(target, encoding="utf-8") as handle:
                rows = json.load(handle)["automations"]
        finally:
            pilot.AUTOMATION_STATUS_PATH = old
        self.assertTrue(all(row["data_status"] == "no_data" for row in rows))


class MergedCommitShaTests(unittest.TestCase):
    """Поезд получает настоящий пост-squash коммит main, а не head ветки."""

    PULLS = [
        {"merged_at": None, "head": {"sha": "a" * 40}, "merge_commit_sha": "b" * 40},
        {"merged_at": "2026-08-14T00:52:00Z", "head": {"sha": "c" * 40},
         "merge_commit_sha": "d" * 40},
    ]

    def test_returns_merge_commit_for_matching_merged_head(self):
        with mock.patch.object(pilot, "gh_json", return_value=self.PULLS):
            self.assertEqual(pilot._merged_commit_sha("o/r", "br", "c" * 40), "d" * 40)

    def test_unmerged_or_foreign_head_yields_empty(self):
        with mock.patch.object(pilot, "gh_json", return_value=self.PULLS):
            self.assertEqual(pilot._merged_commit_sha("o/r", "br", "a" * 40), "")
        with mock.patch.object(pilot, "gh_json", return_value=None):
            self.assertEqual(pilot._merged_commit_sha("o/r", "br"), "")

    def test_without_expected_head_takes_any_merged(self):
        with mock.patch.object(pilot, "gh_json", return_value=self.PULLS):
            self.assertEqual(pilot._merged_commit_sha("o/r", "br"), "d" * 40)
class SameTitlePlanEpicBudgetIsolationTests(unittest.TestCase):
    """Concurrent owner work keeps real Pilot state partitioned by work_id."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = self.temp.name
        for name in ("questions", "epics", "verdicts"):
            os.makedirs(os.path.join(self.home, name))
        self.paths = {
            "ideas": os.path.join(self.home, "ideas.json"),
            "works": os.path.join(self.home, "works.json"),
            "questions": os.path.join(self.home, "questions"),
            "epics": os.path.join(self.home, "epics"),
            "verdicts": os.path.join(self.home, "verdicts"),
            "merges": os.path.join(self.home, "merges.jsonl"),
            "budget": os.path.join(self.home, "budget.json"),
            "budget_stops": os.path.join(self.home, "budget_stops.json"),
            "config": os.path.join(self.home, "config.json"),
        }
        self.patches = [
            mock.patch.object(pilot, "IDEAS_PATH", self.paths["ideas"]),
            mock.patch.object(pilot, "WORKS_PATH", self.paths["works"]),
            mock.patch.object(pilot, "QUESTION_DIR", self.paths["questions"]),
            mock.patch.object(pilot, "EPIC_DIR", self.paths["epics"]),
            mock.patch.object(pilot, "VERDICT_DIR", self.paths["verdicts"]),
            mock.patch.object(pilot, "MERGES_PATH", self.paths["merges"]),
            mock.patch.object(pilot, "BUDGET_PATH", self.paths["budget"]),
            mock.patch.object(pilot, "BUDGET_STOPS", self.paths["budget_stops"]),
            mock.patch.object(pilot, "CONF_PATH", self.paths["config"]),
        ]
        for patch in self.patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in reversed(self.patches)])
        pilot.save(self.paths["config"], {"stopped_pipelines": []})

    def test_plan_completion_never_closes_other_same_title_work(self):
        title = "Одинаковая карточка"
        pilot.save(self.paths["ideas"], [
            {"id": "idea-a", "title": title, "state": "in_work",
             "task_id": "root-a", "work_id": "work-a"},
            {"id": "idea-b", "title": title, "state": "in_work",
             "task_id": "root-b", "work_id": "work-b"},
        ])
        tasks = [
            {"id": "root-a", "work_id": "work-a", "state": "succeeded",
             "created_at": "2026-08-11T10:00:00Z",
             "title": f"[auto] [1/5 Triage] {title}"},
            {"id": "root-b", "work_id": "work-b", "state": "succeeded",
             "created_at": "2026-08-11T10:00:01Z",
             "title": f"[auto] [1/5 Triage] {title}"},
            {"id": "verify-a", "work_id": "work-a", "parent_task_id": "root-a",
             "state": "succeeded", "created_at": "2026-08-11T11:00:00Z",
             "title": f"[auto] [5/5 Verify] {title}"},
        ]
        pilot.mark_final("verify-a", "Verify", True)

        self.assertEqual(pilot.cleanup_completed_plan_cards(tasks, 5), ["idea-a"])
        states = {idea["id"]: idea["state"] for idea in pilot.ideas_all()}
        self.assertEqual(states, {"idea-a": "done", "idea-b": "in_work"})

    def test_plan_and_epic_producers_record_both_same_title_roots(self):
        title = "Одинаковый корень"
        pilot.save(self.paths["ideas"], [
            {"id": "plan-a", "title": title, "origin": "owner-a",
             "state": "planned", "order": 1, "repo": "repo",
             "run_generation": "generation-a"},
            {"id": "plan-b", "title": title, "origin": "owner-b",
             "state": "planned", "order": 2, "repo": "repo",
             "run_generation": "generation-b"},
        ])
        conf = {"stages": [{"workflow": "Triage", "workers": {"medium": "triager"}}],
                "max_parallel_works": 4}
        workflows = {"Triage": {"enabled": True, "revision_id": "triage-rev"}}
        workers = {"triager": {"id": "triager-id", "online": True,
                                "health": "healthy"}}
        roots = iter((
            {"task": {"id": "task-a", "work_id": "plan-work-a"}},
            {"task": {"id": "task-b", "work_id": "plan-work-b"}},
        ))
        with mock.patch.object(pilot, "create_task", side_effect=lambda *_: next(roots)), \
                mock.patch.object(pilot, "notify"):
            self.assertEqual(pilot.autostart_plan(conf, [], workflows, workers), "task-a")
            self.assertEqual(pilot.autostart_plan(conf, [], workflows, workers), "task-b")

        works = pilot.load(self.paths["works"], {})
        self.assertEqual(works["plan-work-a"]["origin"], "owner-a")
        self.assertEqual(works["plan-work-b"]["origin"], "owner-b")
        self.assertEqual(works["plan-work-a"]["start_stage"], "Triage")
        self.assertEqual(works["plan-work-b"]["skipped"], [])

        epic_conf = {
            "stages": [
                {"workflow": "Triage", "workers": {"medium": "triager"}},
                {"workflow": "Specification", "workers": {"medium": "triager"}},
                {"workflow": "Implement + Test", "workers": {"low": "implementer"}},
            ],
            "skip_stages_for_low": ["Triage", "Specification"],
        }
        epic_workflows = {
            name: {"enabled": True, "revision_id": name + "-rev"}
            for name in ("Triage", "Specification", "Implement + Test")
        }
        epic_workers = {"implementer": {"id": "implementer-id", "online": True,
                                         "health": "healthy"}}
        epics = [
            {"id": "epic-a", "name": "A", "goal": "A", "origin": "agent-a",
             "repository_id": "repo", "subtasks": [{"title": title, "complexity": "low"}]},
            {"id": "epic-b", "name": "B", "goal": "B", "origin": "agent-b",
             "repository_id": "repo", "subtasks": [{"title": title, "complexity": "low"}]},
        ]
        epic_roots = iter((
            {"task": {"id": "epic-task-a", "work_id": "epic-work-a"}},
            {"task": {"id": "epic-task-b", "work_id": "epic-work-b"}},
        ))
        with mock.patch.object(pilot, "create_task",
                               side_effect=lambda *_: next(epic_roots)):
            for epic in epics:
                self.assertTrue(pilot.start_epic(
                    epic_conf, epic, epic_workflows, epic_workers)[0])

        works = pilot.load(self.paths["works"], {})
        self.assertEqual(works["epic-work-a"]["origin"], "agent-a")
        self.assertEqual(works["epic-work-b"]["origin"], "agent-b")
        self.assertEqual(works["epic-work-a"]["start_stage"], "Implement + Test")
        self.assertEqual(works["epic-work-b"]["skipped"], ["Triage", "Specification"])

    def test_epic_completion_and_merge_receipt_ignore_other_work(self):
        title = "Одинаковая подзадача"
        for suffix in ("a", "b"):
            pilot.save(os.path.join(self.paths["epics"], f"epic-{suffix}.json"), {
                "id": f"epic-{suffix}", "name": suffix.upper(), "status": "running",
                "created_at": "2026-08-11T09:00:00Z",
                "subtasks": [{"title": title, "status": "running",
                              "task_id": f"root-{suffix}", "work_id": f"work-{suffix}",
                              "started_at": "2026-08-11T10:00:00Z"}],
                "children": [],
            })
        tasks = [
            {"id": "verify-a", "work_id": "work-a", "parent_task_id": "root-a",
             "state": "succeeded", "created_at": "2026-08-11T11:00:00Z",
             "title": f"[auto] [2/2 Verify] {title}"},
            {"id": "root-b", "work_id": "work-b", "state": "running",
             "created_at": "2026-08-11T10:00:00Z",
             "title": f"[auto] [1/2 Implement + Test] {title}"},
        ]
        pilot.mark_final("verify-a", "Verify", True)
        with open(self.paths["merges"], "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"task_id": "verify-a", "base": title,
                                     "work_id": "work-a",
                                     "at": "2026-08-11T11:01:00Z"}) + "\n")

        with mock.patch.object(pilot, "notify"):
            pilot.advance_epics({"stages": [{"workflow": "Implement + Test"},
                                             {"workflow": "Verify"}]},
                                tasks, {}, {})

        saved_a = pilot.load(os.path.join(self.paths["epics"], "epic-a.json"), {})
        saved_b = pilot.load(os.path.join(self.paths["epics"], "epic-b.json"), {})
        self.assertEqual(saved_a["status"], "done")
        self.assertEqual(saved_b["status"], "running")
        self.assertIsNotNone(pilot.merge_receipt(title, work_id="work-a"))
        self.assertIsNone(pilot.merge_receipt(title, work_id="work-b"))

    def test_budget_spend_limit_and_history_branch_are_partitioned(self):
        title = "Одинаковый бюджет"
        tasks = [
            {"id": "task-a", "work_id": "work-a", "worker_id": "worker",
             "state": "running", "title": f"[auto] [1/1 Triage] {title}"},
            {"id": "task-b", "work_id": "work-b", "worker_id": "worker",
             "state": "running", "title": f"[auto] [1/1 Triage] {title}"},
        ]
        attempts = {"task-a": ["attempt-a"], "task-b": ["attempt-b"]}
        costs = {"attempt-a": 5.0, "attempt-b": 0.1}

        def fake_api(path, payload=None):
            task_id = path.split("/")[2]
            if path.endswith("/cancel"):
                return {}
            return {"task": {"repository_id": "repo",
                              "context": f"Branch: factory/{task_id[-1]}"},
                    "attempts": []}

        with mock.patch.object(pilot, "attempts_of",
                               side_effect=lambda task_id, _finished: attempts[task_id]), \
                mock.patch.object(pilot, "task_cost_usd",
                                  side_effect=lambda ids: sum(costs[i] for i in ids)), \
                mock.patch.object(pilot, "api", side_effect=fake_api), \
                mock.patch.object(pilot, "branch_head", return_value=""), \
                mock.patch.object(pilot, "notify"):
            self.assertEqual(pilot.work_spent(tasks, title, work_id="work-a"), 5.0)
            self.assertEqual(pilot.work_spent(tasks, title, work_id="work-b"), 0.1)
            self.assertEqual(pilot.branch_from_history(
                tasks, title, work_id="work-a"), "factory/a")
            self.assertEqual(pilot.branch_from_history(
                tasks, title, work_id="work-b"), "factory/b")
            conf = {"stages": [{"workflow": "Triage",
                                 "workers": {"medium": "triager"}}]}
            workers = {"worker": {"id": "worker", "name": "triager"}}
            pilot.budget_guard(conf, tasks, workers)

        budget = pilot.load(self.paths["budget"], {})
        self.assertEqual(budget["work-a"]["downgrades"], 1)
        self.assertEqual(budget["work-b"]["downgrades"], 0)
        question = pilot.load(os.path.join(self.paths["questions"], "task-a.json"), {})
        self.assertEqual(question["work_id"], "work-a")
        self.assertEqual(question["branch"], "factory/a")


if __name__ == "__main__":
    unittest.main()
