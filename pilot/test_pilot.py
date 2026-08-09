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
            {"id": "later", "title": "Вторая", "state": "planned", "order": 20},
            {"id": "top", "title": "Первая", "why": "важнее", "source": "находка",
             "repo": "repo-1", "origin": "agent", "state": "planned", "order": 10},
        ]

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


if __name__ == "__main__":
    unittest.main()
