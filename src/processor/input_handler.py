"""
Input handler for processing various filing sources.
"""

import os
import tempfile
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests


class FilingSource(ABC):
    """Abstract base class for filing sources."""

    @abstractmethod
    def validate(self) -> bool:
        """Validate the filing source."""
        pass

    @abstractmethod
    def get_path(self) -> str:
        """Get the local file path."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up temporary resources."""
        pass


class LocalFileSource(FilingSource):
    """Handler for local iXBRL files."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def validate(self) -> bool:
        """Validate local file exists and is readable."""
        return self.file_path.exists() and self.file_path.is_file()

    def get_path(self) -> str:
        """Return the local file path."""
        return str(self.file_path)

    def cleanup(self) -> None:
        """No cleanup needed for local files."""
        pass


class URLSource(FilingSource):
    """Handler for SEC EDGAR URLs."""

    def __init__(self, url: str, temp_dir: Optional[Path] = None):
        self.url = url
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.temp_file: Optional[Path] = None

    def validate(self) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(self.url)
            return bool(result.netloc) and result.scheme in ('http', 'https')
        except:
            return False

    def get_path(self) -> str:
        """Download URL and return local path."""
        if self.temp_file and self.temp_file.exists():
            return str(self.temp_file)

        # Download the file with proper User-Agent for SEC
        headers = {
            'User-Agent': 'SECDataExtractor v3.0 user@example.com'
        }
        response = requests.get(self.url, headers=headers, timeout=30)
        response.raise_for_status()

        # Save to temp file
        self.temp_file = self.temp_dir / f"filing_{hash(self.url) % 10000}.htm"
        self.temp_file.write_bytes(response.content)

        return str(self.temp_file)

    def cleanup(self) -> None:
        """Remove temporary file."""
        if self.temp_file and self.temp_file.exists():
            self.temp_file.unlink()


class ZipSource(FilingSource):
    """Handler for ZIP archives containing filing documents."""

    def __init__(self, zip_path: str, temp_dir: Optional[Path] = None):
        self.zip_path = Path(zip_path)
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.extract_dir: Optional[Path] = None
        self.filing_file: Optional[Path] = None

    def validate(self) -> bool:
        """Validate ZIP file exists and is readable."""
        return self.zip_path.exists() and zipfile.is_zipfile(self.zip_path)

    def get_path(self) -> str:
        """Extract ZIP and find the main filing document."""
        if self.filing_file and self.filing_file.exists():
            return str(self.filing_file)

        # Create extraction directory
        self.extract_dir = self.temp_dir / f"extract_{hash(str(self.zip_path)) % 10000}"
        self.extract_dir.mkdir(exist_ok=True)

        # Extract ZIP
        with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.extract_dir)

        # Find the main filing document (largest .htm/.html file)
        html_files = list(self.extract_dir.glob('*.htm')) + list(self.extract_dir.glob('*.html'))

        if not html_files:
            raise ValueError("No HTML files found in ZIP archive")

        # Pick the largest HTML file (usually the main filing)
        self.filing_file = max(html_files, key=lambda p: p.stat().st_size)

        return str(self.filing_file)

    def cleanup(self) -> None:
        """Remove extracted files."""
        if self.extract_dir and self.extract_dir.exists():
            import shutil
            shutil.rmtree(self.extract_dir)


class InputHandler:
    """Handler for various types of filing inputs."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())

    def create_source(self, input_path: str) -> FilingSource:
        """Create appropriate FilingSource based on input type."""

        # URL
        if input_path.startswith(('http://', 'https://')):
            return URLSource(input_path, self.temp_dir)

        # Local file
        input_file = Path(input_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # ZIP archive
        if input_path.lower().endswith('.zip'):
            return ZipSource(input_path, self.temp_dir)

        # Regular file
        return LocalFileSource(input_path)

    def validate_filing(self, file_path: str) -> bool:
        """Basic validation that file looks like an iXBRL filing."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Read first 10KB

            # Check for basic iXBRL/HTML indicators
            indicators = [
                '<html',
                'xbrl',
                'edgar',
                'sec.gov'
            ]

            content_lower = content.lower()
            return any(indicator in content_lower for indicator in indicators)

        except Exception:
            return False