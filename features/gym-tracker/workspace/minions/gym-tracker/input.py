#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "items.json"
SCHEMA_FILE = ROOT / "input.schema.json"


def load_schema() -> dict[str, Any]:
    if not SCHEMA_FILE.exists():
        return {}
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def load_items() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_items(items: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_payload(payload: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    active_schema = schema if schema is not None else load_schema()
    if not isinstance(payload, dict):
        raise ValueError("Input payload must be a JSON object")

    props = active_schema.get("properties", {}) if isinstance(active_schema, dict) else {}
    required = active_schema.get("required", []) if isinstance(active_schema, dict) else []
    additional_ok = active_schema.get("additionalProperties", True) if isinstance(active_schema, dict) else True

    cleaned: dict[str, Any] = {}
    for key, val in payload.items():
        if val is None or (isinstance(val, str) and val.strip() == "" and key not in required):
            continue
        cleaned[key] = val.strip() if isinstance(val, str) else val

    for key, prop_spec in props.items():
        if key not in cleaned and isinstance(prop_spec, dict) and "default" in prop_spec:
            cleaned[key] = prop_spec["default"]

    for req_key in required:
        val = cleaned.get(req_key)
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValueError(f"Missing required field: '{req_key}'")

    if additional_ok is False and props:
        unknown = [k for k in cleaned if k not in props]
        if unknown:
            raise ValueError(f"Unrecognized input field(s): {', '.join(unknown)}")

    for key, val in list(cleaned.items()):
        prop_spec = props.get(key)
        if not isinstance(prop_spec, dict):
            continue
        enum_vals = prop_spec.get("enum")
        if isinstance(enum_vals, list) and val not in enum_vals:
            raise ValueError(f"Invalid value for '{key}': expected one of {enum_vals}")

    return cleaned


def record_entry(raw_payload: dict[str, Any], today: str | None = None) -> dict[str, Any]:
    validated = validate_payload(raw_payload)
    entry: dict[str, Any] = {
        "date": str(validated.get("date") or today or dt.date.today().isoformat()),
        "item": str(validated["item"]).strip(),
        "category": str(validated.get("category") or "strength"),
        "status": str(validated.get("status") or "completed"),
    }
    if "value" in validated and validated["value"] not in (None, ""):
        entry["value"] = validated["value"]
    if "notes" in validated and validated["notes"]:
        entry["notes"] = str(validated["notes"])
    for extra_key, extra_val in validated.items():
        if extra_key not in entry:
            entry[extra_key] = extra_val

    items = load_items()
    items.append(entry)
    save_items(items)
    return entry


def parse_cli_payload(data_arg: str = "", input_arg: str = "") -> dict[str, Any]:
    raw_json = data_arg.strip() or os.environ.get("OPENLIA_MINION_INPUT_JSON", "").strip()
    if raw_json:
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object for --data")
        return parsed
    text = input_arg.strip() or os.environ.get("OPENLIA_MINION_INPUT", "").strip()
    if text:
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {"item": text}
    raise ValueError("No input payload provided (pass --data '<json>' or --input '<text>')")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and record a new Gym Tracker entry")
    parser.add_argument("--data", default="", help="JSON object conforming to input.schema.json")
    parser.add_argument("--input", default="", help="Quick text entry mapped to item")
    args, _ = parser.parse_known_args()

    payload = parse_cli_payload(args.data, args.input)
    entry = record_entry(payload)
    items = load_items()
    print(f"Added entry ({len(items)} total): {entry.get('item', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
