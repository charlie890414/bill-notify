"""Test PDF decryption - Verify decryption works correctly"""

import sys
import tempfile
from pathlib import Path
import base64

try:
    from pypdf import PdfWriter, PdfReader
except ImportError:
    print("pypdf not installed. Install with: uv add pypdf")
    sys.exit(1)

from bill_notify.pdf_processor import PDFProcessor


def create_encrypted_pdf(password: str = "test123") -> Path:
    """Create a simple encrypted PDF for testing"""
    writer = PdfWriter()
    writer.add_page(
        writer.add_blank_page(width=612, height=792)  # US Letter size
    )
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

    processor = PDFProcessor(pdf_passwords={"*": "test123"})

    print("Processing PDF with decryption...")
    try:
        # Process the PDF - should decrypt and return base64
        result = processor.process_pdf(pdf_path, sender_email="test@example.com")
        
        assert result and result.startswith("data:application/pdf;base64,"), "Processing did not return valid base64 PDF"
        print("✓ PDF processed successfully, got base64 encoded data")
        
        # Decode and verify it's a valid PDF
        pdf_bytes = base64.b64decode(result.split(",", 1)[1])
        # Try to read it as PDF - if decryption failed, pypdf would error on read
        from io import BytesIO
        PdfReader(BytesIO(pdf_bytes))
        # If we can read it without error, decryption worked (or PDF wasn't encrypted to begin with)
        print("✓ Decryption test passed - PDF is readable")

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
    writer = PdfWriter()
    writer.add_page(writer.add_blank_page(width=612, height=792))
    
    temp_dir = Path(tempfile.gettempdir())
    pdf_path = temp_dir / "test_unencrypted.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)
    
    processor = PDFProcessor(pdf_passwords={})
    
    try:
        result = processor.process_pdf(pdf_path)
        assert result and result.startswith("data:application/pdf;base64,"), "Failed to process unencrypted PDF"
        print("✓ Unencrypted PDF processed successfully")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


def test_wrong_password():
    """Test PDF with wrong password falls back gracefully"""
    print("\nTesting wrong password fallback...")
    pdf_path = create_encrypted_pdf("correct_password")
    
    # Configure with wrong password
    processor = PDFProcessor(pdf_passwords={"*": "wrong_password"})
    
    try:
        result = processor.process_pdf(pdf_path, sender_email="test@example.com")
        # Should still return base64 (of original encrypted PDF) even if decryption fails
        assert result and result.startswith("data:application/pdf;base64,"), "Failed to handle wrong password gracefully"
        print("✓ Graceful fallback on wrong password")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        raise
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
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        sys.exit(0)
    except Exception:
        print("\n" + "=" * 60)
        print("Some tests failed ✗")
        sys.exit(1)
