"""
Fact matcher for matching facts to presentation nodes.

This module handles the matching of XBRL facts from viewer JSON to presentation
nodes, creating complete statement tables ready for Excel generation.
"""

import logging
from typing import Dict, List, Optional, Any

from .presentation_models import PresentationStatement, StatementTable, StatementRow
from .data_models import Period, Cell

logger = logging.getLogger(__name__)


class FactMatcher:
    """Match facts to presentation rows to create complete statement tables."""

    def __init__(self, formatter=None):
        """Initialize fact matcher.

        Args:
            formatter: Optional ValueFormatter for formatting cell values
        """
        self.formatter = formatter

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

        # Flatten presentation tree to get all rows in presentation order
        for node, depth in statement.get_all_nodes_flat():
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

    def extract_periods_from_facts(self, facts: dict) -> List[Period]:
        """Extract reporting periods from facts data.

        Args:
            facts: Facts data from viewer JSON

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

        periods = list(periods_dict.values())

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
                    # Add fact_id to the context data for reference
                    context_with_id = context_data.copy()
                    context_with_id['fact_id'] = fact_id
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
        unit = fact.get('u')
        decimals = fact.get('d')
        concept = fact.get('c', '')

        # Apply formatting if formatter is available
        if self.formatter and raw_value is not None:
            try:
                formatted_value = self.formatter.format_cell_value(
                    raw_value, unit, decimals, concept
                )
            except Exception as e:
                logger.warning(f"Error formatting value {raw_value}: {e}")
                formatted_value = str(raw_value)
        else:
            # Basic formatting without formatter
            if raw_value is not None:
                if isinstance(raw_value, (int, float)):
                    # Apply decimals scaling if present
                    if decimals is not None and decimals < 0:
                        # Negative decimals mean divide by 10^abs(decimals)
                        scaled_value = raw_value / (10 ** abs(decimals))
                    else:
                        scaled_value = raw_value

                    # Basic number formatting
                    if scaled_value == int(scaled_value):
                        formatted_value = f"{int(scaled_value):,}"
                    else:
                        formatted_value = f"{scaled_value:,.2f}"
                else:
                    formatted_value = str(raw_value)
            else:
                formatted_value = "—"

        return Cell(
            value=formatted_value,
            raw_value=raw_value,
            unit=unit,
            decimals=decimals,
            period=period.label
        )

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

    def get_statement_summary(self, table: StatementTable) -> Dict[str, Any]:
        """Get summary information about a statement table.

        Args:
            table: StatementTable to summarize

        Returns:
            Dictionary with summary statistics
        """
        total_rows = len(table.rows)
        abstract_rows = len(table.get_abstract_rows())
        data_rows = len(table.get_data_rows())
        rows_with_data = len(table.get_rows_with_data())

        return {
            'statement_name': table.statement.statement_name,
            'statement_type': table.statement.statement_type.value,
            'total_rows': total_rows,
            'abstract_rows': abstract_rows,
            'data_rows': data_rows,
            'rows_with_data': rows_with_data,
            'periods': len(table.periods),
            'period_labels': [p.label for p in table.periods]
        }