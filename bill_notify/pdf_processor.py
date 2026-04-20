"""PDF Processor - Prepare PDF for LLM analysis via base64 encoding"""

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional
from pypdf import PdfReader, PdfWriter
from bill_notify.exceptions import PDFProcessingError
from paddleocr import PaddleOCR

ocr = PaddleOCR(lang='chinese_cht')

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF Processor"""

    def __init__(self, pdf_passwords: Optional[dict] = None):
        """
        Initialize PDF processor
        Args:
            pdf_passwords: Dictionary mapping sender emails/domains to passwords
        """
        self.pdf_passwords = pdf_passwords or {}

    def _find_password(self, sender_email: str) -> Optional[str]:
        """
        Find password for given sender email
        Supports exact match and domain wildcard (e.g., "*@example.com")
        """
        if not self.pdf_passwords:
            return None

        # Try exact email match first
        if sender_email in self.pdf_passwords:
            return self.pdf_passwords[sender_email]

        # Try domain wildcard pattern
        if "@" in sender_email:
            domain = sender_email.split("@")[1]
            wildcard_pattern = f"*@{domain}"
            if wildcard_pattern in self.pdf_passwords:
                return self.pdf_passwords[wildcard_pattern]

        # Try default wildcard
        if "*" in self.pdf_passwords:
            return self.pdf_passwords["*"]

        return None

    def _process_pdf_bytes(
        self, pdf_bytes: bytes, password: Optional[str] = None
    ) -> bytes:
        """
        Process PDF bytes: decrypt if needed and return final bytes
        Args:
            pdf_bytes: Original PDF file bytes
            password: Password for decryption (if needed)
        Returns:
            Processed PDF bytes (decrypted if password provided and correct, else original)
        Raises:
            PDFProcessingError: If PDF is encrypted and decryption fails with provided password
        """
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
        except Exception as e:
            raise PDFProcessingError(
                f"Failed to read PDF: {e}", original_error=e
            ) from e

        # If not encrypted, return original bytes
        if not reader.is_encrypted:
            return pdf_bytes

        # If encrypted but no password provided, raise error
        if not password:
            raise PDFProcessingError(
                "PDF is encrypted but no password provided", original_error=None
            )

        # Try to decrypt
        if reader.decrypt(password):
            # Write decrypted PDF to memory
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            output_buffer = BytesIO()
            writer.write(output_buffer)
            decrypted_bytes = output_buffer.getvalue()
            output_buffer.close()
            logger.debug("PDF decrypted successfully")
            return decrypted_bytes
        else:
            raise PDFProcessingError(
                "PDF decryption failed - incorrect password", original_error=None
            )

    def process_pdf(self, pdf_path: Path, sender_email: str = "") -> str:
        """
        Process PDF file and extract text using PaddleOCR
        Args:
            pdf_path: PDF file path
            sender_email: Sender email for password lookup
        Returns:
            Extracted text from PDF using PaddleOCR
        Raises:
            PDFProcessingError: If PDF processing or OCR fails
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        # Read PDF bytes once
        try:
            pdf_bytes = pdf_path.read_bytes()
        except Exception as e:
            raise PDFProcessingError(
                f"Failed to read PDF file: {e}", original_error=e
            ) from e

        # Check if PDF needs decryption
        password = self._find_password(sender_email) if sender_email else None

        if password:
            logger.info(f"Attempting decryption with password for {sender_email}")
            processed_bytes = self._process_pdf_bytes(pdf_bytes, password)
            logger.info("PDF processed successfully")
        else:
            # No password found for sender
            if sender_email:
                logger.info(f"No password configured for {sender_email}")
            # Process as-is - _process_pdf_bytes will check encryption and raise if needed
            processed_bytes = self._process_pdf_bytes(pdf_bytes)

        # Use PaddleOCR to extract text
        try:
            # Convert PDF to image for OCR processing
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_pdf:
                tmp_pdf.write(processed_bytes)
                tmp_pdf.flush()

                result = ocr.predict(tmp_pdf.name)
                all_text = []
                for page in result:
                    all_text.extend(page['rec_texts'])                
                extracted_text = "\n".join(all_text)
                logger.info("OCR text extraction successful")
                return extracted_text
        except Exception as e:
            raise PDFProcessingError(
                f"OCR text extraction failed: {e}", original_error=e
            ) from e
