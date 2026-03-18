"""PDF Processor - Prepare PDF for LLM analysis via base64 encoding"""

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional
from pypdf import PdfReader, PdfWriter


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

    def _process_pdf_bytes(self, pdf_bytes: bytes, password: Optional[str] = None) -> bytes:
        """
        Process PDF bytes: decrypt if needed and return final bytes
        Args:
            pdf_bytes: Original PDF file bytes
            password: Password for decryption (if needed)
        Returns:
            Processed PDF bytes (decrypted if password provided and correct, else original)
        """
        reader = PdfReader(BytesIO(pdf_bytes))
        
        # If not encrypted, return original bytes
        if not reader.is_encrypted:
            return pdf_bytes
        
        # If encrypted but no password provided, return original bytes (won't be usable but caller handles it)
        if not password:
            return pdf_bytes
        
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
            logger.warning("Decryption failed, using original file")
            return pdf_bytes

    def process_pdf(self, pdf_path: Path, sender_email: str = "") -> str:
        """
        Process PDF file, return base64-encoded PDF string
        Args:
            pdf_path: PDF file path
            sender_email: Sender email for password lookup
        Returns:
            Base64 PDF string with data:application/pdf;base64, prefix
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        # Read PDF bytes once
        pdf_bytes = pdf_path.read_bytes()
        
        # Check if PDF needs decryption
        password = self._find_password(sender_email) if sender_email else None
        
        if password:
            logger.info(f"Attempting decryption with password for {sender_email}")
            processed_bytes = self._process_pdf_bytes(pdf_bytes, password)
            # Log if decryption actually happened (bytes changed)
            if processed_bytes != pdf_bytes:
                logger.info("PDF decrypted successfully")
            else:
                logger.warning("Decryption failed or PDF was not encrypted, using original")
        else:
            # No password found for sender, skip decryption for this time
            if sender_email:
                logger.info(f"No password configured for {sender_email}, skipping decryption")
            # Process as-is - will check encryption in _process_pdf_bytes
            processed_bytes = self._process_pdf_bytes(pdf_bytes)

        # Encode to base64
        base64_pdf = base64.b64encode(processed_bytes).decode('utf-8')
        return f"data:application/pdf;base64,{base64_pdf}"