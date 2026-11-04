import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
import main


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "minions/calendar"
        shutil.copytree(main.ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", "data", "config.json"))
        self.root_patch = patch.object(main, "ROOT", self.root)
        self.root_patch.start()
        self.environment = patch.dict(
            os.environ,
            {
                "OPENLIA_WORKSPACE_ROOT": str(self.workspace),
                "OPENLIA_MINION_CONFIG_JSON": json.dumps(
                    {"trigger": {"on_new_entry": False}, "calendar_file": "reminders.rem", "timezone": "UTC"}
                ),
            },
        )
        self.environment.start()
        self.native = patch.object(main, "run_native")
        self.native.start()

    def tearDown(self):
        self.native.stop()
        self.environment.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def payload(self, **changes):
        result = {
            "title": "Synthetic planning",
            "start": "2026-10-02T10:00:00+00:00",
            "end": "2026-10-02T11:30:00+00:00",
            "timezone": "UTC",
            "agenda": "Review launch readiness.",
            "attendees": "Alice, Bob",
            "location": "Room 1",
            "tags": "meeting, planning",
        }
        result.update(changes)
        return result

    def preview(self):
        return main.process_input(self.payload())["proposal_id"]

    def test_preview_then_confirm_creates_remind_entry_and_note(self):
        identifier = self.preview()
        self.assertFalse((self.root / "data/reminders.rem").exists())
        result = main.process_input({"action": "confirm", "proposal_id": identifier, "confirmation": "SAVE"})
        self.assertEqual(result["status"], "posted")
        reminder = (self.root / "data/reminders.rem").read_text()
        self.assertIn("REM NOQUEUE 2026-10-02 AT 10:00 DURATION 90 TZ UTC", reminder)
        self.assertIn("NOQUEUE", reminder)
        self.assertIn('INFO "Timezone: UTC"', reminder)
        self.assertIn("Synthetic planning", reminder)
        notes = list((self.root / "data/notes").glob("*.md"))
        self.assertEqual(len(notes), 1)
        note = notes[0].read_text()
        self.assertIn("$schema: ../../templates/event-note-template.schema.json", note)
        self.assertIn("Review launch readiness.", note)
        self.assertIn("minions/calendar/data/notes/", reminder)

    def test_cancel_never_creates_calendar_data(self):
        identifier = self.preview()
        result = main.process_input({"action": "cancel", "proposal_id": identifier})
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse((self.root / "data/reminders.rem").exists())
        self.assertFalse((self.root / "data/notes").exists())

    def test_changed_calendar_invalidates_pending_proposal(self):
        identifier = self.preview()
        calendar = self.root / "data/reminders.rem"
        calendar.write_text("# changed by another writer\n")
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            main.process_input({"action": "confirm", "proposal_id": identifier, "confirmation": "SAVE"})
        self.assertNotIn("Synthetic planning", calendar.read_text())

    def test_repeated_confirmation_is_rejected(self):
        identifier = self.preview()
        main.process_input({"action": "confirm", "proposal_id": identifier, "confirmation": "SAVE"})
        with self.assertRaisesRegex(ValueError, "already completed"):
            main.process_input({"action": "confirm", "proposal_id": identifier, "confirmation": "SAVE"})

    def test_timezone_and_duration_boundaries_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "nonexistent"):
            main.process_input(self.payload(
                start="2026-03-08T02:30:00-05:00",
                end="2026-03-08T03:30:00-04:00",
                timezone="America/New_York",
            ))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            main.process_input(self.payload(
                start="2026-11-01T01:30:00-04:00",
                end="2026-11-01T02:30:00-05:00",
                timezone="America/New_York",
            ))
        with self.assertRaisesRegex(ValueError, "seven days"):
            main.process_input(self.payload(end="2026-10-10T11:30:00+00:00"))

    def test_literal_includes_are_preserved_and_unsafe_includes_rejected(self):
        data = self.root / "data"
        data.mkdir()
        (data / "reminders.rem").write_text("INCLUDE work.rem\n")
        (data / "work.rem").write_text("# existing\n")
        identifier = self.preview()
        main.process_input({"action": "confirm", "proposal_id": identifier, "confirmation": "SAVE"})
        self.assertTrue((data / "work.rem").read_text().startswith("# existing"))
        (data / "reminders.rem").write_text("INCLUDE ../../secret.rem\n")
        with self.assertRaisesRegex(ValueError, "literal relative"):
            main.process_input(self.payload())

    def test_invalid_input_and_symlink_are_rejected(self):
        with self.assertRaises((ValueError, jsonschema.ValidationError)):
            main.process_input(self.payload(start="2026-10-02T10:00:00"))
        with self.assertRaisesRegex(ValueError, "expression brackets"):
            main.process_input(self.payload(title="Unsafe [expression]"))
        data = self.root / "data"
        shutil.rmtree(data)
        data.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            main.process_input(self.payload())

    def test_dashboard_has_calendar_views_without_seeded_data(self):
        dashboard = main.render_dashboard()
        self.assertIn("CalendarMonth()", dashboard)
        self.assertIn("CalendarWeek()", dashboard)
        self.assertIn("GanttChart()", dashboard)
        self.assertFalse((self.root / "data").exists())


if __name__ == "__main__":
    unittest.main()
