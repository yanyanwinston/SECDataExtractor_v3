"""
Data models for SEC filing downloader.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class Company:
    """Represents a company in the SEC database."""
    cik: str
    ticker: Optional[str] = None
    name: Optional[str] = None
    exchange: Optional[str] = None

    @property
    def cik_padded(self) -> str:
        """Return CIK padded to 10 digits."""
        return self.cik.zfill(10)

    def __str__(self) -> str:
        if self.ticker and self.name:
            return f"{self.ticker} ({self.name})"
        elif self.ticker:
            return self.ticker
        elif self.name:
            return f"{self.name} (CIK: {self.cik})"
        else:
            return f"CIK: {self.cik}"


@dataclass
class Filing:
    """Represents a SEC filing."""
    cik: str
    accession_number: str
    form_type: str
    filing_date: datetime
    report_date: Optional[datetime] = None
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    document_urls: Dict[str, str] = field(default_factory=dict)
    primary_document: Optional[str] = None
    filing_url: Optional[str] = None

    @property
    def cik_padded(self) -> str:
        """Return CIK padded to 10 digits."""
        return self.cik.zfill(10)

    def _ensure_accession_number(self) -> str:
        """Ensure accession_number is populated, deriving it when possible."""
        if self.accession_number:
            return self.accession_number

        if self.primary_document:
            base_name = self.primary_document

            # Strip extension if present
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]

            # Remove trailing "-index" or similar suffixes
            if base_name.lower().endswith('-index'):
                base_name = base_name[:-6]

            if base_name.replace('-', '').isdigit():
                self.accession_number = base_name
                return self.accession_number

        return self.accession_number or ''

    @property
    def accession_clean(self) -> str:
        """Return accession number without dashes."""
        accession = self._ensure_accession_number()
        return accession.replace('-', '') if accession else ''

    @property
    def base_edgar_url(self) -> str:
        """Return base EDGAR URL for this filing."""
        accession = self.accession_clean
        if accession:
            return f"https://www.sec.gov/Archives/edgar/data/{self.cik_padded}/{accession}"
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik_padded}"

    @property
    def display_name(self) -> str:
        """Return display name for this filing."""
        ticker_part = f"{self.ticker} " if self.ticker else ""
        date_part = self.filing_date.strftime("%Y-%m-%d")
        return f"{ticker_part}{self.form_type} {date_part}"

    def __str__(self) -> str:
        return self.display_name


@dataclass
class DownloadConfig:
    """Configuration for filing downloads."""
    output_dir: Path
    create_subdirs: bool = True
    include_exhibits: bool = False
    max_parallel: int = 3
    retry_attempts: int = 3
    timeout_seconds: int = 30
    verify_downloads: bool = True

    def get_filing_dir(self, filing: Filing) -> Path:
        """Get output directory for a specific filing."""
        if not self.create_subdirs:
            return self.output_dir

        ticker = filing.ticker or f"CIK_{filing.cik}"
        date_str = filing.report_date.strftime("%Y-%m-%d") if filing.report_date else filing.filing_date.strftime("%Y-%m-%d")
        filing_dir = self.output_dir / ticker / f"{filing.form_type}_{date_str}"

        return filing_dir


@dataclass
class DownloadResult:
    """Result of a filing download operation."""
    filing: Filing
    success: bool
    local_path: Optional[Path] = None
    error: Optional[str] = None
    downloaded_files: List[str] = field(default_factory=list)
    metadata_path: Optional[Path] = None

    @property
    def primary_file_path(self) -> Optional[Path]:
        """Return path to the primary filing document."""
        if not self.success or not self.local_path:
            return None

        # Look for the primary document file
        if self.filing.primary_document:
            primary_path = self.local_path / self.filing.primary_document
            if primary_path.exists():
                return primary_path

        # Fall back to looking for .htm files
        for file_path in self.local_path.glob("*.htm"):
            return file_path

        for file_path in self.local_path.glob("*.html"):
            return file_path

        return None


@dataclass
class SearchFilters:
    """Filters for filing searches."""
    form_types: List[str] = field(default_factory=lambda: ["10-K", "10-Q"])
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_amendments: bool = False
    max_results: Optional[int] = None

    @property
    def expanded_form_types(self) -> List[str]:
        """Return form types including amendments if requested."""
        types = self.form_types.copy()
        if self.include_amendments:
            for form_type in self.form_types:
                types.append(f"{form_type}/A")
        return types
