"""Utilities for constructing silver-layer statement tables."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import pandas as pd

from .bronze_writer import BronzeFilingMetadata
from .presentation_models import StatementRow, StatementTable
from .bronze_fact_exporter import (
    _collect_concept_metadata,
    _extract_labels,
    _compute_dimension_hash,
    _is_extension_concept,
    _safe_float,
)


@dataclass
class SilverWriteResult:
    """Paths to persisted silver artifacts for a single filing."""

    base_path: Path
    statement_lines_path: Optional[Path]
    statement_facts_path: Optional[Path]


def build_statement_lines_dataframe(
    statement_tables: Sequence[StatementTable],
    filing_metadata: BronzeFilingMetadata,
    viewer_data: Mapping[str, object],
) -> pd.DataFrame:
    """Flatten presentation rows into the statement_lines schema."""

    records: list[dict] = []
    concept_meta = _collect_concept_metadata(viewer_data)

    for table in statement_tables:
        statement = table.statement
        for line_order, row in enumerate(table.rows, start=1):
            concept_qname = row.node.concept
            concept_info = concept_meta.get(concept_qname, {}) if concept_qname else {}
            label_terse, label_standard = _extract_labels(concept_info)
            if label_standard is None and concept_info:
                label_standard = concept_info.get("l")

            records.append(
                {
                    "filing_id": filing_metadata.filing_id,
                    "entity_cik": filing_metadata.entity_cik,
                    "accession_number": filing_metadata.accession_number,
                    "statement_role_id": statement.role_id,
                    "statement_role_uri": statement.role_uri,
                    "role_name": statement.statement_name,
                    "statement_short_name": statement.get_short_name(),
                    "statement_type": statement.statement_type.value,
                    "metalink_group_type": statement.group_type,
                    "metalink_subgroup_type": statement.sub_group_type,
                    "line_order": line_order,
                    "concept_qname": concept_qname,
                    "label": row.label,
                    "label_terse": label_terse,
                    "label_standard": label_standard,
                    "is_abstract": row.is_abstract,
                    "preferred_label_role": row.node.preferred_label_role,
                    "line_depth": row.depth,
                    "is_extension": _is_extension_concept(concept_qname or ""),
                }
            )

    columns = [
        "filing_id",
        "entity_cik",
        "accession_number",
        "statement_role_id",
        "statement_role_uri",
        "role_name",
        "statement_short_name",
        "statement_type",
        "metalink_group_type",
        "metalink_subgroup_type",
        "line_order",
        "concept_qname",
        "label",
        "label_terse",
        "label_standard",
        "is_abstract",
        "preferred_label_role",
        "line_depth",
        "is_extension",
    ]

    return pd.DataFrame.from_records(records, columns=columns)


def build_statement_facts_dataframe(
    statement_tables: Sequence[StatementTable],
    filing_metadata: BronzeFilingMetadata,
    viewer_data: Mapping[str, object],
) -> pd.DataFrame:
    """Explode statement tables into the statement_facts schema."""

    records: list[dict] = []
    concept_meta = _collect_concept_metadata(viewer_data)

    for table in statement_tables:
        statement = table.statement
        periods_by_label = {period.label: period for period in table.periods}

        for line_order, row in enumerate(table.rows, start=1):
            concept_qname = row.node.concept
            concept_info = concept_meta.get(concept_qname, {}) if concept_qname else {}
            label_terse, label_standard = _extract_labels(concept_info)
            if label_standard is None and concept_info:
                label_standard = concept_info.get("l")

            for period_label, cell in row.cells.items():
                period = periods_by_label.get(period_label)
                if period is None:
                    continue

                context = cell.metadata.get("context") if cell.metadata else None
                if not context:
                    continue

                raw_value = context.get("v")
                if raw_value in (None, "", "—"):
                    continue

                dims: dict[str, str] = cell.metadata.get("dimensions", {}) if cell.metadata else {}
                dimension_hash = _compute_dimension_hash(dims)
                dimension_json = json.dumps(dims, sort_keys=True) if dims else None

                period_raw = context.get("p")
                period_start, period_end = _split_period_bounds(
                    period_raw, fallback_end=period.end_date
                )

                value_numeric = _safe_float(raw_value)
                decimals_hint = context.get("d")
                unit = context.get("u") or context.get("unit") or cell.unit
                entity = context.get("e") or context.get("entity")
                fact_id = context.get("fact_id")

                records.append(
                    {
                        "filing_id": filing_metadata.filing_id,
                        "entity_cik": filing_metadata.entity_cik,
                        "accession_number": filing_metadata.accession_number,
                        "statement_role_id": statement.role_id,
                        "statement_role_uri": statement.role_uri,
                        "role_name": statement.statement_name,
                        "statement_short_name": statement.get_short_name(),
                        "statement_type": statement.statement_type.value,
                        "metalink_group_type": statement.group_type,
                        "metalink_subgroup_type": statement.sub_group_type,
                        "line_order": line_order,
                        "concept_qname": concept_qname,
                        "label": row.label,
                        "label_terse": label_terse,
                        "label_standard": label_standard,
                        "is_abstract": row.is_abstract,
                        "preferred_label_role": row.node.preferred_label_role,
                        "period_label": period.label,
                        "period_end": period_end,
                        "period_start": period_start,
                        "is_instant": period.instant,
                        "value_raw": str(raw_value),
                        "value_numeric": value_numeric,
                        "decimals_hint": decimals_hint,
                        "unit": unit,
                        "entity": entity,
                        "dimension_json": dimension_json,
                        "dimension_hash": dimension_hash,
                        "is_consolidated": not bool(dims),
                        "fact_id": fact_id,
                        "is_extension": _is_extension_concept(concept_qname or ""),
                    }
                )

    columns = [
        "filing_id",
        "entity_cik",
        "accession_number",
        "statement_role_id",
        "statement_role_uri",
        "role_name",
        "statement_short_name",
        "statement_type",
        "metalink_group_type",
        "metalink_subgroup_type",
        "line_order",
        "concept_qname",
        "label",
        "label_terse",
        "label_standard",
        "is_abstract",
        "preferred_label_role",
        "period_label",
        "period_end",
        "period_start",
        "is_instant",
        "value_raw",
        "value_numeric",
        "decimals_hint",
        "unit",
        "entity",
        "dimension_json",
        "dimension_hash",
        "is_consolidated",
        "fact_id",
        "is_extension",
    ]

    return pd.DataFrame.from_records(records, columns=columns)


class SilverWriter:
    """Persist statement_lines and statement_facts outputs."""

    def __init__(self, base_dir: Path | str = Path("data/silver")) -> None:
        self.base_dir = Path(base_dir)

    def write(
        self,
        metadata: BronzeFilingMetadata,
        statement_lines_df: Optional[pd.DataFrame] = None,
        statement_facts_df: Optional[pd.DataFrame] = None,
        *,
        parquet_kwargs: Optional[Mapping[str, object]] = None,
    ) -> SilverWriteResult:
        parquet_kwargs = dict(parquet_kwargs or {})

        filing_dir = self._ensure_filing_dir(metadata)

        lines_path = None
        if statement_lines_df is not None and not statement_lines_df.empty:
            lines_path = filing_dir / "statement_lines.parquet"
            self._write_parquet(statement_lines_df, lines_path, parquet_kwargs)

        facts_path = None
        if statement_facts_df is not None and not statement_facts_df.empty:
            facts_path = filing_dir / "statement_facts.parquet"
            self._write_parquet(statement_facts_df, facts_path, parquet_kwargs)

        return SilverWriteResult(
            base_path=filing_dir,
            statement_lines_path=lines_path,
            statement_facts_path=facts_path,
        )

    def _ensure_filing_dir(self, metadata: BronzeFilingMetadata) -> Path:
        cik_part = _sanitize_path_component(metadata.entity_cik) or "unknown"
        accession_part = (
            _sanitize_path_component(metadata.accession_number)
            or _sanitize_path_component(metadata.filing_id)
            or "unknown"
        )
        target_dir = self.base_dir / cik_part / accession_part
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    @staticmethod
    def _write_parquet(
        df: pd.DataFrame, path: Path, parquet_kwargs: Mapping[str, object]
    ) -> None:
        try:
            df.to_parquet(path, index=False, **parquet_kwargs)
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "pyarrow or fastparquet is required to write silver outputs"
            ) from exc


def _split_period_bounds(
    period_raw: Optional[str], fallback_end: str
) -> tuple[Optional[str], str]:
    if not period_raw or not isinstance(period_raw, str):
        return None, fallback_end

    if "/" in period_raw:
        start, end = period_raw.split("/", 1)
        return (start or None, end or fallback_end)

    return None, period_raw


def _sanitize_path_component(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", value)
    return safe.strip("._-") or None
