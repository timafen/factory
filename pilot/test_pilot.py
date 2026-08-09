import contextlib
import time
import unittest
import urllib.error
from unittest import mock

from pilot import pilot


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

    def test_cycle_recounts_slots_after_pipeline_continuation(self):
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

        def continue_pipeline(*_args):
            tasks.append({"id": "c", "title": "[auto] [2/2 Implement] C",
                          "state": "queued"})

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
            stack.enter_context(mock.patch.object(pilot, "pipeline_watch",
                                                  side_effect=continue_pipeline))
            create = stack.enter_context(mock.patch.object(pilot, "create_task"))
            ideas = stack.enter_context(mock.patch.object(pilot, "ideas_all",
                return_value=self.cards))
            stack.enter_context(mock.patch.object(pilot, "load_questions", return_value=[]))
            for name in noops:
                stack.enter_context(mock.patch.object(pilot, name))
            pilot.cycle(self.conf, state)

        ideas.assert_not_called()
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
