"""
Fact matcher for matching facts to presentation nodes.

This module handles the matching of XBRL facts from viewer JSON to presentation
nodes, creating complete statement tables ready for Excel generation.
"""

import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .presentation_models import (
    PresentationNode,
    PresentationStatement,
    StatementRow,
    StatementTable,
)
from .data_models import Period, Cell

logger = logging.getLogger(__name__)


class FactMatcher:
    """Match facts to presentation rows to create complete statement tables."""

    def __init__(
        self,
        formatter=None,
        use_scale_hint: bool = True,
        expand_dimensions: bool = True,
    ):
        """Initialize fact matcher.

        Args:
            formatter: Optional ValueFormatter for formatting cell values
        """
        self.formatter = formatter
        self.use_scale_hint = use_scale_hint
        self.expand_dimensions = expand_dimensions
        self.concept_labels: Dict[str, Dict[str, str]] = {}

    def update_concept_labels(
        self, labels: Optional[Dict[str, Dict[str, str]]]
    ) -> None:
        """Refresh the concept label map supplied by the presentation parser."""
        self.concept_labels = labels or {}

    def match_facts_to_statement(
        self, statement: PresentationStatement, facts: dict, periods: List[Period]
    ) -> StatementTable:
        """Create a complete statement table with facts matched to presentation.

        Args:
            statement: PresentationStatement with hierarchical structure
            facts: Facts data from viewer JSON
            periods: List of reporting periods to include

        Returns:
            Complete StatementTable ready for Excel generation
        """
        logger.debug(f"Matching facts for statement: {statement.statement_name}")

        rows: List[StatementRow] = []

        # Track display depth per structural level so we can collapse axis/table/domain nodes
        display_depth_by_level: Dict[int, int] = {}

        axis_metadata = (
            self._extract_axis_metadata(statement) if self.expand_dimensions else {}
        )
        concept_context_cache: Dict[str, List[dict]] = {}

        # Flatten presentation tree to get all rows in presentation order
        for node, depth in statement.get_all_nodes_flat():
            # Remove deeper levels when walking back up the tree while keeping parent depth metadata
            for level in sorted(list(display_depth_by_level.keys()), reverse=True):
                if level >= depth:
                    del display_depth_by_level[level]

            parent_display_depth = display_depth_by_level.get(depth - 1, -1)

            if self._is_structural_node(node):
                # Propagate parent display depth so descendants keep indentation stable
                display_depth_by_level[depth] = parent_display_depth
                continue

            display_depth = max(parent_display_depth + 1, 0)
            display_depth_by_level[depth] = display_depth

            rows.extend(
                self._generate_rows_for_node(
                    node,
                    display_depth,
                    periods,
                    facts,
                    axis_metadata,
                    concept_context_cache,
                )
            )

        logger.debug(f"Created {len(rows)} rows for statement")

        return StatementTable(statement=statement, periods=periods, rows=rows)

    def _generate_rows_for_node(
        self,
        node: PresentationNode,
        display_depth: int,
        periods: List[Period],
        facts: dict,
        axis_metadata: Dict[str, Dict[str, str]],
        concept_context_cache: Dict[str, List[dict]],
    ) -> List[StatementRow]:
        """Create one or more rows for a presentation node, expanding by dimensions."""

        concept = node.concept or ""

        if not concept:
            clone = self._clone_node(node, depth=display_depth)
            return [
                StatementRow(
                    node=clone,
                    cells=self._build_empty_cells(periods),
                    dimension_signature=None,
                )
            ]

        if not self.expand_dimensions:
            clone = self._clone_node(node, depth=display_depth)
            cells = self._build_cells_without_dimensions(concept, periods, facts)
            return [
                StatementRow(
                    node=clone,
                    cells=cells,
                    dimension_signature=(),
                )
            ]

        fact_groups = self._group_facts_by_dimensions(
            concept,
            facts,
            axis_metadata,
            concept_context_cache,
        )

        if not fact_groups:
            clone = self._clone_node(node, depth=display_depth)
            return [
                StatementRow(
                    node=clone,
                    cells=self._build_empty_cells(periods),
                    dimension_signature=(),
                )
            ]

        # Sort: base row (no dimensions) first, then remaining dimension combinations.
        sorted_keys = sorted(
            fact_groups.keys(),
            key=lambda key: (
                len(key),
                [axis for axis, _ in key],
                [member for _, member in key],
            ),
        )

        generated_rows: List[StatementRow] = []

        for dims_key in sorted_keys:
            group = fact_groups[dims_key]
            dims_map = dict(dims_key)

            if not dims_map:
                row_label = node.label
                row_depth = display_depth
                abstract = node.abstract
            else:
                row_label = self._format_dimension_label(
                    dims_map, axis_metadata, node.label
                )
                row_depth = display_depth + 1
                abstract = False

            clone = self._clone_node(
                node,
                label=row_label,
                depth=row_depth,
                abstract=abstract,
            )

            cells = self._build_cells_for_group(group["contexts"], periods)

            # Skip rows where every cell is blank.
            if all(cell.raw_value is None for cell in cells.values()):
                continue

            dimension_signature = self._derive_dimension_signature(
                group["contexts"], dims_key
            )

            generated_rows.append(
                StatementRow(
                    node=clone,
                    cells=cells,
                    dimension_signature=dimension_signature,
                )
            )

        return generated_rows or [
            StatementRow(
                node=self._clone_node(node, depth=display_depth),
                cells=self._build_empty_cells(periods),
                dimension_signature=(),
            )
        ]

    def _group_facts_by_dimensions(
        self,
        concept: str,
        facts: dict,
        axis_metadata: Dict[str, Dict[str, str]],
        concept_context_cache: Dict[str, List[dict]],
    ) -> Dict[Tuple[Tuple[str, str], ...], Dict[str, Any]]:
        """Group fact contexts by their dimensional fingerprints."""

        contexts = concept_context_cache.get(concept)
        if contexts is None:
            contexts = self._extract_fact_contexts(concept, facts)
            concept_context_cache[concept] = contexts

        groups: Dict[Tuple[Tuple[str, str], ...], Dict[str, Any]] = {}

        for context in contexts:
            dims = context.get("dims", {}) or {}
            filtered_dims = {
                axis: member for axis, member in dims.items() if axis in axis_metadata
            }
            dim_key = tuple(sorted(filtered_dims.items()))
            group = groups.setdefault(dim_key, {"dims": filtered_dims, "contexts": []})
            group["contexts"].append(context)

        return groups

    def _derive_dimension_signature(
        self,
        contexts: List[dict],
        fallback_dims_key: Tuple[Tuple[str, str], ...],
    ) -> Tuple[Tuple[str, str], ...]:
        """Return an unsanitised axis/member signature for the group."""

        if contexts:
            sample = contexts[0]
            dims = sample.get("dims") or {}
            if isinstance(dims, dict):
                signature = tuple(
                    sorted(
                        (
                            self._normalise_dimension_axis(axis),
                            self._normalise_dimension_member(member),
                        )
                        for axis, member in dims.items()
                    )
                )
                if signature:
                    return signature

        return tuple(
            (
                self._normalise_dimension_axis(axis),
                self._normalise_dimension_member(member),
            )
            for axis, member in fallback_dims_key
        )

    @staticmethod
    def _normalise_dimension_axis(axis: str) -> str:
        if not axis:
            return ""
        return axis.split(":", 1)[-1].lower()

    @staticmethod
    def _normalise_dimension_member(member: str) -> str:
        if not member:
            return ""
        return member.split(":", 1)[-1].lower()

    def _extract_fact_contexts(self, concept: str, facts: dict) -> List[dict]:
        """Extract all contexts for a concept, including dimensional metadata."""

        contexts: List[dict] = []

        for fact_id, fact_data in facts.items():
            for context_key, context_data in fact_data.items():
                if not isinstance(context_data, dict):
                    continue

                if context_data.get("c") != concept:
                    continue

                record = dict(context_data)
                record["fact_id"] = fact_id

                for key in ("v", "value", "d", "u", "unit"):
                    if key in fact_data and key not in record:
                        record[key] = fact_data[key]

                record["dims"] = self._extract_dimensions_from_context(context_data)
                contexts.append(record)

        return contexts

    def _extract_dimensions_from_context(self, context: dict) -> Dict[str, str]:
        """Return axis -> member mapping from a context entry."""

        dims: Dict[str, str] = {}

        for container_key in ("dims", "dimValues"):
            container = context.get(container_key)
            if isinstance(container, dict):
                dims.update({k: v for k, v in container.items() if isinstance(v, str)})

        skip_keys = {
            "c",
            "p",
            "u",
            "unit",
            "e",
            "entity",
            "m",
            "fact_id",
            "v",
            "value",
            "d",
            "dims",
            "dimValues",
        }

        for key, value in context.items():
            if key in skip_keys:
                continue
            if isinstance(value, str):
                dims[key] = value

        return dims

    def _build_cells_for_group(
        self,
        contexts: Iterable[dict],
        periods: List[Period],
    ) -> Dict[str, Cell]:
        """Create cells for each period using the provided fact contexts."""

        context_list = list(contexts)
        cells: Dict[str, Cell] = {}

        for period in periods:
            context = self._select_context_for_period(context_list, period)
            if context:
                cell = self._create_cell_from_fact(context, period)
            else:
                cell = Cell(
                    value="—",
                    raw_value=None,
                    unit=None,
                    decimals=None,
                    period=period.label,
                )
            cells[period.label] = cell

        return cells

    def _build_cells_without_dimensions(
        self,
        concept: str,
        periods: List[Period],
        facts: dict,
    ) -> Dict[str, Cell]:
        """Create cells by matching concept/period only (no dimension breakdown)."""

        cells: Dict[str, Cell] = {}

        for period in periods:
            fact = self._find_fact_for_concept_and_period(concept, period, facts)
            if fact:
                cell = self._create_cell_from_fact(fact, period)
            else:
                cell = Cell(
                    value="—",
                    raw_value=None,
                    unit=None,
                    decimals=None,
                    period=period.label,
                )
            cells[period.label] = cell

        return cells

    def _select_context_for_period(
        self,
        contexts: Iterable[dict],
        period: Period,
    ) -> Optional[dict]:
        """Return the first context in the iterable matching the period."""

        for context in contexts:
            if self._period_matches(period, context.get("p")):
                return context
        return None

    def _build_empty_cells(self, periods: List[Period]) -> Dict[str, Cell]:
        """Generate empty cells for the supplied periods."""

        return {
            period.label: Cell(
                value="—",
                raw_value=None,
                unit=None,
                decimals=None,
                period=period.label,
            )
            for period in periods
        }

    @staticmethod
    def _clone_node(
        node: PresentationNode,
        *,
        label: Optional[str] = None,
        depth: Optional[int] = None,
        abstract: Optional[bool] = None,
    ) -> PresentationNode:
        """Create a lightweight clone of a presentation node for row materialisation."""

        return PresentationNode(
            concept=node.concept,
            label=label if label is not None else node.label,
            order=node.order,
            depth=depth if depth is not None else node.depth,
            abstract=abstract if abstract is not None else node.abstract,
            preferred_label_role=node.preferred_label_role,
            children=[],
        )

    def _format_dimension_label(
        self,
        dims: Dict[str, str],
        axis_metadata: Dict[str, Dict[str, str]],
        fallback: str,
    ) -> str:
        """Derive a display label for a dimensional breakdown row."""

        if not dims:
            return fallback

        labels: List[str] = []

        for axis, member in dims.items():
            member_label = axis_metadata.get(axis, {}).get(member)
            if not member_label:
                member_label = self._label_for_concept(member)
            if not member_label:
                member_label = member.split(":", 1)[-1]
            labels.append(self._clean_member_label(member_label))

        if not labels:
            return fallback
        if len(labels) == 1:
            return labels[0]

        return " / ".join(labels)

    def _label_for_concept(self, concept: str) -> Optional[str]:
        """Look up a preferred label for the supplied concept."""

        entries = self.concept_labels.get(concept) or {}
        for key in (
            "ns0",
            "terseLabel",
            "label",
            "std",
            "en-us",
            "en",
        ):
            if key in entries and entries[key]:
                return entries[key]
        return None

    @staticmethod
    def _clean_member_label(label: str) -> str:
        """Remove trailing member suffixes for cleaner display."""

        cleaned = (label or "").strip()
        if cleaned.endswith("[Member]"):
            cleaned = cleaned[: -len("[Member]")].strip()
        return cleaned

    def _extract_axis_metadata(
        self,
        statement: PresentationStatement,
    ) -> Dict[str, Dict[str, str]]:
        """Collect axis/member label mappings for the statement."""

        metadata: Dict[str, Dict[str, str]] = {}

        def traverse(node: PresentationNode, active_axis: Optional[str] = None) -> None:
            concept = node.concept or ""
            local_name = concept.split(":", 1)[-1]

            if local_name.endswith("Axis"):
                active_axis = concept
                metadata.setdefault(concept, {})
            elif local_name.endswith("Member") and active_axis:
                metadata.setdefault(active_axis, {})[concept] = node.label

            for child in node.children:
                traverse(child, active_axis)

        for root in statement.root_nodes:
            traverse(root, None)

        return metadata

    @staticmethod
    def _is_structural_node(node: PresentationNode) -> bool:
        """Return True when the presentation node is purely structural.

        Structural nodes represent tables, axes, domains, or members that the
        HTML viewer exposes only as dimensional filters. They should not become
        standalone rows in the generated workbook.
        """

        concept = node.concept or ""
        if not concept:
            return False

        local_name = concept.split(":", 1)[-1]

        if local_name == "StatementLineItems":
            return True

        structural_suffixes = ("Table", "Axis", "Domain", "Member")
        return any(local_name.endswith(suffix) for suffix in structural_suffixes)

    def extract_periods_from_facts(
        self, facts: dict, concept_filter: Optional[set] = None
    ) -> List[Period]:
        """Extract reporting periods from facts data.

        Args:
            facts: Facts data from viewer JSON
            concept_filter: Optional set of concept names to include

        Returns:
            List of unique periods found in facts
        """
        periods_found = set()

        # Scan through all facts to find periods
        for fact_id, fact_data in facts.items():
            # Each fact can have multiple contexts (a, b, c, etc.)
            for context_key, context_data in fact_data.items():
                if not isinstance(context_data, dict):
                    continue

                concept_name = context_data.get("c")
                if concept_filter and concept_name not in concept_filter:
                    continue

                period = context_data.get("p")
                if period:
                    periods_found.add(period)

        # Convert to Period objects, avoiding duplicates
        periods_dict: Dict[str, Period] = {}
        for period_str in sorted(periods_found):
            # Determine if this is an instant or duration period
            if "/" in period_str:
                # Duration period (start/end)
                start_date, end_date = period_str.split("/")
                key = f"duration_{end_date}"
                if key not in periods_dict:
                    label = self._format_period_label(end_date)
                    # Make duration periods distinctive if there's both instant and duration
                    if f"instant_{end_date}" in [
                        p.end_date + ("_instant" if p.instant else "_duration")
                        for p in periods_dict.values()
                    ]:
                        label = f"{label} (YTD)"
                    periods_dict[key] = Period(
                        label=label, end_date=end_date, instant=False
                    )
            else:
                # Instant period (single date)
                key = f"instant_{period_str}"
                if key not in periods_dict:
                    label = self._format_period_label(period_str)
                    # Make instant periods distinctive if there's both instant and duration
                    duration_key = f"duration_{period_str}"
                    if duration_key in periods_dict:
                        label = f"{label} (As of)"
                    periods_dict[key] = Period(
                        label=label, end_date=period_str, instant=True
                    )

        periods = sorted(periods_dict.values(), key=lambda p: p.end_date, reverse=True)

        logger.info(f"Extracted {len(periods)} periods from facts")
        return periods

    def _find_fact_for_concept_and_period(
        self, concept: str, period: Period, facts: dict
    ) -> Optional[dict]:
        """Find the fact matching concept and period.

        Args:
            concept: XBRL concept name to search for
            period: Period to match
            facts: Facts data from viewer JSON

        Returns:
            Fact data if found, None otherwise
        """
        # Search through compressed facts structure
        for fact_id, fact_data in facts.items():
            # Each fact can have multiple contexts (a, b, c, etc.)
            for context_key, context_data in fact_data.items():
                if not isinstance(context_data, dict):
                    continue

                # Check if concept matches
                if context_data.get("c") != concept:
                    continue

                # Check if period matches
                if self._period_matches(period, context_data.get("p")):
                    # Add fact_id to the context data for reference and enrich with value metadata
                    context_with_id = context_data.copy()
                    context_with_id["fact_id"] = fact_id

                    # Values in the viewer JSON are typically stored at the fact root.
                    # Propagate those onto the returned context so downstream consumers see them.
                    if "v" in fact_data and "v" not in context_with_id:
                        context_with_id["v"] = fact_data["v"]
                    if "value" in fact_data and "value" not in context_with_id:
                        context_with_id["value"] = fact_data["value"]
                    if "d" in fact_data and "d" not in context_with_id:
                        context_with_id["d"] = fact_data["d"]
                    if "u" in fact_data and "u" not in context_with_id:
                        context_with_id["u"] = fact_data["u"]
                    if "unit" in fact_data and "unit" not in context_with_id:
                        context_with_id["unit"] = fact_data["unit"]

                    return context_with_id

        return None

    def _period_matches(self, period: Period, fact_period: Optional[str]) -> bool:
        """Check if period matches fact period.

        Args:
            period: Period object to match
            fact_period: Period string from fact data

        Returns:
            True if periods match
        """
        if not fact_period:
            return False

        if period.instant:
            # For instant periods, match end date exactly
            return fact_period == period.end_date
        else:
            # For duration periods, could be in format "2022-09-25/2023-10-01"
            if "/" in fact_period:
                start_date, end_date = fact_period.split("/")
                return end_date == period.end_date
            else:
                # Single date might represent end of period for duration
                return fact_period == period.end_date

    def _create_cell_from_fact(self, fact: dict, period: Period) -> Cell:
        """Create a Cell from fact data.

        Args:
            fact: Fact data with value, unit, decimals, etc.
            period: Period this fact represents

        Returns:
            Cell object with formatted value
        """
        raw_value = fact.get("v")
        numeric_value: Optional[float] = None
        if raw_value is not None:
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                numeric_value = None

        unit = fact.get("u") or fact.get("unit")
        decimals = fact.get("d")
        concept = fact.get("c", "")

        decimals_value = self._coerce_decimals(decimals)

        scaled_numeric = numeric_value
        scale_applied = False
        if (
            self.use_scale_hint
            and numeric_value is not None
            and decimals_value is not None
            and decimals_value < 0
        ):
            try:
                scaled_numeric = numeric_value * (10**decimals_value)
                scale_applied = True
            except (TypeError, ValueError, OverflowError):
                scaled_numeric = numeric_value
                scale_applied = False

        # Apply formatting if formatter is available
        if self.formatter and scaled_numeric is not None:
            try:
                formatter_decimals: Optional[int]
                if decimals_value is not None and decimals_value >= 0:
                    formatter_decimals = decimals_value
                else:
                    formatter_decimals = None

                formatted_value = self._format_with_scale_control(
                    scaled_numeric, unit, formatter_decimals, concept, scale_applied
                )
            except Exception as e:
                logger.warning(f"Error formatting value {raw_value}: {e}")
                formatted_value = str(scaled_numeric)
        else:
            # Basic formatting without formatter
            if scaled_numeric is not None:
                if isinstance(scaled_numeric, (int, float)):
                    if scaled_numeric == int(scaled_numeric):
                        formatted_value = f"{int(scaled_numeric):,}"
                    else:
                        formatted_value = f"{scaled_numeric:,.2f}"
                else:
                    formatted_value = str(scaled_numeric)
            else:
                formatted_value = "—"

        return Cell(
            value=formatted_value,
            raw_value=scaled_numeric if scaled_numeric is not None else raw_value,
            unit=unit,
            decimals=decimals,
            period=period.label,
        )

    def _format_with_scale_control(
        self,
        value: float,
        unit: Optional[str],
        decimals: Optional[int],
        concept: str,
        scale_applied: bool,
    ) -> str:
        """Format a numeric value while preventing double scaling when hints are applied."""
        if not self.use_scale_hint or not getattr(
            self.formatter, "scale_millions", False
        ):
            return self.formatter.format_cell_value(value, unit, decimals, concept)

        if not scale_applied:
            return self.formatter.format_cell_value(value, unit, decimals, concept)

        original_scale = self.formatter.scale_millions
        try:
            self.formatter.scale_millions = False
            return self.formatter.format_cell_value(value, unit, decimals, concept)
        finally:
            self.formatter.scale_millions = original_scale

    @staticmethod
    def _coerce_decimals(decimals: Any) -> Optional[int]:
        """Convert XBRL decimals metadata into an integer when possible."""
        if isinstance(decimals, bool):  # bool is a subclass of int
            return int(decimals)

        if isinstance(decimals, (int, float)):
            if isinstance(decimals, float) and (
                math.isnan(decimals) or math.isinf(decimals)
            ):
                return None
            return int(decimals)

        if isinstance(decimals, str):
            try:
                return int(decimals)
            except ValueError:
                return None

        return None

    def _format_period_label(self, date_str: str) -> str:
        """Format period date string for display.

        Args:
            date_str: Date string (e.g., "2023-12-31")

        Returns:
            Formatted label (e.g., "2023" or "Dec 31, 2023")
        """
        try:
            from datetime import datetime

            date_obj = datetime.strptime(date_str, "%Y-%m-%d")

            # For year-end dates, just show year
            if date_obj.month == 12 and date_obj.day == 31:
                return str(date_obj.year)
            else:
                return date_obj.strftime("%b %d, %Y")

        except Exception:
            # Fallback to original string if parsing fails
            return date_str
