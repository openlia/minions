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


if __name__ == "__main__":
    unittest.main()
