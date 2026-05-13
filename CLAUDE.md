# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bill Notify is an automated bill notification system that:
1. Fetches PDF attachments from Gmail emails with a specific label
2. Uses PaddleOCR to extract text from PDFs (supports encrypted PDFs)
3. Sends extracted text to OpenRouter LLM to identify due dates
4. Creates calendar events in Google Calendar with reminders

## Commands

### Install dependencies
```bash
uv sync
```

### Run the application
```bash
uv run python -m bill_notify.main
```

### Run tests
```bash
uv run pytest
```

### Run a specific test file
```bash
uv run pytest tests/test_llm_analyzer.py -v
```

### Run with verbose logging
```bash
uv run python -m bill_notify.main --verbose
```

### Dry run (no changes made)
```bash
uv run python -m bill_notify.main --dry-run
```

## Architecture

```
bill_notify/
├── main.py            # Orchestrates the workflow; BillNotify class runs: fetch → analyze → create event
├── config.py          # Loads config from YAML + env vars; defines AppConfig dataclass
├── gmail_fetcher.py   # Gmail API: fetch emails by label, download attachments, track processed emails
├── pdf_processor.py   # PDF decryption (pypdf) + OCR text extraction (PaddleOCR)
├── llm_analyzer.py    # OpenRouter API: sends extracted text, parses DUE_DATE/SUMMARY/AMOUNT from response
├── calendar_sync.py   # Google Calendar API: create events, check for duplicates
├── auth_manager.py    # Shared OAuth 2.0 authentication for Gmail/Calendar APIs
└── exceptions.py      # Custom exceptions (GmailError, CalendarError, PDFProcessingError, LLMAnalysisError)
```

## Key Data Flows

### Main Processing Pipeline
1. `BillNotify.run()` orchestrates the workflow
2. `GmailFetcher.process_emails()` downloads PDFs from labeled emails (skips already-processed via `processed_emails.log`)
3. For each PDF: `PDFProcessor.process_pdf()` decrypts if needed, then PaddleOCR extracts text
4. `LLMAnalyzer.analyze_pdf()` sends text to OpenRouter, parses structured response
5. `CalendarSync.check_event_exists()` detects duplicates by checking for same sender/file in description
6. `CalendarSync.create_event()` creates all-day events with email/popup reminders

### Authentication
- `AuthManager` handles OAuth 2.0 flow for both Gmail and Calendar APIs
- On first run, opens browser for user authentication
- Tokens cached in `token.json`

### Config Loading Priority (highest to lowest)
1. CLI arguments (`--label`, `--reminder-days`, etc.)
2. Environment variables (e.g., `OPENROUTER_API_KEY`)
3. `config.yaml`
4. Defaults in `config.py` dataclasses

## PDF Processing

- PDFs are processed using PaddleOCR for text extraction (not base64 encoding to LLM)
- Encrypted PDFs supported via `pdf_passwords.yaml` with sender-to-password mapping
- Password lookup order: exact email match → domain wildcard (`*@domain.com`) → default (`"*"`)

## LLM Response Format

The LLM returns structured text that is parsed:
```
DUE_DATE: 2025-03-15
SUMMARY: AT&T Internet Bill
AMOUNT: $89.99
```

Special cases: `EXTRACTION_FAILED` (technical issue, retry later), `NOT_BILL` (receipt/statement, skip).

## Duplicate Detection

Events are considered duplicates if they share the same date AND contain either:
- The sender email in the description, or
- The PDF filename in the description

This prevents creating duplicate events when the same bill arrives from the same source.

## Environment Variables

- `OPENROUTER_API_KEY` - Required; OpenRouter API key
- `CONFIG_FILE` - Override config file path
- `PDF_PASSWORDS_FILE` - Override PDF passwords file path

## Files to Never Commit

Listed in `.gitignore`:
- `credentials.json` - Google OAuth client credentials
- `token.json` - OAuth access token
- `.env` - Environment variables (API keys)
- `config.yaml` - User configuration
- `pdf_passwords.yaml` - PDF decryption passwords
- `downloads/` - Temporary PDF storage
- `processed_emails.log` - Email processing history