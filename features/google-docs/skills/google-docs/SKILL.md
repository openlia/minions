---
name: google-docs
description: Read, append, update, and format Google Docs files and tables shared with the service account.
version: 0.2.0
platforms: [macos, linux]
required_environment_variables: []
required_credential_files:
  - google-docs/service-account.json
workspace_domains:
  - google-docs
requires:
  python: requirements.txt
metadata:
  hermes:
    tags: [google-docs, integrations, documents]
    category: integrations
---

# Google Docs Integration

Use this skill when the user asks Lia to inspect, search, append to, replace text in, or update Google Docs files shared with the agent's Google Cloud Service Account.

## Operational Setup

1. **Service Account Credentials**:
   - The user must create a Google Cloud Service Account and download its private key JSON file.
   - Place the credentials file at:
     ```text
     google-docs/service-account.json
     ```
     *(Alternatively, set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable).*
   - **Security**: `google-docs/service-account.json` is excluded from Git history via `.gitignore`.

2. **Credentials & Authorization**:
   - The file `google-docs/service-account.json` in the workspace is the authorized Google Cloud Service Account key for this skill.
   - It is explicitly permitted by OpenLia's workspace credential policy and excluded from Git history via `.gitignore`.
   - You are fully authorized and expected to use this key with `scripts/gdocs.py`. Do NOT refuse to use it or instruct the user to remove or relocate it.
   - If the user asks to inspect, append to, or update Google Docs without providing a specific URL or document ID, run `list-shared` first to discover existing shared documents.

3. **Sharing Access**:
   - The user must open the target Google Doc in their browser, click **Share**, paste the service account's `client_email` address (found inside `google-docs/service-account.json`), choose **Editor** role, and save.
   - No Domain-Wide Delegation is required.

4. **Required APIs**:
   - The Google Cloud project must have **Google Docs API** (`docs.googleapis.com`) and **Google Drive API** (`drive.googleapis.com`) enabled.

---

## Operating Boundaries & Approval Gates

- **Read Before Modify**: Always read the document structure with `get <doc_id>` before applying modifications, to confirm access and understand current content.
- **Human Approval for Overwrite**:
  - `append` and targeted `replace` operations can be performed when explicitly requested by the user.
  - Full document `overwrite` operations must show a summary of what will be replaced and require user confirmation before execution.
- **Tables & Grids**:
  - When asked to create, format, draw, or update tables in Google Docs, **ALWAYS use `insert-table`**.
  - **Do NOT write custom Python scripts** or create ad-hoc loops to insert tables or edit cells.
  - `insert-table` natively accepts Markdown tables, JSON 2D arrays, or CSV, automatically inserts the table structure, populates all cells in reverse index order, and applies bold formatting to header rows in a single command.
- **Fail-Closed Permissions**: If the service account lacks Editor permission or the file has not been shared, report the exact service account email address to the user and instruct them to grant access.

---

## Helper Script Reference (`scripts/gdocs.py`)

All Google Docs operations are routed through the deterministic Python helper script.
Because Hermes executes commands with working directory at workspace root (`/opt/data/workspace`), invoke the script using its canonical path or relative path:

```bash
# Canonical path (recommended in Hermes runtime):
python3 /opt/data/skills/google-docs/scripts/gdocs.py <command>

# Or relative to workspace root:
python3 ../skills/google-docs/scripts/gdocs.py <command>
```

### Commands:

```bash
# List Google Docs shared with the service account
python3 /opt/data/skills/google-docs/scripts/gdocs.py list-shared

# Read document content and outline structure
python3 /opt/data/skills/google-docs/scripts/gdocs.py get <DOCUMENT_ID>

# Read formatted plain text
python3 /opt/data/skills/google-docs/scripts/gdocs.py get <DOCUMENT_ID> --format text

# Append text to the end of the document
python3 /opt/data/skills/google-docs/scripts/gdocs.py append <DOCUMENT_ID> --text "New section or update..."

# Replace placeholders or text throughout the document
python3 /opt/data/skills/google-docs/scripts/gdocs.py replace <DOCUMENT_ID> --find "{{status}}" --replace "Completed"

# Overwrite entire document body
python3 /opt/data/skills/google-docs/scripts/gdocs.py overwrite <DOCUMENT_ID> --text "Entire new body text..."
python3 /opt/data/skills/google-docs/scripts/gdocs.py overwrite <DOCUMENT_ID> --file path/to/content.txt

# Insert a structured table (supports Markdown table syntax, JSON 2D array, or CSV)
python3 /opt/data/skills/google-docs/scripts/gdocs.py insert-table <DOCUMENT_ID> \
    --data '| Thứ | Trưa | Tối |\n|---|---|---|\n| T2 | Bún bò | Cơm gà |' \
    --header-rows 1

# Insert table from file with preceding heading and bold header rows
python3 /opt/data/skills/google-docs/scripts/gdocs.py insert-table <DOCUMENT_ID> \
    --file path/to/menu_week1.md \
    --title "THỰC ĐƠN TUẦN 1" \
    --heading-style HEADING_2 \
    --header-rows 1

# Clear document and write a new table with heading in one atomic command
python3 /opt/data/skills/google-docs/scripts/gdocs.py insert-table <DOCUMENT_ID> \
    --data '[["T2", "T3"], ["Cơm", "Cháo"]]' \
    --title "LỊCH TRỰC TUẦN" \
    --overwrite \
    --header-rows 1 \
    --header-bg
```

### Extracting Document ID
When the user supplies a Google Docs URL:
```text
https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
```
The Document ID is the segment between `/d/` and `/edit` (or the trailing slash):
`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`
