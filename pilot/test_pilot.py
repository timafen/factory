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
if __name__ == "__main__":
    unittest.main()
