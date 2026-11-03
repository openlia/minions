#!/usr/bin/env python3
"""App-owned Markdown records, not diagnoses or a duplicate private dataset."""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

import jsonschema
import yaml

from audit_health import audit_health

ROOT = Path(__file__).resolve().parent
COLLECTIONS = {"profile": ("profiles", "profile"), "encounter": ("history", "history"),
               "measurement": ("history", "history"), "condition": ("conditions", "condition"),
               "treatment": ("treatments", "treatment")}


def safe_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("Expected a relative path without traversal")
    path = root / rel
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError(f"Symlinks are not supported: {parent}")
        if parent == root:
            break
    return path


def data_path(relative: str) -> Path:
    return safe_path(ROOT, f"data/{relative}")


def validate(value, schema: Path):
    schema = safe_path(ROOT, schema.relative_to(ROOT).as_posix())
    document = json.loads(schema.read_text())
    def local_references(node):
        if isinstance(node, dict):
            if "$ref" in node and not str(node["$ref"]).startswith("#"):
                raise ValueError("External schema references are not supported")
            for child in node.values():
                local_references(child)
        elif isinstance(node, list):
            for child in node:
                local_references(child)
    local_references(document)
    jsonschema.Draft202012Validator(document,
                                  format_checker=jsonschema.FormatChecker()).validate(value)


def load_config():
    raw = os.environ.get("OPENLIA_MINION_CONFIG_JSON")
    config = json.loads(raw) if raw else json.loads(safe_path(ROOT, "config.json").read_text())
    validate(config, ROOT / "config.schema.json")
    return config


def read_record(path: Path):
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"Missing frontmatter: {path}")
    fields = yaml.safe_load(match[1])
    if not isinstance(fields, dict):
        raise ValueError(f"Invalid record frontmatter: {path}")
    return fields, match[2]


def check_date(value: str):
    if re.fullmatch(r"\d{4}", value):
        dt.date(int(value), 1, 1)
    elif re.fullmatch(r"\d{4}-\d{2}", value):
        dt.date.fromisoformat(value + "-01")
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        dt.date.fromisoformat(value)
    else:
        parsed = dt.datetime.fromisoformat(value)
        if "T" not in value or parsed.tzinfo is None:
            raise ValueError("Timestamps require a timezone; preserve known date precision")


def contract(directory: str, stem: str):
    template = safe_path(ROOT, f"templates/{directory}/{stem}-template.md")
    fields, body = read_record(template)
    schema = safe_path(template.parent, str(fields.pop("$schema")))
    return fields, body, schema


def build_record(payload: dict):
    kind = payload["record_type"]
    person = payload["person_id"]
    directory, stem = COLLECTIONS[kind]
    fields, body, schema = contract(directory, stem)
    identifier = person if kind == "profile" else f"{stem}-{uuid.uuid4().hex}"
    path = data_path(f"profiles/{person}.md" if kind == "profile" else f"{directory}/{person}/{identifier}.md")
    if path.exists():
        raise ValueError("Profile already exists; never overwrite identity records")
    if kind != "profile":
        profile = data_path(f"profiles/{person}.md")
        identity, _ = read_record(profile)
        if identity.get("person_id") != person or identity.get("id") != person:
            raise ValueError("The selected person ID does not match its profile")
    fields.update(id=identifier, person_id=person)
    source = payload.get("source_ref")
    source_type = payload.get("source_type", "user-report")
    if source_type != "user-report" and not source:
        raise ValueError("Clinician, imported, lab, device, or prescription evidence needs a source reference")
    event_date = payload.get("event_date")
    if event_date:
        check_date(event_date)
    if kind == "profile":
        fields.update(display_name=payload["title"], relationship_to_user=payload["relationship_to_user"],
                      source_refs=[source] if source else [])
    elif kind in ("encounter", "measurement"):
        fields.update(kind="encounter" if kind == "encounter" else "test", occurred_start=event_date,
                      recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(), source_type=source_type,
                      source_ref=source, status="reported")
        if kind == "measurement":
            fields["results"] = [dict(name=payload["title"], value=payload["value"], unit=payload["unit"],
                                      reference_range=None, interpretation=None, coding=None)]
    elif kind == "condition":
        verification = payload.get("verification_status", "reported")
        if verification == "confirmed" and (source_type != "clinician" or not source):
            raise ValueError("A confirmed condition requires explicit clinician evidence, not a user hypothesis")
        condition_kind = payload.get("condition_kind", "other")
        if condition_kind == "family-history" and not payload.get("family_member_relation"):
            raise ValueError("Family history requires the explicit relative's relationship to the subject")
        fields.update(name=payload["title"], kind=condition_kind,
                      family_member_relation=payload.get("family_member_relation"), verification_status=verification,
                      clinical_status=payload.get("clinical_status", "unknown"), onset=event_date,
                      source_refs=[source] if source else [])
    elif kind == "treatment":
        intent = payload.get("treatment_intent", "reported-use")
        if intent == "prescribed" and (source_type not in ("clinician", "prescription") or not source):
            raise ValueError("Prescribed intent requires clinician/prescription evidence")
        fields.update(name=payload["title"], kind=payload.get("treatment_kind", "other"),
                      started_on=event_date, source_ref=source, source_type=source_type,
                      status=payload.get("treatment_status", "unknown"), intent=intent)
    validate(fields, schema)
    fields["$schema"] = os.path.relpath(schema, path.parent)
    body = re.sub(r"(?m)^# .*$", lambda _: "# " + payload["title"], body, count=1)
    if source_type == "user-report" and not source:
        body += "\nSource basis: user report; no external source supplied.\n"
    if payload.get("notes"):
        body += "\n" + payload["notes"] + "\n"
    return path, "---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n" + body


