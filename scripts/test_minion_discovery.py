"""Exercise distributed workflow helpers without running any Minion code."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workspace_registry as registry


ROOT = Path(__file__).resolve().parents[1]
COPIES = sorted((ROOT / "skills").glob("*/scripts/workspace_registry.py")) + sorted(
    (ROOT / "features").glob("*/skills/*/scripts/workspace_registry.py")
)


class MinionDiscoveryTests(unittest.TestCase):
    def test_distributed_helpers_match_the_canonical_source(self):
        self.assertEqual(len(COPIES), 5)
        canonical = (ROOT / "scripts/workspace_registry.py").read_bytes()
        for path in COPIES:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(path.read_bytes(), canonical)

    def test_apps_are_pruned_but_intentional_reports_are_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "minions/gym-tracker"
            app.mkdir(parents=True)
            (app / "README.md").write_text(
                "---\nname: Gym Tracker\ndescription: Workout app\n---\n# Gym\n"
            )
            (app / "main.py").write_text("raise RuntimeError('never execute during discovery')\n")
            for name in ("data/history", "tests", "scripts", "node_modules/pkg", ".venv/pkg"):
                folder = app / name
                folder.mkdir(parents=True)
                (folder / "record-template.md").write_text("# Not a collection\n")
                (folder / "example.md").write_text("# INTERNAL_APP_RECORD\n")
            export = root / "reports/fitness"
            export.mkdir(parents=True)
            (export / "2026-11-02.md").write_text("# Published workout review\nSource-linked observations.\n")

            walked = []
            original_walk = os.walk

            def record_walk(*args, **kwargs):
                for item in original_walk(*args, **kwargs):
                    walked.append(Path(item[0]))
                    yield item

            with patch.object(registry.os, "walk", side_effect=record_walk):
                result = registry.load_registry(root)
            by_path = {item["path"]: item for item in result["domains"]}
            self.assertEqual([p for p in by_path if p.startswith("minions")], ["minions/gym-tracker"])
            self.assertTrue(by_path["minions/gym-tracker"]["minion"])
            self.assertEqual(by_path["minions/gym-tracker"]["label"], "Gym Tracker")
            self.assertFalse(by_path["minions/gym-tracker"]["include_in_briefing"])
            self.assertFalse(any(p == app or app in p.parents for p in walked))
            sources = {item["path"] for item in registry.briefing_sources(result)}
            self.assertIn("reports/fitness", sources)
            self.assertFalse(any(p.startswith("minions") for p in sources))

            # Exercise each separately installed collector, not just the registry.
            for path in (
                ROOT / "skills/daily-briefing/scripts/build_briefing.py",
                ROOT / "features/daily-briefing/skills/daily-briefing/scripts/build_briefing.py",
            ):
                with self.subTest(collector=path.relative_to(ROOT)):
                    collected = subprocess.run(
                        [sys.executable, str(path), "--collect", "--workspace-root", str(root),
                         "--date", "2026-11-02", "--recent-days", "3650"],
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(collected.returncode, 0, collected.stderr)
                    self.assertNotIn("INTERNAL_APP_RECORD", collected.stdout)
                    self.assertIn("Published workout review", collected.stdout)

    def test_calendar_minion_is_read_through_native_remind_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "minions/calendar"
            data = app / "data"
            data.mkdir(parents=True)
            (app / "README.md").write_text(
                "---\nname: Calendar\ndescription: Native Remind calendar\n---\n# Calendar\n"
            )
            (app / "main.py").write_text("raise RuntimeError('must not execute')\n")
            (data / "reminders.rem").write_text("# Native source\n")
            (data / "notes").mkdir()
            (data / "notes/internal.md").write_text("# INTERNAL_NOTE\n")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            remind = fake_bin / "remind"
            remind.write_text(
                "#!/bin/sh\n"
                "printf '%s' '[{\"caltype\":\"monthly\",\"entries\":[{\"date\":\"2026-11-02\",\"eventstart_in_tz\":\"2026-11-02T10:00\",\"eventduration\":60,\"body\":\"Native planning\",\"info\":{\"description\":\"Launch review\"}}]}]'\n"
            )
            remind.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
            for path in (
                ROOT / "skills/daily-briefing/scripts/build_briefing.py",
                ROOT / "features/daily-briefing/skills/daily-briefing/scripts/build_briefing.py",
            ):
                with self.subTest(collector=path.relative_to(ROOT)):
                    collected = subprocess.run(
                        [sys.executable, str(path), "--collect", "--workspace-root", str(root),
                         "--date", "2026-11-02"],
                        capture_output=True, text=True, timeout=20, env=environment,
                    )
                    self.assertEqual(collected.returncode, 0, collected.stderr)
                    self.assertIn("Native planning", collected.stdout)
                    self.assertIn("minions/calendar/data/reminders.rem", collected.stdout)
                    self.assertNotIn("INTERNAL_NOTE", collected.stdout)

    def test_invalid_ids_symlinks_and_dependencies_are_not_collections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("minions/Invalid_ID", "minions/.hidden", "node_modules/pkg", "notes/__pycache__"):
                folder = root / name
                folder.mkdir(parents=True)
                (folder / "example.md").write_text("# Not a collection\n")
            outside = root / ".outside"
            outside.mkdir()
            (outside / "example.md").write_text("# Private\n")
            (root / "minions/linked-app").symlink_to(outside, target_is_directory=True)
            (root / "linked-records").symlink_to(outside, target_is_directory=True)
            paths = {item["path"] for item in registry.discover_domains(root)}
            self.assertFalse(any(p.startswith("minions") for p in paths))
            self.assertNotIn("node_modules", paths)
            self.assertNotIn("notes/__pycache__", paths)
            self.assertNotIn("linked-records", paths)

    def test_malformed_or_symlinked_readme_is_not_a_discovery_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "minions/unfinished-app"
            app.mkdir(parents=True)
            readme = app / "README.md"
            readme.write_text("---\nname: [invalid\n---\n# Unfinished\n")
            for _ in range(2):
                by_path = {item["path"]: item for item in registry.discover_domains(root)}
                self.assertTrue(by_path["minions/unfinished-app"]["minion"])
                self.assertFalse(by_path["minions/unfinished-app"]["include_in_briefing"])
                readme.unlink()
                readme.symlink_to(root / "missing.md")

    def test_organizing_audit_does_not_read_app_internals(self):
        path = ROOT / "skills/workspace-organize/scripts/audit_workspace.py"
        spec = importlib.util.spec_from_file_location("minion_audit", path)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("minions/gym-tracker/tests", "node_modules/pkg"):
                folder = root / name
                folder.mkdir(parents=True)
                (folder / "example.md").write_text("# Internal\n[Broken](missing.md)\n(deleted source: src_internal)\n")
            reports = root / "reports"
            reports.mkdir()
            (reports / "review.md").write_text("# Review\n[Broken](missing.md)\n")
            result = audit.run_audit(root)
            self.assertEqual([item["file"] for item in result["issues"]], ["reports/review.md"])


if __name__ == "__main__":
    unittest.main()
