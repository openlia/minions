#!/usr/bin/env python3
"""Collect a compact, read-only briefing source packet."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import quote

SCRIPT_PATH = Path(__file__).resolve()
SYSTEM_SCRIPTS_CANDIDATES = (
    SCRIPT_PATH.parents[3] / "system-skills" / "workspace-template-customization" / "scripts",
    SCRIPT_PATH.parents[3] / "skills" / "workspace-template-customization" / "scripts",
    SCRIPT_PATH.parents[2] / "workspace-template-customization" / "scripts",
)
for SYSTEM_SCRIPTS in SYSTEM_SCRIPTS_CANDIDATES:
    if SYSTEM_SCRIPTS.is_dir() and str(SYSTEM_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SYSTEM_SCRIPTS))
        break

from workspace_registry import briefing_sources, load_registry


MAX_SOURCE_READ = 16 * 1024
DEFAULT_EXCERPT_CHARS = 420
FRONTMATTER_PATTERN = re.compile(r"\A---[ \t]*\r?\n(.*?)(?:\r?\n---[ \t]*(?:\r?\n|\Z))", re.DOTALL)
FRONTMATTER_FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
DATE_FILENAME_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})\.md\Z")
LEGACY_BRIEFING_NAME_PATTERN = re.compile(r"daily-briefing-(\d{4}-\d{2}-\d{2})\.md\Z")

SOURCE_DIRECTORIES = (
    ("calendar", "Calendar", "calendar"),
    ("tasks", "Tasks", "tasks"),
    ("goals", "Goals", "goals"),
    ("decisions", "Decisions", "decisions"),
    ("knowledge/claims", "Claims", "claims"),
    ("inbox", "Inbox", "inbox"),
)
MINION_VIEW_FILENAME = "briefing.view.json"
MINION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BRIEFING_CATEGORIES = {"calendar", "tasks", "goals", "decisions", "monitors", "claims", "finance", "inbox", "extension"}
MINION_CATEGORY_ROOTS = {
    "calendar": "calendar",
    "tasks": "tasks",
    "goals": "goals",
    "decisions": "decisions",
    "claims": "knowledge/claims",
    "inbox": "inbox",
}
TERMINAL_TASK_STATUSES = {"done", "completed", "cancelled", "canceled", "archived"}
INACTIVE_RECORD_STATUSES = {"paused", "completed", "abandoned", "archived", "retired", "superseded", "rejected", "retracted"}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        return None
    return value


def _minion_briefing_sources(workspace: Path) -> dict[str, dict[str, Any]]:
    """Load reviewed, data-only Minion briefing views without executing apps."""
    root = workspace / "minions"
    if not root.is_dir() or root.is_symlink():
        return {}
    sources: dict[str, dict[str, Any]] = {}
    for app in sorted(root.iterdir()):
        if not app.is_dir() or app.is_symlink() or not MINION_ID_PATTERN.fullmatch(app.name):
            continue
        view_path = app / MINION_VIEW_FILENAME
        if view_path.is_symlink() or not view_path.is_file():
            continue
        try:
            if view_path.stat().st_size > 64 * 1024:
                continue
            view = json.loads(view_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(view, dict) or view.get("schema") != 1 or not isinstance(view.get("sources"), list):
            continue
        limits = view.get("limits") if isinstance(view.get("limits"), dict) else {}
        max_records = _bounded_int(limits.get("max_records"), 40, 1, 200)
        max_excerpt = _bounded_int(limits.get("max_excerpt_chars"), DEFAULT_EXCERPT_CHARS, 40, 4000)
        max_files = _bounded_int(limits.get("max_files"), 32, 1, 128)
        max_bytes = _bounded_int(limits.get("max_bytes"), 2 * 1024 * 1024, 1024, 8 * 1024 * 1024)
        if None in (max_records, max_excerpt, max_files, max_bytes):
            continue
        for raw in view["sources"]:
            if not isinstance(raw, dict):
                continue
            relative = raw.get("path")
            reader = raw.get("reader")
            label = raw.get("label")
            category = raw.get("category")
            if (
                not isinstance(relative, str)
                or not isinstance(label, str)
                or not label.strip()
                or reader not in {"markdown", "remind"}
                or category not in BRIEFING_CATEGORIES
            ):
                continue
            parts = Path(relative).parts
            if (
                len(parts) < 2
                or parts[0] != "data"
                or any(not part or part in {".", ".."} or part.startswith(".") for part in parts)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", relative)
            ):
                continue
            target = app / relative
            try:
                target.resolve().relative_to(app.resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            source_path = f"minions/{app.name}/{relative}"
            source_max_records = _bounded_int(raw.get("max_records"), max_records, 1, max_records)
            source_lookahead = _bounded_int(raw.get("lookahead_days"), 7, 0, 31)
            if source_max_records is None or source_lookahead is None:
                continue
            fields = raw.get("metadata_fields", [])
            if not isinstance(fields, list) or any(not isinstance(field, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", field) for field in fields):
                continue
            if source_path in sources:
                continue
            sources[source_path] = {
                "path": source_path,
                "target": target,
                "reader": reader,
                "label": label.strip(),
                "category": category,
                "max_records": source_max_records,
                "max_excerpt_chars": max_excerpt,
                "max_files": max_files,
                "max_bytes": max_bytes,
                "lookahead_days": source_lookahead,
                "metadata_fields": fields,
            }
    return sources


def _source_directories(workspace: Path) -> tuple[tuple[str, str, str], ...]:
    registry = load_registry(workspace)
    if registry is None:
        sources = SOURCE_DIRECTORIES
    else:
        sources = tuple(
            (source["path"], source["heading"], source["category"])
            for source in briefing_sources(registry)
        )
    minion_sources = _minion_briefing_sources(workspace)
    for spec in minion_sources.values():
        root = MINION_CATEGORY_ROOTS.get(spec["category"])
        if root:
            sources = tuple(source for source in sources if source[0] != root)
    sources += tuple((spec["path"], spec["label"], spec["category"]) for spec in minion_sources.values())
    return sources


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _date_value(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "~"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_scalar(value: str) -> str | None:
    value = value.strip()
    if not value or value.lower() in {"null", "none", "~"}:
        return None
    if value.startswith("[") or value.startswith("{"):
        return None
    if value.startswith("#"):
        return None
    if value[0] in {"'", '"'}:
        delimiter = value[0]
        escaped = False
        closing = None
        for index, char in enumerate(value[1:], start=1):
            if char == delimiter and not escaped:
                closing = index
                break
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
        if closing is not None:
            value = value[1:closing]
        else:
            value = value[1:]
    else:
        value = re.split(r"[ \t]+#", value, maxsplit=1)[0].strip()
    return value or None


def _parse_frontmatter(text: str) -> tuple[dict[str, str | None], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    metadata = {
        key: _parse_scalar(value)
        for key, value in FRONTMATTER_FIELD_PATTERN.findall(match.group(1))
    }
    return metadata, text[match.end() :]


def _briefing_report_date(relative_path: str | Path) -> date | None:
    """Return the date for a current or legacy daily briefing report path."""
    path = Path(relative_path)
    if path.parent.name == "daily-briefing" and path.parent.parent.name == "inbox":
        match = DATE_FILENAME_PATTERN.fullmatch(path.name)
    elif path.parent.name == "inbox":
        match = LEGACY_BRIEFING_NAME_PATTERN.fullmatch(path.name)
    else:
        return None
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _read_record(path: Path, workspace: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(MAX_SOURCE_READ)
        stat = path.stat()
    except OSError:
        return None
    try:
        relative = path.relative_to(workspace).as_posix()
    except ValueError:
        return None
    metadata, body = _parse_frontmatter(text)
    heading = HEADING_PATTERN.search(body)
    title = heading.group(1).strip() if heading else path.stem.replace("-", " ").strip().title()
    excerpt_lines = []
    excerpt_length = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        excerpt_lines.append(stripped)
        excerpt_length += len(stripped)
        if excerpt_length >= DEFAULT_EXCERPT_CHARS:
            break
    excerpt = re.sub(r"\s+", " ", " ".join(excerpt_lines)).strip()
    if len(excerpt) > DEFAULT_EXCERPT_CHARS:
        excerpt = excerpt[: DEFAULT_EXCERPT_CHARS - 1].rstrip() + "…"
    return {
        "path": relative,
        "title": title,
        "metadata": metadata,
        "excerpt": excerpt,
        "modified": date.fromtimestamp(stat.st_mtime),
    }


def _source_files(directory: Path, workspace: Path) -> list[Path]:
    if not _within_workspace(directory, workspace):
        return []
    if directory.is_file():
        if directory.is_symlink() or directory.suffix != ".md":
            return []
        return [directory]
    if not directory.is_dir():
        return []
    paths = []
    for root, directories, filenames in os.walk(directory, topdown=True, followlinks=False):
        current = Path(root)
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(".")
            and name != "archive"
            and not (current == workspace / "inbox" and name == "daily-briefing")
            and not (current / name).is_symlink()
        )
        for filename in sorted(filenames):
            if (
                not filename.endswith(".md")
                or filename.startswith(".")
                or filename == "README.md"
                or filename.endswith("-template.md")
            ):
                continue
            path = current / filename
            if path.is_symlink() or not path.is_file():
                continue
            try:
                relative = path.relative_to(workspace)
            except ValueError:
                continue
            if _briefing_report_date(relative) is not None:
                continue
            paths.append(path)
    return paths


def _remind_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        nested = payload.get("entries")
        if isinstance(nested, list):
            return _remind_entries(nested)
        if "date" in payload and any(key in payload for key in ("body", "plain_body", "summary", "text", "title")):
            return [payload]
        return []
    if isinstance(payload, list):
        entries = []
        for item in payload:
            entries.extend(_remind_entries(item))
        return entries
    return []


def _remind_info(entry: dict[str, Any]) -> dict[str, str]:
    raw = entry.get("info") or entry.get("INFO") or {}
    if isinstance(raw, dict):
        return {str(key).casefold().replace("_", "-"): str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if not isinstance(item, str) or ":" not in item:
                continue
            key, value = item.split(":", 1)
            result[key.strip().casefold().replace("_", "-")] = value.strip()
        return result
    return {}


def _bounded_remind_tree(spec: dict[str, Any]) -> str | None:
    """Bound literal includes before invoking the approved native reader."""
    primary = spec["target"]
    root = primary.parent
    pending = [primary]
    visited: set[Path] = set()
    total_bytes = 0
    include_pattern = re.compile(r"^\s*INCLUDE\s+(.+?)\s*$", re.IGNORECASE)
    forbidden_pattern = re.compile(r"^\s*(?:SYSINCLUDE|INCLUDECMD|DO)\b", re.IGNORECASE)
    while pending:
        path = pending.pop()
        try:
            resolved = path.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, RuntimeError, ValueError):
            return "Remind source path escapes its declared data folder"
        if path.is_symlink():
            return "Remind source contains a symlink"
        if resolved in visited:
            return "Remind source contains a repeated or cyclic include"
        if len(visited) >= spec["max_files"]:
            return "Remind source exceeds its file limit"
        if not path.is_file():
            return "Remind source or include is missing"
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "Remind source could not be read"
        visited.add(resolved)
        total_bytes += len(content.encode("utf-8"))
        if total_bytes > spec["max_bytes"]:
            return "Remind source exceeds its byte limit"
        for line in content.splitlines():
            if forbidden_pattern.match(line):
                return "Remind source contains an unsupported executable directive"
            match = include_pattern.match(line)
            if not match:
                continue
            relative = match.group(1).strip()
            parts = Path(relative).parts
            if (
                not parts
                or ".." in parts
                or any(part.startswith(".") for part in parts)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:rem|remind)", relative)
            ):
                return "Remind source contains a non-literal or unsafe include"
            pending.append(path.parent / relative)
    return None


def _read_remind_source(
    spec: dict[str, Any],
    lookahead_days: int,
    briefing_date: date,
) -> tuple[list[dict[str, Any]], str]:
    """Read a declared Minion Remind source through native JSON mode."""
    primary = spec["target"]
    directory = primary.parent
    filename = primary.name
    if not directory.is_dir():
        return [], "source directory missing"
    if not primary.is_file() or primary.is_symlink():
        return [], "native Remind source missing"
    tree_error = _bounded_remind_tree(spec)
    if tree_error:
        return [], tree_error
    try:
        modified = date.fromtimestamp(primary.stat().st_mtime)
    except OSError:
        modified = briefing_date
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for offset in range(min(spec["lookahead_days"], lookahead_days) + 1):
        requested = briefing_date + timedelta(days=offset)
        try:
            result = subprocess.run(
                ["remind", "-r", "-q", "-ppp", filename, requested.isoformat()],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return records, f"native Remind unavailable ({type(exc).__name__})"
        if result.returncode != 0 or result.stderr.strip():
            detail = result.stderr.strip() or result.stdout.strip() or "unknown native Remind error"
            return records, f"native Remind error: {detail[:160]}"
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return records, "native Remind returned invalid JSON"
        for index, entry in enumerate(_remind_entries(payload)):
            raw_date = entry.get("date") or entry.get("start_date") or entry.get("start")
            event_date = _date_value(raw_date) if raw_date is not None else requested
            if event_date != requested:
                continue
            info = _remind_info(entry)
            title = str(
                entry.get("body")
                or entry.get("plain_body")
                or entry.get("summary")
                or entry.get("text")
                or entry.get("msg")
                or entry.get("title")
                or "Untitled event"
            ).strip()
            raw_start = entry.get("eventstart_in_tz") or entry.get("eventstart") or entry.get("start_time") or entry.get("start")
            start = str(raw_start or "").strip()
            if not start and entry.get("time_in_tz", entry.get("time")) is not None:
                try:
                    minutes = int(entry.get("time_in_tz", entry.get("time")))
                    start = f"{minutes // 60:02d}:{minutes % 60:02d}"
                except (TypeError, ValueError):
                    start = ""
            duration = str(entry.get("eventduration") or entry.get("duration") or "").strip()
            key = (event_date.isoformat(), start, title)
            if key in seen:
                continue
            seen.add(key)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?", start):
                starts_at = start
            else:
                starts_at = event_date.isoformat() + (f"T{start}" if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", start) else "")
            excerpt = info.get("description") or info.get("agenda") or ""
            metadata = {
                "starts_at": starts_at,
                "date": event_date.isoformat(),
                "duration": duration,
                "status": "scheduled",
                "location": info.get("location"),
            }
            fields = spec["metadata_fields"]
            if fields:
                metadata = {key: metadata.get(key) for key in fields if key in metadata}
            source = f"{spec['path']}#{event_date.isoformat()}-{index}"
            records.append(
                {
                    "path": source,
                    "title": title,
                    "metadata": metadata,
                    "excerpt": excerpt[:spec["max_excerpt_chars"]],
                    "modified": modified,
                }
            )
            if len(records) >= spec["max_records"]:
                return records, f"{len(records)} native event(s) (limit reached)"
    return records, f"{len(records)} native event(s)"


def _read_markdown_source(spec: dict[str, Any], workspace: Path) -> tuple[list[dict[str, Any]], str]:
    target = spec["target"]
    if not target.exists():
        return [], "source directory missing"
    if target.is_symlink() or not _within_workspace(target, workspace):
        return [], "source path skipped"
    paths = _source_files(target, workspace)[: spec["max_files"]]
    total_bytes = 0
    records = []
    for path in paths:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue
        if total_bytes > spec["max_bytes"]:
            break
        record = _read_record(path, workspace)
        if record is None:
            continue
        fields = spec["metadata_fields"]
        if fields:
            record["metadata"] = {key: record["metadata"].get(key) for key in fields if key in record["metadata"]}
        record["excerpt"] = record["excerpt"][: spec["max_excerpt_chars"]]
        records.append(record)
        if len(records) >= spec["max_records"]:
            break
    suffix = " (limit reached)" if len(records) >= spec["max_records"] or len(paths) >= spec["max_files"] or total_bytes > spec["max_bytes"] else ""
    return records, f"{len(records)} Markdown record(s){suffix}"


def _read_minion_source(
    spec: dict[str, Any], workspace: Path, briefing_date: date, lookahead_days: int
) -> tuple[list[dict[str, Any]], str]:
    if spec["reader"] == "remind":
        return _read_remind_source(spec, lookahead_days, briefing_date)
    return _read_markdown_source(spec, workspace)


def _within_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _previous_briefing(workspace: Path, briefing_date: date) -> tuple[date, str] | None:
    inbox = workspace / "inbox"
    if not inbox.is_dir() or not _within_workspace(inbox, workspace):
        return None
    reports = []
    for path in inbox.rglob("*.md"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            relative = path.relative_to(workspace)
        except ValueError:
            continue
        report_date = _briefing_report_date(relative)
        if report_date is None:
            continue
        if report_date < briefing_date:
            reports.append((report_date, relative.as_posix()))
    return max(reports, default=None)


def _git_changes(
    workspace: Path,
    since: date,
    source_directories: tuple[tuple[str, str, str], ...] = SOURCE_DIRECTORIES,
) -> tuple[bool, list[str]]:
    try:
        root_result = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if root_result.returncode != 0:
            return False, []
        git_root = Path(root_result.stdout.strip()).resolve()
        if git_root != workspace:
            return False, []
        result = subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "log",
                f"--since={since.isoformat()} 00:00:00",
                "--format=",
                "--name-only",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, []
    if result.returncode != 0:
        return False, []
    changes = set()
    for raw_path in result.stdout.splitlines():
        relative = raw_path.strip().replace("\\", "/")
        if not relative or relative.startswith("/") or "../" in f"{relative}/":
            continue
        parts = Path(relative).parts
        if not parts or any(part.startswith(".") or part == "archive" for part in parts):
            continue
        if not relative.endswith(".md") or relative.endswith("-template.md"):
            continue
        if _briefing_report_date(relative) is not None:
            continue
        if any(
            relative == source_path or relative.startswith(source_path.rstrip("/") + "/")
            for source_path, _, _ in source_directories
        ):
            changes.add(relative)
    return True, sorted(changes)


def _record_candidate(
    record: dict[str, Any],
    category: str,
    briefing_date: date,
    lookahead_days: int,
    recent_days: int,
    changed_paths: set[str],
) -> tuple[int, str] | None:
    metadata = record["metadata"]
    status = str(metadata.get("status") or "").strip().lower()
    modified = record["modified"]
    recent_cutoff = briefing_date - timedelta(days=recent_days)
    reason = ""
    score = 0

    if category == "calendar":
        event_date = _date_value(metadata.get("starts_at") or metadata.get("date"))
        if event_date is None:
            score, reason = 20, "event date is missing or unrecognized; verify"
        elif briefing_date <= event_date <= briefing_date + timedelta(days=lookahead_days):
            distance = (event_date - briefing_date).days
            score, reason = 100 - distance * 4, "today" if distance == 0 else f"within {distance} day(s)"
        else:
            return None
    elif category == "tasks":
        if status in TERMINAL_TASK_STATUSES:
            return None
        due_date = _date_value(metadata.get("due_date") or metadata.get("due"))
        priority = str(metadata.get("priority") or "").lower()
        if due_date is not None and due_date < briefing_date:
            score, reason = 110, f"overdue since {due_date.isoformat()}"
        elif due_date == briefing_date:
            score, reason = 105, "due today"
        elif due_date is not None and due_date <= briefing_date + timedelta(days=lookahead_days):
            distance = (due_date - briefing_date).days
            score, reason = 85 - distance, f"due within {distance} day(s)"
        elif priority == "high":
            score, reason = 75, "open high-priority task"
        elif status in {"todo", "in-progress", "waiting", "in progress"}:
            score, reason = 55, f"open task ({status})"
        else:
            score, reason = 35, "task status or due date needs review"
    elif category == "goals":
        if status in INACTIVE_RECORD_STATUSES:
            return None
        target = _date_value(metadata.get("target_completion"))
        if target is not None and target <= briefing_date + timedelta(days=lookahead_days):
            score, reason = 80, f"active record with target date {target.isoformat()}"
        elif status == "active":
            score, reason = 65, "active record"
        else:
            score, reason = 35, "record status needs review"
    elif category == "monitors":
        if status in {"paused", "retired"}:
            return None
        if status in {"active", "triggered"}:
            score, reason = 75 if status == "triggered" else 65, f"{status} monitor"
        else:
            score, reason = 35, "monitor status needs review"
    elif category == "decisions":
        review_date = _date_value(metadata.get("review_date"))
        decision_date = _date_value(metadata.get("decision_date"))
        if review_date is not None and review_date <= briefing_date:
            score, reason = 90, f"review date reached ({review_date.isoformat()})"
        elif status in {"proposed", "pending"}:
            score, reason = 75, "unresolved decision"
        elif decision_date is not None and recent_cutoff <= decision_date <= briefing_date:
            score, reason = 65, f"decision recorded {decision_date.isoformat()}"
        elif record["path"] in changed_paths or modified >= recent_cutoff:
            age = max(0, (briefing_date - modified).days)
            score, reason = 60 + max(0, recent_days - age), "recently changed decision record"
        elif status:
            return None
        else:
            score, reason = 30, "decision status needs review"
    elif category == "finance":
        review_date = _date_value(metadata.get("review_date") or metadata.get("next_review_date"))
        reconciliation = str(metadata.get("reconciliation_status") or "").lower()
        if status in {"blocked", "needs-attention"} or reconciliation == "discrepancy":
            score, reason = 100, "finance record needs attention"
        elif review_date is not None and review_date < briefing_date:
            score, reason = 105, f"finance review overdue since {review_date.isoformat()}"
        elif review_date == briefing_date:
            score, reason = 100, "finance review due today"
        elif review_date is not None and review_date <= briefing_date + timedelta(days=lookahead_days):
            distance = (review_date - briefing_date).days
            score, reason = 85 - distance, f"finance review due within {distance} day(s)"
        elif status in {"received", "extracting", "pending-review", "ready-to-post", "draft", "in-progress"}:
            score, reason = 75, f"open finance record ({status})"
        elif record["path"] in changed_paths or modified >= recent_cutoff:
            age = max(0, (briefing_date - modified).days)
            score, reason = 60 + max(0, recent_days - age), "recently changed finance record"
        else:
            return None
    elif category == "claims":
        valid_from = _date_value(metadata.get("valid_from"))
        valid_until = _date_value(metadata.get("valid_until"))
        review_after = _date_value(metadata.get("review_after"))
        if status in {"superseded", "retracted", "rejected"}:
            return None
        if status in {"candidate", "contested", "stale"}:
            score, reason = 85, f"claim status is {status}"
        elif valid_until is not None and valid_until < briefing_date:
            score, reason = 80, f"claim validity ended {valid_until.isoformat()}"
        elif review_after is not None and review_after <= briefing_date:
            score, reason = 75, f"claim review due ({review_after.isoformat()})"
        elif valid_from is not None and valid_from > briefing_date:
            return None
        elif status == "active":
            score, reason = 45, "active claim for context"
        else:
            score, reason = 30, "claim status needs review"
    elif category == "inbox":
        if record["path"] in changed_paths:
            score, reason = 65, "recently changed capture"
        elif modified >= recent_cutoff:
            age = max(0, (briefing_date - modified).days)
            score, reason = 60 - age, f"inbox capture {age} day(s) old"
        else:
            score, reason = 30, "older inbox item; verify whether still pending"
    elif category == "extension":
        if record["path"] in changed_paths:
            score, reason = 65, "recently changed registered extension record"
        elif modified >= recent_cutoff:
            age = max(0, (briefing_date - modified).days)
            score, reason = 55 - age, f"registered extension record {age} day(s) old"
        else:
            return None
    else:
        return None

    if record["path"] in changed_paths:
        score += 15
        reason += "; changed in Git history"
    return score, reason


def _source_link(relative_path: str) -> str:
    normalized = relative_path.strip().replace("\\", "/")
    parts = Path(normalized).parts
    if (
        not parts
        or Path(normalized).is_absolute()
        or ".." in parts
        or any(part in {"", "."} or part.startswith(".") for part in parts)
    ):
        return "source path unavailable"
    uri = "openlia://workspace/" + quote(normalized, safe="/-._~")
    return f"[source]({uri})"


def _candidate_block(record: dict[str, Any], reason: str) -> str:
    metadata = record["metadata"]
    relevant_fields = (
        "status",
        "priority",
        "starts_at",
        "due_date",
        "target_completion",
        "decision_date",
        "review_date",
        "valid_until",
        "review_after",
    )
    details = [f"{key}={metadata[key]}" for key in relevant_fields if metadata.get(key)]
    lines = [f"- **{record['title']}**"]
    lines.append(f"  - Relevance: {reason}")
    lines.append(f"  - Path: `{record['path']}` ({_source_link(record['path'])})")
    if details:
        lines.append(f"  - Metadata: {'; '.join(details)}")
    if record["excerpt"]:
        lines.append(f"  - Excerpt: {record['excerpt']}")
    return "\n".join(lines)


def collect_sources(
    workspace_dir: str | Path,
    briefing_date: date,
    *,
    since: date | None = None,
    lookahead_days: int = 7,
    recent_days: int = 7,
    max_docs: int = 40,
    max_per_section: int = 8,
    max_chars: int = 18000,
) -> str:
    """Collect a bounded, read-only packet of likely briefing sources."""
    workspace = Path(workspace_dir).expanduser().resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace directory not found: {workspace}")
    if lookahead_days < 0 or recent_days < 0:
        raise ValueError("date windows must be zero or greater")
    if max_docs < 1 or max_per_section < 1:
        raise ValueError("document limits must be greater than zero")
    if max_chars < 2048:
        raise ValueError("max_chars must be at least 2048")

    previous = _previous_briefing(workspace, briefing_date)
    since_date = since or (previous[0] if previous else briefing_date - timedelta(days=1))
    source_directories = _source_directories(workspace)
    minion_sources = _minion_briefing_sources(workspace)
    git_available, git_paths = _git_changes(workspace, since_date, source_directories)
    changed_paths = set(git_paths)

    status_by_source: dict[str, str] = {}
    candidates_by_source: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
    scanned_count = 0
    for relative_dir, heading, category in source_directories:
        directory = workspace / relative_dir
        minion_spec = minion_sources.get(relative_dir)
        if minion_spec is not None:
            minion_records, minion_status = _read_minion_source(
                minion_spec, workspace, briefing_date, lookahead_days
            )
            scanned_count += len(minion_records)
            records = []
            for record in minion_records:
                candidate = _record_candidate(
                    record,
                    category,
                    briefing_date,
                    lookahead_days,
                    recent_days,
                    changed_paths,
                )
                if candidate is not None:
                    score, reason = candidate
                    records.append((score, record, reason))
            records.sort(
                key=lambda item: (
                    -item[0],
                    str(item[1]["metadata"].get("starts_at") or "9999"),
                    item[1]["title"].casefold(),
                    item[1]["path"],
                )
            )
            candidates_by_source[relative_dir] = records
            status_by_source[relative_dir] = minion_status
            continue
        if not directory.is_dir():
            status_by_source[relative_dir] = "source directory missing"
            candidates_by_source[relative_dir] = []
            continue
        if not _within_workspace(directory, workspace):
            status_by_source[relative_dir] = "source directory resolves outside workspace; skipped"
            candidates_by_source[relative_dir] = []
            continue
        records = []
        for path in _source_files(directory, workspace):
            scanned_count += 1
            record = _read_record(path, workspace)
            if record is None:
                continue
            candidate = _record_candidate(
                record,
                category,
                briefing_date,
                lookahead_days,
                recent_days,
                changed_paths,
            )
            if candidate is not None:
                score, reason = candidate
                records.append((score, record, reason))
        records.sort(
            key=lambda item: (
                -item[0],
                str(item[1]["metadata"].get("due_date") or item[1]["metadata"].get("starts_at") or "9999"),
                item[1]["title"].casefold(),
                item[1]["path"],
            )
        )
        candidates_by_source[relative_dir] = records
        status_by_source[relative_dir] = f"{len(records)} matching record(s)"

    if since is not None:
        previous_line = f"Git history baseline: {since.isoformat()} (explicit)."
    elif previous:
        previous_line = f"Git history baseline: {previous[0].isoformat()} (latest earlier briefing)."
    else:
        previous_line = f"Git history baseline: {since_date.isoformat()} (previous day; no earlier briefing found)."

    header_lines = [
        "# Daily Briefing Source Packet",
        "",
        f"Date: {briefing_date.isoformat()}",
        f"Calendar window: today through {lookahead_days} day(s) ahead.",
        f"Recent-record window: {recent_days} day(s).",
        previous_line,
        "",
        "## Collection Status",
        f"- Source records scanned: {scanned_count}.",
    ]
    for relative_dir, heading, _ in source_directories:
        header_lines.append(f"- {heading}: {status_by_source[relative_dir]}.")
    if git_available:
        header_lines.append(f"- Git history: {len(git_paths)} relevant path(s) changed since baseline.")
    else:
        header_lines.append("- Git history: unavailable for this workspace.")
    header = "\n".join(header_lines) + "\n\n"

    blocks: list[tuple[str, bool]] = []
    total_candidates = 0
    selected_records: dict[str, list[tuple[int, dict[str, Any], str]]] = {
        relative_dir: [] for relative_dir, _, _ in source_directories
    }
    for records in candidates_by_source.values():
        total_candidates += len(records)
    remaining_docs = max_docs
    while remaining_docs:
        selected_any = False
        for relative_dir, _, _ in source_directories:
            records = candidates_by_source[relative_dir]
            selected_for_section = selected_records[relative_dir]
            if len(selected_for_section) >= min(len(records), max_per_section):
                continue
            selected_for_section.append(records[len(selected_for_section)])
            remaining_docs -= 1
            selected_any = True
            if not remaining_docs:
                break
        if not selected_any:
            break

    for relative_dir, heading, _ in source_directories:
        records = candidates_by_source[relative_dir]
        section_records = selected_records[relative_dir]
        blocks.append((f"## {heading}", False))
        if not (workspace / relative_dir).exists():
            blocks.append(("- Source directory is missing.", False))
        elif "resolves outside workspace" in status_by_source[relative_dir]:
            blocks.append(("- Source directory skipped because it resolves outside the workspace.", False))
        elif not section_records:
            if records:
                blocks.append(("- No matching records included (document limit reached).", False))
            else:
                blocks.append(("- No matching records found in the available source directory.", False))
        else:
            blocks.extend((_candidate_block(record, reason), True) for _, record, reason in section_records)
        blocks.append(("", False))
    selected_count = sum(len(records) for records in selected_records.values())
    doc_limit_omitted = max(0, total_candidates - selected_count)

    git_block = ["## Recent Workspace Changes"]
    if git_available and git_paths:
        git_block.extend(f"- `{path}` ({_source_link(path)})" for path in git_paths[:20])
        if len(git_paths) > 20:
            git_block.append(f"- {len(git_paths) - 20} additional changed path(s) omitted from this list.")
    elif git_available:
        git_block.append("- No relevant Markdown changes found since the baseline.")
    else:
        git_block.append("- No local Git history available; use source mtimes and dates as context.")
    blocks.extend((block, False) for block in git_block)

    body_blocks: list[tuple[str, bool]] = []
    candidates_in_packet = 0
    packet_char_omitted = 0
    for index, (block, is_record) in enumerate(blocks):
        remaining_records = sum(1 for _, is_pending_record in blocks[index + 1 :] if is_pending_record)
        would_include = candidates_in_packet + (1 if is_record else 0)
        proposed_footer = (
            "\n\n## Packet limits\n"
            f"- Included source records: {would_include}.\n"
            f"- Omitted by document/section limits: {doc_limit_omitted}.\n"
            f"- Omitted by character limit: {remaining_records}.\n"
            "Use the cited paths to read selected full records when needed.\n"
        )
        proposed_body = "\n\n".join([*(text for text, _ in body_blocks), block])
        if len(header) + len(proposed_body) + len(proposed_footer) <= max_chars:
            body_blocks.append((block, is_record))
            if is_record:
                candidates_in_packet += 1
        else:
            packet_char_omitted = sum(1 for _, is_pending_record in blocks[index:] if is_pending_record)
            break

    def assemble_packet() -> str:
        footer = (
            "\n\n## Packet limits\n"
            f"- Included source records: {candidates_in_packet}.\n"
            f"- Omitted by document/section limits: {doc_limit_omitted}.\n"
            f"- Omitted by character limit: {packet_char_omitted}.\n"
            "Use the cited paths to read selected full records when needed.\n"
        )
        body = "\n\n".join(text for text, _ in body_blocks)
        return header + body + footer

    packet = assemble_packet()
    while len(packet) > max_chars and body_blocks:
        _, was_record = body_blocks.pop()
        if was_record:
            candidates_in_packet -= 1
            packet_char_omitted += 1
        packet = assemble_packet()
    return packet


def _write_test_record(path: Path, text: str, modified: date | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if modified:
        stamp = datetime.combine(modified, datetime.min.time()).timestamp()
        os.utime(path, (stamp, stamp))


def self_test() -> None:
    assert _source_link("calendar/today.md") == "[source](openlia://workspace/calendar/today.md)"
    assert _source_link("/outside/private.md") == "source path unavailable"
    assert _briefing_report_date("inbox/daily-briefing/2026-01-02.md") == date(2026, 1, 2)
    assert _briefing_report_date("inbox/daily-briefing-2026-01-02.md") == date(2026, 1, 2)
    assert _briefing_report_date("inbox/daily-briefing/not-a-date.md") is None

    with TemporaryDirectory(prefix="daily-briefing-collect-") as temp_dir:
        workspace = Path(temp_dir)
        _write_test_record(
            workspace / "calendar" / "today.md",
            "---\nstarts_at: 2026-01-02T10:00:00Z\n---\n# Planning\nDiscuss launch readiness.\n",
        )
        _write_test_record(
            workspace / "calendar" / "next-week.md",
            "---\nstarts_at: 2026-01-20T10:00:00Z\n---\n# Far event\n",
        )
        _write_test_record(
            workspace / "calendar" / "undated.md",
            "---\nstarts_at: null\n---\n# Undated event\nConfirm the date.\n",
        )
        _write_test_record(
            workspace / "tasks" / "open.md",
            "---\nstatus: todo\npriority: high\ndue_date: 2026-01-02\n---\n# Prepare agenda\nSend the draft.\n",
        )
        _write_test_record(
            workspace / "tasks" / "done.md",
            "---\nstatus: done\npriority: high\ndue_date: 2026-01-02\n---\n# Completed task\n",
        )
        _write_test_record(
            workspace / "goals" / "active.md",
            '---\nstatus: "active" # current\n---\n# Website refresh\nReview the next milestone.\n',
        )
        _write_test_record(
            workspace / "monitors" / "active.md",
            "---\nstatus: active\n---\n# Service status\nWatch error rate.\n",
        )
        _write_test_record(
            workspace / "knowledge" / "claims" / "claim.md",
            "---\nstatus: active\nvalid_until: 2026-12-31\n---\n# Preferred focus\nMorning work is best.\n",
        )
        _write_test_record(
            workspace / "inbox" / "capture.md",
            "# Capture\nFollow up on the launch notes.\n",
            modified=date(2026, 1, 2),
        )
        _write_test_record(workspace / "archive" / "old.md", "# Archived secret\n")
        _write_test_record(workspace / "tasks" / "task-template.md", "# Template secret\n")
        _write_test_record(workspace / "tasks" / ".hidden.md", "# Hidden secret\n")
        _write_test_record(
            workspace / "inbox" / "daily-briefing" / "2026-01-01.md",
            "# Previous briefing\n",
        )
        _write_test_record(
            workspace / "inbox" / "daily-briefing-2025-12-31.md",
            "# Legacy previous briefing\n",
        )

        packet = collect_sources(workspace, date(2026, 1, 2), max_chars=12000)
        assert "Planning" in packet
        assert "Undated event" in packet
        assert "event date is missing or unrecognized" in packet
        assert "Prepare agenda" in packet
        assert "Website refresh" in packet
        assert "Preferred focus" in packet
        assert "Follow up on the launch notes" in packet
        assert "Far event" not in packet
        assert "Completed task" not in packet
        assert "Archived secret" not in packet
        assert "Template secret" not in packet
        assert "Hidden secret" not in packet
        assert "Previous briefing" not in packet
        assert "Legacy previous briefing" not in packet
        assert "Git history baseline: 2026-01-01" in packet
        assert "openlia://workspace/calendar/today.md" in packet
        assert "Source directory is missing" in packet
        short_packet = collect_sources(workspace, date(2026, 1, 2), max_chars=2048)
        assert len(short_packet) <= 2048
        limited_packet = collect_sources(workspace, date(2026, 1, 2), max_docs=2, max_chars=12000)
        omitted = re.search(r"Omitted by document/section limits: (\d+)", limited_packet)
        assert omitted and int(omitted.group(1)) > 0
        exit_code = main(
            [
                "--collect",
                "--workspace-root",
                str(workspace),
                "--date",
                "2026-01-02",
                "--max-chars",
                "2048",
            ]
        )
        assert exit_code == 0
        assert not (workspace / "inbox" / "daily-briefing" / "2026-01-02.md").exists()

        _write_test_record(
            workspace / "learning" / "topics" / "workflow.md",
            "# Workflow experiment\nTry one reversible AI-assisted task.\n",
            modified=date(2026, 1, 2),
        )
        registered_packet = collect_sources(workspace, date(2026, 1, 2), max_chars=30000)
        assert "Service status" in registered_packet
        assert "## Learning Topics" in registered_packet
        assert "learning/topics/workflow.md" in registered_packet
        assert "Workflow experiment" in registered_packet
        _write_test_record(
            workspace / "finance" / "reviews" / "monthly.md",
            "---\nstatus: needs-attention\nreview_date: 2026-01-02\n---\n# January finance review\nReconcile the card statement.\n",
            modified=date(2026, 1, 2),
        )
        registered_packet = collect_sources(workspace, date(2026, 1, 2), max_chars=30000)
        assert "## Finance Reviews" in registered_packet
        assert "January finance review" in registered_packet
        assert "finance record needs attention" in registered_packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="Collect a compact packet from a workspace")
    parser.add_argument("--workspace-root", type=Path, help="Explicit workspace root")
    parser.add_argument("--date", type=_parse_iso_date, help="Briefing date (YYYY-MM-DD)")
    parser.add_argument("--since", type=_parse_iso_date, help="Git history baseline date (YYYY-MM-DD)")
    parser.add_argument("--lookahead-days", type=int, default=7, help="Calendar/task lookahead window")
    parser.add_argument("--recent-days", type=int, default=7, help="Recent decision/inbox window")
    parser.add_argument("--max-docs", type=int, default=40, help="Maximum source documents in packet")
    parser.add_argument("--max-per-section", type=int, default=8, help="Maximum source documents per area")
    parser.add_argument("--max-chars", type=int, default=18000, help="Maximum packet size in characters")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic offline tests")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("ok")
        return 0
    try:
        if not args.collect:
            parser.error("--collect is required unless --self-test is used")
        if args.workspace_root is None or args.date is None:
            parser.error("--collect requires --workspace-root and --date")
        packet = collect_sources(
            args.workspace_root,
            args.date,
            since=args.since,
            lookahead_days=args.lookahead_days,
            recent_days=args.recent_days,
            max_docs=args.max_docs,
            max_per_section=args.max_per_section,
            max_chars=args.max_chars,
        )
        sys.stdout.write(packet)
    except OSError | ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
