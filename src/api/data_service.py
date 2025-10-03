"""Facade exposing filing and statement retrieval services."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from sec_downloader.edgar_client import EdgarClient

from .data_models import FilingRecord, StatementRecord
from .services.exceptions import DataRetrievalError
from .services.filing_service import FilingRetrievalService
from .services.statement_service import StatementRetrievalService


class DataRetrievalService:
    """Backward-compatible facade exposing filing and statement services."""

    def __init__(
        self,
        download_dir: Path | str = Path("downloads"),
        excel_dir: Path | str = Path("output"),
        edgar_client: Optional[EdgarClient] = None,
        cache_ttl: timedelta | int | float = timedelta(minutes=5),
    ) -> None:
        self.filings = FilingRetrievalService(
            download_dir=download_dir,
            edgar_client=edgar_client,
            cache_ttl=cache_ttl,
        )
        self.statements = StatementRetrievalService(
            filing_service=self.filings,
            excel_dir=excel_dir,
            cache_ttl=cache_ttl,
        )

    # Filing passthroughs
    def get_filings_by_date_range(self, *args, **kwargs) -> list[FilingRecord]:
        return self.filings.get_filings_by_date_range(*args, **kwargs)

    def get_latest_filings(self, *args, **kwargs) -> list[FilingRecord]:
        return self.filings.get_latest_filings(*args, **kwargs)

    def ensure_local_filing(self, *args, **kwargs) -> Optional[FilingRecord]:
        return self.filings.ensure_local_filing(*args, **kwargs)

    # Statement passthroughs
    def get_statements_by_date_range(self, *args, **kwargs) -> list[StatementRecord]:
        return self.statements.get_statements_by_date_range(*args, **kwargs)

    def get_latest_statements(self, *args, **kwargs) -> list[StatementRecord]:
        return self.statements.get_latest_statements(*args, **kwargs)


__all__ = [
    "DataRetrievalError",
    "DataRetrievalService",
    "FilingRetrievalService",
    "StatementRetrievalService",
]
