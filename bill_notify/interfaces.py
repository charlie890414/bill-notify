"""Protocol definitions (interfaces) for bill-notify"""

from typing import Protocol, Any


class PasswordProvider(Protocol):
    """Interface for getting PDF passwords by sender email"""

    def get_password(self, sender_email: str) -> str | None:
        """
        Get password for encrypted PDF from sender.
        Returns None if no password found.
        """
        ...

    def clear_password(self, sender_email: str) -> None:
        """
        Clear cached password for sender (forces re-prompt).
        """
        ...

    def save_password(self, sender_email: str, password: str) -> None:
        """
        Persist a password after it has been verified.
        """
        ...


class GmailServiceProvider(Protocol):
    """Interface for Gmail API access"""

    def gmail_service(self) -> Any:
        """Get authenticated Gmail service"""
        ...


class CalendarServiceProvider(Protocol):
    """Interface for Calendar API access"""

    def calendar_service(self) -> Any:
        """Get authenticated Calendar service"""
        ...
