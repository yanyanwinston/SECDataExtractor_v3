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
    cik: Optional[str] = None
    accession_number: str
    form_type: str
    filing_date: datetime
    report_date: Optional[datetime]
    company_name: Optional[str]
    primary_document: Optional[str]
    edgar_url: Optional[str]
    local_path: Optional[Path]
    metadata_path: Optional[Path]
    source: Literal["local", "downloaded", "remote"]

    def available_locally(self) -> bool:
        """Return True when the filing artifacts are present on disk."""

        return self.local_path is not None and self.local_path.exists()

    def to_dict(self) -> Dict[str, object]:
        """Serialize the record into a JSON-serializable dictionary."""

        return {
            "ticker": self.ticker,
            "cik": self.cik,
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
    report_date: Optional[datetime]
    form_type: str
    accession_number: str
    workbook_path: Path
    sheet: StatementSheet

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
