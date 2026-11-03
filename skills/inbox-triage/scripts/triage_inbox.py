#!/usr/bin/env python3
"""Classify inbox records with deterministic, local-only rules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

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

from workspace_registry import load_policy, load_registry, policy_allows, resolve_route_destination


ROUTES = ("task", "event", "decision", "idea", "research", "claim", "finance", "archive", "review")
ROUTE_DETAILS = {
    "task": {
        "destination": "tasks/",
        "next_step": "Define one concrete physical next action and its owner.",
    },
    "event": {
        "destination": "calendar/",
        "next_step": "Confirm the explicit date, time, timezone, participants, and location.",
    },
    "decision": {
        "destination": "decisions/",
        "next_step": "Record the question, options, constraints, and evidence gaps.",
    },
    "idea": {
        "destination": "ideas/",
        "next_step": "Capture why it matters and one small exploration experiment.",
    },
    "research": {
        "destination": "knowledge/research/",
        "next_step": "Record the question and the sources to inspect.",
    },
    "claim": {
        "destination": "knowledge/claims/",
        "next_step": "Write one specific candidate claim with a stable source and evidence.",
    },
    "finance": {
        "destination": "minions/personal-finance/data/intake/",
        "next_step": "Identify the source, covered dates, accounts, proposed postings, and reconciliation status.",
    },
    "archive": {
        "destination": "archive/",
        "next_step": "Retain the record only if it is inactive or useful for reference.",
    },
    "review": {
        "destination": "inbox/",
        "next_step": "Ask one focused question before choosing a destination.",
    },
}


def _text(item: dict[str, Any]) -> str:
    parts = [item.get("title", ""), item.get("subject", ""), item.get("content", "")]
    tags = item.get("tags", [])
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    return " ".join(str(part) for part in parts if part).lower()


def _tags(item: dict[str, Any]) -> list[str]:
    tags = item.get("tags", [])
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def _explicit_route(item: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("route", "type", "category"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip().lower()
        if normalized in ROUTES:
            return normalized, None
        return (
            "review",
            f"unsupported explicit {key} '{value}'; manual review is required",
        )
    return None, None


def classify(item: dict[str, Any]) -> tuple[str, str]:
    """Return a route and a short reason without using the current date."""
    explicit, explicit_reason = _explicit_route(item)
    if explicit:
        return explicit, explicit_reason or "preserved explicit route"

    text = _text(item)
    if re.search(r"\b(bank|card|wallet)\s+(?:statement|export)|\bpay\s*slip\b|\breceipt\b|\btransaction\s+export\b|\bcash\s+(?:note|spending)\b", text):
        return "finance", "contains a financial source or transaction signal"
    if re.search(r"\b(should\s+(?:we|i|you|they)|decide|choose|trade[- ]off|option|compare)\b", text):
        return "decision", "contains a choice or trade-off"
    if re.search(r"\b(todo|to-do|action|follow[- ]?up|need to|remember to|deadline)\b", text):
        return "task", "contains an action or commitment"
    if re.search(r"\b(calendar|meeting|appointment|event|invite|invitation|rsvp|scheduled)\b", text):
        return "event", "contains an event or scheduling signal"
    if re.search(r"\b(idea|maybe|what if|learn|interesting)\b", text):
        return "idea", "looks like a possibility or observation"
    if re.search(r"\b(research|read|source|article|paper|reference)\b", text):
        return "research", "points to knowledge work"
    if re.search(r"\b(archive|archived|completed|for reference|inactive)\b", text):
        return "archive", "explicitly appears inactive or reference-only"
    return "review", "no reliable route signal was detected; manual review is required"


def _identifier(item: dict[str, Any], index: int) -> str:
    raw_id = item.get("id")
    if raw_id is None or not str(raw_id).strip():
        return f"item-{index:03d}"
    return str(raw_id)


def triage(
    items: list[dict[str, Any]],
    registry: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    counts = {route: 0 for route in ROUTES}
    seen_ids: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")
        identifier = _identifier(item, index)
        if identifier in seen_ids:
            raise ValueError(f"duplicate item id: {identifier}")
        seen_ids.add(identifier)
        route, reason = classify(item)
        destination = ROUTE_DETAILS[route]["destination"]
        if registry is not None:
            route_tags = _tags(item)
            if route == "finance" and not route_tags:
                route_tags = ["finance", "intake"]
            destination = resolve_route_destination(registry, route, route_tags)
            if route == "finance" and destination is None and any(domain.get("path") == "minions/personal-finance"
                                          for domain in registry.get("domains", [])):
                destination = "minions/personal-finance/data/intake/"
            if destination is None and route != "review":
                reason = f"route '{route}' has no registered destination; manual review is required"
                route = "review"
                destination = resolve_route_destination(registry, route, _tags(item))
            if destination is None:
                destination = "inbox/"
        details = ROUTE_DETAILS[route]
        authorization_action = "archive_records" if route == "archive" else "create_records"
        delegated = (
            route != "review"
            and policy_allows(policy, authorization_action, destination)
        )
        confidence = (
            "low"
            if route == "review"
            else "high"
            if reason == "preserved explicit route"
            else "medium"
        )
        record = {
            "id": identifier,
            "title": str(item.get("title") or item.get("subject") or "Untitled item"),
            "route": route,
            "destination": destination,
            "reason": reason,
            "confidence": confidence,
            "needs_review": route == "review" or "manual review is required" in reason,
            "delegation_available": delegated,
            "authorization_action": authorization_action,
            "approval_required": not delegated,
            "approval_state": "delegated" if delegated else "pending",
            "authorization": "standing-delegation" if delegated else "pending",
            "next_step": details["next_step"],
        }
        result.append(record)
        counts[route] += 1
    return {"counts": counts, "items": result}


def load_items(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("input must be a JSON list or an object with an items list")


def self_test() -> None:
    output = triage(
        [
            {"id": "a", "title": "Decide which option fits", "content": "Compare two paths."},
            {"id": "b", "title": "Follow up on the draft"},
            {"id": "b2", "title": "I should follow up on the draft"},
            {"id": "c", "title": "Interesting reading", "type": "research"},
            {"id": "c2", "title": "March bank statement"},
            {"id": "d", "title": "A quiet note"},
            {"id": "e", "title": "Dentist appointment", "type": "event"},
            {"id": "f", "title": "Timezone preference", "type": "claim"},
            {"id": "g", "title": "Old reference", "route": "archive"},
            {"id": "h", "title": "Unclear note", "type": "message"},
        ]
    )
    assert [item["route"] for item in output["items"]] == [
        "decision",
        "task",
        "task",
        "research",
        "finance",
        "review",
        "event",
        "claim",
        "archive",
        "review",
    ]
    assert output["counts"]["task"] == 2
    assert output["items"][3]["confidence"] == "high"
    assert output["items"][3]["approval_state"] == "pending"
    assert output["items"][4]["destination"] == "minions/personal-finance/data/intake/"
    assert output["items"][4]["approval_state"] == "pending"
    assert output["items"][6]["destination"] == "calendar/"
    assert output["items"][7]["destination"] == "knowledge/claims/"
    assert output["items"][5]["needs_review"] is True
    assert output["items"][9]["needs_review"] is True

    delegated = triage(
        [{"id": "task", "title": "Follow up on the draft"}],
        policy={
            "delegation": {
                "workspace": {
                    "enabled": True,
                    "allowed_actions": ["create_records"],
                    "allowed_domains": ["tasks"],
                }
            }
        },
    )
    assert delegated["items"][0]["delegation_available"] is True
    assert delegated["items"][0]["approval_required"] is False
    assert delegated["items"][0]["authorization"] == "standing-delegation"

    registry = {
        "domains": [
            {"path": "inbox", "kind": "core", "route": "review", "tags": []},
            {"path": "ideas", "kind": "core", "route": "idea", "tags": []},
            {
                "path": "finance/intake",
                "kind": "extension",
                "route": "finance",
                "tags": ["finance", "intake"],
                "lifecycle": "received -> reconciled or archived",
            },
            {
                "path": "travel/ideas",
                "kind": "extension",
                "route": "idea",
                "tags": ["travel"],
                "lifecycle": "idea -> trip or archive",
            },
        ]
    }
    registered = triage(
        [
            {"id": "travel", "title": "Summer trip idea", "type": "idea", "tags": ["travel"]},
            {"id": "generic", "title": "Product idea", "type": "idea"},
            {"id": "statement", "title": "Wallet statement", "type": "finance"},
        ],
        registry,
    )
    assert registered["items"][0]["destination"] == "travel/ideas"
    assert registered["items"][1]["destination"] == "ideas"
    assert registered["items"][2]["destination"] == "finance/intake"

    try:
        triage([{"id": "same"}, {"id": "same"}])
    except ValueError as exc:
        assert str(exc) == "duplicate item id: same"
    else:
        raise AssertionError("duplicate IDs must be rejected")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="JSON file containing inbox items")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace root containing workspace.yaml and assistant-policy.yaml; default routes and no standing delegation are used when omitted",
    )
    parser.add_argument("--output", type=Path, help="Write JSON output to this file")
    parser.add_argument("--self-test", action="store_true", help="Run the built-in deterministic test")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("ok")
        return 0
    if args.input is None:
        parser.error("input is required unless --self-test is used")
    try:
        registry = load_registry(args.workspace_root) if args.workspace_root else None
        policy = load_policy(args.workspace_root, registry=registry) if args.workspace_root else None
        payload = triage(load_items(args.input), registry, policy)
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
