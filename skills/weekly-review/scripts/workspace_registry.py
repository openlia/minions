#!/usr/bin/env python3
"""Discover workspace collections and load OpenLia runtime permissions."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml


PERMISSIONS_FILENAME = "permissions.yaml"
DEFAULT_PERMISSIONS_PATH = Path("/opt/data/permissions.yaml")
FEATURE_SCHEMA_FILENAME = "feature.schema.json"
REGISTRY_VERSION = 1

# Legacy constants retained for import compatibility where needed
REGISTRY_FILENAME = "workspace.yaml"
REGISTRY_SCHEMA_FILENAME = "workspace.schema.json"
POLICY_FILENAME = "permissions.yaml"
POLICY_SCHEMA_FILENAME = "permissions.schema.json"

CORE_ROOTS = {
    "inbox",
    "goals",
    "knowledge",
    "tasks",
    "calendar",
    "archive",
}
ROUTES = {
    "task",
    "event",
    "decision",
    "idea",
    "research",
    "claim",
    "finance",
    "archive",
    "review",
}
BRIEFING_CATEGORIES = {
    "calendar",
    "tasks",
    "goals",
    "decisions",
    "monitors",
    "claims",
    "finance",
    "inbox",
    "extension",
}
PATH_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$"
)

DEFAULT_PERMISSIONS: dict[str, Any] = {
    "version": 1,
    "destructive": {
        "delete_records": "ask",
        "overwrite_records": "ask",
    },
    "external": {
        "send_messages": "ask",
        "modify_external_calendar": "ask",
        "purchases": "ask",
        "financial_transactions": "ask",
    },
    "scheduled_work": {
        "enabled": True,
        "report_destination": "inbox/daily-briefing",
    },
}

_KNOWN_DOMAIN_METADATA: dict[str, dict[str, Any]] = {
    "inbox": {
        "kind": "core",
        "label": "Inbox",
        "purpose": "Captured items awaiting review or triage",
        "route": "review",
        "include_in_briefing": True,
        "briefing_category": "inbox",
    },
    "inbox/daily-briefing": {
        "kind": "extension",
        "label": "Daily Briefings",
        "purpose": "Generated daily briefing reports",
        "include_in_briefing": False,
    },
    "goals": {
        "kind": "core",
        "label": "Goals",
        "purpose": "Outcome-oriented personal and project goals",
        "include_in_briefing": True,
        "briefing_category": "goals",
    },
    "goals/decisions": {
        "kind": "extension",
        "label": "Decisions",
        "purpose": "Decision records under goals",
        "route": "decision",
        "include_in_briefing": True,
        "briefing_category": "decisions",
    },
    "decisions": {
        "kind": "extension",
        "label": "Decisions",
        "purpose": "Decision records and trade-off analyses",
        "route": "decision",
        "include_in_briefing": True,
        "briefing_category": "decisions",
    },
    "knowledge": {
        "kind": "core",
        "label": "Knowledge",
        "purpose": "Durable notes, research, and claims",
        "include_in_briefing": False,
    },
    "knowledge/claims": {
        "kind": "extension",
        "label": "Claims",
        "purpose": "Atomic, evidence-backed claims and preferences",
        "route": "claim",
        "include_in_briefing": True,
        "briefing_category": "claims",
    },
    "knowledge/research": {
        "kind": "extension",
        "label": "Research",
        "purpose": "Research notes and source syntheses",
        "route": "research",
        "include_in_briefing": False,
    },
    "tasks": {
        "kind": "core",
        "label": "Tasks",
        "purpose": "Actionable commitments and next steps",
        "route": "task",
        "include_in_briefing": True,
        "briefing_category": "tasks",
    },
    "calendar": {
        "kind": "core",
        "label": "Calendar",
        "purpose": "Scheduled events, reminders, and dated plans",
        "route": "event",
        "include_in_briefing": True,
        "briefing_category": "calendar",
    },
    "archive": {
        "kind": "core",
        "label": "Archive",
        "purpose": "Inactive or completed records preserved for reference",
        "route": "archive",
        "include_in_briefing": False,
    },
    "finance": {
        "kind": "extension",
        "label": "Finance",
        "purpose": "Journals, budgets, and financial records",
        "include_in_briefing": True,
        "briefing_category": "finance",
    },
    "finance/intake": {
        "kind": "extension",
        "label": "Finance Intake",
        "purpose": "Financial statements and receipts pending reconciliation",
        "route": "finance",
        "include_in_briefing": False,
    },
    "monitors": {
        "kind": "extension",
        "label": "Monitors",
        "purpose": "Recurring watch topics and alert conditions",
        "include_in_briefing": True,
        "briefing_category": "monitors",
    },
    "ideas": {
        "kind": "extension",
        "label": "Ideas",
        "purpose": "Exploratory concepts and possibilities",
        "route": "idea",
        "include_in_briefing": False,
    },
}


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in mapping:
                raise ValueError(f"duplicate YAML key: {key}")
        except TypeError as exc:
            raise ValueError("YAML mapping keys must be scalar values") from exc
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _normalize(value: Any, active: set[int] | None = None) -> Any:
    if active is None:
        active = set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise ValueError("recursive YAML aliases are not supported")
        active.add(identity)
        try:
            return {key: _normalize(item, active) for key, item in value.items()}
        finally:
            active.remove(identity)
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise ValueError("recursive YAML aliases are not supported")
        active.add(identity)
        try:
            return [_normalize(item, active) for item in value]
        finally:
            active.remove(identity)
    return value


def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or not PATH_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a relative slash-separated workspace path")
    parts = value.split("/")
    if any(part in {".", ".."} or part.startswith(".") for part in parts):
        raise ValueError(f"{field} must not contain hidden or parent path segments")
    return value


def registry_path(workspace: Path) -> Path:
    return workspace / REGISTRY_FILENAME


def schema_path(workspace: Path) -> Path:
    return workspace / REGISTRY_SCHEMA_FILENAME


def permissions_path(workspace: Path | None = None) -> Path:
    configured = os.environ.get("OPENLIA_PERMISSIONS_FILE")
    if configured:
        return Path(configured).expanduser()
    if workspace is not None:
        root = Path(workspace).expanduser().resolve()
        sibling = root.parent / PERMISSIONS_FILENAME
        if sibling.exists() or root.parent != Path("/"):
            return sibling
    return DEFAULT_PERMISSIONS_PATH


def policy_path(workspace: Path) -> Path:
    return permissions_path(workspace)


def policy_schema_path(workspace: Path) -> Path:
    return workspace / POLICY_SCHEMA_FILENAME


def feature_schema_path(workspace: Path) -> Path:
    return workspace / FEATURE_SCHEMA_FILENAME


def _path_is_within(path: Any, parent: Any) -> bool:
    """Return whether two relative workspace paths have a safe containment relationship."""
    if not isinstance(path, str) or not isinstance(parent, str):
        return False
    if path.startswith("/") or parent.startswith("/"):
        return False
    path_parts = path.strip("/").split("/")
    parent_parts = parent.strip("/").split("/")
    if not path_parts or not parent_parts:
        return False
    if any(not part or part in {".", ".."} for part in path_parts + parent_parts):
        return False
    return path_parts[: len(parent_parts)] == parent_parts


def _human_label(rel_path: str) -> str:
    words = [
        part.capitalize()
        for segment in rel_path.split("/")
        for part in re.split(r"[-_]+", segment)
        if part
    ]
    return " ".join(words) or rel_path


IGNORED_COLLECTION_DIRS = {"node_modules", "__pycache__", ".venv", ".pytest_cache"}


def discover_domains(workspace: str | Path) -> list[dict[str, Any]]:
    """Discover workspace domains and collections from folders, templates, and manifests."""
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        return []

    discovered_paths: set[str] = set(CORE_ROOTS) | {"knowledge/claims"}
    if (root / "goals/decisions").is_dir():
        discovered_paths.add("goals/decisions")
    else:
        discovered_paths.add("decisions")

    # 1. Top-level directories
    try:
        for entry in sorted(root.iterdir()):
            if entry.name.startswith(".") or entry.is_symlink() or not entry.is_dir():
                continue
            if entry.name in IGNORED_COLLECTION_DIRS:
                continue
            discovered_paths.add(entry.name)
    except OSError:
        pass

    # 2. Prune app internals and dependencies before walking ordinary collections.
    for current, directories, filenames in os.walk(root, followlinks=False):
        folder = Path(current)
        directories[:] = sorted(
            name for name in directories
            if not name.startswith(".") and name not in IGNORED_COLLECTION_DIRS
            and not (folder / name).is_symlink()
        )
        rel_parent = folder.relative_to(root).as_posix()
        if rel_parent == ".":
            continue
        top_root = rel_parent.split("/", 1)[0]
        files = [name for name in filenames if not (folder / name).is_symlink()]
        has_contract = any(name.endswith(("-template.md", ".schema.json")) for name in files)
        has_records = any(name.endswith(".md") for name in files)
        if has_contract or (has_records and (top_root not in CORE_ROOTS or rel_parent in _KNOWN_DOMAIN_METADATA)):
            discovered_paths.add(rel_parent)

    # 3. Well-known subdirectories if they exist on disk
    for known_path in _KNOWN_DOMAIN_METADATA:
        if (root / known_path).is_dir():
            discovered_paths.add(known_path)

    # Leaf custom directories (with no deeper discovered child) are included in briefing as extensions
    custom_candidates = {
        p
        for p in discovered_paths
        if p not in _KNOWN_DOMAIN_METADATA
        and p.split("/", 1)[0] not in CORE_ROOTS
        and p.split("/", 1)[0] != "sources"
    }
    leaf_custom_candidates = {
        p
        for p in custom_candidates
        if not any(other != p and other.startswith(p + "/") for other in custom_candidates)
    }

    result: list[dict[str, Any]] = []
    for rel_path in sorted(discovered_paths):
        folder = root / rel_path
        known = _KNOWN_DOMAIN_METADATA.get(rel_path, {})
        kind = "core" if rel_path in CORE_ROOTS else "extension"
        label = known.get("label") or _human_label(rel_path)
        purpose = known.get("purpose") or f"Workspace collection in {rel_path}"
        include_in_briefing = bool(known.get("include_in_briefing", False))
        briefing_category = known.get("briefing_category")
        route = known.get("route")

        if rel_path not in _KNOWN_DOMAIN_METADATA and rel_path in leaf_custom_candidates:
            if rel_path.startswith("finance/"):
                include_in_briefing = True
                briefing_category = "finance"
            else:
                include_in_briefing = True
                briefing_category = "extension"
        elif rel_path == "finance" and any(
            p.startswith("finance/") and p in leaf_custom_candidates for p in discovered_paths
        ):
            # Avoid overlapping briefing paths when a finance/* leaf collection is present
            include_in_briefing = False

        template_rel: str | None = None
        if folder.is_dir():
            templates = sorted(
                p for p in folder.glob("*-template.md") if p.is_file() and not p.is_symlink()
            )
            if len(templates) == 1:
                template_rel = templates[0].relative_to(root).as_posix()

            manifest_file = folder / "project-manifest.toml"
            if manifest_file.is_file() and not manifest_file.is_symlink():
                try:
                    manifest = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
                    proj = manifest.get("project")
                    if isinstance(proj, dict):
                        if isinstance(proj.get("name"), str) and proj["name"].strip():
                            label = proj["name"].strip()
                        elif isinstance(proj.get("title"), str) and proj["title"].strip():
                            label = proj["title"].strip()
                        if isinstance(proj.get("description"), str) and proj["description"].strip():
                            purpose = proj["description"].strip()
                except Exception:
                    pass

        entry_dict: dict[str, Any] = {
            "path": rel_path,
            "kind": kind,
            "label": label,
            "purpose": purpose,
            "include_in_briefing": include_in_briefing,
        }
        if briefing_category:
            entry_dict["briefing_category"] = briefing_category
        if route:
            entry_dict["route"] = route
        if template_rel:
            entry_dict["template"] = template_rel
        result.append(entry_dict)

    return result


def load_registry(workspace: str | Path, *, required: bool = False) -> dict[str, Any] | None:
    """Return discovered workspace collections as a registry structure."""
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        if required:
            raise ValueError(f"workspace directory does not exist: {root}")
        return None
    return {
        "version": REGISTRY_VERSION,
        "domains": discover_domains(root),
    }


def _validate_and_normalize_permissions(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("permissions file must contain a YAML mapping")

    # Support either top-level destructive/external or legacy delegation.destructive/external
    delegation = raw.get("delegation") if isinstance(raw.get("delegation"), dict) else {}

    raw_destructive = raw.get("destructive")
    if raw_destructive is None and isinstance(delegation, dict):
        raw_destructive = delegation.get("destructive")
    if raw_destructive is None:
        raw_destructive = {}
    if not isinstance(raw_destructive, dict):
        raise ValueError("permissions.destructive must be a mapping")

    destructive: dict[str, str] = {}
    for key, default_val in DEFAULT_PERMISSIONS["destructive"].items():
        val = raw_destructive.get(key, default_val)
        if val not in {"ask", "deny"}:
            raise ValueError(
                f"invalid destructive permission for {key}: {val!r} (expected 'ask' or 'deny')"
            )
        destructive[key] = val

    raw_external = raw.get("external")
    if raw_external is None and isinstance(delegation, dict):
        raw_external = delegation.get("external")
    if raw_external is None:
        raw_external = {}
    if not isinstance(raw_external, dict):
        raise ValueError("permissions.external must be a mapping")

    external: dict[str, str] = {}
    for key, default_val in DEFAULT_PERMISSIONS["external"].items():
        val = raw_external.get(key, default_val)
        if val not in {"ask", "allow", "deny"}:
            raise ValueError(
                f"invalid external permission for {key}: {val!r} (expected 'ask', 'allow', or 'deny')"
            )
        external[key] = val

    raw_scheduled = raw.get("scheduled_work")
    if raw_scheduled is None:
        raw_scheduled = {}
    if not isinstance(raw_scheduled, dict):
        raise ValueError("permissions.scheduled_work must be a mapping")

    enabled = raw_scheduled.get("enabled", DEFAULT_PERMISSIONS["scheduled_work"]["enabled"])
    if not isinstance(enabled, bool):
        raise ValueError("permissions.scheduled_work.enabled must be a boolean")

    report_dest = raw_scheduled.get(
        "report_destination",
        DEFAULT_PERMISSIONS["scheduled_work"]["report_destination"],
    )
    report_dest = _safe_relative_path(
        report_dest, "permissions.scheduled_work.report_destination"
    )

    return {
        "version": 1,
        "destructive": destructive,
        "external": external,
        "scheduled_work": {
            "enabled": enabled,
            "report_destination": report_dest,
        },
        # Retain normalized delegation view for callers reading policy["delegation"]
        "delegation": {
            "destructive": destructive,
            "external": external,
        },
    }


def load_permissions(
    workspace_or_file: str | Path | None = None,
    *,
    required: bool = False,
) -> dict[str, Any]:
    """Load and validate consequential permissions from /opt/data/permissions.yaml."""
    candidate: Path
    if workspace_or_file is not None:
        given = Path(workspace_or_file).expanduser()
        if given.suffix in {".yaml", ".yml"}:
            candidate = given
        else:
            candidate = permissions_path(given)
    else:
        candidate = permissions_path(None)

    if not candidate.exists():
        if required:
            raise ValueError(f"permissions file is missing: {candidate}")
        return _validate_and_normalize_permissions(DEFAULT_PERMISSIONS)

    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"permissions file is not a regular file: {candidate}")

    try:
        data = yaml.load(candidate.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
        normalized = _normalize(data)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError) as exc:
        raise ValueError(f"invalid permissions file: {exc}") from exc

    return _validate_and_normalize_permissions(normalized)


def load_policy(
    workspace: str | Path,
    *,
    registry: dict[str, Any] | None = None,
    required: bool = False,
) -> dict[str, Any] | None:
    """Compatibility wrapper that loads runtime permissions for a workspace."""
    del registry
    return load_permissions(workspace, required=required)


def policy_allows(
    policy: dict[str, Any] | None,
    action: str,
    destination: str | None = None,
    *,
    scheduled: bool = False,
) -> bool:
    """Return whether runtime permissions allow a local workspace action."""
    if not policy:
        return False
    effective = policy
    if destination is not None:
        try:
            _safe_relative_path(destination.strip("/"), "destination")
        except ValueError:
            return False

    if scheduled:
        sched = effective.get("scheduled_work", {})
        if not sched.get("enabled", True):
            return False
        if action == "generate_reports":
            report_dest = sched.get("report_destination", "inbox/daily-briefing")
            return destination is None or _path_is_within(destination, report_dest)
        if action in {"capture", "triage_inbox"}:
            return destination is None or (
                _path_is_within(destination, "inbox")
                or _path_is_within(destination, "sources")
            )
        return False

    if action == "local_git_commits":
        return False

    # In interactive sessions, creating, updating, capturing, triaging, and archiving
    # records or contracts in any safe workspace folder is allowed by default.
    return action in {
        "create_records",
        "update_records",
        "archive_records",
        "capture",
        "triage_inbox",
        "generate_reports",
        "record_financial_data",
    }


def domains(registry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not registry:
        return []
    return [domain for domain in registry.get("domains", []) if isinstance(domain, dict)]


def allowed_root_domains(registry: dict[str, Any] | None) -> set[str]:
    discovered = {domain["path"].split("/", 1)[0] for domain in domains(registry)}
    return discovered | set(CORE_ROOTS)


def resolve_route_destination(
    registry: dict[str, Any] | None,
    route: str,
    tags: list[str] | None = None,
) -> str | None:
    """Resolve a route to a discovered collection path."""
    if not registry:
        return None
    normalized_tags = {str(tag).strip().lower() for tag in tags or [] if str(tag).strip()}
    candidates = []
    for domain in domains(registry):
        if domain.get("route") != route:
            continue
        required_tags = {str(tag).strip().lower() for tag in domain.get("tags", [])}
        if not required_tags.issubset(normalized_tags):
            continue
        candidates.append(
            (len(required_tags), domain.get("kind") == "core", domain["path"])
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], not item[1], item[2]))
    return candidates[0][2]


def briefing_sources(registry: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return discovered collections included in daily briefings."""
    sources = []
    for domain in domains(registry):
        if not domain.get("include_in_briefing", False):
            continue
        sources.append(
            {
                "path": domain["path"],
                "heading": domain.get("label") or domain["path"],
                "category": domain.get("briefing_category") or "extension",
            }
        )
    return sources
