#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops/reconcile-factory-delivery-waits.py"
sys.path.insert(0, str(ROOT))
from pilot import pilot  # noqa: E402


class ReconcileFactoryDeliveryWaitsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.merge_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD^"], cwd=ROOT, text=True).strip()
        self.entries = [{"task_id": f"wait-{index:02d}", "verified_merge_sha": self.merge_sha}
                        for index in range(28)]
        waits = {item["task_id"]: {"task_id": item["task_id"], "base": f"Работа {index:02d}",
                 "merge_receipt": {"task_id": item["task_id"]}}
                 for index, item in enumerate(self.entries)}
        intents = {item["task_id"]: {"commit_sha": self.merge_sha, "phase": "waiting"}
                   for item in self.entries}
        self.state = {"merge_intents": intents, pilot.DELIVERY_STATE_KEY: {"version": 2,
            "targets": {"factory": {"id": "factory", "current_generation": "factory-orphan",
            "generations": {"factory-orphan": {"id": "factory-orphan", "sequence": 4,
            "phase": "failed", "waits": waits}}}}, "outbox": {}, "audit": {}}}
        self.review = {"format": 1, "target": "factory", "audit_id": "manual-release-2026-08-13",
                       "generation_id": "factory-orphan", "release_sha": self.release_sha,
                       "waits": self.entries}

    def write_json(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def fixture(self, state=None, review=None):
        state_path = self.write_json("state.json", self.state if state is None else state)
        review_path = self.write_json("review.json", self.review if review is None else review)
        release_info = self.write_json("factory-current.json", {"sha": self.release_sha})
        generation = self.root / "generation"
        generation.mkdir(exist_ok=True)
        generation_manifest = self.write_json("generation/manifest.json", {"candidate_sha": self.release_sha})
        output, audit = self.root / "output.json", self.root / "audit.json"
        checksum = hashlib.sha256(state_path.read_bytes()).hexdigest()
        args = [sys.executable, str(TOOL), "--state-copy", str(state_path),
                "--state-sha256", checksum, "--release-info", str(release_info),
                "--generation-manifest", str(generation_manifest),
                "--current-generation", str(generation),
                "--release-journal", str(self.root / "transaction"), "--repo", str(ROOT),
                "--manifest", str(review_path), "--output-state", str(output),
                "--audit-output", str(audit), "--now", "2026-08-13T12:00:00+00:00"]
        return args, state_path, output, audit

    def run_tool(self, args, success):
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def test_exact_28_builds_output_without_changing_input(self):
        args, state_path, output, audit = self.fixture()
        before = state_path.read_bytes()
        result = self.run_tool(args, True)
        self.assertIn("28 waits; live state unchanged", result.stdout)
        self.assertEqual(state_path.read_bytes(), before)
        recovered = json.loads(output.read_text())
        generation = recovered[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]["generations"]["factory-orphan"]
        self.assertEqual(generation["phase"], "completed")
        self.assertEqual(json.loads(audit.read_text())["count"], 28)

    def test_recovered_state_finishes_exactly_28_waits_and_one_done_event(self):
        args, _state_path, output, _audit = self.fixture()
        self.run_tool(args, True)
        recovered = json.loads(output.read_text())
        receipts, outbox = self.root / "receipts.jsonl", self.root / "outbox.jsonl"
        finalized = []
        with mock.patch.object(pilot, "STATE_PATH", str(output)), \
                mock.patch.object(pilot, "DELIVERY_RECEIPTS_PATH", str(receipts)), \
                mock.patch.object(pilot, "DELIVERY_OUTBOX_PATH", str(outbox)), \
                mock.patch.object(pilot, "mark_final", side_effect=lambda task, _stage, ok: finalized.append((task, ok))), \
                mock.patch.object(pilot, "notify"):
            pilot.poll_delivery_state({}, recovered)
            pilot.poll_delivery_state({}, pilot.load(str(output), {}))
        self.assertEqual(len(receipts.read_text().splitlines()), 28)
        self.assertEqual(len(finalized), 28)
        durable = pilot.load(str(output), {})[pilot.DELIVERY_STATE_KEY]
        done = [item for key, item in durable["outbox"].items() if key.endswith(":done")]
        self.assertEqual(len(done), 1)
        self.assertEqual(len(outbox.read_text().splitlines()), 1)

    def test_existing_audit_id_is_a_noop(self):
        state = copy.deepcopy(self.state)
        state[pilot.DELIVERY_STATE_KEY]["audit"] = {"reconciliations": {
            self.review["audit_id"]: {"manifest_sha256": "already-reviewed", "count": 28}}}
        args, state_path, output, audit = self.fixture(state)
        self.run_tool(args, True)
        self.assertEqual(json.loads(output.read_text()), json.loads(state_path.read_text()))
        self.assertEqual(json.loads(audit.read_text())["result"], "noop")

    def test_manifest_count_duplicate_extra_and_missing_fail_closed(self):
        cases = {}
        for count in (27, 29):
            review = copy.deepcopy(self.review)
            review["waits"] = (self.entries[:count] if count < 28 else self.entries + [
                {"task_id": "extra", "verified_merge_sha": self.merge_sha}])
            cases[str(count)] = (self.state, review)
        duplicate = copy.deepcopy(self.review); duplicate["waits"][-1] = duplicate["waits"][0]
        cases["duplicate"] = (self.state, duplicate)
        missing = copy.deepcopy(self.review); missing["waits"][-1]["task_id"] = "not-in-state"
        cases["missing"] = (self.state, missing)
        extra_state = copy.deepcopy(self.state)
        extra_state[pilot.DELIVERY_STATE_KEY]["targets"]["factory"]["generations"]["factory-orphan"]["waits"]["extra"] = {}
        cases["extra-state"] = (extra_state, self.review)
        for name, (state, review) in cases.items():
            with self.subTest(name=name):
                args, _state_path, output, audit = self.fixture(state, review)
                self.run_tool(args, False)
                self.assertFalse(output.exists()); self.assertFalse(audit.exists())
                for path in (output, audit):
                    if path.exists(): path.unlink()

    def test_evidence_preimage_ancestry_and_journal_fail_closed(self):
        mutations = ("preimage", "release-info", "intent", "non-ancestor", "journal")
        for name in mutations:
            with self.subTest(name=name):
                state, review = copy.deepcopy(self.state), copy.deepcopy(self.review)
                args, state_path, output, audit = self.fixture(state, review)
                if name == "preimage":
                    state_path.write_text(state_path.read_text() + " ", encoding="utf-8")
                elif name == "release-info":
                    Path(args[args.index("--release-info") + 1]).write_text(json.dumps({"sha": "a" * 40}))
                elif name == "intent":
                    state["merge_intents"]["wait-00"]["commit_sha"] = "a" * 40
                    state_path.write_text(json.dumps(state)); args[args.index("--state-sha256") + 1] = hashlib.sha256(state_path.read_bytes()).hexdigest()
                elif name == "non-ancestor":
                    review["waits"][0]["verified_merge_sha"] = "a" * 40
                    Path(args[args.index("--manifest") + 1]).write_text(json.dumps(review))
                    state["merge_intents"]["wait-00"]["commit_sha"] = "a" * 40
                    state_path.write_text(json.dumps(state)); args[args.index("--state-sha256") + 1] = hashlib.sha256(state_path.read_bytes()).hexdigest()
                else:
                    Path(args[args.index("--release-journal") + 1]).write_text("phase=services-started\n")
                self.run_tool(args, False)
                self.assertFalse(output.exists()); self.assertFalse(audit.exists())

    def test_output_cannot_alias_or_overwrite_input(self):
        args, state_path, output, audit = self.fixture()
        args[args.index("--output-state") + 1] = str(state_path)
        self.run_tool(args, False)
        self.assertFalse(audit.exists())
        args, _state_path, output, audit = self.fixture()
        output.write_text("do not overwrite")
        self.run_tool(args, False)
        self.assertEqual(output.read_text(), "do not overwrite")
        self.assertFalse(audit.exists())


if __name__ == "__main__":
    unittest.main()
