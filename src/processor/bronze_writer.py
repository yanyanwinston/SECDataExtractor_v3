"""Utilities for persisting bronze-layer artifacts (viewer payload + metadata)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

from ..sec_downloader.utils import normalize_cik, parse_accession_number


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BronzeFilingMetadata:
    """Lightweight metadata describing a single filing at the bronze layer."""

    entity_cik: str
    accession_number: str
    filing_id: str
    company_name: Optional[str] = None
    form_type: Optional[str] = None
    filing_date: Optional[str] = None
    taxonomy: Optional[str] = None
    tool_versions: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_viewer_data(
        cls,
        viewer_data: Mapping[str, Any],
        *,
        accession_number: Optional[str] = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> "BronzeFilingMetadata":
        """Build metadata from viewer payload and optional overrides."""

        overrides = dict(overrides or {})
        meta_block = viewer_data.get("meta") or {}

        entity_cik = overrides.get("entity_cik") or _extract_fact_value(
            viewer_data, ["EntityCentralIndexKey"]
        )
        if not entity_cik:
            entity_cik = meta_block.get("entityCik") or meta_block.get("cik")

        normalized_cik = _safe_normalize_cik(entity_cik)

        accession = (
            overrides.get("accession_number")
            or accession_number
            or meta_block.get("accessionNumber")
            or meta_block.get("accession_number")
            or meta_block.get("accession")
        )
        normalized_accession = _safe_normalize_accession(accession)

        filing_id = overrides.get("filing_id") or _build_filing_id(
            normalized_cik, normalized_accession
        )

        company_name = (
            overrides.get("company_name")
            or meta_block.get("companyName")
            or _extract_fact_value(viewer_data, ["EntityRegistrantName"])
        )
        form_type = (
            overrides.get("form_type")
            or meta_block.get("formType")
            or _extract_fact_value(viewer_data, ["DocumentType"])
        )

        filing_date = (
            overrides.get("filing_date")
            or meta_block.get("filingDate")
            or _extract_fact_value(
                viewer_data,
                [
                    "DocumentFilingDate",
                    "DocumentPeriodEndDate",
                    "DocumentReportDate",
                ],
            )
        )

        taxonomy = overrides.get("taxonomy") or meta_block.get("taxonomy")
        tool_versions = dict(meta_block.get("toolVersions") or {})
        tool_versions.update(overrides.get("tool_versions") or {})

        extra: Dict[str, Any] = dict(overrides.get("extra") or {})

        return cls(
            entity_cik=normalized_cik or "",
            accession_number=normalized_accession or "",
            filing_id=filing_id or "",
            company_name=company_name,
            form_type=form_type,
            filing_date=filing_date,
            taxonomy=taxonomy,
            tool_versions=tool_versions,
            extra=extra,
        )

    def as_dict(self) -> Dict[str, Any]:
        """Serialize metadata to a JSON-friendly dictionary."""
        payload = {
            "filing_id": self.filing_id or None,
            "entity_cik": self.entity_cik or None,
            "accession_number": self.accession_number or None,
            "company_name": self.company_name or None,
            "form_type": self.form_type or None,
            "filing_date": self.filing_date or None,
            "taxonomy": self.taxonomy or None,
        }
        if self.tool_versions:
            payload["tool_versions"] = self.tool_versions
        if self.extra:
            payload["extra"] = self.extra
        return {k: v for k, v in payload.items() if v is not None}


@dataclass(slots=True)
class BronzeWriteResult:
    """Result of writing bronze artifacts to disk."""

    base_path: Path
    viewer_json_path: Path
    metadata_path: Path
    metalinks_path: Optional[Path] = None
    fact_long_path: Optional[Path] = None


class BronzeWriter:
    """Persist viewer payloads and metadata into the bronze layer layout."""

    def __init__(self, base_dir: Path | str = Path("data/bronze")) -> None:
        self.base_dir = Path(base_dir)

    def write(
        self,
        viewer_data: Mapping[str, Any],
        metadata: BronzeFilingMetadata,
        fact_long_df: Optional["pd.DataFrame"] = None,
        *,
        parquet_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> BronzeWriteResult:
        """Write viewer JSON, MetaLinks (if present), and filing metadata."""

        filing_dir = self._ensure_filing_dir(metadata)

        viewer_json_path = filing_dir / "viewer.json"
        metalinks_path: Optional[Path] = None

        payload = dict(viewer_data)
        meta_links = payload.pop("meta_links", None)

        with viewer_json_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        if meta_links:
            metalinks_path = filing_dir / "MetaLinks.json"
            with metalinks_path.open("w", encoding="utf-8") as handle:
                json.dump(meta_links, handle, indent=2)

        metadata_path = filing_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata.as_dict(), handle, indent=2)

        logger.info(
            "Wrote bronze viewer payload", extra={"filing_dir": str(filing_dir)}
        )

        fact_long_path: Optional[Path] = None
        if fact_long_df is not None and not fact_long_df.empty:
            fact_long_path = self._write_fact_long(
                filing_dir, fact_long_df, parquet_kwargs or {}
            )

        return BronzeWriteResult(
            base_path=filing_dir,
            viewer_json_path=viewer_json_path,
            metadata_path=metadata_path,
            metalinks_path=metalinks_path,
            fact_long_path=fact_long_path,
        )

    def _ensure_filing_dir(self, metadata: BronzeFilingMetadata) -> Path:
        cik_part = metadata.entity_cik or "unknown"
        accession_part = _sanitize_for_path(metadata.accession_number) or metadata.filing_id
        target_dir = self.base_dir / cik_part / (accession_part or "unknown")
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _write_fact_long(
        self,
        filing_dir: Path,
        fact_long_df: "pd.DataFrame",
        parquet_kwargs: Mapping[str, Any],
    ) -> Path:
        try:
            import pandas as pd  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pandas is required to persist fact_long parquet outputs"
            ) from exc

        if not isinstance(fact_long_df, pd.DataFrame):
            raise TypeError("fact_long_df must be a pandas DataFrame")

        fact_long_path = filing_dir / "fact_long.parquet"
        try:
            fact_long_df.to_parquet(fact_long_path, index=False, **parquet_kwargs)
        except ImportError as exc:  # pragma: no cover - dependent on optional engine
            raise RuntimeError(
                "pyarrow or fastparquet is required to write fact_long parquet outputs"
            ) from exc
        logger.info("Wrote bronze fact_long table", extra={"path": str(fact_long_path)})
        return fact_long_path


def _extract_fact_value(
    viewer_data: Mapping[str, Any], concept_suffixes: Iterable[str]
) -> Optional[str]:
    suffixes = [suffix.lower() for suffix in concept_suffixes]
    for facts in _iter_fact_containers(viewer_data):
        for entry in facts.values():
            for variant in entry.values():
                if not isinstance(variant, Mapping):
                    continue
                concept = str(variant.get("c") or "").lower()
                if not concept:
                    continue
                if any(concept.endswith(suffix.lower()) for suffix in suffixes):
                    value = variant.get("v")
                    if value is not None:
                        return str(value)
    return None


def _iter_fact_containers(viewer_data: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    top_level = viewer_data.get("facts")
    if isinstance(top_level, Mapping):
        yield top_level

    for source in viewer_data.get("sourceReports", []) or []:
        if not isinstance(source, Mapping):
            continue
        for report in source.get("targetReports", []) or []:
            facts = report.get("facts") if isinstance(report, Mapping) else None
            if isinstance(facts, Mapping):
                yield facts


def _safe_normalize_cik(raw_cik: Optional[str]) -> Optional[str]:
    if not raw_cik:
        return None
    try:
        return normalize_cik(str(raw_cik))
    except ValueError:
        logger.warning("Unable to normalize CIK", extra={"value": raw_cik})
        return str(raw_cik)


def _safe_normalize_accession(raw_accession: Optional[str]) -> Optional[str]:
    if not raw_accession:
        return None
    digits = re.sub(r"\D", "", str(raw_accession))
    if len(digits) == 18:
        return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"
    if len(digits) != 20:
        logger.warning(
            "Unable to normalize accession number", extra={"value": raw_accession}
        )
        return str(raw_accession)
    try:
        return parse_accession_number(str(raw_accession))
    except ValueError:
        logger.warning(
            "Unable to normalize accession number", extra={"value": raw_accession}
        )
        return str(raw_accession)


def _build_filing_id(
    entity_cik: Optional[str], accession_number: Optional[str]
) -> Optional[str]:
    if entity_cik and accession_number:
        accession_clean = re.sub(r"\W", "", accession_number)
        return f"{entity_cik}-{accession_clean}"
    if accession_number:
        return re.sub(r"\W", "", accession_number)
    return entity_cik


def _sanitize_for_path(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", value)
    return safe.strip("._-") or None
