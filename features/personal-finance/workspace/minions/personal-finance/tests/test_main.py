import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import jsonschema
import main


@unittest.skipUnless(shutil.which("hledger"), "Native hledger is required")
class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "minions/personal-finance"
        shutil.copytree(main.ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", "data", "config.json"))
        self.root_patch = patch.object(main, "ROOT", self.root)
        self.root_patch.start()
        self.environment = patch.dict(os.environ, {"OPENLIA_WORKSPACE_ROOT": str(self.workspace),
                                                   "OPENLIA_MINION_CONFIG_JSON": json.dumps({"trigger": {"on_new_entry": False}, "journal": "journal.hledger"})})
        self.environment.start()
        self.payload = dict(date="2026-10-02", description="Synthetic groceries", amount="10.01", commodity="USD",
                            debit_account="expenses:food", credit_account="assets:checking",
                            source_ref="openlia://source/synthetic#v1/p1")

    def tearDown(self):
        self.environment.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def preview(self):
        return main.process_input(self.payload)["proposal_id"]

    def confirm(self, identifier):
        return main.process_input(dict(action="confirm", proposal_id=identifier, confirmation="POST"))

    def test_preview_never_creates_journal_confirmation_posts_once(self):
        identifier = self.preview()
        journal = self.root / "data/journal.hledger"
        self.assertFalse(journal.exists())
        self.assertEqual(self.confirm(identifier)["status"], "posted")
        content = journal.read_text()
        self.assertIn("10.01 USD", content)
        self.assertIn(self.payload["source_ref"], content)
        self.assertIn("direct-request", (self.root / f"data/intake/{identifier}.md").read_text())
        with self.assertRaisesRegex(ValueError, "completed"):
            self.confirm(identifier)
        self.assertEqual(journal.read_text(), content)

    def test_cancellation_never_creates_journal(self):
        identifier = self.preview()
        result = main.process_input(dict(action="cancel", proposal_id=identifier))
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse((self.root / "data/journal.hledger").exists())

    def test_repeated_proposal_forms_have_independent_names_and_explicit_actions(self):
        first = self.preview()
        second = self.preview()
        dashboard = main.render_dashboard()
        for identifier in (first, second):
            self.assertIn(f'Form(name: "finance-proposal-{identifier}"', dashboard)
            self.assertIn(f'Select(name: "proposal_id", value: "{identifier}"', dashboard)
        self.assertEqual(dashboard.count('RadioGroup(name: "action"'), 2)
        self.assertNotIn('Form(name: "minionInput"', dashboard)
        self.assertLess(dashboard.index('CardHeader(title: "Pending posting'), dashboard.index('Finance(children:'))

    def test_blank_confirmation_cancels_but_never_authorizes_posting(self):
        identifier = self.preview()
        with self.assertRaises(jsonschema.ValidationError):
            main.process_input(dict(action="confirm", proposal_id=identifier, confirmation=""))
        self.assertFalse((self.root / "data/journal.hledger").exists())
        result = main.process_input(dict(action="cancel", proposal_id=identifier, confirmation=""))
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse((self.root / "data/journal.hledger").exists())

    def test_only_the_confirmed_proposal_posts_and_sibling_can_still_be_cancelled(self):
        first = self.preview()
        second = self.preview()
        self.confirm(second)
        journal = self.root / "data/journal.hledger"
        before = journal.read_text()
        self.assertIn(f"minion-id: {second}", before)
        self.assertNotIn(f"minion-id: {first}", before)
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            self.confirm(first)
        main.process_input(dict(action="cancel", proposal_id=first, confirmation=""))
        self.assertEqual(journal.read_text(), before)

    def test_changed_journal_invalidates_preview(self):
        identifier = self.preview()
        journal = self.root / "data/journal.hledger"
        journal.write_text("; an unrelated writer changed the baseline\n")
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            self.confirm(identifier)
        self.assertNotIn("Synthetic", journal.read_text())

    def test_existing_unconfigured_journal_does_not_create_a_second_ledger(self):
        directory = self.root / "data"
        directory.mkdir()
        (directory / "custom.journal").write_text("; existing main entry point\n")
        with self.assertRaisesRegex(ValueError, "select the main journal"):
            self.preview()
        self.assertFalse((directory / "journal.hledger").exists())

    def test_changed_intake_contract_is_validated_before_journal_write(self):
        identifier = self.preview()
        schema = self.root / "templates/intake/intake-template.schema.json"
        document = json.loads(schema.read_text())
        document["required"].append("new-required-field")
        schema.write_text(json.dumps(document))
        with self.assertRaises(jsonschema.ValidationError):
            self.confirm(identifier)
        self.assertFalse((self.root / "data/journal.hledger").exists())

    def test_includes_preserved_and_checked_as_one_ledger(self):
        directory = self.root / "data"
        directory.mkdir()
        (directory / "journal.hledger").write_text("include 2025.hledger\n")
        prior = "2025-01-01 * Opening\n    assets:checking  100 USD\n    equity:opening\n"
        (directory / "2025.hledger").write_text(prior)
        identifier = self.preview()
        self.confirm(identifier)
        self.assertTrue((directory / "journal.hledger").read_text().startswith("include 2025.hledger\n"))
        self.assertEqual((directory / "2025.hledger").read_text(), prior)

    def test_invalid_inputs_and_unconfirmed_action_write_no_ledger(self):
        for change in ({"date": "2026-02-30"}, {"amount": "0"}, {"amount": 0.1},
                       {"description": "Injected\ninclude private"}, {"debit_account": "assets:checking"},
                       {"commodity": "USD\n"}, {"credit_account": "assets:checking;comment"}):
            with self.subTest(change=change), self.assertRaises((ValueError, jsonschema.ValidationError)):
                main.process_input({**self.payload, **change})
        with self.assertRaises(jsonschema.ValidationError):
            main.process_input(dict(action="confirm", proposal_id="a" * 32))
        self.assertFalse((self.root / "data/journal.hledger").exists())

    def test_invalid_baseline_and_unsafe_includes_refuse(self):
        directory = self.root / "data"
        directory.mkdir()
        journal = directory / "journal.hledger"
        for content in ("include ../../private.hledger\n", "include *.hledger\n",
                        "2026-01-01 * Broken\n    assets:checking  2 USD\n    expenses:food  3 USD\n"):
            journal.write_text(content)
            with self.assertRaises(ValueError):
                self.preview()
            self.assertEqual(journal.read_text(), content)

    def test_symlinks_rejected(self):
        (self.root / "data").symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.preview()

    def test_refresh_does_not_initialize_data_and_state_survives_reload(self):
        main.render_dashboard()
        self.assertFalse((self.root / "data").exists())
        identifier = self.preview()
        dashboard = main.render_dashboard()
        self.assertIn(identifier, dashboard)
        self.assertEqual(main.proposals()[0]["status"], "pending")
        self.confirm(identifier)
        self.assertEqual(main.proposals()[0]["status"], "posted")
