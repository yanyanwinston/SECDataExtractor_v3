"""
Data parser for converting viewer JSON to structured data models.
"""

import logging
from typing import Dict, Any, List, Optional

from .data_models import Statement, Period, Row, Cell, ProcessingResult
from .value_formatter import ValueFormatter


logger = logging.getLogger(__name__)


class DataParser:
    """Parser for converting iXBRL viewer JSON to structured data models."""

    def __init__(self, formatter: Optional[ValueFormatter] = None):
        """
        Initialize data parser.

        Args:
            formatter: Value formatter for display formatting
        """
        self.formatter = formatter or ValueFormatter()

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        """
        Parse viewer JSON data into structured models.

        Args:
            viewer_data: JSON data from iXBRL viewer

        Returns:
            Processing result with parsed statements
        """
        try:
            # Extract basic metadata
            company_name = self._extract_company_name(viewer_data)
            filing_date = self._extract_filing_date(viewer_data)
            form_type = self._extract_form_type(viewer_data)

            # Parse statements
            statements = self._parse_statements(viewer_data)

            return ProcessingResult(
                statements=statements,
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
                success=True
            )

        except Exception as e:
            logger.error(f"Error parsing viewer data: {e}")
            return ProcessingResult(
                statements=[],
                company_name="",
                filing_date="",
                form_type="",
                success=False,
                error=str(e)
            )

    def _extract_company_name(self, data: Dict[str, Any]) -> str:
        """Extract company name from viewer data."""
        company_name = ""

        # Handle new sourceReports format
        if 'sourceReports' in data:
            source_reports = data['sourceReports']
            if isinstance(source_reports, list) and len(source_reports) > 0:
                first_report = source_reports[0]
                if 'targetReports' in first_report:
                    target_reports = first_report['targetReports']
                    if isinstance(target_reports, list) and len(target_reports) > 0:
                        target_report = target_reports[0]
                        facts = target_report.get('facts', {})
                        concepts = target_report.get('concepts', {})

                        # Look for entity name in facts
                        for fact_data in facts.values():
                            for concept_name in fact_data.keys():
                                if 'entityregistrantname' in concept_name.lower():
                                    company_name = fact_data[concept_name].get('v', '')
                                    if company_name:
                                        break
                            if company_name:
                                break

        # Check facts for company name concept (older format)
        if not company_name:
            facts = data.get('facts', {})
            for fact_id, fact_data in facts.items():
                concept = fact_data.get('c', '')
                if 'entityregistrantname' in concept.lower():
                    company_name = fact_data.get('v', '')
                    break

        # Fallback to other metadata fields
        if not company_name:
            metadata = data.get('meta', {})
            company_name = metadata.get('entityName', metadata.get('companyName', 'Unknown Company'))

        return str(company_name) if company_name else "Unknown Company"

    def _extract_filing_date(self, data: Dict[str, Any]) -> str:
        """Extract filing date from viewer data."""
        # Look for document date or filing date concepts
        facts = data.get('facts', {})
        for fact_id, fact_data in facts.items():
            concept = fact_data.get('c', '')
            if any(term in concept.lower() for term in ['documentdate', 'filingdate', 'periodenddate']):
                return fact_data.get('v', '')

        # Fallback
        return data.get('meta', {}).get('filingDate', 'Unknown Date')

    def _extract_form_type(self, data: Dict[str, Any]) -> str:
        """Extract form type from viewer data."""
        # Look for document type concept
        facts = data.get('facts', {})
        for fact_id, fact_data in facts.items():
            concept = fact_data.get('c', '')
            if 'documenttype' in concept.lower():
                return fact_data.get('v', '')

        # Fallback
        return data.get('meta', {}).get('formType', 'Unknown Form')

    def _parse_statements(self, data: Dict[str, Any]) -> List[Statement]:
        """Parse financial statements from viewer data."""
        statements = []

        # Get role-based statements (common structure for iXBRL viewers)
        roles = data.get('roles', {})

        for role_id, role_data in roles.items():
            statement = self._parse_single_statement(role_id, role_data, data)
            if statement and statement.rows:
                statements.append(statement)

        # If no role-based statements found, try alternative structures
        if not statements:
            logger.warning("No role-based statements found, trying alternative parsing")
            statements = self._parse_alternative_structure(data)

        return statements

    def _parse_single_statement(self, role_id: str, role_data: Dict[str, Any],
                               full_data: Dict[str, Any]) -> Optional[Statement]:
        """Parse a single financial statement from role data."""
        try:
            # Get statement name
            statement_name = self._clean_statement_name(role_data.get('definition', role_id))
            short_name = self._get_short_name(statement_name)

            # Skip if not a financial statement
            if not self._is_financial_statement(statement_name):
                return None

            # Parse periods
            periods = self._extract_periods(role_data, full_data)
            if not periods:
                logger.warning(f"No periods found for statement: {statement_name}")
                return None

            # Parse rows
            rows = self._parse_statement_rows(role_data, full_data, periods)
            if not rows:
                logger.warning(f"No rows found for statement: {statement_name}")
                return None

            return Statement(
                name=statement_name,
                short_name=short_name,
                periods=periods,
                rows=rows
            )

        except Exception as e:
            logger.error(f"Error parsing statement {role_id}: {e}")
            return None

    def _clean_statement_name(self, name: str) -> str:
        """Clean up statement name."""
        if not name:
            return "Unknown Statement"

        # Remove common prefixes/suffixes
        name = name.replace('CONSOLIDATED', '').replace('CONDENSED', '')
        name = name.replace('STATEMENTS OF', '').replace('STATEMENT OF', '')

        # Clean up whitespace
        return ' '.join(name.split()).title()

    def _get_short_name(self, full_name: str) -> str:
        """Get short name for sheet tabs."""
        name_lower = full_name.lower()

        if 'balance' in name_lower or 'position' in name_lower:
            return "Balance Sheet"
        elif any(term in name_lower for term in ['income', 'operations', 'comprehensive']):
            return "Income Statement"
        elif 'cash' in name_lower and 'flow' in name_lower:
            return "Cash Flows"
        elif 'equity' in name_lower or 'stockholder' in name_lower:
            return "Equity"
        else:
            return full_name[:20]  # Truncate long names

    def _is_financial_statement(self, name: str) -> bool:
        """Check if this looks like a financial statement."""
        name_lower = name.lower()
        statement_keywords = [
            'balance', 'income', 'cash flow', 'equity', 'position',
            'operations', 'comprehensive', 'statement'
        ]

        return any(keyword in name_lower for keyword in statement_keywords)

    def _extract_periods(self, role_data: Dict[str, Any],
                        full_data: Dict[str, Any]) -> List[Period]:
        """Extract periods from statement data."""
        periods = []

        # Try to get periods from role data or full data
        contexts = full_data.get('contexts', {})

        # Collect unique periods
        period_map = {}

        for context_id, context_data in contexts.items():
            period_info = context_data.get('period', {})

            if 'instant' in period_info:
                date = period_info['instant']
                period_map[date] = Period(label=date, end_date=date, instant=True)
            elif 'startDate' in period_info and 'endDate' in period_info:
                start_date = period_info['startDate']
                end_date = period_info['endDate']
                label = f"{start_date} to {end_date}"
                period_map[end_date] = Period(label=label, end_date=end_date, instant=False)

        # Sort periods by date (most recent first)
        periods = list(period_map.values())
        periods.sort(key=lambda p: p.end_date, reverse=True)

        return periods

    def _parse_statement_rows(self, role_data: Dict[str, Any], full_data: Dict[str, Any],
                            periods: List[Period]) -> List[Row]:
        """Parse rows for a statement."""
        rows = []
        facts = full_data.get('facts', {})
        concepts = full_data.get('concepts', {})

        # Get presentation order from role
        presentation = role_data.get('presentation', [])

        for item in presentation:
            concept_id = item.get('concept', '')
            if not concept_id:
                continue

            concept_info = concepts.get(concept_id, {})
            label = concept_info.get('label', concept_id)
            is_abstract = concept_info.get('abstract', False)

            # Build cells for this row
            cells = {}

            for period in periods:
                # Find fact for this concept and period
                cell_value = self._find_fact_value(concept_id, period, facts, full_data)
                cells[period.label] = cell_value

            row = Row(
                label=self.formatter.clean_label(label),
                concept=concept_id,
                is_abstract=is_abstract,
                depth=item.get('depth', 0),
                cells=cells
            )

            rows.append(row)

        return rows

    def _find_fact_value(self, concept: str, period: Period, facts: Dict[str, Any],
                        full_data: Dict[str, Any]) -> Cell:
        """Find fact value for a specific concept and period."""
        # Search through facts for matching concept and period
        for fact_id, fact_data in facts.items():
            if fact_data.get('c') == concept:
                # Check if period matches
                context_id = fact_data.get('context')
                context = full_data.get('contexts', {}).get(context_id, {})

                if self._period_matches(period, context):
                    raw_value = fact_data.get('v')
                    unit = fact_data.get('u')
                    decimals = fact_data.get('d')

                    # Format value
                    formatted_value = self.formatter.format_cell_value(
                        raw_value, unit, decimals, concept
                    )

                    return Cell(
                        value=formatted_value,
                        raw_value=raw_value,
                        unit=unit,
                        decimals=decimals,
                        period=period.label
                    )

        # Return empty cell if no fact found
        return Cell(
            value="—",
            raw_value=None,
            unit=None,
            decimals=None,
            period=period.label
        )

    def _period_matches(self, period: Period, context: Dict[str, Any]) -> bool:
        """Check if period matches context."""
        context_period = context.get('period', {})

        if period.instant and 'instant' in context_period:
            return context_period['instant'] == period.end_date
        elif not period.instant and 'endDate' in context_period:
            return context_period['endDate'] == period.end_date

        return False

    def _parse_alternative_structure(self, data: Dict[str, Any]) -> List[Statement]:
        """Fallback parsing for alternative data structures."""
        logger.info("Attempting alternative parsing structure")

        # This is a simplified fallback - in practice, you'd need to handle
        # various possible structures based on different iXBRL viewer formats
        statements = []

        # Try to create a single statement with all available facts
        facts = data.get('facts', {})
        if facts:
            # Create a generic statement
            statement = self._create_generic_statement(data)
            if statement:
                statements.append(statement)

        return statements

    def _create_generic_statement(self, data: Dict[str, Any]) -> Optional[Statement]:
        """Create a generic statement from all available facts."""
        try:
            # Extract periods
            periods = self._extract_periods({}, data)
            if not periods:
                return None

            # Create rows from all facts
            facts = data.get('facts', {})
            concepts = data.get('concepts', {})
            rows = []

            for concept_id, concept_info in concepts.items():
                label = concept_info.get('label', concept_id)
                is_abstract = concept_info.get('abstract', False)

                # Build cells
                cells = {}
                for period in periods:
                    cell_value = self._find_fact_value(concept_id, period, facts, data)
                    cells[period.label] = cell_value

                row = Row(
                    label=self.formatter.clean_label(label),
                    concept=concept_id,
                    is_abstract=is_abstract,
                    depth=0,
                    cells=cells
                )
                rows.append(row)

            return Statement(
                name="Financial Data",
                short_name="Financial Data",
                periods=periods,
                rows=rows
            )

        except Exception as e:
            logger.error(f"Error creating generic statement: {e}")
            return None