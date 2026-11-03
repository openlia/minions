"""Run each distributable Python app's tests in isolation (no module-name clashes)."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CatalogAppTests(unittest.TestCase):
    def test_python_app_suites(self):
        apps = sorted((ROOT / "features").glob("*/workspace/minions/*/main.py"))
        self.assertGreaterEqual(len(apps), 3)
        for entrypoint in apps:
            with self.subTest(app=entrypoint.parent.name):
                result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                        cwd=entrypoint.parent, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
