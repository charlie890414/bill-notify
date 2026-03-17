# Bill Notify - Bill Notification System

Automatically fetch bill PDFs from Gmail, use LLM to extract due dates, and create reminders in Google Calendar.

## Features

- 📧 Automatically download PDF attachments from unread emails with a specific Gmail label
- 🤖 Use OpenRouter's LLM (vision model) to scan PDFs and extract due dates
- 📅 Automatically create all-day events in Google Calendar with reminders
- 🔍 Automatically check for duplicate events to avoid duplicates
- ✅ Automatically mark processed emails to prevent reprocessing

## System Architecture

```
bill-notify/
├── bill_notify/
│   ├── config.py          # Configuration management
│   ├── gmail_fetcher.py   # Gmail API integration
│   ├── pdf_processor.py   # PDF to image conversion
│   ├── llm_analyzer.py    # LLM analysis (OpenRouter)
│   ├── calendar_sync.py   # Google Calendar integration
│   └── main.py            # Main program
├── config.yaml            # Configuration file (user-defined)
├── .env                   # Environment variables (API keys)
├── credentials.json       # Google OAuth credentials
├── token.json             # OAuth token (auto-generated)
├── downloads/            # Temporary download directory
└── processed_emails.log  # Processed email record
```

## Prerequisites

1. **Python 3.13+** and **uv** package manager
2. **Google Cloud Console** project with enabled APIs:
   - Gmail API
   - Calendar API
3. **OpenRouter** account and API Key
4. **poppler** (pdf2image dependency, for PDF conversion)

### Install poppler

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler

# Windows
# Download https://github.com/oschwartz10612/poppler-windows/releases/
# and add bin/ to PATH
```

## Installation and Configuration

### 1. Clone or create the project

```bash
cd /path/to/bill-notify
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Set up Google OAuth 2.0 credentials

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing project
3. Enable APIs:
   - Gmail API
   - Google Calendar API
4. Create OAuth 2.0 client credentials:
   - Application type: Desktop app
   - Download JSON credentials file
5. Rename the downloaded file to `credentials.json` and place it in the project root

### 4. Configure OpenRouter

1. Visit [OpenRouter](https://openrouter.ai/keys) to get an API Key
2. Create `.env` file (copy `.env.example`):
   ```bash
   cp .env.example .env
   ```
3. Edit `.env`, fill in your API Key:
   ```
   OPENROUTER_API_KEY=your_actual_api_key
   ```

### 5. Configure application settings

1. Copy configuration example:
   ```bash
   cp config.yaml.example config.yaml
   ```
2. Edit `config.yaml`:
   ```yaml
   gmail_label: "bills"        # Gmail label for filtering bill emails
   calendar_id: "primary"      # Target calendar (default calendar)
   reminder_days: 3            # Days in advance for reminder
   # model: "meta-llama/llama-3.2-vision-instruct"  # Optional: specify model
   ```

### 6. Prepare Gmail label

Create a label in your Gmail (e.g., "bills") and add all bill emails that need processing to this label.

**Note**: If the configured label does not exist, the program will raise an error.

## Usage

### Manual Run

```bash
uv run python -m bill_notify.main
```

Or use uv to run:

```bash
uv run bill-notify
```

### Expected Output

```
============================================================
Bill Notification System Started
Config: Label=bills, Reminder 3 days in advance
============================================================

[1/3] Fetching PDF attachments from Gmail...
  Downloaded 2 PDF files

[2/3] Analyzing PDFs to extract due dates...

Processing file: electricity_bill.pdf
  Converting PDF to images...
  Using LLM to analyze due date...
  LLM response: 2025-03-15
  ✓  Extracted due date: 2025-03-15
  ✓  Created calendar event (ID: abc123...)

Processing file: credit_card_bill.pdf
  Converting PDF to images...
  Using LLM to analyze due date...
  LLM response: 2025-04-10
  ✓  Extracted due date: 2025-04-10
  ✓  Created calendar event (ID: def456...)

============================================================
Processing complete: 2 succeeded, 0 skipped
============================================================
```

## Automated Execution (Optional)

### Using cron (Linux/macOS)

```bash
# Edit crontab
crontab -e

# Run once daily at 10 AM
0 10 * * * cd /path/to/bill-notify && uv run python -m bill_notify.main >> logs/cron.log 2>&1
```

### Using Windows Task Scheduler

1. Open "Task Scheduler"
2. Create Basic Task
3. Set trigger (e.g., daily)
4. Action: "Start a program"
   - Program: `uv`
   - Arguments: `run python -m bill_notify.main`
   - Start in: Project directory path

## First Run Authentication

On first run, the program will open a browser window to request Google access permissions:

1. Grant Gmail read-only and modify permissions
2. Grant Calendar read/write permissions
3. After successful authorization, `token.json` will be auto-generated
4. Subsequent runs will automatically use the token, no re-authorization needed

## Troubleshooting

### ImportError: No module named 'dotenv'

```bash
uv sync  # Re-sync dependencies
```

### pdf2image error: poppler not found

Confirm poppler is installed and added to PATH.

### Google authentication fails

- Confirm `credentials.json` is in project root
- Confirm Gmail API and Calendar API are enabled in Google Cloud Console
- Delete `token.json` and re-run authentication

### LLM cannot extract due date

- Check if OpenRouter API Key is correct
- Check network connection
- Confirm PDF is clear and readable
- Consider adjusting the prompt in `llm_analyzer.py`

### Label not found

Confirm the configured label (default "bills") exists in Gmail, case-sensitive.

## Configuration Recommendations

### Recommended OpenRouter Free Models

Optional in `config.yaml`:
```yaml
model: "anthropic/claude-3-haiku"      # Fast, good accuracy
# or
model: "meta-llama/llama-3.2-vision-instruct"  # Open source, free
# or
model: "google/gemma-3-4b-it"          # Google model
```

### Adjust Reminder Time

```yaml
reminder_days: 7  # Remind one week in advance
```

### Multi-language Support

The system supports both Chinese and English bills. For other languages, modify the `system_prompt` in `llm_analyzer.py`.

## Development and Testing

### Run tests (if available)

```bash
uv run pytest
```

### Adding New Features

The project structure is clear with separated modules:
- Add new email provider: extend `gmail_fetcher.py`
- Support other calendars: extend `calendar_sync.py`
- Use local LLM: modify `llm_analyzer.py`

## Security Notes

- Do not commit `credentials.json`, `token.json`, `.env` to version control
- These files are already in `.gitignore`
- OpenRouter API Key is only used for your bill analysis, monitor usage
- The program only reads emails with the specified label, does not access entire inbox

## License

MIT

## Contributing

Issues and Pull Requests are welcome.