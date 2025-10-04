"""Data models shared across the data retrieval API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional


@dataclass(slots=True)
class FilingRecord:
    """Represents a filing exposed by the data retrieval API."""

    ticker: str
    accession_number: str
    form_type: str
    filing_date: datetime
    source: Literal["local", "downloaded", "remote"]
    cik: Optional[str] = None
    report_date: Optional[datetime] = None
    company_name: Optional[str] = None
    primary_document: Optional[str] = None
    edgar_url: Optional[str] = None
    local_path: Optional[Path] = None
    metadata_path: Optional[Path] = None

    def available_locally(self) -> bool:
        """Return True when the filing artifacts are present on disk."""

        return self.local_path is not None and self.local_path.exists()

    def to_dict(self) -> Dict[str, object]:
        """Serialize the record into a JSON-serializable dictionary."""

        return {
            "ticker": self.ticker,
            "accessionNumber": self.accession_number,
            "formType": self.form_type,
            "filingDate": self.filing_date.isoformat(),
            "reportDate": self.report_date.isoformat() if self.report_date else None,
            "companyName": self.company_name,
            "primaryDocument": self.primary_document,
            "edgarUrl": self.edgar_url,
            "localPath": str(self.local_path) if self.local_path else None,
            "metadataPath": str(self.metadata_path) if self.metadata_path else None,
            "source": self.source,
            "cik": self.cik,
            "availableLocally": self.available_locally(),
        }


@dataclass(slots=True)
class StatementRow:
    """Represents a single row within a financial statement."""

    label: str
    values: Dict[str, Optional[object]]

    def to_dict(self) -> Dict[str, object]:
        return {"label": self.label, "values": self.values}


@dataclass(slots=True)
class StatementSheet:
    """Holds the structured data extracted from an Excel sheet."""

    sheet_name: str
    periods: List[str]
    rows: List[StatementRow]

    def to_dict(self) -> Dict[str, object]:
        return {
            "sheetName": self.sheet_name,
            "periods": self.periods,
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(slots=True)
class StatementRecord:
    """Metadata for a statement alongside its structured numeric content."""

    ticker: str
    statement_type: str
    filing_date: datetime
    form_type: str
    accession_number: str
    workbook_path: Path
    sheet: StatementSheet
    report_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "ticker": self.ticker,
            "statementType": self.statement_type,
            "filingDate": self.filing_date.isoformat(),
            "reportDate": self.report_date.isoformat() if self.report_date else None,
            "formType": self.form_type,
            "accessionNumber": self.accession_number,
            "workbookPath": str(self.workbook_path),
            "sheet": self.sheet.to_dict(),
        }
