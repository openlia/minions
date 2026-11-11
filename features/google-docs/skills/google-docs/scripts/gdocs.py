#!/usr/bin/env python3
"""Google Docs helper script for reading, appending, replacing, and updating documents."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DOC_ID_REGEX = re.compile(r"(?:/document)?/d/([a-zA-Z0-9-_]{10,})")
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
]


def resolve_credentials_path(explicit_path: str | None = None) -> Path:
    """Resolve service account JSON credentials path.

    Order of precedence:
    1. Explicit CLI argument (--credentials)
    2. google-docs/service-account.json (relative to cwd or search upward)
    3. GOOGLE_APPLICATION_CREDENTIALS environment variable
    """
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Credentials file not found at explicit path: {p}")

    # Check relative to cwd
    local_path = Path("google-docs/service-account.json").resolve()
    if local_path.is_file():
        return local_path

    # Check parent directories for workspace root (markers: .git, AGENTS.md, or workspace.yaml)
    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        candidate = parent / "google-docs" / "service-account.json"
        if candidate.is_file():
            return candidate
        if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
            # Stop searching above workspace root
            break

    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_file():
            return p

    raise FileNotFoundError(
        "Google Service Account credentials not found.\n"
        "Please place your service account JSON key at 'google-docs/service-account.json' "
        "or set $GOOGLE_APPLICATION_CREDENTIALS to its absolute path."
    )


def extract_document_id(doc_id_or_url: str) -> str:
    """Extract Google Doc ID from a raw ID or full Google Docs URL."""
    value = doc_id_or_url.strip()
    match = DOC_ID_REGEX.search(value)
    if match:
        return match.group(1)
    if "/" in value or "?" in value:
        raise ValueError(f"Could not extract Document ID from URL: {value}")
    return value


def extract_document_text_and_outline(doc_data: dict[str, Any]) -> tuple[str, list[dict[str, Any]], int]:
    """Parse Google Docs JSON document to extract plain text, outline headings, and end index."""
    body = doc_data.get("body", {})
    content = body.get("content", [])

    text_parts: list[str] = []
    outline: list[dict[str, Any]] = []
    max_end_index = 1

    for element in content:
        end_idx = element.get("endIndex", 1)
        if end_idx > max_end_index:
            max_end_index = end_idx

        paragraph = element.get("paragraph")
        if not paragraph:
            continue

        p_style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
        p_text = ""
        for pe in paragraph.get("elements", []):
            text_run = pe.get("textRun")
            if text_run and "content" in text_run:
                p_text += text_run["content"]

        if p_text:
            text_parts.append(p_text)
            if p_style.startswith("HEADING_") or p_style == "TITLE":
                outline.append({
                    "style": p_style,
                    "text": p_text.strip(),
                    "startIndex": element.get("startIndex", 1),
                })

    full_text = "".join(text_parts)
    return full_text, outline, max_end_index


def build_append_requests(text_to_append: str, end_index: int) -> list[dict[str, Any]]:
    """Build batchUpdate request to append text at document end (end_index - 1)."""
    # The last index (end_index - 1) is before the terminating newline of the doc body
    target_index = max(1, end_index - 1)
    # Ensure text starts with a newline if appending after existing content
    text = text_to_append
    if target_index > 1 and not text.startswith("\n"):
        text = "\n" + text
    return [
        {
            "insertText": {
                "location": {"index": target_index},
                "text": text,
            }
        }
    ]


def build_replace_requests(find_text: str, replace_text: str, case_sensitive: bool = True) -> list[dict[str, Any]]:
    """Build batchUpdate request to replace occurrences of text."""
    return [
        {
            "replaceAllText": {
                "containsText": {
                    "text": find_text,
                    "matchCase": case_sensitive,
                },
                "replaceText": replace_text,
            }
        }
    ]


def build_overwrite_requests(new_text: str, end_index: int) -> list[dict[str, Any]]:
    """Build batchUpdate requests to clear existing body content and insert new text."""
    requests: list[dict[str, Any]] = []
    # Google Docs body index starts at 1, and always ends with a newline at end_index - 1.
    # To delete everything: delete from index 1 to end_index - 1.
    if end_index > 2:
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index - 1,
                }
            }
        })
    requests.append({
        "insertText": {
            "location": {"index": 1},
            "text": new_text,
        }
    })
    return requests


def get_google_services(creds_path: Path):
    """Authenticate and return Google Docs and Drive service clients."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Missing Google client libraries. Please install them with:\n"
            "uv pip install google-api-python-client google-auth google-auth-httplib2"
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )
    docs_service = build("docs", "v1", credentials=credentials, cache_discovery=False)
    drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return docs_service, drive_service


