"""Thin bridge to the trusted OpenLia runtime. Never inspect app files."""
import json
import os
from datetime import timedelta
from pathlib import Path
import subprocess


def runtime_request(workspace, request):
    environment = dict(os.environ, OPENLIA_WORKSPACE_ROOT=str(workspace))
    try:
        result = subprocess.run(
            ["/usr/local/bin/bun", "/usr/local/lib/openlia/minion-views.js"],
            input=json.dumps(request), text=True, capture_output=True, timeout=20,
            env=environment, check=False,
        )
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or (result.returncode and value.get("status") == "ok"):
            raise ValueError("Invalid runtime response")
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "message": "Runtime Minion data-view reader unavailable; no app-data fallback."}


def collect_minion_views(workspace: Path, date, lookahead_days, limit, max_records=40):
    discovered = runtime_request(workspace, {"action": "list"})
    blocks = ["## Minion data views"]
    if discovered.get("status") != "ok":
        return blocks + ["- Minion sources unavailable; this does not mean zero activity."]
    budget = min(40, max_records)
    queries = 0
    seen = set()
    for app in discovered.get("minions", [])[:200]:
        if app.get("status") != "ok":
            blocks.append(f"- {app.get('id', 'Minion')}: view unavailable.")
            continue
        for view in app.get("views", [])[:8]:
            if not view.get("briefing_enabled"):
                continue
            if budget <= 0 or queries >= 8:
                return blocks + ["- Additional Minion sources omitted by collection budget."]
            queries += 1
            lookback = min(14, max(0, view.get("lookback_days", 0)))
            result = runtime_request(workspace, {"action": "query", "query": {
                "id": app["id"], "view": view["id"], "purpose": "briefing",
                "from": (date - timedelta(days=lookback)).isoformat(),
                "to": (date + timedelta(days=min(30 - lookback, lookahead_days) + 1)).isoformat(),
                "limit": min(100, budget, limit),
            }})
            label = f"{app['id']}/{view['id']}"
            if result.get("status") != "ok":
                blocks.append(f"- {label}: unavailable; do not infer no activity.")
                continue
            blocks.append(f"### {label}\nObserved: {result.get('observed_at')}; revision: {result.get('revision')}")
            records = result.get("records", [])[:min(budget, limit)]
            for record in records:
                # Canonical source and structured fields are supplied by runtime,
                # never read again as generic app records or execute the app.
                key = (record.get("source"), record.get("id"))
                if key not in seen:
                    seen.add(key)
                    blocks.append(json.dumps(record, ensure_ascii=False))
            budget -= len(records)
            if result.get("truncated"):
                blocks.append("- Additional matching records omitted by view limit.")
            if result.get("unknown_dates"):
                blocks.append(f"- {result['unknown_dates']} scoped record(s) have unknown dates; do not assume they are irrelevant.")
            if not records:
                blocks.append("- No matching records in this successfully read view and date range.")
    return blocks
