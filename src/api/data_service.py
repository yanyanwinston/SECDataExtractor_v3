"""Service layer implementing the local-first data retrieval contract."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from sec_downloader import FilingDownload, FilingSearch
from sec_downloader.edgar_client import EdgarClient, EdgarError
from sec_downloader.filing_download import FilingDownloadError
from sec_downloader.filing_search import FilingSearchError
from sec_downloader.models import DownloadConfig, Filing, SearchFilters
from sec_downloader.utils import normalize_ticker

from .data_models import FilingRecord


logger = logging.getLogger(__name__)

_ALLOWED_FORM_TYPES = ["10-K", "10-Q"]


@dataclass(slots=True)
class _TickerCache:
    records: Dict[str, FilingRecord]
    loaded_at: datetime


class DataRetrievalError(Exception):
    """Raised when the data retrieval service cannot satisfy a request."""


class DataRetrievalService:
    """Expose reusable methods backing the `/data` API endpoints."""

    def __init__(
        self,
        download_dir: Path | str = Path("downloads"),
        edgar_client: Optional[EdgarClient] = None,
        cache_ttl: timedelta | int | float = timedelta(minutes=5),
    ) -> None:
        """
        Initialize the service.

        Args:
            download_dir: Root directory where filings are cached on disk.
            edgar_client: Optional EDGAR client for dependency injection.
            cache_ttl: Duration to keep ticker records cached in memory. Provide
                seconds as int/float or a :class:`datetime.timedelta`.
        """
        self.download_dir = Path(download_dir)
        self._client = edgar_client or EdgarClient()
        self._search = FilingSearch(self._client)
        self._downloader = FilingDownload(self._client)
        self._cache: Dict[str, _TickerCache] = {}
        if isinstance(cache_ttl, (int, float)):
            cache_ttl = timedelta(seconds=float(cache_ttl))
        if cache_ttl.total_seconds() < 0:
            raise ValueError("cache_ttl must be non-negative")
        self._cache_ttl = cache_ttl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_filings_by_date_range(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        document_type: Optional[str] = None,
    ) -> List[FilingRecord]:
        """Return filings for ``ticker`` within ``[start_date, end_date]``.

        The method first inspects the local cache. Missing filings are fetched
        from EDGAR, persisted to disk, and then surfaced in the response.
        """

        normalized_ticker = normalize_ticker(ticker)
        form_types = self._resolve_form_types(document_type)
        start_dt, end_dt = self._normalize_date_bounds(start_date, end_date)

        logger.info(
            "Start date-range lookup for ticker=%s start=%s end=%s forms=%s",
            normalized_ticker,
            start_dt,
            end_dt,
            form_types,
        )

        local_records = self._get_cached_local_records(normalized_ticker)
        filtered_local = self._filter_records(local_records.values(), form_types, start_dt, end_dt)
        records_by_accession: Dict[str, FilingRecord] = {
            record.accession_number: record for record in filtered_local
        }
        logger.info(
            "Found %d locally cached filings for ticker=%s",
            len(filtered_local),
            normalized_ticker,
        )

        try:
            remote_filings = self._search_filings(
                normalized_ticker,
                SearchFilters(
                    form_types=form_types,
                    start_date=start_dt,
                    end_date=end_dt,
                ),
            )
        except DataRetrievalError as exc:
            logger.warning("Remote search failed for %s: %s", normalized_ticker, exc)
            remote_filings = []
        else:
            logger.info(
                "Remote search returned %d filings for ticker=%s",
                len(remote_filings),
                normalized_ticker,
            )

        missing_filings = [
            filing
            for filing in remote_filings
            if filing.accession_number not in records_by_accession
        ]

        if missing_filings:
            logger.info(
                "Downloading %d missing filings for %s", len(missing_filings), normalized_ticker
            )
            downloaded_records = self._ensure_cached(normalized_ticker, missing_filings)
            for record in downloaded_records:
                records_by_accession[record.accession_number] = record

            # Any filings that could not be cached are surfaced as remote placeholders.
            cached_accessions = {record.accession_number for record in downloaded_records}
            for filing in missing_filings:
                if filing.accession_number not in cached_accessions:
                    record = self._record_from_filing(filing, source="remote", local_path=None)
                    records_by_accession[record.accession_number] = record
        else:
            self._touch_cache(normalized_ticker, local_records)

        sorted_records = sorted(
            records_by_accession.values(), key=lambda record: record.filing_date, reverse=True
        )
        logger.info(
            "Returning %d filings for ticker=%s",
            len(sorted_records),
            normalized_ticker,
        )
        return sorted_records

    def get_latest_filings(
        self,
        ticker: str,
        limit: int,
        document_type: Optional[str] = None,
    ) -> List[FilingRecord]:
        """Return up to ``limit`` most recent filings for ``ticker``.

        Local cache is preferred. Remote results are downloaded when the
        cache does not satisfy the requested count.
        """

        if limit < 1:
            raise DataRetrievalError("limit must be a positive integer")

        normalized_ticker = normalize_ticker(ticker)
        form_types = self._resolve_form_types(document_type)
        logger.info(
            "Start latest lookup for ticker=%s limit=%d forms=%s",
            normalized_ticker,
            limit,
            form_types,
        )

        local_records = self._get_cached_local_records(normalized_ticker)
        filtered_local = [
            record
            for record in local_records.values()
            if record.form_type in form_types
        ]
        filtered_local.sort(key=lambda record: record.filing_date, reverse=True)
        logger.info(
            "Located %d locally cached filings for ticker=%s",
            len(filtered_local),
            normalized_ticker,
        )

        records_by_accession: Dict[str, FilingRecord] = {}
        for record in filtered_local[:limit]:
            records_by_accession[record.accession_number] = record

        if len(records_by_accession) >= limit:
            return list(records_by_accession.values())

        try:
            remote_filings = self._search_filings(
                normalized_ticker,
                SearchFilters(
                    form_types=form_types,
                    max_results=limit,
                ),
            )
        except DataRetrievalError as exc:
            logger.warning("Remote search failed for %s: %s", normalized_ticker, exc)
            remote_filings = []
        else:
            logger.info(
                "Remote latest search returned %d filings for ticker=%s",
                len(remote_filings),
                normalized_ticker,
            )

        missing_filings = [
            filing
            for filing in remote_filings
            if filing.accession_number not in records_by_accession
        ]

        if missing_filings and len(records_by_accession) < limit:
            downloaded_records = self._ensure_cached(normalized_ticker, missing_filings)
            for record in downloaded_records:
                records_by_accession.setdefault(record.accession_number, record)

            cached_accessions = {record.accession_number for record in downloaded_records}
            for filing in missing_filings:
                if filing.accession_number not in cached_accessions:
                    placeholder = self._record_from_filing(filing, source="remote", local_path=None)
                    records_by_accession.setdefault(placeholder.accession_number, placeholder)
        else:
            self._touch_cache(normalized_ticker, local_records)

        sorted_records = sorted(
            records_by_accession.values(), key=lambda record: record.filing_date, reverse=True
        )

        result = sorted_records[:limit]
        logger.info(
            "Returning %d latest filings for ticker=%s",
            len(result),
            normalized_ticker,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_form_types(self, document_type: Optional[str]) -> List[str]:
        if document_type is None:
            return list(_ALLOWED_FORM_TYPES)

        resolved = document_type.upper()
        if resolved not in _ALLOWED_FORM_TYPES:
            raise DataRetrievalError(
                f"Unsupported documentType '{document_type}'. Allowed values: {', '.join(_ALLOWED_FORM_TYPES)}"
            )
        return [resolved]

    def _normalize_date_bounds(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        end = end_date or date.today()
        start_dt = (
            datetime.combine(start_date, time.min) if start_date else None
        )
        end_dt = datetime.combine(end, time.max)
        if start_dt and start_dt > end_dt:
            raise DataRetrievalError("startDate must be before endDate")
        return start_dt, end_dt

    def _get_cached_local_records(self, ticker: str) -> Dict[str, FilingRecord]:
        cache_entry = self._cache.get(ticker)
        if cache_entry and not self._is_cache_expired(cache_entry.loaded_at):
            cache_entry.loaded_at = datetime.utcnow()
            logger.info(
                "Serving ticker=%s from in-memory cache (%d filings)",
                ticker,
                len(cache_entry.records),
            )
            return dict(cache_entry.records)

        records = self._load_local_filings_from_disk(ticker)
        self._cache[ticker] = _TickerCache(records=dict(records), loaded_at=datetime.utcnow())
        logger.info(
            "Cached %d filings for ticker=%s", len(records), ticker
        )
        return dict(records)

    def _touch_cache(self, ticker: str, records: Dict[str, FilingRecord]) -> None:
        if not records:
            return
        now = datetime.utcnow()
        entry = self._cache.get(ticker)
        if entry is None or self._is_cache_expired(entry.loaded_at):
            self._cache[ticker] = _TickerCache(records=dict(records), loaded_at=now)
        else:
            entry.loaded_at = now

    def _load_local_filings_from_disk(self, ticker: str) -> Dict[str, FilingRecord]:
        ticker_dir = self.download_dir / ticker
        if not ticker_dir.exists():
            return {}

        records: Dict[str, FilingRecord] = {}
        for filing_dir in ticker_dir.iterdir():
            if not filing_dir.is_dir():
                continue
            metadata_path = filing_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                record = self._record_from_metadata(metadata_path, source="local")
            except Exception as exc:  # pragma: no cover - defensive parsing guard
                logger.warning("Failed to parse metadata for %s: %s", filing_dir, exc)
                continue
            records[record.accession_number] = record
        return records

    def _record_from_metadata(self, metadata_path: Path, source: str) -> FilingRecord:
        with metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        filing_info = payload.get("filing_info", {})
        download_info = payload.get("download_info", {})

        ticker = filing_info.get("ticker") or ""
        accession = filing_info.get("accession_number") or ""
        form_type = filing_info.get("form_type") or ""
        filing_date = self._parse_datetime(filing_info.get("filing_date"))
        report_date = self._parse_datetime(filing_info.get("report_date"))
        primary_document = filing_info.get("primary_document")
        company_name = filing_info.get("company_name")

        if not accession or not form_type or not filing_date:
            raise ValueError("metadata.json missing required fields")

        return FilingRecord(
            ticker=ticker,
            accession_number=accession,
            form_type=form_type,
            filing_date=filing_date,
            report_date=report_date,
            company_name=company_name,
            primary_document=primary_document,
            edgar_url=download_info.get("edgar_url"),
            local_path=metadata_path.parent,
            metadata_path=metadata_path,
            source=source,
        )

    def _record_from_filing(
        self,
        filing: Filing,
        source: str,
        local_path: Optional[Path],
    ) -> FilingRecord:
        return FilingRecord(
            ticker=filing.ticker or "",
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            report_date=filing.report_date,
            company_name=filing.company_name,
            primary_document=filing.primary_document,
            edgar_url=filing.base_edgar_url,
            local_path=local_path,
            metadata_path=(local_path / "metadata.json" if local_path else None),
            source=source,
        )

    def _filter_records(
        self,
        records: Iterable[FilingRecord],
        form_types: Sequence[str],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> List[FilingRecord]:
        filtered = []
        for record in records:
            if record.form_type not in form_types:
                continue
            if start_dt and record.filing_date < start_dt:
                continue
            if end_dt and record.filing_date > end_dt:
                continue
            filtered.append(record)
        return filtered

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _search_filings(
        self, ticker: str, filters: SearchFilters
    ) -> List[Filing]:
        try:
            return self._search.search_by_ticker(ticker, filters)
        except (FilingSearchError, EdgarError) as exc:
            raise DataRetrievalError(str(exc)) from exc

    def _ensure_cached(
        self, ticker: str, filings: Sequence[Filing]
    ) -> List[FilingRecord]:
        if not filings:
            return []

        config = DownloadConfig(output_dir=self.download_dir)
        cached_records: List[FilingRecord] = []
        for filing in filings:
            try:
                result = self._downloader.download_filing(filing, config)
            except FilingDownloadError as exc:
                logger.warning("Download failed for %s: %s", filing.display_name, exc)
                continue

            if result.success and result.metadata_path:
                try:
                    record = self._record_from_metadata(result.metadata_path, source="downloaded")
                    cached_records.append(record)
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.warning(
                        "Downloaded filing %s but failed to parse metadata: %s",
                        filing.display_name,
                        exc,
                    )
                    placeholder = self._record_from_filing(
                        filing, source="downloaded", local_path=result.local_path
                    )
                    cached_records.append(placeholder)
            else:
                logger.warning("Download unsuccessful for %s", filing.display_name)
        if cached_records:
            refreshed = self._load_local_filings_from_disk(ticker)
            self._cache[ticker] = _TickerCache(records=refreshed, loaded_at=datetime.utcnow())
            logger.info(
                "Refreshed cache for ticker=%s after downloading (%d filings cached)",
                ticker,
                len(refreshed),
            )
        return cached_records

    def _is_cache_expired(self, loaded_at: datetime) -> bool:
        if self._cache_ttl.total_seconds() == 0:
            return True
        if self._cache_ttl.total_seconds() < 0:
            return True
        return datetime.utcnow() - loaded_at > self._cache_ttl
