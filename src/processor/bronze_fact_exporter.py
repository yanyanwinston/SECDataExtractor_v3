"""Utilities for building bronze-layer fact_long tables."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .bronze_writer import BronzeFilingMetadata, BronzeWriter, BronzeWriteResult
from .presentation_models import StatementTable

logger = logging.getLogger(__name__)


STANDARD_PREFIXES = {
    "us-gaap",
    "dei",
    "ifrs",
    "ifrs-full",
    "srt",
    "invest",
    "country",
    "currency",
    "naics",
}


def build_fact_long_dataframe(
    statement_tables: Sequence[StatementTable],
    filing_metadata: BronzeFilingMetadata,
    viewer_data: Mapping[str, Any],
) -> pd.DataFrame:
    """Construct a bronze fact_long DataFrame from matched statement tables."""

    if not statement_tables:
        raise ValueError("No statement tables available for fact_long export")

    concepts_meta = _collect_concept_metadata(viewer_data)
    records = []

    for table in statement_tables:
        statement = table.statement
        periods_by_label = {period.label: period for period in table.periods}

        for line_order, row in enumerate(table.rows, start=1):
            concept_qname = row.node.concept
            if not concept_qname:
                continue

            dims = row.dimensions or {}
            dimension_hash = row.dimension_hash or _compute_dimension_hash(dims)
            dims_json = json.dumps(dims, sort_keys=True) if dims else None

            concept_info = concepts_meta.get(concept_qname, {})
            label_terse, label_standard = _extract_labels(concept_info)
            concept_balance = _extract_concept_balance(concept_info)
            concept_datatype = _extract_concept_datatype(concept_info)
            has_negated_label = _has_negated_label(concept_info)

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

                value_numeric = _safe_float(raw_value)
                decimals_hint = context.get("d")
                unit = context.get("u") or context.get("unit") or cell.unit
                entity = context.get("e") or context.get("entity")
                fact_id = context.get("fact_id")
                period_raw = context.get("p")
                period_start, period_end = _split_period_bounds(
                    period_raw, fallback_end=period.end_date
                )

                record = {
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
                    "label": row.node.label,
                    "label_terse": label_terse,
                    "label_standard": label_standard,
                    "period_label": period.label,
                    "period_end": period_end,
                    "period_start": period_start,
                    "is_instant": period.instant,
                    "value_raw": str(raw_value),
                    "value_numeric": value_numeric,
                    "decimals_hint": decimals_hint,
                    "unit": unit,
                    "entity": entity,
                    "dimension_json": dims_json,
                    "dimension_hash": dimension_hash,
                    "is_consolidated": not bool(dims),
                    "fact_id": fact_id,
                    "is_extension": _is_extension_concept(concept_qname),
                    "concept_balance": concept_balance,
                    "concept_datatype": concept_datatype,
                    "has_negated_label": has_negated_label,
                }

                records.append(record)

    if not records:
        logger.warning("No fact_long records were produced from statement tables")
        return pd.DataFrame()

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
        "concept_balance",
        "concept_datatype",
        "has_negated_label",
    ]

    df = pd.DataFrame(records)
    return df.reindex(columns=columns)


def export_fact_long(
    parser_tables: Sequence[StatementTable],
    filing_metadata: BronzeFilingMetadata,
    viewer_data: Mapping[str, Any],
    writer: BronzeWriter,
    *,
    parquet_kwargs: Optional[Mapping[str, Any]] = None,
) -> BronzeWriteResult:
    """Build fact_long and persist full bronze artifacts via BronzeWriter."""

    fact_long_df = build_fact_long_dataframe(
        parser_tables, filing_metadata, viewer_data
    )
    return writer.write(
        viewer_data,
        filing_metadata,
        fact_long_df=fact_long_df,
        parquet_kwargs=parquet_kwargs or {},
    )


def _collect_concept_metadata(viewer_data: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    concepts: Dict[str, Dict[str, Any]] = {}

    def merge_concept(name: str, payload: Mapping[str, Any]) -> None:
        existing = concepts.setdefault(name, {})
        for key, value in payload.items():
            if key == "labels" and isinstance(value, Mapping):
                labels = existing.setdefault("labels", {})
                for label_key, label_value in value.items():
                    labels[label_key] = label_value
            else:
                existing.setdefault(key, value)

    top_level = viewer_data.get("concepts")
    if isinstance(top_level, Mapping):
        for concept_name, payload in top_level.items():
            if isinstance(payload, Mapping):
                merge_concept(concept_name, payload)

    for source in viewer_data.get("sourceReports", []) or []:
        if not isinstance(source, Mapping):
            continue
        for report in source.get("targetReports", []) or []:
            concepts_block = report.get("concepts")
            if not isinstance(concepts_block, Mapping):
                continue
            for concept_name, payload in concepts_block.items():
                if isinstance(payload, Mapping):
                    merge_concept(concept_name, payload)

    return concepts


def _extract_labels(concept_info: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    labels = concept_info.get("labels") if isinstance(concept_info, Mapping) else None
    terse = _normalize_label_lookup(labels, "terseLabel")
    standard = _normalize_label_lookup(labels, "label")
    if standard is None:
        standard = concept_info.get("l") if isinstance(concept_info, Mapping) else None
    return terse, standard


def _normalize_label_lookup(labels: Optional[Mapping[str, Any]], key: str) -> Optional[str]:
    if not labels or key not in labels:
        return None
    value = labels[key]
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        # Prefer English entries when available
        for locale in ("en-US", "en-us", "en"):
            if locale in value and isinstance(value[locale], str):
                return value[locale]
        # Otherwise return the first string value
        for candidate in value.values():
            if isinstance(candidate, str):
                return candidate
    return None


def _extract_concept_balance(concept_info: Mapping[str, Any]) -> Optional[str]:
    for key in ("balance", "crdr"):
        value = concept_info.get(key) if isinstance(concept_info, Mapping) else None
        if isinstance(value, str):
            return value.lower()
    return None


def _extract_concept_datatype(concept_info: Mapping[str, Any]) -> Optional[str]:
    for key in ("type", "dataType", "n"):
        value = concept_info.get(key) if isinstance(concept_info, Mapping) else None
        if isinstance(value, str):
            return value
    return None


def _has_negated_label(concept_info: Mapping[str, Any]) -> bool:
    labels = concept_info.get("labels") if isinstance(concept_info, Mapping) else None
    if not isinstance(labels, Mapping):
        return False
    for key in labels.keys():
        if isinstance(key, str) and "negated" in key.lower():
            return True
    return False


def _is_extension_concept(concept_qname: str) -> bool:
    if not concept_qname or ":" not in concept_qname:
        return True
    prefix, _ = concept_qname.split(":", 1)
    return prefix.lower() not in STANDARD_PREFIXES


def _split_period_bounds(
    period_raw: Optional[str], fallback_end: str
) -> Tuple[Optional[str], str]:
    if not period_raw or not isinstance(period_raw, str):
        return None, fallback_end

    if "/" in period_raw:
        start, end = period_raw.split("/", 1)
        return (start or None, end or fallback_end)

    return None, period_raw


def _compute_dimension_hash(dimensions: Mapping[str, str]) -> Optional[str]:
    if not dimensions:
        return None
    serialized = json.dumps(dimensions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "—"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
