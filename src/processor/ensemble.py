"""Utilities for combining multiple filing results into a single workbook."""

from __future__ import annotations

import logging
from collections import defaultdict, OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .data_models import Cell, Period, ProcessingResult, Row, Statement


logger = logging.getLogger(__name__)


def _safe_parse_date(value: Optional[str]) -> datetime:
    """Parse a filing date string into a datetime for sorting purposes."""

    if not value:
        return datetime.min

    candidate = value.strip()

    if not candidate:
        return datetime.min

    if "T" in candidate:
        candidate = candidate.split("T", 1)[0]

    if len(candidate) > 10:
        candidate = candidate[:10]

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue

    logger.debug("Could not parse filing_date '%s'; defaulting to datetime.min", value)
    return datetime.min


def _canonical_statement_key(statement: Statement) -> str:
    """Build a lookup key for a statement consistent across filings."""

    return (statement.short_name or statement.name or "").strip().lower()


def _canonical_row_key(row: Row) -> Tuple:
    """Create a canonical identifier for a row used during alignment."""

    presentation_node = getattr(row, "presentation_node", None)
    preferred_role = None
    order = None

    if presentation_node is not None:
        preferred_role = getattr(presentation_node, "preferred_label_role", None)
        order = getattr(presentation_node, "order", None)

    return (
        (row.concept or "").lower(),
        (row.label or "").strip().lower(),
        row.depth,
        row.is_abstract,
        preferred_role,
        order,
    )


def _clone_row_structure(row: Row) -> Row:
    """Create a shallow clone of the row structure without cells."""

    return Row(
        label=row.label,
        concept=row.concept,
        is_abstract=row.is_abstract,
        depth=row.depth,
        cells={},
        presentation_node=getattr(row, "presentation_node", None),
    )


def _clone_cell(cell: Optional[Cell], period_label: str) -> Optional[Cell]:
    """Clone a cell so ensemble output does not mutate source results."""

    if cell is None:
        return None

    return Cell(
        value=cell.value,
        raw_value=cell.raw_value,
        unit=cell.unit,
        decimals=cell.decimals,
        period=period_label,
    )


def _map_rows(
    anchor_rows: Sequence[Row],
    candidate_rows: Sequence[Row],
) -> Tuple[List[Optional[Row]], List[Row]]:
    """Align candidate rows against the anchor skeleton."""

    bucket: Dict[Tuple, List[Row]] = defaultdict(list)

    for row in candidate_rows:
        bucket[_canonical_row_key(row)].append(row)

    matched: List[Optional[Row]] = []

    for anchor_row in anchor_rows:
        key = _canonical_row_key(anchor_row)
        rows = bucket.get(key)
        if rows:
            matched.append(rows.pop(0))
        else:
            matched.append(None)

    leftovers: List[Row] = []
    for remaining in bucket.values():
        leftovers.extend(remaining)

    return matched, leftovers


@dataclass
class FilingSlice:
    """Wrapper tying a processing result to metadata used during ensemble."""

    source: str
    result: ProcessingResult
    filing_date: datetime

    @classmethod
    def from_processing_result(cls, source: str, result: ProcessingResult) -> "FilingSlice":
        return cls(source=source, result=result, filing_date=_safe_parse_date(result.filing_date))


def build_ensemble_result(slices: Iterable[FilingSlice]) -> ProcessingResult:
    """Combine multiple single-filing results into one multi-period workbook."""

    slices = list(slices)
    if not slices:
        raise ValueError("At least one filing slice is required for ensemble output")

    sorted_slices = sorted(slices, key=lambda item: item.filing_date, reverse=True)
    anchor_slice = sorted_slices[0]
    anchor_result = anchor_slice.result

    anchor_statement_keys = {
        _canonical_statement_key(statement): statement for statement in anchor_result.statements
    }

    combined_warnings: List[str] = []
    for individual in sorted_slices:
        combined_warnings.extend(individual.result.warnings or [])

    ensemble_statements: List[Statement] = []

    for statement_key, anchor_statement in anchor_statement_keys.items():
        aggregated_statement, statement_warnings = _aggregate_statement(
            statement_key, anchor_statement, sorted_slices
        )
        ensemble_statements.append(aggregated_statement)
        combined_warnings.extend(statement_warnings)

    # Detect statements present in non-anchor filings but missing from the anchor set
    anchor_keys = set(anchor_statement_keys.keys())
    for slice_item in sorted_slices[1:]:
        for other_statement in slice_item.result.statements:
            key = _canonical_statement_key(other_statement)
            if key and key not in anchor_keys:
                combined_warnings.append(
                    f"Statement '{other_statement.name}' present in {slice_item.source} but not in anchor filing; skipped"
                )

    # Ensure warnings are unique while preserving order
    deduped_warnings: List[str] = []
    seen = set()
    for warning in combined_warnings:
        if warning and warning not in seen:
            deduped_warnings.append(warning)
            seen.add(warning)

    return ProcessingResult(
        statements=ensemble_statements,
        company_name=anchor_result.company_name,
        filing_date=anchor_result.filing_date,
        form_type=anchor_result.form_type,
        success=True,
        warnings=deduped_warnings,
    )


