#!/usr/bin/env python3
"""Plan and apply the one-time renumbering of duplicate knowledge cards."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


CARD_RE = re.compile(r"^(CARD-(\d{4}))(?:-.+)?\.md$")


def card_files(root: Path) -> list[Path]:
    cards = root / "knowledge" / "cards"
    return sorted(path for path in cards.glob("CARD-*.md") if CARD_RE.match(path.name))


def plan_renumbering(root: Path) -> list[tuple[Path, Path]]:
    files = card_files(root)
    groups: dict[str, list[Path]] = {}
    for path in files:
        number = CARD_RE.match(path.name).group(1)
        groups.setdefault(number, []).append(path)

    used = {int(CARD_RE.match(path.name).group(2)) for path in files}
    next_number = max(used, default=0) + 1
    plan: list[tuple[Path, Path]] = []
    for number in sorted(groups):
        duplicates = groups[number][1:]
        for source in duplicates:
            while next_number in used:
                next_number += 1
            target = source.with_name(
                source.name.replace(number, f"CARD-{next_number:04d}", 1)
            )
            plan.append((source, target))
            used.add(next_number)
            next_number += 1
    return plan


def tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(path for path in root.rglob("*") if path.is_file())
    return [root / name.decode() for name in result.stdout.split(b"\0") if name]


def validate_plan(root: Path, plan: list[tuple[Path, Path]]) -> None:
    sources = {source for source, _ in plan}
    targets = [target for _, target in plan]
    if len(targets) != len(set(targets)):
        raise RuntimeError("renumbering plan assigns the same target more than once")
    for source, target in plan:
        if not source.is_file():
            raise RuntimeError(f"source card does not exist: {source.relative_to(root)}")
        if target.exists() and target not in sources:
            raise RuntimeError(f"target card already exists: {target.relative_to(root)}")
        if not target.is_relative_to(root):
            raise RuntimeError("renumbering target escapes the repository root")


def replace_references(root: Path, plan: list[tuple[Path, Path]]) -> None:
    replacements = {
        source.relative_to(root).as_posix(): target.relative_to(root).as_posix()
        for source, target in plan
    }
    moved_paths = {source: target for source, target in plan}
    for path in tracked_files(root):
        if not path.is_file() and path in moved_paths:
            path = moved_paths[path]
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def apply_plan(root: Path, plan: list[tuple[Path, Path]]) -> None:
    validate_plan(root, plan)
    if not plan:
        return
    temporary: list[tuple[Path, Path]] = []
    for index, (source, target) in enumerate(plan):
        temporary_path = source.with_name(f".renumber-{index:04d}-{source.name}")
        source.rename(temporary_path)
        temporary.append((temporary_path, target))
    for temporary_path, target in temporary:
        temporary_path.rename(target)
    replace_references(root, plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true", help="apply the displayed plan")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    plan = plan_renumbering(root)
    validate_plan(root, plan)
    for source, target in plan:
        print(f"{source.relative_to(root)} -> {target.relative_to(root)}")
    if args.apply:
        apply_plan(root, plan)
        if plan:
            print(f"Applied {len(plan)} renames.")
    elif not plan:
        print("No duplicate card numbers found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