def cmd_get(args: argparse.Namespace) -> int:
    doc_id = extract_document_id(args.doc_id)
    creds_path = resolve_credentials_path(args.credentials)
    docs_service, _ = get_google_services(creds_path)

    doc = docs_service.documents().get(documentId=doc_id).execute()
    full_text, outline, end_index = extract_document_text_and_outline(doc)

    if args.format == "text":
        sys.stdout.write(full_text)
    else:
        out = {
            "documentId": doc.get("documentId"),
            "title": doc.get("title"),
            "revisionId": doc.get("revisionId"),
            "endIndex": end_index,
            "outline": outline,
            "text": full_text,
        }
        print(json.dumps(out, indent=2))
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    doc_id = extract_document_id(args.doc_id)
    creds_path = resolve_credentials_path(args.credentials)
    docs_service, _ = get_google_services(creds_path)

    doc = docs_service.documents().get(documentId=doc_id).execute()
    _, _, end_index = extract_document_text_and_outline(doc)

    requests = build_append_requests(args.text, end_index)
    result = docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    print(json.dumps({
        "status": "success",
        "documentId": doc_id,
        "action": "append",
        "appendedLength": len(args.text),
        "response": result,
    }, indent=2))
    return 0


def cmd_replace(args: argparse.Namespace) -> int:
    doc_id = extract_document_id(args.doc_id)
    creds_path = resolve_credentials_path(args.credentials)
    docs_service, _ = get_google_services(creds_path)

    requests = build_replace_requests(
        find_text=args.find,
        replace_text=args.replace,
        case_sensitive=not args.ignore_case,
    )
    result = docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    replies = result.get("replies", [])
    occurrences = 0
    if replies and "replaceAllText" in replies[0]:
        occurrences = replies[0]["replaceAllText"].get("occurrencesChanged", 0)

    print(json.dumps({
        "status": "success",
        "documentId": doc_id,
        "action": "replace",
        "find": args.find,
        "replace": args.replace,
        "occurrencesChanged": occurrences,
    }, indent=2))
    return 0


def cmd_overwrite(args: argparse.Namespace) -> int:
    doc_id = extract_document_id(args.doc_id)
    new_text = args.text
    if args.file:
        new_text = Path(args.file).read_text(encoding="utf-8")
    if new_text is None:
        raise ValueError("Either --text or --file must be specified for overwrite.")

    creds_path = resolve_credentials_path(args.credentials)
    docs_service, _ = get_google_services(creds_path)

    doc = docs_service.documents().get(documentId=doc_id).execute()
    _, _, end_index = extract_document_text_and_outline(doc)

    requests = build_overwrite_requests(new_text, end_index)
    result = docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    print(json.dumps({
        "status": "success",
        "documentId": doc_id,
        "action": "overwrite",
        "contentLength": len(new_text),
        "response": result,
    }, indent=2))
    return 0


def cmd_list_shared(args: argparse.Namespace) -> int:
    creds_path = resolve_credentials_path(args.credentials)
    _, drive_service = get_google_services(creds_path)

    q = "mimeType='application/vnd.google-apps.document' and trashed = false"
    result = drive_service.files().list(
        q=q,
        pageSize=args.limit,
        fields="files(id, name, modifiedTime, owners)",
    ).execute()

    files = result.get("files", [])
    summary = [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "modifiedTime": f.get("modifiedTime"),
            "owners": [o.get("emailAddress") for o in f.get("owners", []) if isinstance(o, dict)],
        }
        for f in files
    ]
    print(json.dumps({"sharedDocuments": summary, "count": len(summary)}, indent=2))
    return 0


