#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import input as minion_input

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "items.json"
CONTEXT_FILE = ROOT / "data" / "context.json"
CONFIG_FILE = ROOT / "config.json"
CONFIG_SCHEMA_FILE = ROOT / "config.schema.json"
DASHBOARD_FILE = ROOT / "dashboard.openui"
TITLE = "Gym Tracker"


def load_config() -> dict[str, Any]:
    raw_env = os.environ.get("OPENLIA_MINION_CONFIG_JSON", "").strip()
    if raw_env:
        try:
            parsed = json.loads(raw_env)
            if isinstance(parsed, dict) and "trigger" in parsed:
                return parsed
        except Exception:
            pass
    if not CONFIG_FILE.exists():
        return {
            "trigger": {"on_new_entry": False},
            "weekly_target_sessions": 3,
            "weight_unit": "kg",
        }
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or "trigger" not in cfg:
        raise ValueError("config.json must be a JSON object containing 'trigger'")
    return cfg


def load_items() -> list[dict[str, Any]]:
    return minion_input.load_items()


def save_items(items: list[dict[str, Any]]) -> None:
    minion_input.save_items(items)


def load_context() -> dict[str, Any]:
    if not CONTEXT_FILE.exists():
        return {}
    try:
        return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_context(context: dict[str, Any]) -> None:
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_recommendation(
    entry: dict[str, Any],
    items: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> str:
    active_config = config if isinstance(config, dict) else load_config()
    unit = str(active_config.get("weight_unit") or "kg")
    target_sessions = int(active_config.get("weekly_target_sessions") or 3)
    today = str(entry.get("date") or dt.date.today().isoformat())
    today_items = [row for row in items if str(row.get("date")) == today]
    category = str(entry.get("category") or "strength")
    value = entry.get("value")
    if value not in (None, ""):
        return (
            f"Recorded {entry.get('item')} ({value} {unit}) in '{category}'. "
            f"{len(today_items)} session(s) logged on {today} against a {target_sessions}/week target—"
            "aim for +2.5% load or +1 rep on the next exposure."
        )
    return (
        f"Logged '{entry.get('item')}' under '{category}' ({len(today_items)} today, {len(items)} total). "
        f"Weekly target: {target_sessions} sessions."
    )


def render_dashboard(
    items: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> str:
    ctx = context if context is not None else load_context()
    active_count = sum(1 for row in items if row.get("status", "active") == "active")
    summary = str(ctx.get("summary") or f"{len(items)} total entries ({active_count} active).")
    latest_rec = str(
        ctx.get("latest_recommendation")
        or (items[-1].get("recommendation") if items else "")
        or "Log your first workout session to calculate volume and progressive overload targets."
    )
    callout_desc = f"{summary} Next recommendation: {latest_rec}"
    cols = '[{"key": "date", "label": "Date"}, {"key": "item", "label": "Exercise"}, {"key": "category", "label": "Focus"}, {"key": "value", "label": "Top Load"}, {"key": "status", "label": "Status"}, {"key": "recommendation", "label": "Recommendation"}]'
    rows = json.dumps(items, ensure_ascii=False)
    content = (
        "Stack(children: [\n"
        f'  Callout(variant: "info", title: "Context & Recommendations", description: {json.dumps(callout_desc)}),\n'
        f"  Table(title: {json.dumps(TITLE)}, columns: {cols}, rows: {rows})\n"
        "])\n"
    )
    DASHBOARD_FILE.write_text(content, encoding="utf-8")
    return content


def analyze_new_entry(
    entry: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_config = config if isinstance(config, dict) else load_config()
    items = load_items()
    target = entry if isinstance(entry, dict) and entry else (items[-1] if items else {})
    recommendation = build_recommendation(target, items, active_config)
    if items:
        items[-1]["recommendation"] = recommendation
        save_items(items)

    active_count = sum(1 for row in items if row.get("status", "active") == "active")
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    ctx = load_context()
    ctx.update({
        "last_trigger": "entry",
        "updated_at": now_iso,
        "trigger_config": active_config.get("trigger"),
        "summary": f"{len(items)} total entries ({active_count} active).",
        "latest_entry": target,
        "latest_recommendation": recommendation,
    })
    save_context(ctx)
    render_dashboard(items, ctx)
    return ctx


def run_heartbeat(config: dict[str, Any] | None = None) -> dict[str, Any]:
    active_config = config if isinstance(config, dict) else load_config()
    items = load_items()
    active_count = sum(1 for row in items if row.get("status", "active") == "active")
    completed_count = sum(1 for row in items if row.get("status") == "completed")
    categories = sorted({str(row.get("category") or "strength") for row in items})
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    ctx = load_context()
    latest_rec = str(
        ctx.get("latest_recommendation")
        or (items[-1].get("recommendation") if items else "")
        or "Log your first workout session to calculate volume and progressive overload targets."
    )
    ctx.update({
        "last_trigger": "heartbeat",
        "updated_at": now_iso,
        "trigger_config": active_config.get("trigger"),
        "summary": f"{len(items)} total entries ({active_count} active, {completed_count} completed).",
        "latest_recommendation": latest_rec,
        "enrichment": {
            "status": "enriched",
            "last_heartbeat_at": now_iso,
            "categories": categories,
            "total_entries": len(items),
            "active_entries": active_count,
        },
    })
    save_context(ctx)
    render_dashboard(items, ctx)
    return ctx


def add_entry(text: str, today: str | None = None) -> list[dict[str, Any]]:
    entry = minion_input.record_entry({"item": text.strip()}, today=today)
    analyze_new_entry(entry)
    return load_items()


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--trigger", choices=["heartbeat", "entry"], default="")
    parser.add_argument("--entry", default="", help="JSON payload of the newly recorded entry")
    parser.add_argument("--action", default="")
    parser.add_argument("--input", default="")
    args, _ = parser.parse_known_args()

    direct_input = args.input.strip()
    trigger = (
        args.trigger.strip()
        or os.environ.get("OPENLIA_MINION_TRIGGER", "").strip()
        or ("heartbeat" if args.action.strip() == "heartbeat" else "")
    )

    if direct_input and trigger != "entry":
        items = add_entry(direct_input)
        print(f"Added entry ({len(items)} total): {direct_input}")
        return 0

    if trigger == "entry":
        raw_entry = args.entry.strip() or os.environ.get("OPENLIA_MINION_ENTRY_JSON", "").strip()
        parsed_entry: dict[str, Any] | None = None
        if raw_entry:
            try:
                candidate = json.loads(raw_entry)
                if isinstance(candidate, dict):
                    parsed_entry = candidate
            except Exception:
                parsed_entry = None
        ctx = analyze_new_entry(parsed_entry)
        items = load_items()
        print(f"Post-entry analysis complete ({len(items)} total): {ctx.get('latest_recommendation', '')}")
        return 0

    ctx = run_heartbeat()
    items = load_items()
    print(f"Heartbeat enrichment complete ({len(items)} entries): {ctx.get('summary', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
