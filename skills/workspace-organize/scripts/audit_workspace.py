#!/usr/bin/env python3
"""Deterministic workspace hygiene and integrity audit linter."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
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

from workspace_registry import allowed_root_domains, load_policy, load_registry

CANONICAL_DOMAINS = {
    "inbox",
    "goals",
    "knowledge",
    "tasks",
    "calendar",
    "archive",
    "sources",
}

ALLOWED_ROOT_FILES = {
    "README.md",
    "AGENTS.md",
    ".gitignore",
    ".git",
    ".DS_Store",
    "feature.schema.json",
}

MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((?!https?://|mailto:|/files/)([^)#]+)(?:#[^)]+)?\)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
URI_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
FENCE_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INLINE_CODE_PATTERN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)
CHECKBOX_PATTERN = re.compile(r"^\s*-\s*\[([ xX])\]", re.MULTILINE)
STATUS_PATTERN = re.compile(r"(?i)^status:\s*([a-z0-9_-]+)", re.MULTILINE)


def _record_walk(workspace: Path, start: Path | None = None):
    """Prune app internals and dependencies before reading ordinary records."""
    for root, directories, files in os.walk(start or workspace, followlinks=False):
        current = Path(root)
        directories[:] = sorted(
            name for name in directories
            if not name.startswith(".")
            and name not in {"node_modules", "__pycache__", ".venv", ".pytest_cache"}
            and not (current / name).is_symlink()
            and not (current == workspace and name == "minions")
        )
        yield root, directories, [name for name in files if not (current / name).is_symlink()]


def _blank_code_text(text: str) -> str:
    return "".join(
        "\n" if char == "\n" else "\r" if char == "\r" else " "
        for char in text
    )


def _blank_code(match: re.Match[str]) -> str:
    return _blank_code_text(match.group())


def mask_markdown_code(content: str) -> str:
    """Blank fenced and inline code so their examples are not treated as links."""
    masked_lines = []
    fence_char = None
    fence_length = 0

    for line in content.splitlines(keepends=True):
        line_content = line.rstrip("\r\n")
        if fence_char:
            closing_fence = re.match(
                rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$",
                line_content,
            )
            masked_lines.append(_blank_code_text(line))
            if closing_fence:
                fence_char = None
                fence_length = 0
            continue

        opening_fence = FENCE_PATTERN.match(line_content)
        if opening_fence:
            marker = opening_fence.group(1)
            if marker[0] == "~" or "`" not in opening_fence.group(2):
                fence_char = marker[0]
                fence_length = len(marker)
                masked_lines.append(_blank_code_text(line))
                continue

        masked_lines.append(line)

    masked = "".join(masked_lines)
    return INLINE_CODE_PATTERN.sub(_blank_code, masked)


def audit_root_files(
    workspace: Path, registry: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    del registry
    issues = []
    try:
        for entry in workspace.iterdir():
            if entry.name in ALLOWED_ROOT_FILES or entry.name.startswith("."):
                continue
            if entry.is_file():
                issues.append({
                    "type": "stray-root-file",
                    "file": entry.name,
                    "observation": f"File '{entry.name}' is located at workspace root outside domain folders.",
                    "suggestion": "Move file into an appropriate collection folder (e.g. inbox/, knowledge/, or archive/).",
                })
    except Exception as e:
        issues.append({"type": "audit-error", "file": ".", "observation": str(e), "suggestion": "Check permissions."})
    return issues


def audit_inbox(workspace: Path) -> list[dict[str, Any]]:
    issues = []
    inbox_dir = workspace / "inbox"
    if not inbox_dir.is_dir():
        return issues
    for root, _, files in _record_walk(workspace, inbox_dir):
        for file in files:
            if file.startswith(".") or file == "README.md":
                continue
            rel_path = Path(root, file).relative_to(workspace).as_posix()
            issues.append({
                "type": "inbox-unfiled",
                "file": rel_path,
                "observation": f"Captured item '{rel_path}' is pending review and filing.",
                "suggestion": "Triage into tasks/, calendar/, knowledge/claims/, or archive/.",
            })
    return issues


def audit_broken_links(workspace: Path) -> list[dict[str, Any]]:
    issues = []
    for root, _, files in _record_walk(workspace):
        # Skip git or hidden dirs
        if "/." in root or "\\." in root:
            continue
        for file in files:
            # Skip templates as they contain placeholder links like [[Project Name]]
            if not file.endswith(".md") or file.endswith("-template.md"):
                continue
            file_path = Path(root, file)
            rel_file_path = file_path.relative_to(workspace).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            content = mask_markdown_code(content)

            # Check markdown links
            for match in MD_LINK_PATTERN.finditer(content):
                target = match.group(2).strip()
                if (
                    not target
                    or "<" in target
                    or ">" in target
                    or URI_SCHEME_PATTERN.match(target)
                ):
                    continue
                # Resolve relative target
                target_path = (file_path.parent / target).resolve()
                try:
                    if not target_path.exists():
                        issues.append({
                            "type": "broken-link",
                            "file": rel_file_path,
                            "observation": f"Reference to '{target}' does not resolve to an existing file.",
                            "suggestion": f"Fix broken link target or update reference in {rel_file_path}.",
                        })
                except Exception:
                    pass

            # Check wikilinks
            for match in WIKI_LINK_PATTERN.finditer(content):
                target_name = match.group(1).strip()
                if not target_name or "<" in target_name or ">" in target_name:
                    continue
                # Wikilinks typically resolve by filename across workspace
                found = False
                for candidate in (target_name, f"{target_name}.md"):
                    if (workspace / candidate).exists():
                        found = True
                        break
                    # Search across subdirectories
                    matches = list(workspace.glob(f"**/{candidate}"))
                    if matches:
                        found = True
                        break
                if not found:
                    issues.append({
                        "type": "broken-wikilink",
                        "file": rel_file_path,
                        "observation": f"Wikilink '[[{target_name}]]' does not resolve to any workspace document.",
                        "suggestion": f"Check if target document was renamed, moved, or deleted.",
                    })
    return issues


def audit_completed_goals(workspace: Path) -> list[dict[str, Any]]:
    issues = []
    goals_dir = workspace / "goals"
    if not goals_dir.is_dir():
        return issues
    for root, _, files in _record_walk(workspace, goals_dir):
        for file in files:
            if not file.endswith(".md") or file in ("goal-template.md", "README.md"):
                continue
            file_path = Path(root, file)
            rel_path = file_path.relative_to(workspace).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Check status header
            status_match = STATUS_PATTERN.search(content)
            is_completed_status = status_match and status_match.group(1).lower() in ("completed", "done", "closed")

            # Check task checkboxes
            boxes = CHECKBOX_PATTERN.findall(content)
            all_checked = len(boxes) > 0 and all(b.lower() == "x" for b in boxes)

            if is_completed_status or all_checked:
                issues.append({
                    "type": "completed-goal",
                    "file": rel_path,
                    "observation": f"Goal '{rel_path}' appears finished (all milestones checked or status completed).",
                    "suggestion": f"Move to archive/goals/{file} to keep active goal list clean.",
                })
    return issues


def audit_claims(workspace: Path) -> list[dict[str, Any]]:
    issues = []
    claims_dir = workspace / "knowledge" / "claims"
    if not claims_dir.is_dir():
        return issues
    for root, _, files in _record_walk(workspace, claims_dir):
        for file in files:
            if not file.endswith(".md") or file.endswith("-template.md") or file == "README.md":
                continue
            file_path = Path(root, file)
            rel_path = file_path.relative_to(workspace).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            status_match = STATUS_PATTERN.search(content)
            if status_match and status_match.group(1).lower() in ("candidate", "contested"):
                issues.append({
                    "type": "claim-requires-review",
                    "file": rel_path,
                    "observation": f"Claim in '{rel_path}' is '{status_match.group(1)}' and requires review.",
                    "suggestion": "Review its evidence and provenance before changing its status.",
                })
    return issues


DELETED_SOURCE_MARKER_RE = re.compile(
    r"(?:\(deleted source:\s*([A-Za-z0-9][A-Za-z0-9._-]*)\)|;\s*source-deleted:\s*([A-Za-z0-9][A-Za-z0-9._-]*))"
)
OPENLIA_SOURCE_URI_RE = re.compile(
    r"openlia://sources?/([A-Za-z0-9][A-Za-z0-9._-]*)(?:#([A-Za-z0-9][A-Za-z0-9._-]*)(?:/p\d+)?)?"
)


def _load_vault_source_versions(
    workspace: Path, ingestion_root: Path | None = None
) -> dict[str, str | None] | None:
    """Return {source_id: latest_version_id} if a local Ingestion Vault SQLite database is present."""
    candidates: list[Path] = []
    if ingestion_root:
        candidates.append(ingestion_root.expanduser().resolve())
    if os.environ.get("OPENLIA_INGESTION_ROOT"):
        candidates.append(Path(os.environ["OPENLIA_INGESTION_ROOT"]).expanduser().resolve())
    if os.environ.get("HERMES_HOME"):
        candidates.append(Path(os.environ["HERMES_HOME"]).expanduser().resolve() / "ingestion")
    candidates.append(workspace.parent / "ingestion")

    db_path: Path | None = None
    for root in candidates:
        for name in ("vault.sqlite", "queue.sqlite"):
            candidate = root / name
            if candidate.is_file():
                db_path = candidate
                break
        if db_path:
            break

    if db_path is None:
        return None

    try:
        import sqlite3

        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT source_id, record_json FROM sources").fetchall()
        finally:
            conn.close()
        out: dict[str, str | None] = {}
        for row in rows:
            sid = str(row["source_id"])
            latest_ver: str | None = None
            try:
                rec = json.loads(row["record_json"] or "{}")
                versions = rec.get("versions") or []
                if versions and isinstance(versions[-1], dict):
                    latest_ver = versions[-1].get("id")
            except Exception:
                pass
            out[sid] = latest_ver
        return out
    except Exception:
        return None


def audit_source_provenance(
    workspace: Path, ingestion_root: Path | None = None
) -> list[dict[str, Any]]:
    """Detect deleted-source markers, broken openlia://source/ links, and superseded version pins."""
    issues: list[dict[str, Any]] = []
    vault_sources = _load_vault_source_versions(workspace, ingestion_root=ingestion_root)

    for root, dirnames, files in _record_walk(workspace):
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d not in {"sources", "node_modules"}
        ]
        for file in files:
            if not file.endswith((".md", ".hledger", ".journal", ".rem", ".yaml")):
                continue
            if file.endswith("-template.md"):
                continue
            file_path = Path(root, file)
            rel_path = file_path.relative_to(workspace).as_posix()
            try:
                raw_content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            content = mask_markdown_code(raw_content) if file.endswith(".md") else raw_content

            seen_deleted: set[str] = set()
            for match in DELETED_SOURCE_MARKER_RE.finditer(content):
                deleted_id = match.group(1) or match.group(2)
                if not deleted_id or deleted_id in seen_deleted:
                    continue
                seen_deleted.add(deleted_id)
                issues.append(
                    {
                        "type": "evidence-provenance",
                        "file": rel_path,
                        "observation": f"Record references deleted source '{deleted_id}'.",
                        "suggestion": "Review whether derived transactions, claims, or notes should be retained, updated with a replacement source, or reversed.",
                    }
                )

            if vault_sources is not None:
                seen_uris: set[tuple[str, str | None]] = set()
                for match in OPENLIA_SOURCE_URI_RE.finditer(content):
                    source_id = match.group(1)
                    pinned_ver = match.group(2)
                    if pinned_ver and re.fullmatch(r"p\d+", pinned_ver):
                        pinned_ver = None
                    if not source_id or source_id.startswith("<"):
                        continue
                    key = (source_id, pinned_ver)
                    if key in seen_uris:
                        continue
                    seen_uris.add(key)
                    if source_id not in vault_sources:
                        issues.append(
                            {
                                "type": "evidence-provenance",
                                "file": rel_path,
                                "observation": f"Reference to 'openlia://source/{source_id}' does not exist in the Ingestion Vault.",
                                "suggestion": "Annotate as deleted source or update the citation to an existing Vault source.",
                            }
                        )
                    elif (
                        pinned_ver
                        and vault_sources.get(source_id)
                        and pinned_ver != vault_sources.get(source_id)
                    ):
                        latest_ver = vault_sources[source_id]
                        issues.append(
                            {
                                "type": "evidence-provenance",
                                "file": rel_path,
                                "observation": f"Citation 'openlia://source/{source_id}#{pinned_ver}' is pinned to a superseded version (latest is '{latest_ver}').",
                                "suggestion": f"Reconcile extracted figures against '{latest_ver}' and update the version pin.",
                            }
                        )

    return issues


