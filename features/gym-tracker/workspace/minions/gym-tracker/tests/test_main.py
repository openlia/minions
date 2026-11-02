import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

import input as minion_input
import main

ROOT = Path(__file__).resolve().parent.parent


class GymTrackerMinionTests(unittest.TestCase):
    def test_schema_validation_and_entry_recording(self):
        schema = minion_input.load_schema()
        self.assertEqual(schema.get("type"), "object")
        validated = minion_input.validate_payload(
            {"item": "Barbell Back Squat 3x5", "category": "strength", "value": 100},
            schema,
        )
        self.assertEqual(validated["item"], "Barbell Back Squat 3x5")
        self.assertEqual(validated["category"], "strength")
        self.assertEqual(validated["value"], 100)
        with self.assertRaises(ValueError):
            minion_input.validate_payload({}, schema)

    def test_isolated_entry_and_heartbeat_update_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            items_file = tmp_path / "data" / "items.json"
            context_file = tmp_path / "data" / "context.json"
            dashboard_file = tmp_path / "dashboard.openui"
            with (
                patch.object(minion_input, "DATA_FILE", items_file),
                patch.object(main, "DATA_FILE", items_file),
                patch.object(main, "CONTEXT_FILE", context_file),
                patch.object(main, "DASHBOARD_FILE", dashboard_file),
            ):
                entry = minion_input.record_entry(
                    {"item": "Bench Press 3x5", "category": "strength", "value": 80},
                    today="2026-11-02",
                )
                ctx = main.analyze_new_entry(entry)
                self.assertIn("80 kg", ctx["latest_recommendation"])
                ui = dashboard_file.read_text(encoding="utf-8")
                self.assertIn("Table(", ui)
                self.assertIn("Callout(", ui)
                hb = main.run_heartbeat()
                self.assertEqual(hb["enrichment"]["total_entries"], 1)

    def test_config_contract_and_package_manifest(self):
        cfg = main.load_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("trigger", cfg)
        pkg = json.loads((ROOT / "minion.package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["schema"], 1)
        self.assertNotIn("config.json", pkg["files"])


if __name__ == "__main__":
    unittest.main()
