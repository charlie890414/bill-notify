"""Authentication manager - Shared OAuth 2.0 authentication for Google APIs"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from google.auth.transport.requests import Request
from google.auth.credentials import Credentials as BaseCredentials
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from bill_notify.config import SCOPES


class AuthenticationError(Exception):
    """Raised when authentication fails"""

    pass


class AuthManager:
    """Manages OAuth 2.0 authentication for Google APIs"""

    def __init__(
        self, credentials_file: str = "credentials.json", token_file: str = "token.json"
    ):
        """
        Initialize authentication manager
        Args:
            credentials_file: Path to OAuth 2.0 client credentials JSON
            token_file: Path to store/load OAuth token
        """
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)

    def get_credentials(self) -> BaseCredentials:
        """
        Get valid OAuth credentials, refreshing or re-authenticating if needed
        Returns:
            Valid Credentials object
        Raises:
            AuthenticationError: If credentials file is missing or auth fails
        """
        creds = None

        # Load existing token if available
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_info(
                    json.loads(self.token_file.read_text()), SCOPES
                )
            except (json.JSONDecodeError, ValueError):
                # Token file exists but is invalid, will re-authenticate
                pass

        # Refresh or obtain new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    # Refresh failed, need full re-authentication
                    creds = self._authenticate_interactively()
            else:
                creds = self._authenticate_interactively()

            # Save token for future use
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json())  # type: ignore[attr-defined]

        return creds

    def _authenticate_interactively(self) -> BaseCredentials:
        """
        Perform interactive OAuth flow (opens browser)
        Returns:
            New Credentials object
        Raises:
            AuthenticationError: If credentials file is missing
        """
        if not self.credentials_file.exists():
            raise AuthenticationError(
                f"OAuth credentials file not found: {self.credentials_file}\n"
                "Please create OAuth 2.0 client credentials in Google Cloud Console "
                "(Gmail API and Calendar API must be enabled) and save to this location."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_file), SCOPES
        )
        return flow.run_local_server(port=0)  # type: ignore[return-value]

    def build_service(self, api_name: str, api_version: str, **kwargs) -> Any:
        """
        Build a Google API service with authenticated credentials
        Args:
            api_name: API name (e.g., 'gmail', 'calendar')
            api_version: API version (e.g., 'v1', 'v3')
            **kwargs: Additional arguments passed to build()
        Returns:
            Authenticated service object
        """
        creds = self.get_credentials()
        return build(
            api_name, api_version, credentials=creds, cache_discovery=False, **kwargs
        )

    def revoke_token(self):
        """Delete stored token to force re-authentication on next run"""
        if self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError:
                pass