def run_audit(
    workspace_dir: str | Path, ingestion_root: Path | None = None
) -> dict[str, Any]:
    workspace = Path(workspace_dir).resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"Workspace directory not found: {workspace}")

    registry = load_registry(workspace)
    root_issues = audit_root_files(workspace, registry)
    inbox_issues = audit_inbox(workspace)
    broken_link_issues = audit_broken_links(workspace)
    goal_issues = audit_completed_goals(workspace)
    claim_issues = audit_claims(workspace)
    provenance_issues = audit_source_provenance(workspace, ingestion_root=ingestion_root)

    all_issues = (
        root_issues
        + inbox_issues
        + broken_link_issues
        + goal_issues
        + claim_issues
        + provenance_issues
    )
    return {
        "workspace": str(workspace),
        "discovered_collections": [
            d.get("path") for d in (registry or {}).get("domains", []) if isinstance(d, dict)
        ],
        "total_issues": len(all_issues),
        "summary": {
            "stray_root_files": sum(
                1 for issue in root_issues if issue["type"] == "stray-root-file"
            ),
            "unfiled_inbox_items": len(inbox_issues),
            "broken_links": len(broken_link_issues),
            "completed_goals": len(goal_issues),
            "claims_requiring_review": len(claim_issues),
            "evidence_provenance_issues": len(provenance_issues),
        },
        "issues": all_issues,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # Create canonical and custom dirs; custom directories are normal workspace content
        for d in ("inbox", "goals", "knowledge/claims", "learning/topics", "music", "family-menu"):
            (tmp / d).mkdir(parents=True)

        # 1. Stray root file
        (tmp / "scratch_notes.txt").write_text("random scratch note", encoding="utf-8")

        # 2. Unfiled inbox item
        (tmp / "inbox" / "2026-09-trip-notes.md").write_text("Trip notes", encoding="utf-8")

        # 3. Broken markdown link
        (tmp / "goals" / "website.md").write_text(
            "status: active\n- [ ] Design [missing doc](missing_spec.md)\n- [x] Wireframe\n",
            encoding="utf-8",
        )

        # 4. Completed goal
        (tmp / "goals" / "garden.md").write_text(
            "status: completed\n- [x] Buy seeds\n- [x] Plant seeds\n",
            encoding="utf-8",
        )

        # 5. Candidate claim and starter template
        (tmp / "knowledge" / "claims" / "c001.md").write_text(
            "---\nstatus: candidate\n---\nUser prefers window seats.\n",
            encoding="utf-8",
        )
        (tmp / "knowledge" / "claims" / "claim-template.md").write_text(
            "---\nstatus: candidate\n---\n# <Claim Record>\n",
            encoding="utf-8",
        )

        result = run_audit(tmp)
        assert result["total_issues"] == 5, f"Expected 5 issues, got {result['total_issues']}: {result['issues']}"
        assert result["summary"]["stray_root_files"] == 1
        assert result["summary"]["unfiled_inbox_items"] == 1
        assert result["summary"]["broken_links"] == 1
        assert result["summary"]["completed_goals"] == 1
        assert result["summary"]["claims_requiring_review"] == 1
        assert "family-menu" in result["discovered_collections"]

        # Also test on a clean directory
        clean_dir = tmp / "clean"
        clean_dir.mkdir()
        (clean_dir / "README.md").write_text("# Clean", encoding="utf-8")
        clean_result = run_audit(clean_dir)
        assert clean_result["total_issues"] == 0, f"Expected 0 issues for clean workspace, got {clean_result}"

        # Example links in code and non-file URIs are not workspace file references.
        link_test = tmp / "link-test"
        (link_test / "goals").mkdir(parents=True)
        (link_test / "goals" / "career.md").write_text("Career goal", encoding="utf-8")
        (link_test / "AGENTS.md").write_text(
            "`[Career Goal](openlia://workspace/goals/career.md)`\n"
            "`[Inbox Triage](openlia://skills/inbox-triage)`\n"
            "`[Specs](./specs.md)`\n"
            "[Canonical URI](openlia://workspace/goals/career.md)\n"
            "[Existing relative link](goals/career.md)\n"
            "[Broken relative link](goals/missing.md)\n"
            "```markdown\n"
            "[Fenced example](./fenced-missing.md)\n"
            "```\n",
            encoding="utf-8",
        )
        link_result = run_audit(link_test)
        broken_links = [issue for issue in link_result["issues"] if issue["type"] == "broken-link"]
        assert len(broken_links) == 1, (
            f"Expected only the active broken relative link, got {broken_links}"
        )
        assert "goals/missing.md" in broken_links[0]["observation"]

        # Test source provenance (deleted-source markers, missing Vault sources, and stale version pins)
        import sqlite3

        prov_ws = tmp / "prov-ws"
        prov_vault = tmp / "prov-vault"
        (prov_ws / "finance").mkdir(parents=True)
        (prov_ws / "knowledge" / "claims").mkdir(parents=True)
        prov_vault.mkdir(parents=True)
        conn = sqlite3.connect(prov_vault / "vault.sqlite")
        conn.execute("CREATE TABLE sources (source_id TEXT PRIMARY KEY, record_json TEXT)")
        conn.execute(
            "INSERT INTO sources VALUES (?, ?)",
            (
                "src_amended",
                json.dumps({"id": "src_amended", "versions": [{"id": "ver_001"}, {"id": "ver_002"}]}),
            ),
        )
        conn.commit()
        conn.close()

        (prov_ws / "finance" / "journal.hledger").write_text(
            "2026-10-01 * Old Entry ; source-deleted: src_removed\n"
            "2026-10-02 * Amended Entry ; source: openlia://source/src_amended#ver_001/p1\n"
            "2026-10-03 * Missing Entry ; source: openlia://source/src_ghost\n",
            encoding="utf-8",
        )
        prov_result = run_audit(prov_ws, ingestion_root=prov_vault)
        assert prov_result["summary"]["evidence_provenance_issues"] == 3, (
            f"Expected 3 provenance issues, got {prov_result}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic workspace organize audit linter")
    parser.add_argument("workspace", nargs="?", default=".", help="Workspace path to audit (default: .)")
    parser.add_argument(
        "--ingestion-root",
        help="Optional local Ingestion Vault root used for source provenance checks",
    )
    parser.add_argument("--self-test", action="store_true", help="Run deterministic offline self-tests")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("ok")
        sys.exit(0)

    try:
        report = run_audit(
            args.workspace,
            ingestion_root=Path(args.ingestion_root) if args.ingestion_root else None,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Workspace Organize Audit ===")
        print(f"Workspace: {report['workspace']}")
        print(f"Total issues found: {report['total_issues']}")
        for k, v in report["summary"].items():
            print(f"  - {k.replace('_', ' ').capitalize()}: {v}")
        if report["issues"]:
            print("\nFindings:")
            for idx, issue in enumerate(report["issues"], 1):
                print(f"  {idx}. [{issue['type']}] {issue['file']}")
                print(f"     Observation: {issue['observation']}")
                print(f"     Suggestion:  {issue['suggestion']}")


if __name__ == "__main__":
    main()
