# Google Docs Integration

Connect OpenLia with Google Docs to let your agent inspect, read, append to, and update Google Docs files shared with a Google Cloud Service Account.

## Features
- Read Google Docs content and structural outlines (`gdocs.py get`).
- Append updates and meeting notes (`gdocs.py append`).
- Find and replace placeholders or text throughout documents (`gdocs.py replace`).
- Overwrite full document content (`gdocs.py overwrite`).
- Discover shared documents via Google Drive API (`gdocs.py list-shared`).

## Setup
1. In Google Cloud Console, enable **Google Docs API** and **Google Drive API**.
2. Create a Service Account and download its JSON key.
3. Place the key in your workspace at `google-docs/service-account.json`.
4. Open the target Google Doc in your browser, click **Share**, and grant **Editor** access to the service account email.
