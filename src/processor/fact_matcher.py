"""
Fact matcher for matching facts to presentation nodes.

This module handles the matching of XBRL facts from viewer JSON to presentation
nodes, creating complete statement tables ready for Excel generation.
"""

import logging
import math
from typing import Any, Dict, List, Optional

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

    def __init__(self, formatter=None, use_scale_hint: bool = True):
        """Initialize fact matcher.

        Args:
            formatter: Optional ValueFormatter for formatting cell values
        """
        self.formatter = formatter
        self.use_scale_hint = use_scale_hint

    def match_facts_to_statement(self, statement: PresentationStatement,
                                facts: dict, periods: List[Period]) -> StatementTable:
        """Create a complete statement table with facts matched to presentation.

        Args:
            statement: PresentationStatement with hierarchical structure
            facts: Facts data from viewer JSON
            periods: List of reporting periods to include

        Returns:
            Complete StatementTable ready for Excel generation
        """
        logger.debug(f"Matching facts for statement: {statement.statement_name}")

        rows = []

        # Track display depth per structural level so we can collapse axis/table/domain nodes
        display_depth_by_level: Dict[int, int] = {}

        # Flatten presentation tree to get all rows in presentation order
        for node, depth in statement.get_all_nodes_flat():
            # Remove deeper levels when walking back up the tree
            for level in list(display_depth_by_level.keys()):
                if level >= depth:
                    del display_depth_by_level[level]

            parent_display_depth = display_depth_by_level.get(depth - 1, -1)

            if self._is_structural_node(node):
                # Propagate parent display depth so descendants keep indentation stable
                display_depth_by_level[depth] = parent_display_depth
                continue

            display_depth = max(parent_display_depth + 1, 0)
            node.depth = display_depth
            display_depth_by_level[depth] = display_depth

            # Find facts for this concept across all periods
            cells = {}

            for period in periods:
                fact = self._find_fact_for_concept_and_period(
                    node.concept, period, facts
                )

                if fact:
                    cell = self._create_cell_from_fact(fact, period)
                else:
                    # Create empty cell for missing data
                    cell = Cell(
                        value="—",
                        raw_value=None,
                        unit=None,
                        decimals=None,
                        period=period.label
                    )

                cells[period.label] = cell

            rows.append(StatementRow(node=node, cells=cells))

        logger.debug(f"Created {len(rows)} rows for statement")

        return StatementTable(
            statement=statement,
            periods=periods,
            rows=rows
        )

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

        local_name = concept.split(':', 1)[-1]

        if local_name == "StatementLineItems":
            return True

        structural_suffixes = ("Table", "Axis", "Domain", "Member")
        return any(local_name.endswith(suffix) for suffix in structural_suffixes)

    def extract_periods_from_facts(
        self,
        facts: dict,
        concept_filter: Optional[set] = None
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

                concept_name = context_data.get('c')
                if concept_filter and concept_name not in concept_filter:
                    continue

                period = context_data.get('p')
                if period:
                    periods_found.add(period)

        # Convert to Period objects, avoiding duplicates
        periods_dict = {}
        for period_str in sorted(periods_found):
            # Determine if this is an instant or duration period
            if '/' in period_str:
                # Duration period (start/end)
                start_date, end_date = period_str.split('/')
                key = f"duration_{end_date}"
                if key not in periods_dict:
                    label = self._format_period_label(end_date)
                    # Make duration periods distinctive if there's both instant and duration
                    if f"instant_{end_date}" in [p.end_date + ("_instant" if p.instant else "_duration") for p in periods_dict.values()]:
                        label = f"{label} (YTD)"
                    periods_dict[key] = Period(
                        label=label,
                        end_date=end_date,
                        instant=False
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
                        label=label,
                        end_date=period_str,
                        instant=True
                    )

        periods = sorted(
            periods_dict.values(),
            key=lambda p: p.end_date,
            reverse=True
        )

        logger.info(f"Extracted {len(periods)} periods from facts")
        return periods

    def _find_fact_for_concept_and_period(self, concept: str,
                                         period: Period, facts: dict) -> Optional[dict]:
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
                if context_data.get('c') != concept:
                    continue

                # Check if period matches
                if self._period_matches(period, context_data.get('p')):
                    # Add fact_id to the context data for reference and enrich with value metadata
                    context_with_id = context_data.copy()
                    context_with_id['fact_id'] = fact_id

                    # Values in the viewer JSON are typically stored at the fact root.
                    # Propagate those onto the returned context so downstream consumers see them.
                    if 'v' in fact_data and 'v' not in context_with_id:
                        context_with_id['v'] = fact_data['v']
                    if 'value' in fact_data and 'value' not in context_with_id:
                        context_with_id['value'] = fact_data['value']
                    if 'd' in fact_data and 'd' not in context_with_id:
                        context_with_id['d'] = fact_data['d']
                    if 'u' in fact_data and 'u' not in context_with_id:
                        context_with_id['u'] = fact_data['u']
                    if 'unit' in fact_data and 'unit' not in context_with_id:
                        context_with_id['unit'] = fact_data['unit']

                    return context_with_id

        return None

    def _period_matches(self, period: Period, fact_period: str) -> bool:
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
            if '/' in fact_period:
                start_date, end_date = fact_period.split('/')
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
        raw_value = fact.get('v')
        numeric_value: Optional[float] = None
        if raw_value is not None:
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                numeric_value = None

        unit = fact.get('u') or fact.get('unit')
        decimals = fact.get('d')
        concept = fact.get('c', '')

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
                scaled_numeric = numeric_value * (10 ** decimals_value)
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
                    scaled_numeric,
                    unit,
                    formatter_decimals,
                    concept,
                    scale_applied
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
            period=period.label
        )

    def _format_with_scale_control(
        self,
        value: float,
        unit: Optional[str],
        decimals: Optional[int],
        concept: str,
        scale_applied: bool
    ) -> str:
        """Format a numeric value while preventing double scaling when hints are applied."""
        if not self.use_scale_hint or not getattr(self.formatter, 'scale_millions', False):
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
            if isinstance(decimals, float) and (math.isnan(decimals) or math.isinf(decimals)):
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
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')

            # For year-end dates, just show year
            if date_obj.month == 12 and date_obj.day == 31:
                return str(date_obj.year)
            else:
                return date_obj.strftime('%b %d, %Y')

        except Exception:
            # Fallback to original string if parsing fails
            return date_str
