"""Keep the native data-backed views installable by the inline OpenUI runtime."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InlineViewTests(unittest.TestCase):
    def test_catalog_no_longer_ships_legacy_project_scaffolds(self):
        self.assertEqual(list((ROOT / "features").rglob("project-manifest.toml")), [])
        self.assertEqual(list((ROOT / "features").rglob("ui.openui")), [])
        self.assertEqual(list((ROOT / "features").rglob("minion.package.json")), [])
        for feature, folder in (
            ("tasks", "tasks"), ("goals", "goals"), ("monitors", "monitors"),
            ("people", "people"), ("shopping", "shopping"), ("travel", "travel"),
            ("decision-analysis", "decisions"), ("calendar", "calendar"),
            ("personal-finance", "finance"), ("personal-health", "health"),
        ):
            with self.subTest(feature=feature):
                root = ROOT / "features" / feature
                self.assertTrue((root / "README.md").is_file())
                self.assertTrue(list((root / "workspace" / folder).rglob("*-template.md")))
                self.assertTrue(list((root / "workspace" / folder).rglob("*.schema.json")))

    def test_profile_teaches_current_views(self):
        root = ROOT / "profiles/personal-os"
        for name in ("AGENTS.md", "WORKSPACE_AGENTS.md", "SOUL.md"):
            with self.subTest(name=name):
                text = (root / name).read_text()
                self.assertNotIn("openlia://projects/", text)
                self.assertNotIn("project-manifest.toml", text)
                self.assertNotIn("openlia://minions/", text)
                self.assertNotIn("minion-authoring", text)
        for name in ("AGENTS.md", "WORKSPACE_AGENTS.md"):
            text = (root / name).read_text()
            self.assertIn("openui_validate", text)


if __name__ == "__main__":
    unittest.main()
