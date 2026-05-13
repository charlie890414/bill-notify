"""PDF Processor - Extract text from PDFs using PaddleOCR"""

import logging
import tempfile
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from bill_notify.interfaces import PasswordProvider
from bill_notify.exceptions import PDFProcessingError


logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF Processor with PaddleOCR text extraction"""

    def __init__(self, password_provider: PasswordProvider):
        self.password_provider = password_provider
        self._ocr = None  # Lazy initialization

    @property
    def ocr(self):
        """Lazy-load PaddleOCR on first use"""
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(lang="chinese_cht")
        return self._ocr

    def process_pdf(self, pdf_path: Path, sender_email: str = "") -> str:
        """
        Process PDF file and extract text using PaddleOCR.
        Args:
            pdf_path: PDF file path
            sender_email: Sender email for password lookup
        Returns:
            Extracted text from PDF
        Raises:
            PDFProcessingError: If PDF processing or OCR fails
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        # Read PDF bytes
        try:
            pdf_bytes = pdf_path.read_bytes()
        except Exception as e:
            raise PDFProcessingError(
                f"Failed to read PDF file: {e}", original_error=e
            ) from e

        # Decrypt if needed
        processed_bytes = self._decrypt_if_needed(pdf_bytes, sender_email)

        # Extract text with OCR
        return self._extract_text(processed_bytes)

    def _decrypt_if_needed(
        self, pdf_bytes: bytes, sender_email: str
    ) -> bytes:
        """Decrypt PDF if it's encrypted. Retries on failure if interactive provider available."""
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
        except Exception as e:
            raise PDFProcessingError(
                f"Failed to read PDF: {e}", original_error=e
            ) from e

        # If not encrypted, return as-is
        if not reader.is_encrypted:
            logger.debug("PDF is not encrypted")
            return pdf_bytes

        # Try to decrypt with password (retry loop for interactive providers)
        while True:
            password = self.password_provider.get_password(sender_email)

            if not password:
                raise PDFProcessingError(
                    f"PDF is encrypted and no password found for {sender_email}",
                    original_error=None,
                )

            logger.info(f"Attempting decryption with password for {sender_email}")
            result = reader.decrypt(password)

            if result:
                logger.info("PDF decrypted successfully")
                return self._write_decrypted_pdf(reader)

            # Decryption failed - clear cached password so provider can prompt again
            logger.warning("Decryption failed, will prompt for correct password")

            # Try to clear and retry if the provider supports it
            if hasattr(self.password_provider, 'clear_password'):
                self.password_provider.clear_password(sender_email)
            else:
                raise PDFProcessingError(
                    f"PDF decryption failed with provided password for {sender_email}",
                    original_error=None,
                )

    def _write_decrypted_pdf(self, reader: PdfReader) -> bytes:
        """Write decrypted PDF to bytes"""
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def _extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF using PaddleOCR"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                tmp_path = tmp.name

            try:
                result = self.ocr.predict(tmp_path)
                all_text = []
                for page in result:
                    all_text.extend(page["rec_texts"])
                return "\n".join(all_text)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            raise PDFProcessingError(
                f"OCR text extraction failed: {e}", original_error=e
            ) from e

    def process_pdf_bytes(
        self, pdf_bytes: bytes, sender_email: str = ""
    ) -> str:
        """
        Process PDF bytes directly (for testing).
        Returns extracted text.
        """
        processed_bytes = self._decrypt_if_needed(pdf_bytes, sender_email)
        return self._extract_text(processed_bytes)