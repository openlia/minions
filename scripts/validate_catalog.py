#!/usr/bin/env python3
"""Validate all profiles, features, schemas, templates, and skills in openlia/minions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
FEATURE_SCHEMA_PATH = ROOT / "feature.schema.json"
FEATURES_DIR = ROOT / "features"
SKILLS_DIR = ROOT / "skills"
PROFILES_DIR = ROOT / "profiles"
CATALOG_PATH = ROOT / "catalog.json"

CREDENTIAL_CONTENT_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b|"
    r"\bglpat-[A-Za-z0-9\-=_]{20,}\b|"
    r"\bsk-[A-Za-z0-9]{20,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b",
    re.IGNORECASE,
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Do not let duplicate YAML keys hide a compatibility declaration."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(f"duplicate YAML key: {key}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(text: str):
    return yaml.load(text, Loader=UniqueKeyLoader)


def validate_runtime_requirement(data: dict, label: str, errors: list[str]) -> None:
    """Use the feature contract for profiles and skill frontmatter as well."""
    requires = data.get("requires", {})
    if not isinstance(requires, dict):
        errors.append(f"{label}: requires must be a mapping")
        return
    schema = json.loads(FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(requires, schema["properties"]["requires"])
    except jsonschema.ValidationError as exc:
        errors.append(f"{label}: requires.openlia: {exc.message}")


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        parts = text.split("\r\n---\r\n", 1)
    if len(parts) != 2:
        raise ValueError("unclosed YAML frontmatter")
    raw_yaml = parts[0][4:]
    body = parts[1]
    data = load_yaml(raw_yaml)
    if data is not None and not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return data or {}, body


def build_catalog() -> dict:
    profiles = []
    if PROFILES_DIR.is_dir():
        for pdir in sorted(p for p in PROFILES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
            manifest_file = pdir / "profile.yaml"
            if manifest_file.is_file():
                data = load_yaml(manifest_file.read_text(encoding="utf-8")) or {}
                profiles.append({
                    "id": data.get("id", pdir.name),
                    "name": data.get("name", pdir.name),
                    "version": str(data.get("version", "0.1.0")),
                    "description": data.get("description", ""),
                    "path": f"profiles/{pdir.name}",
                    "features": data.get("features", []),
                    "skills": data.get("skills", []),
                    "requires": data.get("requires", {}),
                })

    features = []
    if FEATURES_DIR.is_dir():
        for fdir in sorted(p for p in FEATURES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
            manifest_file = fdir / "feature.yaml"
            if manifest_file.is_file():
                data = load_yaml(manifest_file.read_text(encoding="utf-8")) or {}
                features.append({
                    "id": data.get("id", fdir.name),
                    "name": data.get("name", fdir.name),
                    "version": str(data.get("version", "0.1.0")),
                    "description": data.get("description", ""),
                    "path": f"features/{fdir.name}",
                    "domains": [d.get("path") for d in data.get("domains", []) if isinstance(d, dict) and d.get("path")],
                    "skills": [s.get("id") for s in data.get("skills", []) if isinstance(s, dict) and s.get("id")],
                    "requires": data.get("requires", {}),
                })

    skills = []
    if SKILLS_DIR.is_dir():
        for sdir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
            skill_md = sdir / "SKILL.md"
            if skill_md.is_file():
                fm, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
                fm = fm or {}
                skills.append({
                    "id": fm.get("name", sdir.name),
                    "name": fm.get("name", sdir.name),
                    "version": str(fm.get("version", "0.1.0")),
                    "description": fm.get("description", ""),
                    "path": f"skills/{sdir.name}",
                    "requires": fm.get("requires", {}),
                })

    return {
        "schema": 1,
        "repository": "https://github.com/openlia/minions.git",
        "profiles": profiles,
        "features": features,
        "skills": skills,
    }


def validate_all(run_self_tests: bool = True) -> list[str]:
    errors: list[str] = []
    if not FEATURE_SCHEMA_PATH.is_file():
        return ["missing feature.schema.json"]
    feature_schema = json.loads(FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))

    # 1. Validate features
    for fdir in sorted(p for p in FEATURES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
        manifest_path = fdir / "feature.yaml"
        if not manifest_path.is_file():
            errors.append(f"features/{fdir.name}: missing feature.yaml")
            continue
        try:
            manifest = load_yaml(manifest_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=manifest, schema=feature_schema)
        except Exception as exc:
            errors.append(f"features/{fdir.name}/feature.yaml: {exc}")
            continue

        ws_root = fdir / "workspace"
        if ws_root.is_dir():
            for tpl_path in sorted(ws_root.rglob("*-template.md")):
                try:
                    fm, _ = parse_frontmatter(tpl_path.read_text(encoding="utf-8"))
                    if fm and "$schema" in fm:
                        schema_rel = fm["$schema"]
                        schema_file = (tpl_path.parent / schema_rel).resolve()
                        if not schema_file.is_file():
                            errors.append(f"{tpl_path.relative_to(ROOT)}: missing schema {schema_rel}")
                        else:
                            schema_obj = json.loads(schema_file.read_text(encoding="utf-8"))
                            instance = {k: v for k, v in fm.items() if k != "$schema"}
                            jsonschema.validate(
                                instance=instance,
                                schema=schema_obj,
                                format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
                            )
                except Exception as exc:
                    errors.append(f"{tpl_path.relative_to(ROOT)}: {exc}")

    # 2. Validate profile runtime requirements before their features are installed.
    for manifest_path in sorted(PROFILES_DIR.glob("*/profile.yaml")):
        try:
            data = load_yaml(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("profile must be a mapping")
            validate_runtime_requirement(data, str(manifest_path.relative_to(ROOT)), errors)
        except Exception as exc:
            errors.append(f"{manifest_path.relative_to(ROOT)}: {exc}")

    # 3. Validate standalone skills and feature skills
    skill_dirs = list(SKILLS_DIR.glob("*")) + list(FEATURES_DIR.glob("*/skills/*"))
    for sdir in sorted(p for p in skill_dirs if p.is_dir() and not p.name.startswith(".")):
        skill_md = sdir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"{sdir.relative_to(ROOT)}: missing SKILL.md")
            continue
        try:
            fm, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            if not fm or not fm.get("name") or not fm.get("description"):
                errors.append(f"{skill_md.relative_to(ROOT)}: frontmatter requires name and description")
            if fm:
                validate_runtime_requirement(fm, str(skill_md.relative_to(ROOT)), errors)
        except Exception as exc:
            errors.append(f"{skill_md.relative_to(ROOT)}: {exc}")

        if run_self_tests:
            for script in sorted((sdir / "scripts").glob("*.py")) if (sdir / "scripts").is_dir() else []:
                res = subprocess.run([sys.executable, str(script), "--self-test"], capture_output=True, text=True)
                if res.returncode != 0:
                    errors.append(f"{script.relative_to(ROOT)} --self-test failed: {res.stderr or res.stdout}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-catalog", action="store_true", help="regenerate catalog.json")
    parser.add_argument("--no-self-test", action="store_true", help="skip running skill python --self-test")
    args = parser.parse_args(argv)

    try:
        catalog = build_catalog()
        errors = validate_all(run_self_tests=not args.no_self_test)
        if not args.write_catalog:
            if not CATALOG_PATH.is_file():
                errors.append("catalog.json is missing; run --write-catalog deliberately")
            elif json.loads(CATALOG_PATH.read_text(encoding="utf-8")) != catalog:
                errors.append("catalog.json is stale; run --write-catalog and review the diff")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    if args.write_catalog:
        CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    print(
        f"Validated {len(catalog['profiles'])} profiles, "
        f"{len(catalog['features'])} features, and "
        f"{len(catalog['skills'])} standalone skills."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
