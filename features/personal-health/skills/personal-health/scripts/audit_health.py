#!/usr/bin/env python3
"""Audit person boundaries and cross-record links in a health workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


RECORD_ROOTS = {
    "profiles": "profile",
    "history": "history",
    "conditions": "condition",
    "treatments": "treatment",
    "reviews": "review",
}
LINK_FIELDS = {
    "history": {"condition_ids": "condition", "treatment_ids": "treatment"},
    "condition": {"history_ids": "history"},
    "treatment": {"condition_ids": "condition", "history_ids": "history"},
    "review": {"source_record_ids": "any"},
}


def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    metadata = yaml.safe_load(text[4:end])
    return metadata if isinstance(metadata, dict) else None


def _record_files(root: Path, record_root: str) -> list[Path]:
    directory = root / "health" / record_root
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*.md")
        if not path.name.endswith("-template.md") and path.is_file()
    )


def _issue(path: Path, code: str, message: str) -> dict[str, str]:
    return {"path": path.as_posix(), "code": code, "message": message}


def audit_health(workspace_root: str | Path) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    health_root = root / "health"
    if not health_root.is_dir():
        raise FileNotFoundError(f"health directory not found: {health_root}")

    issues: list[dict[str, str]] = []
    records: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in RECORD_ROOTS.values()}
    paths: dict[str, Path] = {}

    for directory, kind in RECORD_ROOTS.items():
        for path in _record_files(root, directory):
            relative = path.relative_to(root)
            try:
                metadata = _parse_frontmatter(path)
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                issues.append(_issue(relative, "frontmatter-error", str(exc)))
                continue
            if metadata is None:
                issues.append(_issue(relative, "frontmatter-missing", "record must begin with YAML frontmatter"))
                continue

            record_id = metadata.get("id")
            person_id = metadata.get("person_id")
            if not isinstance(record_id, str) or not record_id.strip():
                issues.append(_issue(relative, "missing-id", "health records need a non-empty stable id"))
            elif record_id in paths:
                issues.append(_issue(relative, "duplicate-id", f"id {record_id!r} is already used by {paths[record_id]}"))
            else:
                paths[record_id] = relative
                records[kind][record_id] = metadata

            if not isinstance(person_id, str) or not person_id.strip():
                issues.append(_issue(relative, "missing-person", "health records need a non-empty person_id"))

            parts = relative.parts
            if kind == "profile":
                if len(parts) != 3 or path.stem != person_id:
                    issues.append(_issue(relative, "profile-path", "profiles must be health/profiles/<person_id>.md"))
            elif len(parts) < 4 or parts[2] != person_id:
                issues.append(_issue(relative, "person-path", "record directory must be health/<type>/<person_id>/..."))

    profile_ids = set(records["profile"])
    for record_id, metadata in records["profile"].items():
        person_id = metadata.get("person_id")
        if person_id != record_id:
            issues.append(_issue(paths[record_id], "profile-id", "profile id and person_id must match"))

    for kind, kind_records in records.items():
        if kind == "profile":
            continue
        for record_id, metadata in kind_records.items():
            path = paths[record_id]
            person_id = metadata.get("person_id")
            if isinstance(person_id, str) and person_id not in profile_ids:
                issues.append(_issue(path, "unknown-person", f"person_id {person_id!r} has no health profile"))
            related_person_id = metadata.get("related_person_id")
            if kind == "condition" and related_person_id is not None:
                if not isinstance(related_person_id, str) or related_person_id not in profile_ids:
                    issues.append(_issue(path, "unknown-related-person", f"related_person_id {related_person_id!r} has no health profile"))
            for field, target_kind in LINK_FIELDS.get(kind, {}).items():
                values = metadata.get(field, [])
                if not isinstance(values, list):
                    issues.append(_issue(path, "link-list", f"{field} must be a list of record IDs"))
                    continue
                for target_id in values:
                    if not isinstance(target_id, str) or not target_id:
                        issues.append(_issue(path, "link-id", f"{field} contains an invalid record ID"))
                        continue
                    target_path = paths.get(target_id)
                    if target_path is None:
                        issues.append(_issue(path, "dangling-link", f"{field} references missing id {target_id!r}"))
                        continue
                    if target_kind == "any":
                        target_metadata = next(
                            (candidate_records[target_id]
                             for candidate_records in records.values()
                             if target_id in candidate_records),
                            {},
                        )
                    else:
                        target_metadata = records[target_kind].get(target_id)
                        if target_metadata is None:
                            issues.append(_issue(path, "wrong-link-type", f"{field} references {target_id!r}, not a {target_kind} record"))
                            continue
                    target_person = target_metadata.get("person_id")
                    if isinstance(person_id, str) and target_person != person_id:
                        issues.append(_issue(path, "cross-person-link", f"{field} links {person_id!r} to {target_person!r}"))

    return {
        "workspace": str(root),
        "record_counts": {kind: len(values) for kind, values in records.items()},
        "total_issues": len(issues),
        "issues": sorted(issues, key=lambda item: (item["path"], item["code"], item["message"])),
    }


def self_test() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="openlia-health-audit-") as directory:
        root = Path(directory)
        (root / "health" / "profiles").mkdir(parents=True)
        (root / "health" / "history" / "person-001").mkdir(parents=True)
        (root / "health" / "conditions" / "person-001").mkdir(parents=True)
        (root / "health" / "conditions" / "person-002").mkdir(parents=True)
        (root / "health" / "profiles" / "person-001.md").write_text(
            "---\nid: person-001\nperson_id: person-001\n---\n# Person\n", encoding="utf-8"
        )
        (root / "health" / "profiles" / "person-002.md").write_text(
            "---\nid: person-002\nperson_id: person-002\n---\n# Person\n", encoding="utf-8"
        )
        (root / "health" / "history" / "person-001" / "event.md").write_text(
            "---\nid: history-001\nperson_id: person-001\n---\n# Event\n", encoding="utf-8"
        )
        (root / "health" / "conditions" / "person-001" / "condition.md").write_text(
            "---\nid: condition-001\nperson_id: person-001\nhistory_ids: [history-001]\n---\n# Condition\n",
            encoding="utf-8",
        )
        (root / "health" / "conditions" / "person-002" / "condition.md").write_text(
            "---\nid: condition-002\nperson_id: person-002\nhistory_ids: [history-missing]\n---\n# Condition\n",
            encoding="utf-8",
        )
        result = audit_health(root)
        assert not any(issue["code"] == "cross-person-link" for issue in result["issues"] if "condition-001" in issue["path"])
        assert any(issue["code"] == "dangling-link" for issue in result["issues"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("ok")
        return 0
    if args.workspace_root is None:
        parser.error("--workspace-root is required unless --self-test is used")
    try:
        result = audit_health(args.workspace_root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json:
        sys.stdout.write(rendered)
    elif result["issues"]:
        for issue in result["issues"]:
            print(f"{issue['path']}: {issue['code']}: {issue['message']}", file=sys.stderr)
    else:
        print(f"Audited {sum(result['record_counts'].values())} health records.")
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
