---
name: google-docs
description: Read, append, and update Google Docs files shared with the service account.
version: 0.1.0
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
   - **Security**: Never commit `google-docs/service-account.json` to Git. Keep it in `.gitignore`.

2. **Sharing Access**:
   - The user must open the target Google Doc in their browser, click **Share**, paste the service account's `client_email` address (found inside `google-docs/service-account.json`), choose **Editor** role, and save.
   - No Domain-Wide Delegation is required.

3. **Required APIs**:
   - The Google Cloud project must have **Google Docs API** (`docs.googleapis.com`) and **Google Drive API** (`drive.googleapis.com`) enabled.

---

## Operating Boundaries & Approval Gates

- **Read Before Modify**: Always read the document structure with `get <doc_id>` before applying modifications, to confirm access and understand current content.
- **Human Approval for Overwrite**:
  - `append` and targeted `replace` operations can be performed when explicitly requested by the user.
  - Full document `overwrite` operations must show a summary of what will be replaced and require user confirmation before execution.
- **Fail-Closed Permissions**: If the service account lacks Editor permission or the file has not been shared, report the exact service account email address to the user and instruct them to grant access.

---

## Helper Script Reference (`scripts/gdocs.py`)

All Google Docs operations are routed through the deterministic Python helper script:

```bash
# Read document content and outline structure
python3 scripts/gdocs.py get <DOCUMENT_ID>

# Read formatted plain text
python3 scripts/gdocs.py get <DOCUMENT_ID> --format text

# Append text to the end of the document
python3 scripts/gdocs.py append <DOCUMENT_ID> --text "New section or update..."

# Replace placeholders or text throughout the document
python3 scripts/gdocs.py replace <DOCUMENT_ID> --find "{{status}}" --replace "Completed"

# Overwrite entire document body
python3 scripts/gdocs.py overwrite <DOCUMENT_ID> --text "Entire new body text..."
python3 scripts/gdocs.py overwrite <DOCUMENT_ID> --file path/to/content.txt

# List Google Docs shared with the service account
python3 scripts/gdocs.py list-shared
```

### Extracting Document ID
When the user supplies a Google Docs URL:
```text
https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
```
The Document ID is the segment between `/d/` and `/edit` (or the trailing slash):
`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`
