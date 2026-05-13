"""Unified Google API services with shared OAuth authentication"""

from pathlib import Path
from typing import Any
from bill_notify.auth_manager import AuthManager
from bill_notify.interfaces import GmailServiceProvider, CalendarServiceProvider


class GmailServiceAdapter:
    """Adapter that implements GmailServiceProvider using GoogleServices"""

    def __init__(self, google_services: "GoogleServices"):
        self._gs = google_services

    def gmail_service(self) -> Any:
        return self._gs.gmail


class CalendarServiceAdapter:
    """Adapter that implements CalendarServiceProvider using GoogleServices"""

    def __init__(self, google_services: "GoogleServices"):
        self._gs = google_services

    def calendar_service(self) -> Any:
        return self._gs.calendar


class GoogleServices:
    """
    Unified factory for Google API services.
    Shares OAuth authentication between Gmail and Calendar.
    """

    def __init__(
        self, credentials_file: str = "credentials.json", token_file: str = "token.json"
    ):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self._auth: AuthManager | None = None

    @property
    def auth(self) -> AuthManager:
        """Lazy initialization of AuthManager"""
        if self._auth is None:
            self._auth = AuthManager(
                credentials_file=str(self.credentials_file),
                token_file=str(self.token_file),
            )
        return self._auth

    @property
    def gmail(self) -> Any:
        """Get authenticated Gmail service"""
        return self.auth.build_service("gmail", "v1")

    @property
    def calendar(self) -> Any:
        """Get authenticated Calendar service"""
        return self.auth.build_service("calendar", "v3")

    def gmail_provider(self) -> GmailServiceProvider:
        """Get as GmailServiceProvider"""
        return GmailServiceAdapter(self)

    def calendar_provider(self) -> CalendarServiceProvider:
        """Get as CalendarServiceProvider"""
        return CalendarServiceAdapter(self)

    def revoke(self):
        """Delete stored token to force re-authentication"""
        self.auth.revoke_token()