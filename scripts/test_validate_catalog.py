#!/usr/bin/env python3
"""Compatibility contract tests; run with unittest discovery in scripts/."""

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validate_catalog import (
    FEATURE_SCHEMA_PATH,
    load_yaml,
    portable_minion_file,
    validate_feature_minions,
    validate_runtime_requirement,
)


class RuntimeRequirementTests(unittest.TestCase):
    def test_environment_manifests_are_paths_not_package_arrays(self):
        for requires in ({"python": "requirements.txt", "bun": "package.json", "tools": ["remind"]},):
            errors = []
            validate_runtime_requirement({"requires": requires}, "test", errors)
            self.assertEqual(errors, [])
        for requires in ({"python": ["requests"]}, {"bun": ["yaml"]}, {"tools": "remind"}, {"python": "../outside.txt"}):
            errors = []
            validate_runtime_requirement({"requires": requires}, "test", errors)
            self.assertTrue(errors)
    def test_profiles_and_skills_share_feature_contract(self):
        for value in (">=0.1.0", ">=12.34.56"):
            with self.subTest(value=value):
                errors = []
                validate_runtime_requirement({"requires": {"openlia": value}}, "test", errors)
                self.assertEqual(errors, [])

    def test_invalid_requirements_are_rejected(self):
        for value in ("", None, 1, [], {}, ">=01.2.3", "^1.2.3", ">=1.2", ">=1.2.3-rc.1", ">=1.2.3\n"):
            with self.subTest(value=value):
                errors = []
                validate_runtime_requirement({"requires": {"openlia": value}}, "test", errors)
                self.assertTrue(errors)

    def test_legacy_requirements_remain_supported(self):
        for data in ({}, {"requires": {}}, {"requires": {"tools": ["remind"]}}):
            errors = []
            validate_runtime_requirement(data, "test", errors)
            self.assertEqual(errors, [])

    def test_requires_must_be_a_mapping(self):
        for value in (None, [], "openlia"):
            errors = []
            validate_runtime_requirement({"requires": value}, "test", errors)
            self.assertTrue(errors)

    def test_feature_schema_checks_runtime_requirement(self):
        schema = json.loads(FEATURE_SCHEMA_PATH.read_text())
        manifest = {"schema": 1, "id": "example", "name": "Example", "version": "1.0.0", "description": "Example"}
        jsonschema.validate(manifest, schema)
        manifest["requires"] = {"openlia": ">=1.2.3"}
        jsonschema.validate(manifest, schema)
        manifest["requires"]["openlia"] = "^1.2.3"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(manifest, schema)

    def test_duplicate_requirements_cannot_hide_a_minimum(self):
        with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
            load_yaml("requires:\n  openlia: '>=2.0.0'\n  openlia: '>=1.0.0'\n")

    def test_requirement_alias_is_valid(self):
        data = load_yaml("minimum: &minimum '>=1.2.3'\nrequires: {openlia: *minimum}\n")
        errors = []
        validate_runtime_requirement(data, "test", errors)
        self.assertEqual(errors, [])

    def test_minion_package_contract_in_catalog_validator(self):
        for allowed in (
            "README.md",
            "main.py",
            "dashboard.openui",
            "scripts/helper.py",
            "tests/test_main.py",
            "tests/fixtures/sample.json",
        ):
            self.assertTrue(portable_minion_file(allowed), allowed)
        for rejected in (
            "",
            "/main.py",
            "../main.py",
            "config.json",
            "data/items.json",
            "node_modules/pkg/index.js",
            ".venv/bin/python",
            "secrets.json",
        ):
            self.assertFalse(portable_minion_file(rejected), rejected)

        with tempfile.TemporaryDirectory() as tmp:
            fdir = Path(tmp) / "gym-tracker"
            app = fdir / "workspace" / "minions" / "gym-tracker"
            app.mkdir(parents=True)
            files = {
                "README.md": "---\nname: Gym Tracker\n---\n# Gym Tracker\n",
                "dashboard.openui": 'Callout(variant: "info", title: "Gym", description: "Ready")',
                "input.openui": 'Form(name: "minionInput", fields: [], buttons: Buttons(buttons: []))',
                "input.schema.json": '{"type": "object"}',
                "config.schema.json": json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["trigger"],
                        "properties": {
                            "trigger": {"type": "object"},
                            "weekly_target_sessions": {"type": "integer", "default": 3},
                        },
                    }
                ),
                "input.py": "# input\n",
                "main.py": "# main\n",
                "requirements.txt": "# deps\n",
                "tests/test_main.py": "# test\n",
            }
            for rel, content in files.items():
                target = app / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            (app / "minion.package.json").write_text(
                json.dumps({"schema": 1, "files": list(files.keys())}, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest = {
                "domains": [
                    {
                        "path": "minions/gym-tracker",
                        "kind": "extension",
                        "label": "Gym Tracker",
                        "purpose": "Track workouts",
                        "lifecycle": "active",
                    }
                ]
            }
            errors: list[str] = []
            validate_feature_minions(fdir, manifest, errors)
            self.assertEqual(errors, [])

            # Undeclared file or local config must fail strict catalog validation
            (app / "config.json").write_text('{"trigger": {"on_new_entry": false}}\n', encoding="utf-8")
            errors = []
            validate_feature_minions(fdir, manifest, errors)
            self.assertTrue(any("config.json" in err for err in errors), errors)
            (app / "config.json").unlink()

            # Missing domain declaration must fail
            errors = []
            validate_feature_minions(fdir, {"domains": []}, errors)
            self.assertTrue(any("exact domain" in err for err in errors), errors)


if __name__ == "__main__":
    unittest.main()
