#!/usr/bin/env python3
"""Native Remind calendar proposals with explicit local confirmation."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parent
DEFAULT_REMIND = "# OpenLia Calendar Minion Remind source\n# Native Remind is the source of truth.\n"
MAX_INCLUDED_FILES = 32
MAX_INCLUDED_BYTES = 2 * 1024 * 1024
SAFE_RELATIVE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")


def data_dir() -> Path:
    return safe_path(ROOT, "data")


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


def validate(value, schema: Path):
    schema = safe_path(ROOT, schema.relative_to(ROOT).as_posix())
    document = json.loads(schema.read_text(encoding="utf-8"))

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
    jsonschema.Draft202012Validator(
        document, format_checker=jsonschema.FormatChecker()
    ).validate(value)


def load_config() -> dict:
    raw = os.environ.get("OPENLIA_MINION_CONFIG_JSON")
    if raw:
        config = json.loads(raw)
    else:
        config = json.loads(safe_path(ROOT, "config.json").read_text(encoding="utf-8"))
    validate(config, ROOT / "config.schema.json")
    return config


def calendar_file(config: dict) -> str:
    relative = config["calendar_file"]
    if not SAFE_RELATIVE.fullmatch(relative) or not relative.endswith((".rem", ".remind")):
        raise ValueError("calendar_file must be a literal relative .rem or .remind path")
    safe_path(data_dir(), relative)
    return relative


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _include_targets(name: str, content: str) -> list[str]:
    targets = []
    for line in content.splitlines():
        match = re.match(r"^\s*INCLUDE\s+(.+?)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        target = match.group(1).strip()
        if (
            not SAFE_RELATIVE.fullmatch(target)
            or ".." in Path(target).parts
            or not target.endswith((".rem", ".remind"))
        ):
            raise ValueError("Only literal relative .rem/.remind includes are supported")
        child = (Path(name).parent / target).as_posix()
        safe_path(data_dir(), child)
        targets.append(child)
    return targets


def snapshot(config: dict) -> dict[str, str]:
    """Read the bounded native Remind include tree without interpreting it."""
    primary = calendar_file(config)
    files: dict[str, str] = {}

    def visit(name: str):
        if name in files:
            raise ValueError("Repeated or cyclic Remind include")
        if len(files) >= MAX_INCLUDED_FILES:
            raise ValueError("Remind include tree exceeds 32 files")
        path = safe_path(data_dir(), name)
        if not path.exists():
            if name == primary and not files:
                return
            raise ValueError(f"Missing included Remind file: {name}")
        if not path.is_file():
            raise ValueError(f"Remind source is not a regular file: {name}")
        content = path.read_text(encoding="utf-8")
        files[name] = content
        if sum(len(text.encode("utf-8")) for text in files.values()) > MAX_INCLUDED_BYTES:
            raise ValueError("Remind include tree exceeds 2 MiB")
        for child in _include_targets(name, content):
            visit(child)

    visit(primary)
    return files


def digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()


def run_native(files: dict[str, str], primary: str, when: str | None = None):
    """Validate a complete Remind tree using the native executable."""
    if not files:
        return
    with tempfile.TemporaryDirectory(prefix="openlia-calendar-check-") as directory:
        root = Path(directory)
        for name, content in files.items():
            target = safe_path(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        command = ["remind", "-r", "-q", "-s1", primary, when or dt.date.today().isoformat()]
        try:
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True, timeout=15, check=False
            )
        except FileNotFoundError as exc:
            raise ValueError("Native Remind is required for Calendar") from exc
        if result.returncode != 0 or result.stderr.strip():
            detail = result.stderr.strip() or result.stdout.strip() or "unknown Remind error"
            raise ValueError(f"Remind validation failed: {detail[:2000]}")


def _parse_attendees(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if any("\n" in item or "\r" in item for item in values):
        raise ValueError("Attendees cannot contain line breaks")
    return list(dict.fromkeys(values))


def _parse_tags(raw: str | None, identifier: str) -> list[str]:
    values = [item.strip() for item in (raw or "").split(",") if item.strip()]
    tags = ["openlia-calendar", f"openlia-ui-{identifier[:12]}"]
    for value in values:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", value):
            raise ValueError(f"Invalid Remind tag: {value}")
        if value not in tags:
            tags.append(value)
    return tags


def _parse_datetime(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid appointment timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Appointment timestamps require an explicit UTC offset")
    if parsed.second or parsed.microsecond:
        raise ValueError("Appointment timestamps must fall on a whole minute")
    return parsed


def _localize(value: str, timezone_name: str) -> dt.datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {timezone_name}") from exc
    parsed = _parse_datetime(value)
    # The explicit IANA timezone owns the wall-clock fields. The offset in the
    # ISO value disambiguates a fold; it must not silently convert a requested
    # local time into another wall time before DST validation.
    naive = parsed.replace(tzinfo=None)
    valid = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = candidate.astimezone(dt.timezone.utc).astimezone(zone).replace(tzinfo=None)
        if roundtrip == naive:
            valid.append(candidate)
    if not valid:
        raise ValueError(f"Appointment uses a nonexistent wall time in {timezone_name}")
    if len({candidate.utcoffset() for candidate in valid}) > 1:
        raise ValueError(f"Appointment uses an ambiguous wall time in {timezone_name}")
    supplied_offset = parsed.utcoffset()
    if supplied_offset not in {candidate.utcoffset() for candidate in valid}:
        raise ValueError(f"Appointment offset does not match {timezone_name}")
    return next(candidate for candidate in valid if candidate.utcoffset() == supplied_offset)


def _clean_text(value: str, field: str, *, max_length: int = 8000) -> str:
    if len(value) > max_length or any(ord(char) < 32 and char not in "\t" for char in value):
        raise ValueError(f"Invalid {field}: control characters or excessive length")
    if field == "title" and ("[" in value or "]" in value or "\\" in value):
        raise ValueError("Title cannot contain Remind expression brackets or escapes")
    return value.strip()


def _info(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ") + '"'


def _msg(value: str) -> str:
    return value.replace("%", "%%").replace("\n", " ").replace("\r", " ")


def _note_name(start: dt.datetime, title: str, identifier: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:50]
    return f"{start.date().isoformat()}-{slug or 'event'}-{identifier[:8]}.md"


def _note_content(payload: dict, start: dt.datetime, note_name: str) -> tuple[Path, str]:
    title = payload["title"]
    attendees = _parse_attendees(payload.get("attendees"))
    fields = {
        "starts_at": start.isoformat(),
        "location": payload.get("location") or None,
        "video_link": payload.get("video_link") or None,
        "attendees": attendees,
    }
    schema = ROOT / "templates/event-note-template.schema.json"
    validate(fields, schema)
    document = {"$schema": "../../templates/event-note-template.schema.json", **fields}
    body = payload.get("agenda", "").strip() or "- Objective and agenda to be confirmed."
    content = "---\n" + yaml.safe_dump(document, sort_keys=False, allow_unicode=True) + "---\n"
    content += f"\n# {title}\n\n## Purpose & Agenda\n{body}\n\n## Discussion & Raw Notes\n-\n\n## Follow-up Action Items\n- [ ] Next action:\n"
    return data_dir() / "notes" / note_name, content


def _event_entry(payload: dict, identifier: str) -> tuple[str, Path | None, str | None]:
    start = _localize(payload["start"], payload["timezone"])
    end = _localize(payload["end"], payload["timezone"])
    duration = end.astimezone(dt.timezone.utc) - start.astimezone(dt.timezone.utc)
    if duration <= dt.timedelta(0):
        raise ValueError("Appointment end must be after start")
    if duration > dt.timedelta(days=7):
        raise ValueError("Appointments cannot exceed seven days")
    minutes = int(duration.total_seconds() // 60)
    if duration.total_seconds() != minutes * 60:
        raise ValueError("Appointment duration must be a whole number of minutes")
    title = _clean_text(payload["title"], "title", max_length=200)
    agenda = _clean_text(payload.get("agenda", ""), "agenda")
    attendees = _parse_attendees(payload.get("attendees"))
    location = _clean_text(payload.get("location", ""), "location", max_length=500)
    video_link = _clean_text(payload.get("video_link", ""), "video_link", max_length=1000)
    tags = _parse_tags(payload.get("tags"), identifier)
    note_path = None
    note_content = None
    if agenda:
        note_name = _note_name(start, title, identifier)
        note_path, note_content = _note_content(payload, start, note_name)
    info = [f'INFO {_info("Timezone: " + payload["timezone"])}']
    if agenda:
        info.append(f'INFO {_info("Description: " + " ".join(agenda.split()))}')
    if attendees:
        info.append(f'INFO {_info("Attendees: " + ", ".join(attendees))}')
    if location:
        info.append(f'INFO {_info("Location: " + " ".join(location.split()))}')
    if video_link:
        info.append(f'INFO {_info("Video-Link: " + video_link)}')
    if note_path:
        relative = note_path.relative_to(ROOT).as_posix()
        info.append(f'INFO {_info("Event-Note: openlia://workspace/minions/calendar/" + relative)}')
    line = (
        f"REM NOQUEUE {start.date().isoformat()} AT {start.strftime('%H:%M')} DURATION {minutes} TZ {payload['timezone']} "
        + " ".join(f"TAG {tag}" for tag in tags)
        + " "
        + " ".join(info)
        + f" MSG {_msg(title)}\n"
    )
    return line, note_path, note_content


def pending_proposals() -> list[dict]:
    directory = data_dir() / "pending"
    if not directory.exists():
        return []
    results = []
    for path in sorted(directory.glob("*.json")):
        safe_path(ROOT, path.relative_to(ROOT).as_posix())
        results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def render_dashboard() -> str:
    children = [
        'Callout(variant: "info", title: "Calendar", description: "Native Remind is the source of truth. New appointments require explicit SAVE confirmation; external notifications and invitations are off.")',
        "Calendar([views])",
    ]
    pending = [proposal for proposal in pending_proposals() if proposal.get("status") == "pending"]
    for proposal in pending:
        identifier = proposal["id"]
        payload = proposal["payload"]
        description = f"{payload['title']} — {payload['start']} to {payload['end']}\nInspect the proposed Remind entry before confirming."
        children.append(f"Callout(variant: \"info\", title: \"Pending appointment\", description: {json.dumps(description)})")
        children.append(
            "Form(name: \"minionInput\", fields: ["
            'FormControl(label: "Action", input: Select(name: "action", items: [SelectItem(value: "confirm", label: "Save appointment"), SelectItem(value: "cancel", label: "Cancel proposal")])), '
            f'FormControl(label: "Proposal", input: Select(name: "proposal_id", items: [SelectItem(value: "{identifier}", label: "{identifier}")])), '
            'FormControl(label: "Type SAVE to authorize", input: Input(name: "confirmation"))'
            "], buttons: Buttons(buttons: [Button(label: \"Apply selected action\", variant: \"primary\")]))"
        )
    content = "Stack(children: [\n  " + ",\n  ".join(children) + "\n])\nviews = Tabs([\n  TabItem(\"month\", \"Month\", [CalendarMonth()]),\n  TabItem(\"week\", \"Week\", [CalendarWeek()]),\n  TabItem(\"timeline\", \"Timeline\", [GanttChart()])\n])\n"
    atomic_write(safe_path(ROOT, "dashboard.openui"), content)
    return content


@contextlib.contextmanager
def write_lock():
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = safe_path(ROOT, "data/.write.lock")
    with path.open("a") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def process_input(payload: dict) -> dict:
    validate(payload, ROOT / "input.schema.json")
    config = load_config()
    action = payload.get("action", "preview")
    with write_lock():
        if action == "preview":
            identifier = uuid.uuid4().hex
            primary = calendar_file(config)
            files = snapshot(config)
            if files:
                run_native(files, primary)
            entry, note_path, note_content = _event_entry(payload, identifier)
            candidate = dict(files)
            candidate[primary] = files.get(primary, DEFAULT_REMIND) + entry
            run_native(candidate, primary)
            proposal = {
                "id": identifier,
                "status": "pending",
                "calendar_file": primary,
                "baseline": digest(files),
                "payload": payload,
                "entry": entry,
                "note_path": note_path.relative_to(ROOT).as_posix() if note_path else None,
                "note_content": note_content,
            }
        else:
            proposal_path = safe_path(ROOT, f"data/pending/{payload['proposal_id']}.json")
            if not proposal_path.is_file():
                raise ValueError("Unknown calendar proposal")
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            if proposal.get("status") != "pending":
                raise ValueError("Proposal already completed; create a new preview")
            if action == "confirm":
                primary = calendar_file(config)
                if proposal["calendar_file"] != primary or payload.get("confirmation") != "SAVE":
                    raise ValueError("Explicit SAVE confirmation and unchanged configuration required")
                files = snapshot(config)
                if digest(files) != proposal["baseline"]:
                    raise ValueError("Calendar changed since preview; cancel and create a new preview")
                if files:
                    run_native(files, primary)
                candidate = dict(files)
                candidate[primary] = files.get(primary, DEFAULT_REMIND) + proposal["entry"]
                run_native(candidate, primary)
                note_path = safe_path(ROOT, proposal["note_path"]) if proposal.get("note_path") else None
                if note_path and note_path.exists():
                    raise ValueError("Companion event note already exists")
                if note_path:
                    atomic_write(note_path, proposal["note_content"])
                try:
                    atomic_write(safe_path(data_dir(), primary), candidate[primary])
                except BaseException:
                    if note_path:
                        note_path.unlink(missing_ok=True)
                    raise
                proposal["status"] = "posted"
            else:
                proposal["status"] = "cancelled"
        atomic_write(
            safe_path(ROOT, f"data/pending/{proposal['id']}.json"),
            json.dumps(proposal, indent=2, ensure_ascii=False) + "\n",
        )
        render_dashboard()
        return {
            "proposal_id": proposal["id"],
            "status": proposal["status"],
            "next": "Inspect Dashboard and confirm with SAVE." if proposal["status"] == "pending" else "No further action required.",
        }


if __name__ == "__main__":
    load_config()
    render_dashboard()
    print("Read-only Calendar dashboard refreshed. No appointment changes.")
