#!/usr/bin/env python3
"""Build an operator-reviewable recovered Pilot state; never edit live state."""

import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

SHA_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


class ReconcileError(Exception):
    pass


def read_bytes(path):
    try:
        with open(path, "rb") as stream:
            return stream.read()
    except OSError as error:
        raise ReconcileError(f"cannot read {path}: {error}") from error


def read_json(path):
    try:
        return json.loads(read_bytes(path))
    except (ValueError, UnicodeDecodeError) as error:
        raise ReconcileError(f"invalid JSON {path}: {error}") from error


def digest(body):
    return hashlib.sha256(body).hexdigest()


def atomic_json(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".reconcile-", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def arguments(argv):
    parser = argparse.ArgumentParser(description="verify and prepare exactly 28 Factory delivery waits")
    parser.add_argument("--state-copy", required=True)
    parser.add_argument("--state-sha256", required=True)
    parser.add_argument("--release-info", required=True)
    parser.add_argument("--generation-manifest", required=True)
    parser.add_argument("--current-generation", required=True)
    parser.add_argument("--release-journal", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-state", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--now", help="fixed RFC3339 audit time for a reproducible fixture")
    return parser.parse_args(argv)


def validate_paths(args):
    state = os.path.realpath(args.state_copy)
    for output in (args.output_state, args.audit_output):
        if os.path.realpath(output) == state:
            raise ReconcileError("output must not be the input/live state")
        if os.path.exists(output):
            raise ReconcileError(f"refusing to overwrite {output}")
    if os.path.realpath(args.output_state) == os.path.realpath(args.audit_output):
        raise ReconcileError("state and audit outputs must be distinct")
    if os.path.exists(args.release_journal):
        raise ReconcileError("release transaction journal is unfinished")
    if os.path.realpath(os.path.dirname(args.generation_manifest)) != os.path.realpath(args.current_generation):
        raise ReconcileError("current generation does not point at the supplied manifest")


def validate_manifest(document):
    if document.get("target") != "factory" or document.get("format") != 1:
        raise ReconcileError("manifest target/format is not factory/1")
    release_sha = document.get("release_sha", "")
    if not SHA_RE.fullmatch(release_sha):
        raise ReconcileError("manifest release_sha is invalid")
    audit_id = document.get("audit_id", "")
    generation_id = document.get("generation_id", "")
    entries = document.get("waits")
    if not isinstance(audit_id, str) or not audit_id or not isinstance(generation_id, str) or not generation_id:
        raise ReconcileError("manifest requires audit_id and generation_id")
    if not isinstance(entries, list) or len(entries) != 28:
        raise ReconcileError("manifest must contain exactly 28 waits")
    pairs = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReconcileError("every wait entry must be an object")
        task_id, merge_sha = entry.get("task_id"), entry.get("verified_merge_sha")
        if not isinstance(task_id, str) or not task_id or not SHA_RE.fullmatch(merge_sha or ""):
            raise ReconcileError("wait entry has invalid task_id or verified_merge_sha")
        pairs.append((task_id, merge_sha))
    if len({task for task, _sha in pairs}) != 28 or len(set(pairs)) != 28:
        raise ReconcileError("manifest wait entries are not unique")
    return release_sha, audit_id, generation_id, pairs


def verify_ancestry(repo, pairs, release_sha):
    for _task_id, merge_sha in pairs:
        result = subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor", merge_sha, release_sha],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if result.returncode != 0:
            raise ReconcileError(f"verified merge {merge_sha} is not an ancestor of release")


def reconcile(args):
    validate_paths(args)
    state_body = read_bytes(args.state_copy)
    if not re.fullmatch(r"[0-9a-f]{64}", args.state_sha256) or digest(state_body) != args.state_sha256:
        raise ReconcileError("state preimage checksum changed")
    state = json.loads(state_body)
    review_body = read_bytes(args.manifest)
    review = json.loads(review_body)
    release_sha, audit_id, generation_id, pairs = validate_manifest(review)
    release_info = read_json(args.release_info)
    generation_manifest = read_json(args.generation_manifest)
    if release_info.get("sha") != release_sha or generation_manifest.get("candidate_sha") != release_sha:
        raise ReconcileError("release SHA evidence does not agree")

    durable = state.get("delivery_state_v2")
    target = durable.get("targets", {}).get("factory") if isinstance(durable, dict) else None
    generation = target.get("generations", {}).get(generation_id) if isinstance(target, dict) else None
    if not isinstance(generation, dict):
        raise ReconcileError("selected orphan generation is absent")
    waits = generation.get("waits")
    task_ids = {task_id for task_id, _sha in pairs}
    if not isinstance(waits, dict) or set(waits) != task_ids or len(waits) != 28:
        raise ReconcileError("manifest and orphan wait set are not exactly equal")
    intents = state.get("merge_intents")
    for task_id, merge_sha in pairs:
        intent = intents.get(task_id) if isinstance(intents, dict) else None
        if not isinstance(intent, dict) or intent.get("commit_sha") != merge_sha:
            raise ReconcileError(f"merge intent mismatch for {task_id}")
        if task_id in generation.get("completed_waits", {}):
            raise ReconcileError(f"wait is already completed: {task_id}")
    verify_ancestry(args.repo, pairs, release_sha)

    audits = durable.setdefault("audit", {}).setdefault("reconciliations", {})
    if audit_id in audits:
        recovered = copy.deepcopy(state)
        outcome = "noop"
    else:
        recovered = copy.deepcopy(state)
        recovered_durable = recovered["delivery_state_v2"]
        recovered_generation = recovered_durable["targets"]["factory"]["generations"][generation_id]
        recovered_generation["phase"] = "completed"
        recovered_generation["finished_at"] = args.now or datetime.datetime.now(datetime.timezone.utc).isoformat()
        recovered_durable.setdefault("audit", {}).setdefault("reconciliations", {})[audit_id] = {
            "manifest_sha256": digest(review_body), "release_sha": release_sha, "count": 28,
        }
        outcome = "prepared"

    encoded = (json.dumps(recovered, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    audit = {
        "format": 1, "audit_id": audit_id, "result": outcome, "target": "factory",
        "generation_id": generation_id, "release_sha": release_sha, "count": 28,
        "manifest_sha256": digest(review_body), "old_state_sha256": digest(state_body),
        "new_state_sha256": digest(encoded),
        "at": args.now or datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    atomic_json(args.output_state, recovered)
    atomic_json(args.audit_output, audit)
    return audit


def main(argv=None):
    try:
        result = reconcile(arguments(argv))
    except (ReconcileError, OSError, ValueError) as error:
        print(f"reconciliation refused: {error}", file=sys.stderr)
        return 2
    print(f"reconciliation {result['result']}: {result['count']} waits; live state unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