def _aggregate_statement(
    statement_key: str,
    anchor_statement: Statement,
    slices: Sequence[FilingSlice],
) -> Tuple[Statement, List[str]]:
    """Aggregate a single statement across all filings."""

    aggregated_rows: List[Row] = [_clone_row_structure(row) for row in anchor_statement.rows]
    extra_rows: "OrderedDict[Tuple, Row]" = OrderedDict()

    aggregated_periods: List[Period] = []
    warnings: List[str] = []

    anchor_primary_period = anchor_statement.periods[0] if anchor_statement.periods else None
    default_label = anchor_primary_period.label if anchor_primary_period else ""
    default_end = anchor_primary_period.end_date if anchor_primary_period else ""
    default_instant = anchor_primary_period.instant if anchor_primary_period else False

    for slice_item in slices:
        statement = _find_statement(slice_item.result.statements, statement_key)

        if statement and statement.periods:
            primary_period = statement.periods[0]
        else:
            if slice_item is slices[0]:  # anchor slice missing data (already handled)
                warnings.append(
                    f"Anchor filing missing periods for statement '{anchor_statement.name}'"
                )
            else:
                warnings.append(
                    f"Statement '{anchor_statement.name}' missing in {slice_item.source}; column populated with blanks"
                )
            primary_period = Period(
                label=slice_item.result.filing_date or default_label or slice_item.source,
                end_date=default_end or _fallback_end_date(slice_item.filing_date),
                instant=default_instant,
            )

        aggregated_periods.append(
            Period(
                label=primary_period.label,
                end_date=primary_period.end_date,
                instant=primary_period.instant,
            )
        )

        if statement and statement.periods:
            matched_rows, additional_rows = _map_rows(
                anchor_statement.rows, statement.rows
            )
        else:
            matched_rows = [None] * len(anchor_statement.rows)
            additional_rows = []

        _populate_matched_rows(
            aggregated_rows,
            matched_rows,
            primary_period.label,
        )

        _populate_additional_rows(
            extra_rows,
            additional_rows,
            primary_period.label,
        )

    aggregated_rows.extend(extra_rows.values())

    return (
        Statement(
            name=anchor_statement.name,
            short_name=anchor_statement.short_name,
            periods=aggregated_periods,
            rows=aggregated_rows,
        ),
        warnings,
    )


def _populate_matched_rows(
    aggregated_rows: Sequence[Row],
    matched_rows: Sequence[Optional[Row]],
    period_label: str,
) -> None:
    """Populate ensemble cells for rows that exist in the anchor skeleton."""

    for target_row, source_row in zip(aggregated_rows, matched_rows):
        if source_row is None:
            continue

        cell = _extract_cell(source_row, period_label)
        if cell is not None:
            target_row.cells[period_label] = cell


def _populate_additional_rows(
    extra_rows: "OrderedDict[Tuple, Row]",
    additional_rows: Sequence[Row],
    period_label: str,
) -> None:
    """Append and populate rows that do not exist in the anchor statement."""

    for source_row in additional_rows:
        key = _canonical_row_key(source_row)
        if key not in extra_rows:
            cloned = _clone_row_structure(source_row)
            extra_rows[key] = cloned
        target_row = extra_rows[key]

        cell = _extract_cell(source_row, period_label)
        if cell is not None:
            target_row.cells[period_label] = cell


def _extract_cell(row: Row, period_label: str) -> Optional[Cell]:
    """Extract and clone the cell for the requested period."""

    cell = row.cells.get(period_label)
    if cell is None:
        return None

    return _clone_cell(cell, period_label)


def _find_statement(statements: Sequence[Statement], key: str) -> Optional[Statement]:
    """Locate a statement matching the given key."""

    key = key.strip().lower()
    for statement in statements:
        candidate_key = _canonical_statement_key(statement)
        if candidate_key == key:
            return statement
    return None


def _fallback_end_date(candidate: datetime) -> str:
    """Fallback formatter for period end dates when data is missing."""

    if candidate is datetime.min:
        return ""
    return candidate.date().isoformat()
