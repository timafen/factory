#!/usr/bin/env python3
"""Switch the existing Factory patrol Automation to the Codex auth checker."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


AUTOMATION_TITLE = "Патруль Factory"
BLOCK_START = "[codex-auth-monitoring]"
BLOCK_END = "[/codex-auth-monitoring]"
MONITORING_BLOCK = """[codex-auth-monitoring]
Run `bash ops/check-codex-auth-permissions.sh` from the checked-out Factory repository.
Exit code 0 is healthy; a nonzero exit is a finding. Use only the reported path and target metadata.
Do not inspect the symlink mode with `stat -c`: `regular file 600 factory factory` is healthy even if the link displays mode 777.
Never run chmod or chown for this check, and never read or print auth.json contents.
[/codex-auth-monitoring]"""


class API:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"Factory API request failed: {method} {path}: HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Factory API request failed: {method} {path}: {error}") from error


def monitoring_context(context: str) -> str:
    start = context.find(BLOCK_START)
    end = context.find(BLOCK_END)
    if start >= 0 and end >= start:
        end += len(BLOCK_END)
        return f"{context[:start].rstrip()}\n\n{MONITORING_BLOCK}{context[end:]}".strip()
    return f"{context.rstrip()}\n\n{MONITORING_BLOCK}".strip()


def find_automation(api: API, title: str) -> dict:
    matches = [item for item in api.request("/automations?limit=200")["automations"] if item["title"] == title]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one Automation titled {title!r}, found {len(matches)}")
    return matches[0]


def occurrence_ids(api: API, automation_id: str) -> set[str]:
    result: set[str] = set()
    cursor = None
    while True:
        query = "?limit=200"
        if cursor:
            query += "&cursor=" + urllib.parse.quote(cursor)
        page = api.request(f"/automations/{automation_id}/occurrences{query}")
        result.update(item["id"] for item in page["occurrences"])
        cursor = page.get("next_cursor")
        if not cursor:
            return result


def update(api: API, title: str) -> dict:
    before = find_automation(api, title)
    automation_id = before["id"]
    before_occurrences = occurrence_ids(api, automation_id)
    new_context = monitoring_context(before["context"])

    if new_context != before["context"]:
        enabled = before["enabled"]
        if enabled:
            api.request(f"/automations/{automation_id}/enabled", "PUT", {"enabled": False})
        try:
            api.request(
                f"/automations/{automation_id}",
                "PUT",
                {
                    "expected_version": before["version"],
                    "title": before["title"],
                    "workflow_id": before["workflow_id"],
                    "context": new_context,
                    "timeout_seconds": before["timeout_seconds"],
                    "trigger": before["trigger"],
                },
            )
        finally:
            if enabled:
                api.request(f"/automations/{automation_id}/enabled", "PUT", {"enabled": True})

    after = find_automation(api, title)
    after_occurrences = occurrence_ids(api, automation_id)
    checks = {
        "same_automation_id": after["id"] == automation_id,
        "same_schedule": after["trigger"] == before["trigger"],
        "same_enabled_state": after["enabled"] == before["enabled"],
        "history_preserved": before_occurrences <= after_occurrences,
        "checker_is_configured": MONITORING_BLOCK in after["context"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"post-update verification failed: {checks}")
    return {
        "automation": title,
        "automation_id": automation_id,
        "version_before": before["version"],
        "version_after": after["version"],
        "schedule": after["trigger"],
        "occurrences_before": len(before_occurrences),
        "occurrences_after": len(after_occurrences),
        "checker_command": "bash ops/check-codex-auth-permissions.sh",
        "verification": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:7337/api/v1")
    parser.add_argument("--automation-title", default=AUTOMATION_TITLE)
    args = parser.parse_args()
    try:
        print(json.dumps(update(API(args.api_url), args.automation_title), ensure_ascii=False, indent=2))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
