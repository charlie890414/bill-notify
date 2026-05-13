"""Test PDF decryption - Verify decryption works correctly"""

import sys
import tempfile
from pathlib import Path

try:
    from pypdf import PdfWriter, PdfReader
    from reportlab.pdfgen import canvas
    import io
except ImportError:
    print("pypdf not installed. Install with: uv add pypdf")
    sys.exit(1)

from bill_notify.pdf_processor import PDFProcessor
from bill_notify.password_providers import YamlPasswordProvider, NoOpPasswordProvider
from bill_notify.exceptions import PDFProcessingError


def create_encrypted_pdf(password: str = "test123") -> Path:
    """Create a simple encrypted PDF for testing"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet)
    can.drawString(100, 700, "Hello World")
    can.save()

    packet.seek(0)

    text_pdf = PdfReader(packet)

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    writer.encrypt(password)

    temp_dir = Path(tempfile.gettempdir())
    pdf_path = temp_dir / "test_encrypted.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    return pdf_path


def test_pdf_decryption():
    """Test that PDF decryption works correctly"""
    print("Creating encrypted test PDF...")
    pdf_path = create_encrypted_pdf("test123")

    # Use YamlPasswordProvider with the password
    password_provider = YamlPasswordProvider({"*": "test123"})
    processor = PDFProcessor(password_provider=password_provider)

    print("Processing PDF with decryption...")
    try:
        result = processor.process_pdf(pdf_path, sender_email="test@example.com")
        # Result should be a string (even if empty due to OCR limitations on simple PDFs)
        assert isinstance(result, str), "Processing did not return text"
        print("✓ PDF processed successfully (decryption worked)")
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_pdf_without_password():
    """Test processing unencrypted PDF without password mapping"""
    print("\nTesting unencrypted PDF...")

    # Create unencrypted PDF
    packet = io.BytesIO()
    can = canvas.Canvas(packet)
    can.drawString(100, 700, "Hello World")
    can.save()
    packet.seek(0)

    text_pdf = PdfReader(packet)
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    writer.add_page(text_pdf.pages[0])

    temp_dir = Path(tempfile.gettempdir())
    pdf_path = temp_dir / "test_unencrypted.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    processor = PDFProcessor(password_provider=NoOpPasswordProvider())

    try:
        result = processor.process_pdf(pdf_path)
        assert result and isinstance(result, str), "Failed to process unencrypted PDF"
        print("✓ Unencrypted PDF processed successfully")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_wrong_password():
    """Test PDF with wrong password raises PDFProcessingError"""
    print("\nTesting wrong password raises exception...")
    pdf_path = create_encrypted_pdf("correct_password")

    # Configure with wrong password
    password_provider = YamlPasswordProvider({"*": "wrong_password"})
    processor = PDFProcessor(password_provider=password_provider)

    try:
        result = processor.process_pdf(pdf_path, sender_email="test@example.com")
        print(f"✗ Expected PDFProcessingError but got result: {result}")
        raise AssertionError("Should have raised PDFProcessingError")
    except PDFProcessingError as e:
        print(f"✓ Correctly raised PDFProcessingError: {e}")
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_no_password_provider():
    """Test that encrypted PDF without password raises error"""
    print("\nTesting encrypted PDF without password...")
    pdf_path = create_encrypted_pdf("test123")

    processor = PDFProcessor(password_provider=NoOpPasswordProvider())

    try:
        result = processor.process_pdf(pdf_path, sender_email="test@example.com")
        print(f"✗ Expected PDFProcessingError but got result: {result}")
        raise AssertionError("Should have raised PDFProcessingError")
    except PDFProcessingError as e:
        print(f"✓ Correctly raised PDFProcessingError: {e}")
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_successful_decryption_saves_verified_password():
    """Test that passwords are only saved after successful decryption."""
    pdf_path = create_encrypted_pdf("test123")

    class RecordingPasswordProvider:
        def __init__(self):
            self.saved = []

        def get_password(self, sender_email: str) -> str | None:
            return "test123"

        def clear_password(self, sender_email: str) -> None:
            pass

        def save_password(self, sender_email: str, password: str) -> None:
            self.saved.append((sender_email, password))

    password_provider = RecordingPasswordProvider()
    processor = PDFProcessor(password_provider=password_provider)

    try:
        processor._decrypt_if_needed(pdf_path.read_bytes(), "test@example.com")

        assert password_provider.saved == [("test@example.com", "test123")]
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_failed_decryption_does_not_save_password():
    """Test that wrong passwords are not saved."""
    pdf_path = create_encrypted_pdf("correct_password")

    class RecordingPasswordProvider:
        def __init__(self):
            self.saved = []
            self.calls = 0

        def get_password(self, sender_email: str) -> str | None:
            self.calls += 1
            if self.calls == 1:
                return "wrong_password"
            return None

        def clear_password(self, sender_email: str) -> None:
            pass

        def save_password(self, sender_email: str, password: str) -> None:
            self.saved.append((sender_email, password))

    password_provider = RecordingPasswordProvider()
    processor = PDFProcessor(password_provider=password_provider)

    try:
        try:
            processor._decrypt_if_needed(pdf_path.read_bytes(), "test@example.com")
        except PDFProcessingError:
            pass

        assert password_provider.saved == []
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


if __name__ == "__main__":
    print("=" * 60)
    print("PDF Decryption Tests")
    print("=" * 60)
    print()

    try:
        test_pdf_decryption()
        test_pdf_without_password()
        test_wrong_password()
        test_no_password_provider()

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        sys.exit(0)
    except Exception:
        print("\n" + "=" * 60)
        print("Some tests failed ✗")
        sys.exit(1)
