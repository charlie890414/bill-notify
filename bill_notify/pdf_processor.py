"""PDF Processor - Convert PDF to images for LLM analysis"""
import base64
from pathlib import Path
from typing import List
from pdf2image import convert_from_path
from PIL import Image


class PDFProcessor:
    """PDF Processor"""

    def __init__(self, dpi: int = 150):
        """
        Initialize PDF processor
        Args:
            dpi: Resolution when converting PDF, default 150 (sufficient for LLM recognition, reduces token usage)
        """
        self.dpi = dpi

    def pdf_to_images(self, pdf_path: Path) -> List[Image.Image]:
        """
        Convert PDF to list of PIL Images
        Args:
            pdf_path: PDF file path
        Returns:
            List of PIL Images
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

        images = convert_from_path(str(pdf_path), dpi=self.dpi)
        return images

    def image_to_base64(self, image: Image.Image, format: str = "JPEG") -> str:
        """
        Convert PIL Image to base64 string
        Args:
            image: PIL Image object
            format: Output format, default JPEG (more space-efficient than PNG)
        Returns:
            Base64 encoded string
        """
        from io import BytesIO

        buffered = BytesIO()
        image.save(buffered, format=format, quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/{format.lower()};base64,{img_str}"

    def process_pdf(self, pdf_path: Path) -> List[str]:
        """
        Process PDF file, return list of base64 images
        Args:
            pdf_path: PDF file path
        Returns:
            List of base64 image strings
        """
        images = self.pdf_to_images(pdf_path)
        base64_images = [self.image_to_base64(img) for img in images]
        return base64_images
