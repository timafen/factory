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


if __name__ == "__main__":
    unittest.main()
