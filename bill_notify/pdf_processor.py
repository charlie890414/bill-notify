"""PDF Processor - Prepare PDF for LLM analysis via base64 encoding"""

import base64
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from pypdf import PdfReader, PdfWriter


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

    def _decrypt_pdf(self, pdf_path: Path, password: str) -> Optional[Path]:
        """
        Decrypt PDF and save to temporary file
        Returns path to decrypted PDF, or None if decryption failed
        """
        try:
            # Read entire file into memory to avoid file handle closure issues
            pdf_bytes = pdf_path.read_bytes()
            reader = PdfReader(BytesIO(pdf_bytes))

            if not reader.is_encrypted:
                return pdf_path

            # Try to decrypt
            if reader.decrypt(password):
                # Save decrypted PDF to temp file using PdfWriter
                decrypted_path = pdf_path.parent / f"decrypted_{pdf_path.name}"
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                with open(decrypted_path, "wb") as output:
                    writer.write(output)
                return decrypted_path
            else:
                return None
        except Exception as e:
            print(f"    Decryption error: {e}")
            return None

    def process_pdf(self, pdf_path: Path, sender_email: str = "") -> List[str]:
        """
        Process PDF file, return base64-encoded PDF string
        Args:
            pdf_path: PDF file path
            sender_email: Sender email for password lookup
        Returns:
            List containing a single base64 PDF string with data:application/pdf;base64, prefix
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        # Check if PDF needs decryption
        password = self._find_password(sender_email) if sender_email else None

        working_pdf = pdf_path
        if password:
            print(f"  Attempting decryption with password for {sender_email}...")
            decrypted_path = self._decrypt_pdf(pdf_path, password)
            if decrypted_path:
                working_pdf = decrypted_path
                print("  ✓  PDF decrypted successfully")
            else:
                print("  ⚠️  Decryption failed, trying without password")
                # Continue with original file (might not be encrypted or wrong password)

        # Read PDF bytes and encode to base64
        pdf_bytes = working_pdf.read_bytes()
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        data_url = f"data:application/pdf;base64,{base64_pdf}"

        # Clean up decrypted temp file if created
        if working_pdf != pdf_path and working_pdf.exists():
            try:
                working_pdf.unlink()
            except OSError:
                pass

        return [data_url]