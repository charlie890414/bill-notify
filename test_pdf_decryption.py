"""Test PDF decryption fix - Verify the 'seek of closed file' bug is resolved"""

import sys
import tempfile
from pathlib import Path
from io import BytesIO

try:
    from pypdf import PdfWriter, PdfReader
except ImportError:
    print("pypdf not installed. Install with: uv add pypdf")
    sys.exit(1)

from bill_notify.pdf_processor import PDFProcessor


def create_encrypted_pdf(password: str = "test123") -> Path:
    """Create a simple encrypted PDF for testing"""
    # Create a simple PDF in memory
    writer = PdfWriter()
    writer.add_page(
        writer.add_blank_page(width=612, height=792)  # US Letter size
    )
    writer.encrypt(password)

    # Save to temp file
    temp_dir = Path(tempfile.gettempdir())
    pdf_path = temp_dir / "test_encrypted.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    return pdf_path


def test_decrypt_with_bytes_io():
    """Test that PDF decryption uses BytesIO and avoids closed file handle issues"""
    print("Creating encrypted test PDF...")
    pdf_path = create_encrypted_pdf("test123")

    # Configure password mapping
    processor = PDFProcessor(pdf_passwords={"*": "test123"})

    print("Attempting to decrypt PDF...")
    try:
        # Call the internal _decrypt_pdf method directly
        decrypted_path = processor._decrypt_pdf(pdf_path, "test123")

        if decrypted_path:
            print("✓ Decryption successful!")

            # Verify the decrypted PDF can be opened
            if decrypted_path.exists():
                reader = PdfReader(str(decrypted_path))
                if not reader.is_encrypted:
                    print("✓ Decrypted PDF is accessible and not encrypted")
                else:
                    print("✗ Decrypted PDF still encrypted!")
                    return False

                # Clean up
                decrypted_path.unlink()
            else:
                print("✗ Decrypted file not created")
                return False

            print("✓ Test passed: PDF decryption works correctly with BytesIO")
            return True
        else:
            print("✗ Decryption returned None")
            return False

    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up original encrypted PDF
        if pdf_path.exists():
            pdf_path.unlink()


def test_process_pdf_full():
    """Test full PDF processing with decryption"""
    print("\nTesting full PDF processing workflow...")
    pdf_path = create_encrypted_pdf("test123")

    processor = PDFProcessor(pdf_passwords={"*": "test123"})

    try:
        # Process the PDF - this should decrypt and convert to images
        images = processor.process_pdf(pdf_path, sender_email="test@example.com")

        if images and len(images) > 0:
            print(f"✓ Successfully processed PDF to {len(images)} image(s)")
            return True
        else:
            print("✗ No images produced")
            return False

    except Exception as e:
        print(f"✗ Full processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if pdf_path.exists():
            pdf_path.unlink()


if __name__ == "__main__":
    print("=" * 60)
    print("PDF Decryption Fix Test")
    print("=" * 60)
    print()

    test1 = test_decrypt_with_bytes_io()
    test2 = test_process_pdf_full()

    print("\n" + "=" * 60)
    if test1 and test2:
        print("All tests passed! ✓")
        print("The 'seek of closed file' bug is fixed.")
        sys.exit(0)
    else:
        print("Some tests failed ✗")
        sys.exit(1)