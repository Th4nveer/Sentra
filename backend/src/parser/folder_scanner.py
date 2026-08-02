"""
Folder Scanner module.
Scans the raw_tenders directory for new tender documents,
extracts text, parses structured data, and optionally moves processed files.
"""
import os
import shutil
from typing import List, Tuple, Optional
from pathlib import Path

from src.parser.document_reader import DocumentReader, SUPPORTED_EXTENSIONS
from src.parser.tender_parser import TenderParser
from src.parser.models import TenderData


class FolderScanner:
    """
    Watches the raw_tenders folder for new tender documents and processes them.
    """

    def __init__(
        self,
        input_dir: str = "./data/raw_tenders",
        processed_dir: str = "./data/processed",
        move_after_processing: bool = True
    ):
        self.input_dir = input_dir
        self.processed_dir = processed_dir
        self.move_after_processing = move_after_processing
        self.reader = DocumentReader()
        self.parser = TenderParser()

        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    def scan(self) -> List[Tuple[str, str, TenderData]]:
        """
        Scans the input directory for supported tender documents.
        
        Returns:
            List of tuples: (original_filepath, extracted_text, parsed_tender_data)
        """
        results = []
        files = self._list_supported_files()

        if not files:
            print(f"[FolderScanner] No supported files found in {self.input_dir}")
            return results

        print(f"[FolderScanner] Found {len(files)} tender document(s) to process.")

        for filepath in files:
            try:
                filename = os.path.basename(filepath)
                print(f"[FolderScanner] Processing: {filename}...")

                # 1. Extract text from document
                text = self.reader.read_file(filepath)

                if not text or len(text.strip()) < 20:
                    print(f"  [WARN] Extracted text too short from {filename} ({len(text.strip())} chars). Skipping.")
                    continue

                print(f"  [OK] Extracted {len(text.strip())} characters from {filename}")

                # 2. Parse structured tender data using Groq LLM (with regex fallback)
                tender_data = self.parser.parse_text(text)
                print(f"  [OK] Parsed tender: {tender_data.tender_id} - {tender_data.project_name}".encode('ascii', errors='replace').decode('ascii'))
                print(f"       Dates: {tender_data.start_date} to {tender_data.completion_date}")
                print(f"       Location: {tender_data.location_text}".encode('ascii', errors='replace').decode('ascii'))

                results.append((filepath, text, tender_data))

                # 3. Optionally move processed file
                if self.move_after_processing:
                    dest = os.path.join(self.processed_dir, filename)
                    # Avoid overwriting: append counter if file exists
                    if os.path.exists(dest):
                        stem = Path(filename).stem
                        ext = Path(filename).suffix
                        counter = 1
                        while os.path.exists(dest):
                            dest = os.path.join(self.processed_dir, f"{stem}_{counter}{ext}")
                            counter += 1
                    shutil.move(filepath, dest)
                    print(f"  [OK] Moved to processed: {dest}")

            except Exception as e:
                print(f"  [ERROR] Failed to process {filepath}: {e}")
                continue

        return results

    def _list_supported_files(self) -> List[str]:
        """Lists all supported files in the input directory (non-recursive)."""
        if not os.path.exists(self.input_dir):
            return []

        files = []
        for filename in sorted(os.listdir(self.input_dir)):
            filepath = os.path.join(self.input_dir, filename)
            if os.path.isfile(filepath) and DocumentReader.is_supported(filepath):
                files.append(filepath)
        return files

    def get_pending_count(self) -> int:
        """Returns the number of unprocessed files waiting in the input directory."""
        return len(self._list_supported_files())
