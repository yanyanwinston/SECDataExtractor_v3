"""Data models shared across the data retrieval API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Literal, Optional


@dataclass(slots=True)
class FilingRecord:
    """Represents a filing exposed by the data retrieval API."""

    ticker: str
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
