#!/usr/bin/env python3
"""Validate all profiles, features, schemas, templates, Minions, and skills in openlia/minions."""

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

MINION_PACKAGE_FILE = "minion.package.json"
MAX_MINION_FILE_BYTES = 10 * 1024 * 1024
MINION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED_MINION_PARTS = {
    "config.json",
    "data",
    "state",
    "cache",
    "caches",
    "logs",
    "uploads",
    "tmp",
    "temp",
    "node_modules",
    "__pycache__",
    "venv",
    "env",
    "dist",
    "build",
    "coverage",
}
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


def portable_minion_file(rel: str) -> bool:
    if not rel or re.search(r"[\\:\x00]", rel) or rel.startswith("/"):
        return False
    for part in rel.split("/"):
        lower = part.lower()
        if (
            not part
            or part in (".", "..")
            or part.startswith(".")
            or lower in RESERVED_MINION_PARTS
            or lower.endswith((".pyc", ".log", ".pem", ".key"))
            or any(token in lower for token in ("credential", "secret", "token", "id_rsa", "id_ed25519"))
        ):
            return False
    return True


def _has_external_schema_ref(node: object) -> bool:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            return True
        return any(_has_external_schema_ref(value) for value in node.values())
    if isinstance(node, list):
        return any(_has_external_schema_ref(item) for item in node)
    return False


