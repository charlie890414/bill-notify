"""Tests for configuration loading priority and locations."""

import pytest

from bill_notify.config import AppConfig


CONFIG_ENV_VARS = [
    "CONFIG_FILE",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "GMAIL_CREDENTIALS_FILE",
    "GMAIL_TOKEN_FILE",
    "GMAIL_LABEL",
    "GMAIL_DAYS_BACK",
    "CALENDAR_ID",
    "REMINDER_DAYS",
    "DOWNLOAD_DIR",
    "PROCESSED_LOG",
    "PDF_PASSWORDS_FILE",
]


@pytest.fixture(autouse=True)
def clean_config_env(monkeypatch):
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_config_priority_defaults_yaml_env_cli(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                'gmail_label: "yaml-label"',
                "days_back: 5",
                'calendar_id: "yaml-calendar"',
                "reminder_days: [4, 2]",
                'model: "yaml-model"',
                'credentials_file: "yaml-credentials.json"',
                'token_file: "yaml-token.json"',
                'download_dir: "yaml-downloads"',
                'processed_log: "yaml-processed.log"',
                'pdf_passwords_file: "yaml-passwords.yaml"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_LABEL", "env-label")
    monkeypatch.setenv("REMINDER_DAYS", "6,3")
    monkeypatch.setenv("OPENROUTER_MODEL", "env-model")
    monkeypatch.setenv("DOWNLOAD_DIR", "env-downloads")

    config = AppConfig.load(
        config_file=str(config_file),
        label="cli-label",
        reminder_days="8,1",
        model="cli-model",
    )

    assert config.gmail.gmail_label == "cli-label"
    assert config.gmail.days_back == 5
    assert config.calendar.calendar_id == "yaml-calendar"
    assert config.calendar.reminder_days == [8, 1]
    assert config.openrouter.model == "cli-model"
    assert config.gmail.credentials_file == str(tmp_path / "yaml-credentials.json")
    assert config.gmail.token_file == str(tmp_path / "yaml-token.json")
    assert config.download_dir == "env-downloads"
    assert config.processed_log == str(tmp_path / "yaml-processed.log")
    assert config.pdf_passwords_file == str(tmp_path / "yaml-passwords.yaml")


def test_config_file_env_selects_config_path(tmp_path, monkeypatch):
    config_file = tmp_path / "from-env.yaml"
    config_file.write_text('gmail_label: "from-env"\n', encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.chdir(tmp_path)

    config = AppConfig.load()

    assert config.gmail.gmail_label == "from-env"


def test_cli_config_path_overrides_env_config_path(tmp_path, monkeypatch):
    env_config = tmp_path / "env.yaml"
    cli_config = tmp_path / "cli.yaml"
    env_config.write_text('gmail_label: "env"\n', encoding="utf-8")
    cli_config.write_text('gmail_label: "cli"\n', encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(env_config))

    config = AppConfig.load(config_file=str(cli_config))

    assert config.gmail.gmail_label == "cli"


def test_explicit_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        AppConfig.load(config_file=str(tmp_path / "missing.yaml"))


def test_default_missing_config_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    config = AppConfig.load()

    assert config.gmail.gmail_label == "bills"
    assert config.calendar.calendar_id == "primary"
    assert config.download_dir == "./downloads"


def test_reminder_days_accept_int_string_and_yaml_list(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("reminder_days: [7, 3, 1]\n", encoding="utf-8")

    config = AppConfig.load(config_file=str(config_file))
    assert config.calendar.reminder_days == [7, 3, 1]

    monkeypatch.setenv("REMINDER_DAYS", "5,2")
    config = AppConfig.load(config_file=str(config_file))
    assert config.calendar.reminder_days == [5, 2]

    config = AppConfig.load(config_file=str(config_file), reminder_days=4)
    assert config.calendar.reminder_days == [4]


def test_yaml_relative_paths_resolve_from_config_file_location(tmp_path):
    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                'credentials_file: "credentials.json"',
                'token_file: "tokens/token.json"',
                'download_dir: "downloads"',
                'processed_log: "state/processed.log"',
                'pdf_passwords_file: "secrets/pdf_passwords.yaml"',
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.load(config_file=str(config_file))

    assert config.gmail.credentials_file == str(config_dir / "credentials.json")
    assert config.gmail.token_file == str(config_dir / "tokens" / "token.json")
    assert config.download_dir == str(config_dir / "downloads")
    assert config.processed_log == str(config_dir / "state" / "processed.log")
    assert config.pdf_passwords_file == str(
        config_dir / "secrets" / "pdf_passwords.yaml"
    )
