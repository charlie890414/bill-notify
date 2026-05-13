"""Password providers for PDF decryption"""

import logging
from getpass import getpass
from pathlib import Path
from typing import Optional
import yaml


logger = logging.getLogger(__name__)


class YamlPasswordProvider:
    """
    Loads PDF passwords from yaml file.
    Supports:
    - Exact email match: "sender@example.com": "password"
    - Domain wildcard: "*@example.com": "password"
    - Default: "*": "password"
    """

    def __init__(self, password_map: Optional[dict[str, str]] = None):
        self._passwords = dict(password_map) if password_map else {}  # Make a copy
        logger.debug(f"YamlPasswordProvider initialized with {len(self._passwords)} passwords: {list(self._passwords.keys())}")

    @classmethod
    def from_file(cls, filepath: str | Path) -> "YamlPasswordProvider":
        """Load passwords from yaml file"""
        path = Path(filepath)
        if not path.exists():
            return cls({})

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(data)

    def get_password(self, sender_email: str) -> str | None:
        """
        Find password for sender email.
        Lookup order: exact match -> domain wildcard -> default
        """
        if not sender_email:
            logger.debug("No sender email provided, returning None")
            return None

        logger.debug(f"Looking for password for: {sender_email}")
        logger.debug(f"Available passwords: {list(self._passwords.keys())}")

        # Exact email match
        if sender_email in self._passwords:
            logger.debug(f"Found exact match for {sender_email}")
            return self._passwords[sender_email]

        # Domain wildcard
        if "@" in sender_email:
            domain = sender_email.split("@")[1]
            wildcard = f"*@{domain}"
            if wildcard in self._passwords:
                logger.debug(f"Found domain wildcard match for {sender_email} ({wildcard})")
                return self._passwords[wildcard]

        # Default wildcard
        if "*" in self._passwords:
            logger.debug("Using default wildcard password")
            return self._passwords["*"]

        logger.debug(f"No password found for {sender_email}")
        return None

    def clear_password(self, sender_email: str) -> None:
        """Remove password for sender (forces re-prompt)"""
        if sender_email in self._passwords:
            del self._passwords[sender_email]
        if "*" in self._passwords:
            del self._passwords["*"]
        if "@" in sender_email:
            wildcard = f"*@{sender_email.split('@')[1]}"
            if wildcard in self._passwords:
                del self._passwords[wildcard]
        logger.debug(f"Cleared password cache for {sender_email}")

    def save(self, sender_email: str, password: str, filepath: str | Path):
        """Save a new password to yaml file"""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        passwords = {}

        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                passwords = yaml.safe_load(f) or {}

        passwords[sender_email] = password
        self._passwords[sender_email] = password

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(passwords, f, sort_keys=False)


class InteractivePasswordProvider:
    """
    Prompts user for password interactively.
    Optionally saves to yaml file.
    """

    def __init__(self, save_path: Optional[str | Path] = None):
        self.save_path = Path(save_path) if save_path else None
        self._pending_email: Optional[str] = None  # Track current sender for retry

    def get_password(self, sender_email: str) -> str | None:
        """Prompt user for password. Call again after failed decryption for retry."""
        # If we have a pending sender and it's the same, prompt for retry
        if self._pending_email == sender_email:
            print("\n密碼錯誤，請重新輸入：")
        else:
            self._pending_email = sender_email
            print(f"\n找不到 {sender_email} 的密碼。請輸入密碼：")

        while True:
            password = getpass("密碼: ")

            if not password:
                print("密碼不能為空。請重新輸入或按 Ctrl+C 取消。")
                continue

            print("密碼已設定")
            return password

    def clear_password(self, sender_email: str) -> None:
        """Reset pending state so next call shows proper prompt"""
        if self._pending_email == sender_email:
            self._pending_email = None


class CompositePasswordProvider:
    """
    Tries multiple providers in sequence.
    First tries yaml, then falls back to interactive.
    """

    def __init__(
        self,
        yaml_provider: Optional[YamlPasswordProvider] = None,
        interactive_provider: Optional[InteractivePasswordProvider] = None,
    ):
        self.yaml_provider = yaml_provider or YamlPasswordProvider()
        self.interactive_provider = interactive_provider

    def get_password(self, sender_email: str) -> str | None:
        """Try yaml first, then interactive"""
        password = self.yaml_provider.get_password(sender_email)
        if password:
            return password

        if self.interactive_provider:
            return self.interactive_provider.get_password(sender_email)

        return None

    def clear_password(self, sender_email: str) -> None:
        """Clear cached passwords to force re-prompt"""
        self.yaml_provider.clear_password(sender_email)
        if self.interactive_provider:
            self.interactive_provider.clear_password(sender_email)
        logger.debug(f"Cleared password cache for {sender_email}")

    def save_password(self, sender_email: str, password: str) -> None:
        """Persist a verified password if interactive saving is configured."""
        if not self.interactive_provider or not self.interactive_provider.save_path:
            return

        self.yaml_provider.save(
            sender_email,
            password,
            self.interactive_provider.save_path,
        )
        logger.info(f"Saved verified PDF password for {sender_email}")


class NoOpPasswordProvider:
    """Password provider that never returns passwords (for testing)"""

    def get_password(self, sender_email: str) -> str | None:
        return None

    def clear_password(self, sender_email: str) -> None:
        pass

    def save_password(self, sender_email: str, password: str) -> None:
        pass