def validate_minion_config_schema(schema: object) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("config.schema.json must declare an object schema")
    if "$schema" in schema and schema["$schema"] != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("config.schema.json must use Draft 2020-12")
    required = schema.get("required")
    if not isinstance(required, list) or "trigger" not in required:
        raise ValueError("config.schema.json must require trigger")
    if _has_external_schema_ref(schema):
        raise ValueError("external schema references are not permitted in config.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def validate_minion_data_views(document: object) -> None:
    """Portable preflight only; paired runtime validates the authoritative contract."""
    if not isinstance(document, dict) or set(document) != {"schema", "views"} or type(document["schema"]) is not int or document["schema"] != 1:
        raise ValueError("data.views.json requires schema: 1 and views")
    views = document["views"]
    if not isinstance(views, list) or len(views) > 8:
        raise ValueError("data.views.json permits at most eight views")
    seen = set()
    for view in views:
        required = {"id", "label", "reader", "path", "fields", "title_field", "date_field"}
        optional = {"id_field", "required_filters", "max_records", "max_files", "max_bytes", "max_field_chars", "lookback_days"}
        if not isinstance(view, dict) or not required.issubset(view) or set(view) - required - optional:
            raise ValueError("data view has missing or unsupported properties")
        if not isinstance(view["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", view["id"]) or view["id"] in seen:
            raise ValueError("Invalid or duplicate data view id")
        seen.add(view["id"])
        if not isinstance(view["label"], str) or not 1 <= len(view["label"]) <= 100 or view["reader"] not in {"markdown", "json", "calendar"}:
            raise ValueError("Invalid view label or reader")
        if not isinstance(view["path"], str) or not re.fullmatch(r"data/[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*", view["path"]):
            raise ValueError("Data view must select a bounded data/ path")
        blocked = {"pending", "cache", "caches", "state", "logs", "uploads", "node_modules", "tests", "scripts", "__pycache__", "config.json", "context.json", "data.views.json", "secrets.json", "credentials.json"}
        if any(part.lower() in blocked for part in view["path"].split("/")):
            raise ValueError("Data view cannot select app internals")
        fields = view["fields"]
        if not isinstance(fields, list) or not 1 <= len(fields) <= 32 or any(not isinstance(field, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", field) for field in fields):
            raise ValueError("Invalid view fields")
        required_filters = view.get("required_filters", [])
        if not isinstance(required_filters, list) or len(required_filters) > 8:
            raise ValueError("Invalid required filters")
        for name in [view["title_field"], view["date_field"], *required_filters, *([view["id_field"]] if "id_field" in view else [])]:
            if name not in fields:
                raise ValueError("View identity/date/scope must be declared fields")
        for key, low, high in [("max_records", 1, 100), ("max_files", 1, 200), ("max_bytes", 1024, 4194304), ("max_field_chars", 40, 1000), ("lookback_days", 0, 14)]:
            if key in view and (type(view[key]) is not int or not low <= view[key] <= high):
                raise ValueError(f"Invalid {key}")


def validate_minion_package_dir(minion_dir: Path, minion_id: str) -> list[str]:
    errors: list[str] = []
    label = f"minions/{minion_id}"
    pkg_path = minion_dir / MINION_PACKAGE_FILE
    if pkg_path.is_symlink() or not pkg_path.is_file():
        return [f"{label}: missing reviewed {MINION_PACKAGE_FILE}"]
    try:
        raw = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{label}/{MINION_PACKAGE_FILE}: {exc}"]
    if (
        not isinstance(raw, dict)
        or set(raw.keys()) != {"schema", "files"}
        or type(raw.get("schema")) is not int
        or raw["schema"] != 1
        or not isinstance(raw.get("files"), list)
        or not raw["files"]
    ):
        return [f"{label}/{MINION_PACKAGE_FILE}: expected schema: 1 and explicit files list"]

    seen = {MINION_PACKAGE_FILE}
    seen_fold = {MINION_PACKAGE_FILE.lower()}
    for rel in raw["files"]:
        if not isinstance(rel, str) or not portable_minion_file(rel) or rel.lower() in seen_fold:
            errors.append(f"{label}: unsafe or duplicate Minion distribution file {rel!r}")
            continue
        target = minion_dir / rel
        for parent in [target, *target.parents]:
            if parent.is_symlink():
                errors.append(f"{label}: symlink in Minion path {rel}")
                break
            if parent == minion_dir:
                break
        else:
            continue
        if target.is_symlink():
            continue
        if not target.is_file() or target.stat().st_size > MAX_MINION_FILE_BYTES:
            errors.append(f"{label}: missing or oversized Minion package file {rel}")
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"{label}/{rel}: {exc}")
            continue
        if CREDENTIAL_CONTENT_RE.search(text):
            errors.append(f"{label}/{rel}: credential pattern detected")
            continue
        seen.add(rel)
        seen_fold.add(rel.lower())

    for req in ("README.md", "dashboard.openui", "input.openui", "input.schema.json", "config.schema.json"):
        if req not in seen:
            errors.append(f"{label}: Minion distribution missing required file {req}")
    if (
        ("main.py" in seen) == ("main.ts" in seen)
        or ("input.py" in seen) == ("input.ts" in seen)
        or ("main.py" in seen) != ("input.py" in seen)
    ):
        errors.append(f"{label}: Minion distribution requires exactly one runtime and its input entrypoint")
    if not any(path.startswith("tests/") for path in seen):
        errors.append(f"{label}: Minion distribution must include tests/")

    config_schema_path = minion_dir / "config.schema.json"
    if "config.schema.json" in seen and config_schema_path.is_file() and not config_schema_path.is_symlink():
        try:
            validate_minion_config_schema(json.loads(config_schema_path.read_text(encoding="utf-8")))
        except Exception as exc:
            errors.append(f"{label}/config.schema.json: {exc}")

    briefing_view_path = minion_dir / "data.views.json"
    if "data.views.json" in seen and briefing_view_path.is_file() and not briefing_view_path.is_symlink():
        try:
            validate_minion_data_views(json.loads(briefing_view_path.read_text(encoding="utf-8")))
        except Exception as exc:
            errors.append(f"{label}/data.views.json: {exc}")

    for path in sorted(minion_dir.rglob("*")):
        rel = path.relative_to(minion_dir).as_posix()
        if path.is_symlink() or not portable_minion_file(rel) or (not path.is_dir() and rel not in seen):
            errors.append(f"{label}: Minion package contains undeclared or local-only path {rel}")

    return errors


def validate_feature_minions(fdir: Path, manifest: dict, errors: list[str]) -> None:
    prefix = f"features/{fdir.name}"
    selected: set[str] = set()
    for domain in manifest.get("domains", []) or []:
        if not isinstance(domain, dict):
            continue
        rel = str(domain.get("path", ""))
        parts = rel.split("/")
        if parts[0] != "minions":
            continue
        if len(parts) != 2 or not MINION_ID_RE.fullmatch(parts[1]):
            errors.append(f"{prefix}: select an exact minions/<slug> domain, not {rel!r}")
            continue
        selected.add(parts[1])

    minions_root = fdir / "workspace" / "minions"
    if minions_root.is_symlink():
        errors.append(f"{prefix}: symlinks are not permitted in Minion paths: workspace/minions")
        return
    if not minions_root.exists():
        if selected:
            errors.append(f"{prefix}: feature declares a missing Minion package: {', '.join(sorted(selected))}")
        return
    if not minions_root.is_dir():
        errors.append(f"{prefix}: workspace/minions must be a directory")
        return

    for entry in sorted(minions_root.iterdir()):
        minion_id = entry.name
        if (
            not entry.is_dir()
            or entry.is_symlink()
            or minion_id not in selected
            or not MINION_ID_RE.fullmatch(minion_id)
        ):
            errors.append(f"{prefix}: feature must declare each Minion as an exact domain: minions/{minion_id}")
            continue
        for err in validate_minion_package_dir(entry, minion_id):
            errors.append(f"{prefix}/{err}")
        selected.discard(minion_id)

    if selected:
        errors.append(f"{prefix}: feature declares a missing Minion package: {', '.join(sorted(selected))}")


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
        validate_feature_minions(fdir, manifest, errors)

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
