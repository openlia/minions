from pathlib import Path
import runpy
import unittest


triage = runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills/inbox-triage/scripts/triage_inbox.py"))["triage"]


class PersonalAppRoutingTests(unittest.TestCase):
    def test_new_app_routes_to_canonical_intake(self):
        registry = {"domains": [{"path": "minions/personal-finance", "minion": True}]}
        result = triage([{"title": "Receipt"}], registry=registry)
        self.assertEqual(result["items"][0]["destination"], "minions/personal-finance/data/intake/")

    def test_explicit_custom_intake_destination_is_respected(self):
        registry = {"domains": [{"path": "minions/personal-finance", "minion": True},
                                {"path": "custom/intake", "route": "finance", "tags": ["finance", "intake"]}]}
        result = triage([{"title": "Receipt"}], registry=registry)
        self.assertEqual(result["items"][0]["destination"], "custom/intake")
