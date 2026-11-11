"""Exercise distributed workflow helpers and workspace registry discovery."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import workspace_registry as registry

ROOT = Path(__file__).resolve().parents[1]
COPIES = sorted((ROOT / "skills").glob("*/scripts/workspace_registry.py")) + sorted(
    (ROOT / "features").glob("*/skills/*/scripts/workspace_registry.py")
)


class WorkspaceRegistryTests(unittest.TestCase):
    def test_distributed_helpers_match_the_canonical_source(self):
        self.assertEqual(len(COPIES), 5)
        canonical = (ROOT / "scripts/workspace_registry.py").read_bytes()
        for path in COPIES:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(path.read_bytes(), canonical)

    def test_invalid_ids_symlinks_and_dependencies_are_not_collections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("node_modules/pkg", "notes/__pycache__", ".hidden/sub"):
                folder = root / name
                folder.mkdir(parents=True)
                (folder / "example.md").write_text("# Not a collection\n")
            outside = root / ".outside"
            outside.mkdir()
            (outside / "example.md").write_text("# Private\n")
            (root / "linked-records").symlink_to(outside, target_is_directory=True)
            paths = {item["path"] for item in registry.discover_domains(root)}
            self.assertNotIn("node_modules", paths)
            self.assertNotIn("notes/__pycache__", paths)
            self.assertNotIn("linked-records", paths)

    def test_organizing_audit_does_not_read_dependencies(self):
        path = ROOT / "skills/workspace-organize/scripts/audit_workspace.py"
        spec = importlib.util.spec_from_file_location("ws_audit", path)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("node_modules/pkg", ".venv/lib"):
                folder = root / name
                folder.mkdir(parents=True)
                (folder / "example.md").write_text("# Internal\n[Broken](missing.md)\n")
            reports = root / "reports"
            reports.mkdir()
            (reports / "review.md").write_text("# Review\n[Broken](missing.md)\n")
            result = audit.run_audit(root)
            self.assertEqual([item["file"] for item in result["issues"]], ["reports/review.md"])


if __name__ == "__main__":
    unittest.main()
