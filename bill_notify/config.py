"""Configuration management module"""

import os
from dataclasses import dataclass
from typing import Dict, Optional
from dotenv import load_dotenv
import yaml

load_dotenv()

# Combined OAuth scopes for both Gmail and Calendar
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


@dataclass
class GmailConfig:
    """Gmail configuration"""

    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    gmail_label: str = "bills"  # label to filter
    days_back: int = 7  # number of days to look back for emails


@dataclass
class OpenRouterConfig:
    """OpenRouter configuration"""

    api_key: str
    model: str = "stepfun/step-3.5-flash:free"  # free model
    base_url: str = "https://openrouter.ai/api/v1"
    pdf_engine: str = "pdf-text"  # PDF processing engine: "pdf-text" (free), "mistral-ocr" (paid), or "native"


@dataclass
class CalendarConfig:
    """Calendar configuration"""

    calendar_id: str = "primary"  # default calendar
    reminder_days: int = 3  # days in advance for reminder


@dataclass
class AppConfig:
    """Application configuration"""

    gmail: GmailConfig
    openrouter: OpenRouterConfig
    calendar: CalendarConfig
    download_dir: str = "./downloads"
    processed_log: str = "./processed_emails.log"
    pdf_passwords: Optional[Dict[str, str]] = None  # PDF password mappings
    dry_run: bool = False
    verbose: bool = False

    @classmethod
    def load(
        cls,
        dry_run: bool = False,
        verbose: bool = False,
        config_file: Optional[str] = None,
        label: Optional[str] = None,
        reminder_days: Optional[int] = None,
        calendar_id: Optional[str] = None,
        days_back: Optional[int] = None,
    ) -> "AppConfig":
        """
        Load from environment variables and config files
        Args:
            dry_run: If True, don't make actual changes
            verbose: If True, enable verbose logging
            config_file: Override config file path
            label: Override Gmail label
            reminder_days: Override reminder days
            calendar_id: Override calendar ID
            days_back: Override days to look back
        """
        # OpenRouter API Key
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        # Determine config file path
        if config_file is None:
            # Check user profile config first
            user_config_dir = os.path.expanduser("~/.config/bill-notify")
            user_config_path = os.path.join(user_config_dir, "config.yaml")
            if os.path.exists(user_config_path):
                config_path = user_config_path
            else:
                config_path = "config.yaml"
        else:
            config_path = config_file

        # Load YAML configuration
        gmail_label = "bills"
        calendar_id_config = "primary"
        reminder_days_config = 3
        pdf_engine = "pdf-text"
        days_back_config = 7

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                gmail_label = user_config.get("gmail_label", "bills")
                calendar_id_config = user_config.get("calendar_id", "primary")
                reminder_days_config = user_config.get("reminder_days", 3)
                pdf_engine = user_config.get("pdf_engine", "pdf-text")
                days_back_config = user_config.get("days_back", 7)
                openrouter_model = user_config.get("model")

        # Apply CLI overrides
        if label is not None:
            gmail_label = label
        if reminder_days is not None:
            reminder_days_config = reminder_days
        if calendar_id is not None:
            calendar_id_config = calendar_id
        if days_back is not None:
            days_back_config = days_back

        # Load PDF passwords from separate file
        pdf_passwords_path = os.getenv("PDF_PASSWORDS_FILE", "pdf_passwords.yaml")
        if os.path.exists(pdf_passwords_path):
            with open(pdf_passwords_path, "r", encoding="utf-8") as f:
                pdf_passwords = yaml.safe_load(f) or {}
        else:
            pdf_passwords = {}

        return cls(
            gmail=GmailConfig(gmail_label=gmail_label, days_back=days_back_config),
            openrouter=OpenRouterConfig(
                api_key=openrouter_api_key, pdf_engine=pdf_engine, model=openrouter_model
            ),
            calendar=CalendarConfig(
                calendar_id=calendar_id_config, reminder_days=reminder_days_config
            ),
            pdf_passwords=pdf_passwords,
            dry_run=dry_run,
            verbose=verbose,
        )