def self_test() -> None:
    """Deterministic offline test of parsing, request generation, and mock flows."""
    # 1. Test Document ID extraction
    url1 = "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    assert extract_document_id(url1) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    raw_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert extract_document_id(raw_id) == raw_id

    try:
        extract_document_id("https://example.com/some/invalid/page")
        assert False, "Should have raised ValueError on bad URL"
    except ValueError:
        pass

    # 2. Test Document structure parsing
    mock_doc = {
        "documentId": "test-doc-id",
        "title": "Meeting Notes",
        "revisionId": "rev1",
        "body": {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": 15,
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "TITLE"},
                        "elements": [{"textRun": {"content": "Meeting Notes\n"}}],
                    },
                },
                {
                    "startIndex": 15,
                    "endIndex": 40,
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [{"textRun": {"content": "We discussed project roadmap.\n"}}],
                    },
                },
            ]
        },
    }

    full_text, outline, end_index = extract_document_text_and_outline(mock_doc)
    assert "Meeting Notes" in full_text
    assert "project roadmap" in full_text
    assert len(outline) == 1
    assert outline[0]["style"] == "TITLE"
    assert outline[0]["text"] == "Meeting Notes"
    assert end_index == 40

    # 3. Test Append request builder
    append_reqs = build_append_requests("Next steps...", end_index=40)
    assert len(append_reqs) == 1
    assert "insertText" in append_reqs[0]
    assert append_reqs[0]["insertText"]["location"]["index"] == 39
    assert append_reqs[0]["insertText"]["text"] == "\nNext steps..."

    # 4. Test Replace request builder
    replace_reqs = build_replace_requests("{{status}}", "Done", case_sensitive=True)
    assert len(replace_reqs) == 1
    assert "replaceAllText" in replace_reqs[0]
    rat = replace_reqs[0]["replaceAllText"]
    assert rat["containsText"]["text"] == "{{status}}"
    assert rat["containsText"]["matchCase"] is True
    assert rat["replaceText"] == "Done"

    # 5. Test Overwrite request builder
    overwrite_reqs = build_overwrite_requests("Brand new document content", end_index=40)
    assert len(overwrite_reqs) == 2
    assert "deleteContentRange" in overwrite_reqs[0]
    dcr = overwrite_reqs[0]["deleteContentRange"]["range"]
    assert dcr["startIndex"] == 1
    assert dcr["endIndex"] == 39
    assert "insertText" in overwrite_reqs[1]
    assert overwrite_reqs[1]["insertText"]["location"]["index"] == 1
    assert overwrite_reqs[1]["insertText"]["text"] == "Brand new document content"

    # Test Overwrite on empty document (end_index <= 2)
    empty_overwrite = build_overwrite_requests("First content", end_index=1)
    assert len(empty_overwrite) == 1
    assert "insertText" in empty_overwrite[0]

    # 6. Test credentials resolution error message
    try:
        resolve_credentials_path("/nonexistent/path/service-account.json")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as exc:
        assert "Credentials file not found" in str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Google Docs agent helper for reading, appending, replacing, and updating documents."
    )
    parser.add_argument(
        "--credentials",
        help="Path to service account JSON file (defaults to google-docs/service-account.json).",
    )

    subparsers = parser.add_subparsers(dest="command")

    # get
    get_p = subparsers.add_parser("get", help="Read document content and outline.")
    get_p.add_argument("doc_id", help="Document ID or Google Docs URL.")
    get_p.add_argument("--format", choices=["json", "text"], default="json", help="Output format.")

    # append
    append_p = subparsers.add_parser("append", help="Append text to the end of the document.")
    append_p.add_argument("doc_id", help="Document ID or Google Docs URL.")
    append_p.add_argument("--text", required=True, help="Text to append.")

    # replace
    replace_p = subparsers.add_parser("replace", help="Replace text or placeholders throughout the document.")
    replace_p.add_argument("doc_id", help="Document ID or Google Docs URL.")
    replace_p.add_argument("--find", required=True, help="Target text or placeholder to find.")
    replace_p.add_argument("--replace", required=True, help="Replacement text.")
    replace_p.add_argument("--ignore-case", action="store_true", help="Case-insensitive search.")

    # overwrite
    overwrite_p = subparsers.add_parser("overwrite", help="Replace entire document body.")
    overwrite_p.add_argument("doc_id", help="Document ID or Google Docs URL.")
    overwrite_p.add_argument("--text", help="New body text.")
    overwrite_p.add_argument("--file", help="Path to text/markdown file containing new body.")

    # list-shared
    list_p = subparsers.add_parser("list-shared", help="List Google Docs shared with the service account.")
    list_p.add_argument("--limit", type=int, default=20, help="Maximum number of files to return.")

    # self-test
    parser.add_argument("--self-test", action="store_true", help="Run deterministic offline self-tests.")

    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        print("ok")
        return 0

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "get":
            return cmd_get(args)
        if args.command == "append":
            return cmd_append(args)
        if args.command == "replace":
            return cmd_replace(args)
        if args.command == "overwrite":
            return cmd_overwrite(args)
        if args.command == "list-shared":
            return cmd_list_shared(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
