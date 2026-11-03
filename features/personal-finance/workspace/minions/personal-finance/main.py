#!/usr/bin/env python3
"""Native hledger preview/confirmation. No external financial effects."""
from __future__ import annotations

import contextlib
import datetime as dt
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent


def safe_path(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks, including symlinked parent directories."""
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


def load_config() -> dict:
    raw = os.environ.get("OPENLIA_MINION_CONFIG_JSON")
    config = json.loads(raw) if raw else json.loads(safe_path(ROOT, "config.json").read_text())
    validate(config, ROOT / "config.schema.json")
    return config


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
    jsonschema.Draft202012Validator(
        document, format_checker=jsonschema.FormatChecker()
    ).validate(value)


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


def snapshot(journal: str) -> dict[str, str]:
    files = {}

    def visit(name):
        if name in files or len(files) >= 32:
            raise ValueError("Repeated/cyclic includes or journal tree exceeds 32 files")
        path = data_path(name)
        if not path.exists():
            if name == journal and not files:
                directory = data_path(".")
                if directory.exists() and any(p.suffix in (".hledger", ".journal") for p in directory.rglob("*")):
                    raise ValueError("Configured journal is absent but existing journals were found; select the main journal in Configuration")
                return
            raise ValueError(f"Missing included journal: {name}")
        content = path.read_text(encoding="utf-8")
        files[name] = content
        if sum(len(value.encode()) for value in files.values()) > 4 * 1024 * 1024:
            raise ValueError("Journal tree exceeds 4 MiB")
        comment = False
        for line in content.splitlines():
            if line.strip().lower() == "comment":
                comment = True
            elif line.strip().lower() == "end comment":
                comment = False
            elif not comment and re.match(r"^\s*include\s+", line):
                target = re.sub(r"^\s*include\s+", "", line).strip()
                if not re.fullmatch(r"[A-Za-z0-9_./-]+\.(?:hledger|journal)", target):
                    raise ValueError("Only literal relative journal includes are supported")
                included = (Path(name).parent / target).as_posix()
                safe_path(ROOT / "data", included)
                visit(included)
    visit(journal)
    return files


def digest(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def check(files: dict, journal: str):
    with tempfile.TemporaryDirectory(prefix="openlia-finance-check-") as directory:
        root = Path(directory)
        for name, text in files.items():
            path = safe_path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        result = subprocess.run(["hledger", "-f", str(root / journal), "check"],
                                capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError(f"hledger check failed: {result.stderr[:2000]}")


def transaction(payload: dict, proposal_id: str) -> str:
    for key in ("description", "debit_account", "credit_account"):
        value = payload[key]
        if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value) or ";" in value:
            raise ValueError(f"Invalid {key}: whitespace/control characters or hledger comments")
    for key in ("debit_account", "credit_account"):
        if not re.fullmatch(r"(?:assets|liabilities|equity|income|expenses)(?::[\w-]+)+", payload[key]):
            raise ValueError("Use an explicit conventional colon-separated account (letters, numbers, '_' or '-')")
    if payload["debit_account"] == payload["credit_account"] or Decimal(payload["amount"]) <= 0:
        raise ValueError("Accounts must differ and amount must be positive")
    source = f" ; source: {payload['source_ref']}" if payload.get("source_ref") else ""
    return (f"\n{payload['date']} * {payload['description']} ; minion-id: {proposal_id}{source}\n"
            f"    {payload['debit_account']}    {payload['amount']} {payload['commodity']}\n"
            f"    {payload['credit_account']}    -{payload['amount']} {payload['commodity']}\n")


def proposals() -> list[dict]:
    directory = data_path("pending")
    if not directory.exists():
        return []
    return [json.loads(safe_path(directory, p.name).read_text()) for p in sorted(directory.glob("*.json"))]


def save_intake(proposal: dict, *, dry_run: bool = False):
    templates = safe_path(ROOT, "templates/intake/intake-template.md")
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", templates.read_text(), re.DOTALL)
    if not match:
        raise ValueError("Malformed intake template")
    fields = yaml.safe_load(match[1])
    body = match[2]
    fields.update(id=proposal["id"], status={"posted": "posted", "pending": "pending-review", "cancelled": "archived"}[proposal["status"]],
                  source_type="manual-entry", source_ref=proposal["payload"].get("source_ref"),
                  received_date=dt.date.today().isoformat(), authority="direct-request" if proposal["status"] == "posted" else "pending",
                  account_scope=[proposal["payload"]["debit_account"], proposal["payload"]["credit_account"]])
    path = data_path(f"intake/{proposal['id']}.md")
    schema = templates.with_suffix(".schema.json")
    fields["$schema"] = os.path.relpath(schema, path.parent)
    validate({k: v for k, v in fields.items() if k != "$schema"}, schema)
    body = body.replace("# <Finance Intake Record>", f"# {proposal['payload']['description']}")
    if not dry_run:
        atomic_write(path, "---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n" + body +
                     f"\n## Confirmed Proposal\n\nStatus: {proposal['status']}; journal: {proposal['journal']}\n\n```hledger\n{proposal['posting']}\n```\n")


def render_dashboard():
    journal = json.dumps(load_config()["journal"])
    children = [f'Finance(children: [FinanceOverview(), FinanceChart(report: "income-expenses", kind: "bar"), FinanceChart(report: "balances", kind: "line"), FinanceAccounts()], journal: {journal}, dataPath: "minions/personal-finance/data")']
    for proposal in proposals():
        if proposal["status"] != "pending":
            continue
        identifier = proposal["id"]
        description = f"Main journal: data/{proposal['journal']}\n{proposal['posting']}\nConfirm only this exact posting. Not reconciled."
        children.append(f'Callout(variant: "info", title: "Pending posting", description: {json.dumps(description)})')
        children.append('Form(name: "minionInput", fields: ['
                        'FormControl(label: "Action", input: Select(name: "action", items: [SelectItem(value: "confirm", label: "Confirm posting"), SelectItem(value: "cancel", label: "Cancel proposal")])), '
                        f'FormControl(label: "Proposal", input: Select(name: "proposal_id", items: [SelectItem(value: "{identifier}", label: "{identifier}")])), '
                        'FormControl(label: "Type POST to authorize (leave blank to cancel)", input: Input(name: "confirmation"))'
                        '], buttons: Buttons(buttons: [Button(label: "Apply selected action", variant: "primary")]))')
    rows = [{"id": p["id"], "status": p["status"], "date": p["payload"]["date"], "description": p["payload"]["description"]} for p in proposals()]
    children.append(f'Table(title: "Intake", columns: [{{"key": "date", "label": "Date"}}, {{"key": "description", "label": "Description"}}, {{"key": "status", "label": "Status"}}], rows: {json.dumps(rows)})')
    content = "Stack(children: [\n" + ",\n".join(children) + "\n])\n"
    atomic_write(safe_path(ROOT, "dashboard.openui"), content)
    return content


@contextlib.contextmanager
def write_lock():
    path = data_path(".write.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def process_input(payload: dict) -> dict:
    validate(payload, ROOT / "input.schema.json")
    config = load_config()
    action = payload.get("action", "preview")
    with write_lock():
        if action == "preview":
            identifier = uuid.uuid4().hex
            journal = config["journal"]
            files = snapshot(journal)
            if files:
                check(files, journal)
            posting = transaction(payload, identifier)
            check({**files, journal: files.get(journal, "") + posting}, journal)
            proposal = dict(id=identifier, status="pending", journal=journal, baseline=digest(files),
                            payload=payload, posting=posting)
        else:
            path = data_path(f"pending/{payload['proposal_id']}.json")
            proposal = json.loads(path.read_text())
            if proposal["status"] != "pending":
                raise ValueError("Proposal already completed; create a new preview")
            if action == "confirm":
                if payload.get("confirmation") != "POST" or proposal["journal"] != config["journal"]:
                    raise ValueError("Explicit POST confirmation and unchanged configuration required")
                files = snapshot(proposal["journal"])
                if any(f"minion-id: {proposal['id']}" in text for text in files.values()):
                    raise ValueError("Proposal already posted; do not replay confirmation")
                if digest(files) != proposal["baseline"]:
                    raise ValueError("Journal changed since preview; cancel and create a new preview")
                if files:
                    check(files, proposal["journal"])
                candidate = {**files, proposal["journal"]: files.get(proposal["journal"], "") + proposal["posting"]}
                check(candidate, proposal["journal"])
                save_intake({**proposal, "status": "posted"}, dry_run=True)
                if digest(snapshot(proposal["journal"])) != proposal["baseline"]:
                    raise ValueError("Journal changed during validation; create a new preview")
                atomic_write(data_path(proposal["journal"]), candidate[proposal["journal"]])
                check(snapshot(proposal["journal"]), proposal["journal"])
                proposal["status"] = "posted"
            else:
                proposal["status"] = "cancelled"
        atomic_write(data_path(f"pending/{proposal['id']}.json"), json.dumps(proposal, indent=2) + "\n")
        save_intake(proposal)
        render_dashboard()
        return {"proposal_id": proposal["id"], "status": proposal["status"], "next": "Inspect Dashboard to confirm a pending posting."}


if __name__ == "__main__":
    load_config()
    render_dashboard()
    print("Read-only dashboard refreshed. No journal changes.")
