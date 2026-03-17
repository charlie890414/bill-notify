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

    @classmethod
    def load(cls) -> "AppConfig":
        """Load from environment variables and config file"""
        # OpenRouter API Key
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        # Load YAML configuration
        config_path = os.getenv("CONFIG_FILE", "config.yaml")
        gmail_label = "bills"
        calendar_id = "primary"
        reminder_days = 3
        pdf_engine = "pdf-text"

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                gmail_label = user_config.get("gmail_label", "bills")
                calendar_id = user_config.get("calendar_id", "primary")
                reminder_days = user_config.get("reminder_days", 3)
                pdf_engine = user_config.get("pdf_engine", "pdf-text")

        # Load PDF passwords from separate file
        pdf_passwords_path = os.getenv("PDF_PASSWORDS_FILE", "pdf_passwords.yaml")
        if os.path.exists(pdf_passwords_path):
            with open(pdf_passwords_path, "r", encoding="utf-8") as f:
                pdf_passwords = yaml.safe_load(f) or {}
        else:
            pdf_passwords = {}

        return cls(
            gmail=GmailConfig(gmail_label=gmail_label),
            openrouter=OpenRouterConfig(
                api_key=openrouter_api_key, pdf_engine=pdf_engine
            ),
            calendar=CalendarConfig(
                calendar_id=calendar_id, reminder_days=reminder_days
            ),
            pdf_passwords=pdf_passwords,
        )