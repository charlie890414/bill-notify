"""Custom exceptions for bill-notify application"""

from typing import Optional


class BillNotifyError(Exception):
    """Base exception for all bill-notify errors"""

    pass


class GmailError(BillNotifyError):
    """Raised when Gmail API operations fail"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class CalendarError(BillNotifyError):
    """Raised when Calendar API operations fail"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class AuthenticationError(BillNotifyError):
    """Raised when authentication fails"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class ConfigurationError(BillNotifyError):
    """Raised when configuration is invalid or missing"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class PDFProcessingError(BillNotifyError):
    """Raised when PDF processing fails"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class LLMAnalysisError(BillNotifyError):
    """Raised when LLM analysis fails"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error
