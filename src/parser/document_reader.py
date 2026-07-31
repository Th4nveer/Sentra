"""
Document Reader module for extracting text from tender documents.
Supports: PDF (text + OCR for scanned), images (OCR), and plain text files.
"""
import os
import io
from typing import Optional
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class DocumentReader:
    """
    Reads and extracts text from various document formats.
    Uses PyMuPDF for PDFs, pytesseract for OCR on scanned docs/images.
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.tesseract_cmd = tesseract_cmd
        
        # Auto-detect Tesseract executable on Windows if not provided
        if not self.tesseract_cmd:
            possible_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    self.tesseract_cmd = p
                    break

        if self.tesseract_cmd:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            except ImportError:
                pass

    def read_file(self, filepath: str) -> str:
        """
        Reads a document file and returns extracted text.
        Dispatches to the appropriate reader based on file extension.
        """
        ext = Path(filepath).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

        if ext == ".txt":
            return self._read_text_file(filepath)
        elif ext == ".pdf":
            return self._read_pdf(filepath)
        elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            return self._read_image_ocr(filepath)
        else:
            raise ValueError(f"No reader available for: {ext}")

    def _read_text_file(self, filepath: str) -> str:
        """Read plain text files with encoding fallback."""
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(filepath, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        # Final fallback — binary read and decode with replacement
        with open(filepath, "rb") as f:
            return f.read().decode("utf-8", errors="replace")

    def _read_pdf(self, filepath: str) -> str:
        """
        Extract text from PDF using PyMuPDF (fitz).
        If text content is too short (likely a scanned/image PDF), falls back to OCR.
        """
        import fitz  # PyMuPDF

        doc = fitz.open(filepath)
        text_parts = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text and page_text.strip():
                text_parts.append(page_text.strip())

        doc.close()
        combined_text = "\n\n".join(text_parts)

        # If extracted text is very short, it's likely a scanned PDF — try OCR
        if len(combined_text.strip()) < 50:
            print(f"[DocumentReader] PDF text extraction yielded little text ({len(combined_text)} chars). Attempting OCR...")
            ocr_text = self._ocr_pdf_pages(filepath)
            if ocr_text and len(ocr_text.strip()) > len(combined_text.strip()):
                return ocr_text

        return combined_text

    def _ocr_pdf_pages(self, filepath: str) -> str:
        """
        OCR each page of a PDF by rendering to image and running pytesseract.
        """
        try:
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image

            doc = fitz.open(filepath)
            ocr_parts = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                # Render page at 300 DPI for good OCR quality
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                page_text = pytesseract.image_to_string(img, lang="eng")
                if page_text and page_text.strip():
                    ocr_parts.append(page_text.strip())

            doc.close()
            return "\n\n".join(ocr_parts)

        except ImportError as e:
            print(f"[DocumentReader] OCR dependencies not available: {e}")
            return ""
        except Exception as e:
            print(f"[DocumentReader] OCR failed for PDF: {e}")
            return ""

    def _read_image_ocr(self, filepath: str) -> str:
        """
        OCR an image file using pytesseract.
        """
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(filepath)
            text = pytesseract.image_to_string(img, lang="eng")
            return text.strip() if text else ""

        except ImportError as e:
            print(f"[DocumentReader] pytesseract not available: {e}")
            return ""
        except Exception as e:
            print(f"[DocumentReader] Image OCR failed: {e}")
            return ""

    @staticmethod
    def is_supported(filepath: str) -> bool:
        """Check if a file type is supported for reading."""
        return Path(filepath).suffix.lower() in SUPPORTED_EXTENSIONS
