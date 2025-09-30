"""Utilities for combining multiple filing results into a single workbook."""

from __future__ import annotations

import difflib
import logging
from collections import defaultdict, OrderedDict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .data_models import Cell, Period, ProcessingResult, Row, Statement, DimensionHierarchy


logger = logging.getLogger(__name__)


class MatchConfidence(Enum):
    """Confidence level for row matching."""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class MatchResult:
    """Result of comparing two rows for alignment."""
    matched: bool
    confidence: MatchConfidence
    score: int
    method: str  # e.g., "xbrl", "hybrid", "label", "fuzzy"


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

    name_token = (statement.name or "").strip().lower()
    if " - " in name_token:
        _, _, tail = name_token.partition(" - ")
        if tail:
            name_token = tail

    if not name_token:
        name_token = (statement.short_name or "").strip().lower()

    return name_token


def _normalise_concept(concept: Optional[str]) -> str:
    """Normalise a concept QName to a namespace-agnostic token."""

    if not concept:
        return ""
    return concept.split(":", 1)[-1].lower()


def _canonical_row_key(row: Row) -> Tuple:
    """Create a canonical identifier for a row used during alignment."""

    presentation_node = getattr(row, "presentation_node", None)
    preferred_role = None
    order = None
    parent_path = None

    if presentation_node is not None:
        preferred_role = getattr(presentation_node, "preferred_label_role", None)
        order = getattr(presentation_node, "order", None)

    parent_path = _parent_path(row)

    concept = (row.concept or "").lower()
    signature = getattr(row, "dimension_signature", None)
    if signature is not None:
        signature = tuple(signature)

    return (
        concept,
        _normalise_concept(row.concept),
        (row.label or "").strip().lower(),
        row.depth,
        row.is_abstract,
        preferred_role,
        order,
        parent_path,
        signature,
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
        dimension_signature=row.dimension_signature,
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


def _label_token(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _fuzzy_label_similarity(label1: Optional[str], label2: Optional[str]) -> float:
    """Calculate similarity between two labels using ratio matching.

    Returns a score between 0.0 (completely different) and 1.0 (identical).
    Uses a simple character-based ratio for now.
    """
    if not label1 or not label2:
        return 0.0

    # Normalize labels
    s1 = _label_token(label1)
    s2 = _label_token(label2)

    if s1 == s2:
        return 1.0

    # Simple ratio: count matching characters in order
    # This is a simplified version - could use difflib.SequenceMatcher for more accuracy
    matches = 0
    total = max(len(s1), len(s2))

    # Count common prefix
    min_len = min(len(s1), len(s2))
    for i in range(min_len):
        if s1[i] == s2[i]:
            matches += 1
        else:
            break

    # Count common suffix (from end)
    i = -1
    while abs(i) <= min_len - matches:
        if s1[i] == s2[i]:
            matches += 1
            i -= 1
        else:
            break

    # Simple Levenshtein-like ratio
    # Better approach: use difflib.SequenceMatcher(None, s1, s2).ratio()
    return matches / total if total > 0 else 0.0


def _normalise_signature(
    signature: Optional[Iterable[Tuple[str, str]]]
) -> Optional[Tuple[Tuple[str, str], ...]]:
    if signature is None:
        return None

    if isinstance(signature, tuple):
        return signature

    try:
        return tuple(signature)
    except TypeError:
        return None


def _parent_path(row: Row) -> Optional[Tuple[str, ...]]:
    presentation_node = getattr(row, "presentation_node", None)
    if presentation_node is None:
        return None

    ancestors = getattr(presentation_node, "_ancestors", None)
    if not ancestors:
        return None

    return tuple(_normalise_concept(node.concept) for node in ancestors)


def _signatures_semantically_compatible(
    anchor_sig: Optional[Tuple[Tuple[str, str], ...]],
    candidate_sig: Optional[Tuple[Tuple[str, str], ...]],
    hierarchy: Optional[DimensionHierarchy],
) -> bool:
    """Check if two dimension signatures are semantically compatible.

    Returns True if:
    - Both are None or empty
    - They are identical
    - One is the parent/ancestor of the other in the dimension hierarchy
    - Multiple children in one signature can roll up to a parent in the other

    Args:
        anchor_sig: Dimension signature from anchor filing
        candidate_sig: Dimension signature from candidate filing
        hierarchy: Dimension hierarchy for semantic lookups

    Returns:
        True if the signatures are compatible for alignment
    """
    if not anchor_sig and not candidate_sig:
        return True

    if anchor_sig == candidate_sig:
        return True

    if not hierarchy:
        return False

    # Both must be present for semantic matching
    if not anchor_sig or not candidate_sig:
        return False

    # Must be on the same axes (keys must match)
    anchor_axes = {axis for axis, _ in anchor_sig}
    candidate_axes = {axis for axis, _ in candidate_sig}
    if anchor_axes != candidate_axes:
        return False

    # Check axis-by-axis if members are semantically related
    for axis in anchor_axes:
        anchor_member = next(member for a, member in anchor_sig if a == axis)
        candidate_member = next(member for a, member in candidate_sig if a == axis)

        if anchor_member == candidate_member:
            continue  # Exact match on this axis

        # Check if one is ancestor of the other
        if hierarchy.is_ancestor(anchor_member, candidate_member):
            logger.debug(
                f"Dimension semantic match: '{candidate_member}' is child of '{anchor_member}' on axis '{axis}'"
            )
            continue
        if hierarchy.is_ancestor(candidate_member, anchor_member):
            logger.debug(
                f"Dimension semantic match: '{anchor_member}' is child of '{candidate_member}' on axis '{axis}'"
            )
            continue

        # No semantic relationship found for this axis
        return False

    return True


def _calculate_match_score(
    anchor: Row,
    candidate: Row,
    hierarchy: Optional[DimensionHierarchy] = None,
) -> MatchResult:
    """Calculate a match score between two rows using multi-factor analysis.

    Phase 2 implementation: returns confidence scores instead of binary yes/no.

    Scoring tiers:
    - HIGH (score >= 150): Exact label, same depth, same parent, dims compatible
    - MEDIUM (score >= 100): Exact label, similar structure (depth ±1)
    - LOW (score >= 80): Fuzzy label, different structure
    - NONE (score < 80): No match

    Args:
        anchor: Row from the anchor filing
        candidate: Row from the candidate filing
        hierarchy: Optional dimension hierarchy for semantic matching

    Returns:
        MatchResult with confidence level and score
    """
    score = 0
    method = "none"

    # Extract normalized attributes
    anchor_label = _label_token(anchor.label)
    candidate_label = _label_token(candidate.label)
    anchor_concept_lower = (anchor.concept or "").lower()
    candidate_concept_lower = (candidate.concept or "").lower()
    anchor_normalised = _normalise_concept(anchor.concept)
    candidate_normalised = _normalise_concept(candidate.concept)
    anchor_signature = _normalise_signature(getattr(anchor, "dimension_signature", None))
    candidate_signature = _normalise_signature(getattr(candidate, "dimension_signature", None))
    anchor_parent_path = _parent_path(anchor)
    candidate_parent_path = _parent_path(candidate)

    # Safety check: revenue/cost conflict is a blocker
    is_revenue_cost_conflict = (
        ("revenue" in anchor_concept_lower and "cost" in candidate_concept_lower)
        or ("cost" in anchor_concept_lower and "revenue" in candidate_concept_lower)
    )
    if is_revenue_cost_conflict:
        return MatchResult(matched=False, confidence=MatchConfidence.NONE, score=0, method="rejected-revenue-cost")

    # Abstract/concrete must match - REQUIREMENT
    if anchor.is_abstract != candidate.is_abstract:
        return MatchResult(matched=False, confidence=MatchConfidence.NONE, score=0, method="rejected-abstract-mismatch")
    else:
        score += 10  # Base score for matching abstract/concrete

    # Label matching - HIGHEST WEIGHT
    if anchor_label and candidate_label:
        if anchor_label == candidate_label:
            score += 100  # Exact label match
            method = "label-exact"
        else:
            # Fuzzy label matching
            similarity = difflib.SequenceMatcher(None, anchor_label, candidate_label).ratio()
            if similarity > 0.9:
                score += 80  # Very similar (typos, formatting)
                method = "label-fuzzy-high"
            elif similarity > 0.7:
                score += 50  # Somewhat similar
                method = "label-fuzzy-medium"

    # Concept matching - SECONDARY
    if anchor_concept_lower and candidate_concept_lower:
        if anchor_concept_lower == candidate_concept_lower:
            score += 50  # Exact concept match
            if method == "none":
                method = "concept-exact"
        elif anchor_normalised == candidate_normalised:
            score += 30  # Normalized concept match
            if method == "none":
                method = "concept-normalized"

    # Structural position - SECONDARY
    if anchor.depth == candidate.depth:
        score += 20  # Same depth
    elif abs(anchor.depth - candidate.depth) == 1:
        score += 10  # Adjacent depth (minor structure drift)

    # Parent context - CRITICAL (must match for high confidence)
    parent_path_matches = False
    if anchor_parent_path and candidate_parent_path:
        if anchor_parent_path == candidate_parent_path:
            score += 30  # Same parent context
            parent_path_matches = True
        else:
            # Different parent paths -> can't be high confidence
            # This prevents matching "Automotive sales" under Revenues with "Automotive sales" under Cost
            pass
    elif not anchor_parent_path and not candidate_parent_path:
        # Both have no parent path (top-level items)
        parent_path_matches = True

    # Dimension compatibility - BONUS, NOT BLOCKER
    dims_compatible = False
    if anchor_signature == candidate_signature:
        score += 20  # Exact dimension match
        dims_compatible = True
    elif hierarchy and anchor_signature and candidate_signature:
        # Check semantic compatibility
        if _signatures_semantically_compatible(anchor_signature, candidate_signature, hierarchy):
            score += 15  # Semantic dimension compatibility
            dims_compatible = True
    elif not anchor_signature and not candidate_signature:
        score += 20  # Both have no dimensions
        dims_compatible = True

    # Determine confidence level based on score
    # IMPORTANT: Parent path must match for HIGH confidence (prevents cross-context matching)
    if score >= 150 and parent_path_matches:
        confidence = MatchConfidence.HIGH
        matched = True
    elif score >= 100:
        confidence = MatchConfidence.MEDIUM
        matched = True
    elif score >= 80:
        confidence = MatchConfidence.LOW
        matched = True
    else:
        confidence = MatchConfidence.NONE
        matched = False

    return MatchResult(matched=matched, confidence=confidence, score=score, method=method)


def _rows_match(
    anchor: Row,
    candidate: Row,
    hierarchy: Optional[DimensionHierarchy] = None,
) -> bool:
    """Determine whether two rows should be considered equivalent.

    This is a wrapper around _calculate_match_score() that maintains backward
    compatibility by returning a boolean. Accepts matches with MEDIUM or HIGH confidence.

    Args:
        anchor: Row from the anchor filing
        candidate: Row from the candidate filing
        hierarchy: Optional dimension hierarchy for semantic matching
    """
    result = _calculate_match_score(anchor, candidate, hierarchy)

    # Log results for automotive rows (debugging)
    is_automotive = (anchor.label and "automotive" in anchor.label.lower())
    if is_automotive or result.confidence != MatchConfidence.NONE:
        if result.matched:
            logger.info(
                f"MATCH [{result.confidence.name}] score={result.score} method={result.method}: "
                f"'{anchor.label}' (concept: {anchor.concept}, depth: {anchor.depth}) ≈ "
                f"'{candidate.label}' (concept: {candidate.concept}, depth: {candidate.depth})"
            )
        elif is_automotive:
            logger.info(
                f"MATCH FAIL score={result.score} method={result.method}: "
                f"'{anchor.label}' vs '{candidate.label}'"
            )

    return result.matched


def _map_rows(
    anchor_rows: Sequence[Row],
    candidate_rows: Sequence[Row],
    hierarchy: Optional[DimensionHierarchy] = None,
) -> Tuple[List[Optional[Row]], List[Row]]:
    """Align candidate rows against the anchor skeleton.

    Args:
        anchor_rows: Rows from the anchor filing
        candidate_rows: Rows from the candidate filing
        hierarchy: Optional dimension hierarchy for semantic matching
    """

    remaining = list(candidate_rows)
    matched: List[Optional[Row]] = []

    for anchor_row in anchor_rows:
        # Debug: log when we're trying to match automotive rows
        is_automotive_anchor = anchor_row.label and "automotive" in anchor_row.label.lower()
        if is_automotive_anchor and "sales" in anchor_row.label.lower():
            logger.info(f"=== Trying to match anchor row: '{anchor_row.label}' ===")
            logger.info(f"    Concept: {anchor_row.concept}")
            logger.info(f"    Sig: {_normalise_signature(getattr(anchor_row, 'dimension_signature', None))}")
            logger.info(f"    Candidates to check: {len(remaining)}")

        match_index: Optional[int] = None
        for idx, candidate in enumerate(remaining):
            if is_automotive_anchor and "sales" in anchor_row.label.lower() and candidate.label and "automotive" in candidate.label.lower():
                logger.info(f"  Checking candidate {idx}: '{candidate.label}'")
            if _rows_match(anchor_row, candidate, hierarchy):
                match_index = idx
                break

        if match_index is None:
            if is_automotive_anchor and "sales" in anchor_row.label.lower():
                logger.info(f"  NO MATCH found for '{anchor_row.label}'")
            matched.append(None)
        else:
            if is_automotive_anchor and "sales" in anchor_row.label.lower():
                matched_label = remaining[match_index].label
                logger.info(f"  MATCHED with candidate: '{matched_label}'")
            matched.append(remaining.pop(match_index))

    leftovers: List[Row] = list(remaining)

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


def _merge_dimension_hierarchies(
    slices: Sequence[FilingSlice],
) -> Optional[DimensionHierarchy]:
    """Merge dimension hierarchies from all filings.

    Args:
        slices: Filing slices to merge hierarchies from

    Returns:
        Combined hierarchy containing all relationships from all filings
    """
    merged = DimensionHierarchy()
    found_any = False

    for slice_item in slices:
        hierarchy = slice_item.result.dimension_hierarchy
        if not hierarchy:
            continue

        found_any = True
        # Merge all relationships
        for parent, children in hierarchy.children.items():
            for child in children:
                merged.add_relationship(parent, child)

    if not found_any:
        logger.debug("No dimension hierarchies found across filings")
        return None

    logger.info(
        f"Merged dimension hierarchies: {len(merged.parents)} members, "
        f"{len(merged.children)} parent nodes"
    )
    return merged


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

    # Merge dimension hierarchies from all filings
    merged_hierarchy = _merge_dimension_hierarchies(sorted_slices)

    combined_warnings: List[str] = []
    for individual in sorted_slices:
        combined_warnings.extend(individual.result.warnings or [])

    ensemble_statements: List[Statement] = []

    for statement_key, anchor_statement in anchor_statement_keys.items():
        aggregated_statement, statement_warnings = _aggregate_statement(
            statement_key, anchor_statement, sorted_slices, merged_hierarchy
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
    merged_hierarchy: Optional[DimensionHierarchy] = None,
) -> Tuple[Statement, List[str]]:
    """Aggregate a single statement across all filings.

    Args:
        statement_key: Canonical key for the statement
        anchor_statement: Statement from the anchor filing
        slices: All filing slices to aggregate
        merged_hierarchy: Merged dimension hierarchy across all filings
    """

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
                anchor_statement.rows, statement.rows, merged_hierarchy
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

    for statement in statements:
        if _canonical_statement_key(statement) == key:
            return statement
    return None


def _fallback_end_date(candidate: datetime) -> str:
    """Fallback formatter for period end dates when data is missing."""

    if candidate is datetime.min:
        return ""
    return candidate.date().isoformat()
