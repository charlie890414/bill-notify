"""Configuration management module"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
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


@dataclass
class CalendarConfig:
    """Calendar configuration"""

    calendar_id: str = "primary"  # default calendar
    reminder_days: Optional[list[int]] = None  # days in advance for reminders

    def __post_init__(self):
        if self.reminder_days is None:
            self.reminder_days = [3]


@dataclass
class AppConfig:
    """Application configuration"""

    gmail: GmailConfig
    openrouter: OpenRouterConfig
    calendar: CalendarConfig
    download_dir: str = "./downloads"
    processed_log: str = "./processed_emails.log"
    pdf_passwords_file: str = "pdf_passwords.yaml"
    ocr_cache_dir: str = "./.cache/paddlex"
    ocr_text_detection_model_name: Optional[str] = None
    ocr_text_recognition_model_name: Optional[str] = None
    ocr_cpu_threads: Optional[int] = None
    dry_run: bool = False
    verbose: bool = False
    force_reprocess: bool = False

    @classmethod
    def load(
        cls,
        dry_run: bool = False,
        verbose: bool = False,
        force_reprocess: bool = False,
        config_file: Optional[str] = None,
        label: Optional[str] = None,
        reminder_days: Optional[str | int | list[int]] = None,
        calendar_id: Optional[str] = None,
        days_back: Optional[int] = None,
        credentials_file: Optional[str] = None,
        token_file: Optional[str] = None,
        download_dir: Optional[str] = None,
        processed_log: Optional[str] = None,
        pdf_passwords_file: Optional[str] = None,
        ocr_cache_dir: Optional[str] = None,
        ocr_text_detection_model_name: Optional[str] = None,
        ocr_text_recognition_model_name: Optional[str] = None,
        ocr_cpu_threads: Optional[int] = None,
        model: Optional[str] = None,
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

        config_path, explicit_config = _resolve_config_path(config_file)

        # Load YAML configuration
        settings = {
            "credentials_file": "credentials.json",
            "token_file": "token.json",
            "gmail_label": "bills",
            "days_back": 7,
            "calendar_id": "primary",
            "reminder_days": [3],
            "model": "stepfun/step-3.5-flash:free",
            "download_dir": "./downloads",
            "processed_log": "./processed_emails.log",
            "pdf_passwords_file": "pdf_passwords.yaml",
            "ocr_cache_dir": os.getenv("PADDLE_PDX_CACHE_HOME", "./.cache/paddlex"),
            "ocr_text_detection_model_name": None,
            "ocr_text_recognition_model_name": None,
            "ocr_cpu_threads": None,
        }

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                for key in settings:
                    if key in user_config:
                        settings[key] = user_config[key]
                _resolve_yaml_paths(settings, user_config, config_path.parent)
        elif explicit_config:
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Environment overrides YAML/defaults.
        env_overrides = {
            "credentials_file": os.getenv("GMAIL_CREDENTIALS_FILE"),
            "token_file": os.getenv("GMAIL_TOKEN_FILE"),
            "gmail_label": os.getenv("GMAIL_LABEL"),
            "days_back": os.getenv("GMAIL_DAYS_BACK"),
            "calendar_id": os.getenv("CALENDAR_ID"),
            "reminder_days": os.getenv("REMINDER_DAYS"),
            "model": os.getenv("OPENROUTER_MODEL"),
            "download_dir": os.getenv("DOWNLOAD_DIR"),
            "processed_log": os.getenv("PROCESSED_LOG"),
            "pdf_passwords_file": os.getenv("PDF_PASSWORDS_FILE"),
            "ocr_cache_dir": os.getenv("OCR_CACHE_DIR"),
            "ocr_text_detection_model_name": os.getenv(
                "OCR_TEXT_DETECTION_MODEL_NAME"
            ),
            "ocr_text_recognition_model_name": os.getenv(
                "OCR_TEXT_RECOGNITION_MODEL_NAME"
            ),
            "ocr_cpu_threads": os.getenv("OCR_CPU_THREADS"),
        }
        for key, value in env_overrides.items():
            if value not in (None, ""):
                settings[key] = value

        # Apply CLI overrides
        if label is not None:
            settings["gmail_label"] = label
        if reminder_days is not None:
            settings["reminder_days"] = reminder_days
        if calendar_id is not None:
            settings["calendar_id"] = calendar_id
        if days_back is not None:
            settings["days_back"] = days_back
        if credentials_file is not None:
            settings["credentials_file"] = credentials_file
        if token_file is not None:
            settings["token_file"] = token_file
        if download_dir is not None:
            settings["download_dir"] = download_dir
        if processed_log is not None:
            settings["processed_log"] = processed_log
        if pdf_passwords_file is not None:
            settings["pdf_passwords_file"] = pdf_passwords_file
        if ocr_cache_dir is not None:
            settings["ocr_cache_dir"] = ocr_cache_dir
        if ocr_text_detection_model_name is not None:
            settings["ocr_text_detection_model_name"] = ocr_text_detection_model_name
        if ocr_text_recognition_model_name is not None:
            settings["ocr_text_recognition_model_name"] = (
                ocr_text_recognition_model_name
            )
        if ocr_cpu_threads is not None:
            settings["ocr_cpu_threads"] = ocr_cpu_threads
        if model is not None:
            settings["model"] = model

        return cls(
            gmail=GmailConfig(
                credentials_file=str(settings["credentials_file"]),
                token_file=str(settings["token_file"]),
                gmail_label=str(settings["gmail_label"]),
                days_back=int(settings["days_back"]),
            ),
            openrouter=OpenRouterConfig(
                api_key=openrouter_api_key,
                model=str(settings["model"]),
            ),
            calendar=CalendarConfig(
                calendar_id=str(settings["calendar_id"]),
                reminder_days=_parse_reminder_days(settings["reminder_days"]),
            ),
            download_dir=str(settings["download_dir"]),
            processed_log=str(settings["processed_log"]),
            pdf_passwords_file=str(settings["pdf_passwords_file"]),
            ocr_cache_dir=str(settings["ocr_cache_dir"]),
            ocr_text_detection_model_name=_optional_str(
                settings["ocr_text_detection_model_name"]
            ),
            ocr_text_recognition_model_name=_optional_str(
                settings["ocr_text_recognition_model_name"]
            ),
            ocr_cpu_threads=_optional_int(settings["ocr_cpu_threads"]),
            dry_run=dry_run,
            verbose=verbose,
            force_reprocess=force_reprocess,
        )


def _resolve_config_path(config_file: Optional[str]) -> tuple[Path, bool]:
    """Resolve config path and whether it was explicitly requested."""
    if config_file:
        return Path(config_file), True

    env_config = os.getenv("CONFIG_FILE")
    if env_config:
        return Path(env_config), True

    user_config_path = Path.home() / ".config" / "bill-notify" / "config.yaml"
    if user_config_path.exists():
        return user_config_path, False

    return Path("config.yaml"), False


def _resolve_yaml_paths(
    settings: dict[str, object], user_config: dict[str, object], config_dir: Path
) -> None:
    """Resolve relative paths that came from YAML relative to the YAML file."""
    for key in (
        "credentials_file",
        "token_file",
        "download_dir",
        "processed_log",
        "pdf_passwords_file",
        "ocr_cache_dir",
    ):
        if key not in user_config:
            continue

        path = Path(str(settings[key])).expanduser()
        if path.is_absolute():
            settings[key] = str(path)
        else:
            settings[key] = str(config_dir / path)


def _parse_reminder_days(value: object) -> list[int]:
    """Parse reminder days from int, comma string, or YAML list."""
    if isinstance(value, int):
        values = [value]
    elif isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise ValueError("reminder_days must be an int, comma string, or list")

    reminder_days = sorted({int(day) for day in values}, reverse=True)
    if not reminder_days:
        raise ValueError("reminder_days must not be empty")
    if any(day < 0 for day in reminder_days):
        raise ValueError("reminder_days cannot contain negative values")

    return reminder_days


def _optional_str(value: object) -> Optional[str]:
    """Convert optional config values without turning None into 'None'."""
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: object) -> Optional[int]:
    """Convert optional integer config values."""
    if value in (None, ""):
        return None
    return int(value)
