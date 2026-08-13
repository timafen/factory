import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.renumber_historical_cards import main, validate_plan


class RenumberHistoricalCardsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        cards = self.root / "knowledge" / "cards"
        cards.mkdir(parents=True)
        for name in (
            "CARD-0001-zeta.md",
            "CARD-0001-alpha.md",
            "CARD-0002-beta.md",
            "CARD-0002-alpha.md",
        ):
            (cards / name).write_text(f"status in {name}\n", encoding="utf-8")
        (cards / "CARD-0001-zeta.md").write_text(
            "knowledge/cards/CARD-0001-zeta.md\n", encoding="utf-8"
        )
        (self.root / "notes.md").write_text(
            "knowledge/cards/CARD-0001-zeta.md\nCARD-0001\n"
            "knowledge/cards/CARD-0002-beta.md\n",
            encoding="utf-8",
        )
        (self.root / "fixture.py").write_text(
            "CARD-0002-alpha.md is only a suffix, not a path\n", encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def run_tool(self, *args):
        return subprocess.run(
            ["python3", "-m", "scripts.renumber_historical_cards", "--root", str(self.root), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_dry_run_is_deterministic_and_does_not_write(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("knowledge/cards/CARD-0001-zeta.md -> knowledge/cards/CARD-0003-zeta.md", result.stdout)
        self.assertIn("knowledge/cards/CARD-0002-beta.md -> knowledge/cards/CARD-0004-beta.md", result.stdout)
        self.assertTrue((self.root / "knowledge/cards/CARD-0001-alpha.md").exists())

    def test_apply_replaces_only_full_paths_and_second_run_is_empty(self):
        result = self.run_tool("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "knowledge/cards/CARD-0001-zeta.md").exists())
        self.assertTrue((self.root / "knowledge/cards/CARD-0003-zeta.md").exists())
        notes = (self.root / "notes.md").read_text(encoding="utf-8")
        self.assertIn("knowledge/cards/CARD-0003-zeta.md", notes)
        self.assertIn(
            "knowledge/cards/CARD-0003-zeta.md",
            (self.root / "knowledge/cards/CARD-0003-zeta.md").read_text(),
        )
        self.assertIn("CARD-0001\n", notes)
        self.assertIn("CARD-0002-alpha.md is only a suffix", (self.root / "fixture.py").read_text())
        second = self.run_tool()
        self.assertEqual(second.stdout.strip(), "No duplicate card numbers found.")

    def test_existing_target_is_rejected_without_changes(self):
        target = self.root / "knowledge/cards/CARD-0003-alpha.md"
        target.write_text("occupied", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "target card already exists"):
            validate_plan(
                self.root,
                [(self.root / "knowledge/cards/CARD-0001-alpha.md", target)],
            )
        self.assertTrue((self.root / "knowledge/cards/CARD-0001-alpha.md").exists())


if __name__ == "__main__":
    unittest.main()
