import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
import main


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "minions/personal-health"
        shutil.copytree(main.ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", "data", "config.json"))
        self.root_patch = patch.object(main, "ROOT", self.root)
        self.root_patch.start()
        self.environment = patch.dict(os.environ, {"OPENLIA_WORKSPACE_ROOT": str(self.workspace),
                                                   "OPENLIA_MINION_CONFIG_JSON": '{"trigger":{"on_new_entry":false}}'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def profile(self, person="person-001", name="Synthetic Person"):
        return main.record_entry(dict(record_type="profile", person_id=person, title=name, relationship_to_user="self"))

    def test_refresh_has_no_seeded_data(self):
        self.assertIn("not medical diagnoses", main.render_dashboard())
        self.assertFalse((self.root / "data").exists())

    def test_profiles_encounters_conditions_treatments_and_measurements(self):
        self.profile()
        examples = [dict(record_type="encounter", event_date="2026-10", title="Synthetic visit"),
                    dict(record_type="condition", title="Reported condition"),
                    dict(record_type="treatment", title="Reported care"),
                    dict(record_type="measurement", event_date="2026-10-02T12:00:00+07:00", title="Synthetic value", value="0.10", unit="mg")]
        for example in examples:
            result = main.record_entry(dict(person_id="person-001", source_ref="openlia://source/synthetic#v1", **example))
            record = self.root / result["path"]
            fields, _ = main.read_record(record)
            self.assertEqual(fields["person_id"], "person-001")
            self.assertTrue((record.parent / fields["$schema"]).is_file())
            if example["record_type"] == "measurement":
                self.assertEqual(fields["results"][0]["value"], "0.10")
                self.assertIsNone(fields["results"][0]["interpretation"])
            if example["record_type"] == "condition":
                self.assertEqual(fields["kind"], "other")
                self.assertEqual(fields["verification_status"], "reported")
                self.assertEqual(fields["clinical_status"], "unknown")
        audit = main.audit_health(self.workspace)
        self.assertEqual(audit["total_issues"], 0, audit)
        self.assertEqual(audit["record_counts"]["history"], 2)

    def test_family_members_have_separate_paths_and_dashboard_tables(self):
        self.profile()
        main.record_entry(dict(record_type="profile", person_id="person-002", title="Synthetic Child", relationship_to_user="child"))
        result = main.record_entry(dict(record_type="encounter", person_id="person-002", title="Child visit", event_date="2026"))
        self.assertIn("history/person-002/", result["path"])
        dashboard = main.render_dashboard()
        self.assertIn("person-001 (self)", dashboard)
        self.assertIn("person-002 (child)", dashboard)
        self.assertIn("Child visit", dashboard)

    def test_unknown_person_and_duplicate_profile_refuse(self):
        with self.assertRaises(FileNotFoundError):
            main.record_entry(dict(record_type="encounter", person_id="unknown", title="Unknown", event_date="2026"))
        self.profile()
        before = (self.root / "data/profiles/person-001.md").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.profile(name="Overwrite")
        self.assertEqual((self.root / "data/profiles/person-001.md").read_bytes(), before)

    def test_no_inferred_diagnoses_or_prescriptions(self):
        self.profile()
        for fields in (dict(record_type="condition", verification_status="confirmed"),
                       dict(record_type="treatment", treatment_intent="prescribed")):
            with self.assertRaisesRegex(ValueError, "evidence"):
                main.record_entry(dict(person_id="person-001", title="Unsupported", **fields))

    def test_dates_units_and_identity_are_validated(self):
        self.profile()
        for fields in (dict(event_date="2026-02-30", unit="kg"), dict(event_date="2026-10-02T12:00:00", unit="kg"),
                       dict(event_date="2026-10-02")):
            with self.assertRaises((ValueError, jsonschema.ValidationError)):
                main.record_entry(dict(record_type="measurement", person_id="person-001", title="Synthetic", value="12", **fields))
        with self.assertRaises(jsonschema.ValidationError):
            main.record_entry(dict(record_type="profile", person_id="../outside", title="Invalid", relationship_to_user="self"))

    def test_existing_cross_person_links_block_new_writes(self):
        self.profile()
        record = self.root / "data/history/person-001/broken.md"
        record.parent.mkdir(parents=True)
        record.write_text("---\nid: bad\nperson_id: person-002\n---\n# Mismatch\n")
        with self.assertRaisesRegex(ValueError, "integrity audit"):
            main.record_entry(dict(record_type="encounter", person_id="person-001", title="Do not save", event_date="2026"))
        self.assertEqual(len(list(record.parent.glob("*.md"))), 1)

    def test_symlinks_refuse(self):
        (self.root / "data").symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.profile()
