"""Keep the native data-backed views installable by the inline OpenUI runtime."""

from pathlib import Path
import unittest

from validate_catalog import parse_frontmatter


ROOT = Path(__file__).resolve().parents[1]


class InlineViewTests(unittest.TestCase):
    def test_catalog_no_longer_ships_legacy_project_scaffolds(self):
        self.assertEqual(list((ROOT / "features").rglob("project-manifest.toml")), [])
        self.assertEqual(list((ROOT / "features").rglob("ui.openui")), [])
        for feature, folder in (
            ("tasks", "tasks"), ("goals", "goals"), ("monitors", "monitors"),
            ("people", "people"), ("shopping", "shopping"), ("travel", "travel"),
            ("decision-analysis", "decisions"),
        ):
            with self.subTest(feature=feature):
                root = ROOT / "features" / feature
                self.assertTrue((root / "README.md").is_file())
                self.assertTrue(list((root / "workspace" / folder).glob("*-template.md")))
                self.assertTrue(list((root / "workspace" / folder).glob("*.schema.json")))

    def test_profile_teaches_current_views_and_minion_links(self):
        root = ROOT / "profiles/personal-os"
        for name in ("AGENTS.md", "WORKSPACE_AGENTS.md", "SOUL.md"):
            with self.subTest(name=name):
                text = (root / name).read_text()
                self.assertNotIn("openlia://projects/", text)
                self.assertNotIn("project-manifest.toml", text)
                self.assertIn("openlia://minions/", text)
        for name in ("AGENTS.md", "WORKSPACE_AGENTS.md"):
            text = (root / name).read_text()
            self.assertIn("minion-authoring", text)
            self.assertIn("openui_validate", text)

    def test_native_views_are_markdown_not_mini_projects(self):
        for feature, folder, component, template in (
            ("calendar", "calendar", "Calendar", "event-note-template.md"),
        ):
            with self.subTest(feature=feature):
                root = ROOT / "features" / feature / "workspace" / folder
                view = (root / "overview.md").read_text()
                metadata, body = parse_frontmatter(view)
                template_metadata, template_body = parse_frontmatter((root / template).read_text())
                self.assertEqual(metadata, template_metadata)
                self.assertIn(f"```openui\nroot = {component}([views])", body)
                self.assertNotIn("RecordTable(", body)
                self.assertFalse((root / "ui.openui").exists())
                self.assertFalse((root / "project-manifest.toml").exists())
                # Overview documents honor their folder-local record contracts.
                for line in template_body.splitlines():
                    if line.startswith("## "):
                        self.assertIn(line, body)

    def test_finance_app_keeps_its_inline_view_outside_instance_data(self):
        root = ROOT / "features/personal-finance/workspace/minions/personal-finance"
        view = (root / "overview.md").read_text()
        metadata, body = parse_frontmatter(view)
        self.assertTrue((root / metadata["$schema"]).is_file())
        self.assertIn('dataPath: "minions/personal-finance/data"', body)
        self.assertFalse((root / "data").exists())


if __name__ == "__main__":
    unittest.main()