def record_entry(payload: dict):
    validate(payload, ROOT / "input.schema.json")
    load_config()
    lock = data_path(".write.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        # Never follow a symlink while staging or reading clinical data.
        for path in (ROOT / "data").rglob("*"):
            safe_path(ROOT, path.relative_to(ROOT).as_posix())
        path, content = build_record(payload)
        with tempfile.TemporaryDirectory(prefix="openlia-health-check-") as directory:
            temporary = Path(directory)
            staged = temporary / "data"
            shutil.copytree(ROOT / "data", staged)
            candidate = staged / path.relative_to(ROOT / "data")
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(content, encoding="utf-8")
            audit = audit_health(temporary, data_root=staged)
            if audit["total_issues"]:
                raise ValueError("Health integrity audit failed: " + json.dumps(audit["issues"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish only a complete record, without replacing an existing identity.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
                os.link(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        render_dashboard()
    return {"person_id": payload["person_id"], "path": path.relative_to(ROOT).as_posix()}


def render_dashboard():
    children = ['Callout(variant: "info", title: "Recorded health facts", description: "Source-linked records, not medical diagnoses or advice. Missing information is unknown. Each table is scoped to one stable person ID.")']
    profiles = data_path("profiles")
    if profiles.exists():
        for profile in sorted(profiles.glob("*.md")):
            if profile.name.endswith("-template.md"):
                continue
            fields, _ = read_record(safe_path(profiles, profile.name))
            person = fields["person_id"]
            if not isinstance(person, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", person) or profile.stem != person:
                raise ValueError("Invalid profile identity; run the health audit")
            rows = [{"type": "profile", "title": fields["display_name"], "source": ", ".join(fields.get("source_refs", [])),
                     "record": f"openlia://workspace/minions/personal-health/data/profiles/{profile.name}"}]
            for directory in ("history", "conditions", "treatments", "reviews"):
                folder = data_path(f"{directory}/{person}")
                if folder.exists():
                    for path in sorted(folder.rglob("*.md")):
                        safe_path(ROOT, path.relative_to(ROOT).as_posix())
                        metadata, body = read_record(path)
                        if metadata.get("person_id") != person:
                            raise ValueError("Cross-person path mismatch; run the health audit")
                        title = next((line[2:] for line in body.splitlines() if line.startswith("# ")), path.stem)
                        details = "; ".join(f"{key}: {metadata[key]}" for key in
                                            ("verification_status", "clinical_status", "status", "intent") if key in metadata)
                        if metadata.get("results"):
                            details += "; " + "; ".join(f"{result['name']}: {result['value']} {result['unit'] or ''}" for result in metadata["results"])
                        rows.append({"type": directory, "title": title,
                                     "date": str(metadata.get("occurred_start") or metadata.get("onset") or metadata.get("started_on") or metadata.get("as_of") or "Unknown"),
                                     "details": details,
                                     "source": metadata.get("source_ref") or ", ".join(metadata.get("source_refs", [])),
                                     "record": "openlia://workspace/minions/personal-health/" + path.relative_to(ROOT).as_posix()})
            title = f"{fields['display_name']} — {person} ({fields['relationship_to_user']})"
            children.append(f'Table(title: {json.dumps(title)}, columns: [{{"key": "type", "label": "Record type"}}, {{"key": "title", "label": "Recorded fact"}}, {{"key": "date", "label": "Date"}}, {{"key": "details", "label": "Recorded values and status"}}, {{"key": "source", "label": "Source"}}, {{"key": "record", "label": "Document URI"}}], rows: {json.dumps(rows)})')
    content = "Stack(children: [\n" + ",\n".join(children) + "\n])\n"
    safe_path(ROOT, "dashboard.openui").write_text(content, encoding="utf-8")
    return content


if __name__ == "__main__":
    load_config()
    render_dashboard()
    print("Read-only health dashboard refreshed. Not medical advice.")
