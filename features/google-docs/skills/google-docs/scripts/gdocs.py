#!/usr/bin/env python3
"""Google Docs helper script for reading, appending, replacing, and updating documents."""

from __future__ import annotations

import argparse
import csv
import io
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
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                row_cells: list[str] = []
                for cell in row.get("tableCells", []):
                    c_text = ""
                    for cp in cell.get("content", []):
                        for cpe in cp.get("paragraph", {}).get("elements", []):
                            c_run = cpe.get("textRun")
                            if c_run and "content" in c_run:
                                c_text += c_run["content"]
                    row_cells.append(c_text.strip().replace("\n", " "))
                if row_cells:
                    text_parts.append("| " + " | ".join(row_cells) + " |\n")
            continue

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


def parse_table_data(raw: str) -> list[list[str]]:
    """Parse table data from JSON, Markdown table syntax, or CSV."""
    raw = raw.strip()
    if not raw:
        return []

    # Unescape escaped newlines if raw has \n but no actual newlines
    if "\n" not in raw and "\\n" in raw:
        raw = raw.replace("\\r", "\r").replace("\\n", "\n")

    # 1. Try JSON 2D array
    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            if isinstance(data, list) and all(isinstance(r, list) for r in data):
                return [[str(c) if c is not None else "" for c in row] for row in data]
        except json.JSONDecodeError:
            pass

    # 2. Try Markdown table
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    table_lines = [l for l in lines if l.startswith("|") or "|" in l]
    if table_lines:
        rows: list[list[str]] = []
        for line in table_lines:
            stripped_inner = re.sub(r"^\||\|$", "", line).strip()
            # Skip delimiter line like |:---|:---| or |---|---|
            if re.match(r"^[\s\-:|]+$", stripped_inner):
                continue
            cells = [
                c.strip()
                .replace("<br>", "\n")
                .replace("<br/>", "\n")
                .replace("<br />", "\n")
                for c in stripped_inner.split("|")
            ]
            rows.append(cells)
        if rows:
            max_cols = max(len(r) for r in rows)
            return [r + [""] * (max_cols - len(r)) for r in rows]

    # 3. Try CSV
    reader = csv.reader(io.StringIO(raw))
    csv_rows = [row for row in reader if any(cell.strip() for cell in row)]
    if csv_rows:
        max_cols = max(len(r) for r in csv_rows)
        return [r + [""] * (max_cols - len(r)) for r in csv_rows]

    return []


def build_insert_table_requests(rows: int, cols: int, location_index: int) -> list[dict[str, Any]]:
    """Build batchUpdate request to insert a table of specified dimensions."""
    return [
        {
            "insertTable": {
                "rows": rows,
                "columns": cols,
                "location": {"index": location_index},
            }
        }
    ]


def build_cell_insert_requests(table_element: dict[str, Any], data: list[list[str]]) -> list[dict[str, Any]]:
    """Build batchUpdate requests to populate cells in descending index order."""
    table_data = table_element.get("table", {})
    table_rows = table_data.get("tableRows", [])
    insert_items: list[tuple[int, str]] = []

    for r_idx, row in enumerate(table_rows):
        if r_idx >= len(data):
            break
        for c_idx, cell in enumerate(row.get("tableCells", [])):
            if c_idx >= len(data[r_idx]):
                break
            val = data[r_idx][c_idx]
            if val:
                content = cell.get("content", [])
                if content:
                    start_idx = content[0].get("startIndex")
                    if start_idx is not None:
                        insert_items.append((start_idx, val))

    # Sort descending so earlier insertions never invalidate later indices
    insert_items.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "insertText": {
                "location": {"index": idx},
                "text": text,
            }
        }
        for idx, text in insert_items
    ]


def build_header_style_requests(
    table_element: dict[str, Any],
    header_rows: int,
    header_bg: bool = False,
) -> list[dict[str, Any]]:
    """Build batchUpdate requests to format header rows as bold (and optional shading)."""
    if header_rows <= 0:
        return []

    table_start = table_element.get("startIndex", 1)
    table_data = table_element.get("table", {})
    table_rows = table_data.get("tableRows", [])
    num_cols = table_data.get("columns", len(table_rows[0].get("tableCells", [])) if table_rows else 0)
    actual_header_rows = min(header_rows, len(table_rows))
    requests: list[dict[str, Any]] = []

    # Bold header cell text runs
    for r_idx in range(actual_header_rows):
        row = table_rows[r_idx]
        for cell in row.get("tableCells", []):
            for p in cell.get("content", []):
                for elem in p.get("paragraph", {}).get("elements", []):
                    run = elem.get("textRun")
                    if run:
                        txt = run.get("content", "").rstrip("\n")
                        s_idx = elem.get("startIndex")
                        if s_idx is not None and txt.strip():
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": s_idx,
                                        "endIndex": s_idx + len(txt),
                                    },
                                    "textStyle": {"bold": True},
                                    "fields": "bold",
                                }
                            })

    # Optional header background shading
    if header_bg and num_cols > 0:
        requests.append({
            "updateTableCellStyle": {
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": table_start},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "rowSpan": actual_header_rows,
                    "columnSpan": num_cols,
                },
                "tableCellStyle": {
                    "backgroundColor": {
                        "color": {
                            "rgbColor": {"red": 0.93, "green": 0.93, "blue": 0.93}
                        }
                    }
                },
                "fields": "backgroundColor",
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


def cmd_insert_table(args: argparse.Namespace) -> int:
    doc_id = extract_document_id(args.doc_id)
    raw_data = args.data
    if args.file:
        raw_data = Path(args.file).read_text(encoding="utf-8")
    if not raw_data:
        raise ValueError("Either --data or --file must be specified for insert-table.")

    table_data = parse_table_data(raw_data)
    if not table_data or not table_data[0]:
        raise ValueError("No valid table data found in input (expected JSON 2D array, Markdown table, or CSV).")

    num_rows = len(table_data)
    num_cols = len(table_data[0])

    creds_path = resolve_credentials_path(args.credentials)
    docs_service, _ = get_google_services(creds_path)

    # Step 1: Handle overwrite and/or title prepending
    doc = docs_service.documents().get(documentId=doc_id).execute()
    _, _, end_index = extract_document_text_and_outline(doc)

    pre_requests: list[dict[str, Any]] = []
    if args.overwrite:
        if end_index > 2:
            pre_requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": 1,
                        "endIndex": end_index - 1,
                    }
                }
            })
        if args.title:
            pre_requests.append({
                "insertText": {
                    "location": {"index": 1},
                    "text": args.title + "\n",
                }
            })
            if args.heading_style and args.heading_style != "NORMAL_TEXT":
                pre_requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": 1,
                            "endIndex": 1 + len(args.title),
                        },
                        "paragraphStyle": {
                            "namedStyleType": args.heading_style,
                        },
                        "fields": "namedStyleType",
                    }
                })
    elif args.title:
        title_target = max(1, end_index - 1)
        title_text = ("\n" if title_target > 1 else "") + args.title + "\n"
        pre_requests.append({
            "insertText": {
                "location": {"index": title_target},
                "text": title_text,
            }
        })
        if args.heading_style and args.heading_style != "NORMAL_TEXT":
            s_idx = title_target + (1 if title_target > 1 else 0)
            pre_requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": s_idx,
                        "endIndex": s_idx + len(args.title),
                    },
                    "paragraphStyle": {
                        "namedStyleType": args.heading_style,
                    },
                    "fields": "namedStyleType",
                }
            })

    if pre_requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": pre_requests}
        ).execute()
        doc = docs_service.documents().get(documentId=doc_id).execute()
        _, _, end_index = extract_document_text_and_outline(doc)

    # Step 2: Determine insertion location
    if args.index is not None:
        target_index = args.index
    else:
        target_index = max(1, end_index - 1)

    # Step 3: Insert table structure
    insert_reqs = build_insert_table_requests(num_rows, num_cols, target_index)
    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": insert_reqs}
    ).execute()

    # Step 4: Locate inserted table and populate cell text
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    tables = [el for el in content if "table" in el]
    if not tables:
        raise RuntimeError("Table was inserted but could not be located in document body.")

    target_table = None
    for el in tables:
        if el.get("startIndex", 0) >= target_index - 2:
            target_table = el
            break
    if not target_table:
        target_table = tables[-1]

    cell_reqs = build_cell_insert_requests(target_table, table_data)
    if cell_reqs:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": cell_reqs}
        ).execute()

    # Step 5: Format header rows if requested
    header_rows = args.header_rows if args.header_rows is not None else 1
    if header_rows > 0:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        content = doc.get("body", {}).get("content", [])
        tables = [el for el in content if "table" in el]
        target_table = None
        for el in tables:
            if el.get("startIndex", 0) >= target_index - 2:
                target_table = el
                break
        if not target_table:
            target_table = tables[-1]

        style_reqs = build_header_style_requests(
            target_table, header_rows=header_rows, header_bg=args.header_bg
        )
        if style_reqs:
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": style_reqs}
            ).execute()

    print(json.dumps({
        "status": "success",
        "documentId": doc_id,
        "action": "insert-table",
        "rows": num_rows,
        "columns": num_cols,
        "headerRows": header_rows,
        "title": args.title,
    }, indent=2))
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

    # 7. Test Table data parsing
    md_table = (
        "| Thứ | Trưa | Tối |\n"
        "| :--- | :--- | :--- |\n"
        "| T2 | Bún bò<br>Rau thơm | Cơm gà |\n"
        "| T3 | Phở | Bò kho |\n"
    )
    parsed_md = parse_table_data(md_table)
    assert len(parsed_md) == 3
    assert parsed_md[0] == ["Thứ", "Trưa", "Tối"]
    assert parsed_md[1] == ["T2", "Bún bò\nRau thơm", "Cơm gà"]
    assert parsed_md[2] == ["T3", "Phở", "Bò kho"]

    # Escaped newline string test
    escaped_md = "| Col 1 | Col 2 |\\n|---|---|\\n| Val 1 | Val 2 |"
    parsed_escaped = parse_table_data(escaped_md)
    assert len(parsed_escaped) == 2
    assert parsed_escaped[0] == ["Col 1", "Col 2"]
    assert parsed_escaped[1] == ["Val 1", "Val 2"]

    json_table = '[["A", "B"], ["1", "2"]]'
    assert parse_table_data(json_table) == [["A", "B"], ["1", "2"]]

    csv_table = "Col1,Col2\nVal1,Val2"
    assert parse_table_data(csv_table) == [["Col1", "Col2"], ["Val1", "Val2"]]

    # 8. Test insertTable request builder
    insert_reqs = build_insert_table_requests(rows=3, cols=3, location_index=15)
    assert len(insert_reqs) == 1
    assert "insertTable" in insert_reqs[0]
    assert insert_reqs[0]["insertTable"]["rows"] == 3
    assert insert_reqs[0]["insertTable"]["columns"] == 3
    assert insert_reqs[0]["insertTable"]["location"]["index"] == 15

    # 9. Test cell population requests descending index ordering
    mock_table_element = {
        "startIndex": 10,
        "endIndex": 80,
        "table": {
            "rows": 2,
            "columns": 2,
            "tableRows": [
                {
                    "tableCells": [
                        {"content": [{"startIndex": 12}]},
                        {"content": [{"startIndex": 24}]},
                    ]
                },
                {
                    "tableCells": [
                        {"content": [{"startIndex": 36}]},
                        {"content": [{"startIndex": 48}]},
                    ]
                },
            ],
        },
    }
    cell_reqs = build_cell_insert_requests(mock_table_element, [["R0C0", "R0C1"], ["R1C0", "R1C1"]])
    assert len(cell_reqs) == 4
    indices = [req["insertText"]["location"]["index"] for req in cell_reqs]
    assert indices == [48, 36, 24, 12]
    assert cell_reqs[0]["insertText"]["text"] == "R1C1"
    assert cell_reqs[3]["insertText"]["text"] == "R0C0"

    # 10. Test header style request builder
    mock_styled_table = {
        "startIndex": 10,
        "endIndex": 80,
        "table": {
            "rows": 2,
            "columns": 2,
            "tableRows": [
                {
                    "tableCells": [
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"startIndex": 12, "textRun": {"content": "Header 1\n"}}
                                        ]
                                    }
                                }
                            ]
                        },
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"startIndex": 24, "textRun": {"content": "Header 2\n"}}
                                        ]
                                    }
                                }
                            ]
                        },
                    ]
                },
                {
                    "tableCells": [
                        {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"startIndex": 36, "textRun": {"content": "Body\n"}}
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                },
            ],
        },
    }
    header_styles = build_header_style_requests(mock_styled_table, header_rows=1, header_bg=True)
    assert len(header_styles) == 3
    assert "updateTextStyle" in header_styles[0]
    assert header_styles[0]["updateTextStyle"]["textStyle"]["bold"] is True
    assert header_styles[0]["updateTextStyle"]["range"]["startIndex"] == 12
    assert header_styles[0]["updateTextStyle"]["range"]["endIndex"] == 20
    assert "updateTableCellStyle" in header_styles[2]


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

    # insert-table
    table_p = subparsers.add_parser("insert-table", help="Insert a structured table from JSON, Markdown, or CSV.")
    table_p.add_argument("doc_id", help="Document ID or Google Docs URL.")
    table_p.add_argument("--data", help="Table data string (JSON 2D array, Markdown table, or CSV).")
    table_p.add_argument("--file", help="Path to file containing table data (.json, .md, .csv).")
    table_p.add_argument("--title", help="Optional heading text to insert immediately before the table.")
    table_p.add_argument(
        "--heading-style",
        choices=["TITLE", "HEADING_1", "HEADING_2", "HEADING_3", "NORMAL_TEXT"],
        default="HEADING_2",
        help="Heading style for --title (default: HEADING_2).",
    )
    table_p.add_argument("--header-rows", type=int, default=1, help="Number of top rows to format bold (default: 1).")
    table_p.add_argument("--header-bg", action="store_true", help="Apply light gray background to header cells.")
    table_p.add_argument("--overwrite", action="store_true", help="Clear document body before inserting.")
    table_p.add_argument("--append", action="store_true", default=True, help="Append at document end (default).")
    table_p.add_argument("--index", type=int, help="Character index where table should be inserted.")

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
        if args.command == "insert-table":
            return cmd_insert_table(args)
        if args.command == "list-shared":
            return cmd_list_shared(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
