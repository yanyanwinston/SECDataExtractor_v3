"""
Data parser for converting viewer JSON to structured data models.
"""

import logging
from typing import Dict, Any, List, Optional

from .data_models import Statement, Period, Row, Cell, ProcessingResult
from .value_formatter import ValueFormatter
from .presentation_parser import PresentationParser
from .fact_matcher import FactMatcher
from .presentation_models import StatementType, StatementTable


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
        self.presentation_parser = PresentationParser()
        self.fact_matcher = FactMatcher(self.formatter)

        # Feature flag for backwards compatibility
        self.use_presentation_parsing = True

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        """
        Parse viewer JSON data into structured models.

        Args:
            viewer_data: JSON data from iXBRL viewer

        Returns:
            Processing result with parsed statements
        """
        company_name = "Unknown Company"
        filing_date = "Unknown Date"
        form_type = "Unknown Form"

        try:
            # Extract basic metadata (best effort)
            company_name = self._extract_company_name(viewer_data)
            filing_date = self._extract_filing_date(viewer_data)
            form_type = self._extract_form_type(viewer_data)

            # Parse statements using presentation-based or legacy approach
            if self.use_presentation_parsing:
                statements = self._parse_with_presentation(viewer_data)
            else:
                statements = self._parse_statements(viewer_data)

            if not statements and self.use_presentation_parsing:
                logger.warning(
                    "Presentation parsing yielded no statements; falling back to legacy pipeline"
                )
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
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
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

    def _parse_with_presentation(self, viewer_data: Dict[str, Any]) -> List[Statement]:
        """New presentation-based parsing method.

        Args:
            viewer_data: Complete viewer JSON structure from Arelle

        Returns:
            List of Statement objects using presentation structure
        """
        logger.info("Using presentation-based parsing")

        try:
            # Parse presentation structure
            presentation_statements = self.presentation_parser.parse_presentation_statements(
                viewer_data
            )

            if not presentation_statements:
                logger.warning("No presentation statements found; falling back to legacy parsing")
                return self._parse_statements(viewer_data)

            # Extract periods and facts
            periods = self._extract_periods_from_viewer_data(viewer_data)
            facts = self._extract_facts_from_viewer_data(viewer_data)

            if not periods:
                logger.warning("No periods found in viewer data; falling back to legacy parsing")
                return self._parse_statements(viewer_data)

            if not facts:
                logger.warning("No facts found in viewer data; falling back to legacy parsing")
                return self._parse_statements(viewer_data)

            # Match facts to presentation for each statement
            primary_tables = []
            supplemental_tables = []

            for pres_statement in presentation_statements:
                try:
                    table = self.fact_matcher.match_facts_to_statement(
                        pres_statement, facts, periods
                    )

                    if not self._statement_table_has_data(table):
                        logger.debug(
                            "Statement %s has no fact data; skipping",
                            pres_statement.statement_name
                        )
                        continue

                    if self._is_primary_statement(pres_statement):
                        primary_tables.append(table)
                    else:
                        supplemental_tables.append(table)

                    logger.info(f"Matched facts for: {pres_statement.statement_name}")
                except Exception as e:
                    logger.warning(
                        f"Failed to match facts for {pres_statement.statement_name}: {e}"
                    )
                    continue

            statement_tables = primary_tables + supplemental_tables

            if not statement_tables:
                logger.info("Presentation statements contained no matchable fact data")
                return []

            # Convert to existing Statement format for compatibility with Excel generator
            statements = self._convert_statement_tables_to_legacy_format(statement_tables)

            logger.info(f"Parsed {len(statements)} statements using presentation structure")
            return statements

        except Exception as e:
            logger.error(f"Error in presentation-based parsing: {e}")
            logger.info("Falling back to legacy parsing")
            return self._parse_statements(viewer_data)

    def _is_primary_statement(self, statement) -> bool:
        """Check if this is a primary financial statement.

        Args:
            statement: PresentationStatement object

        Returns:
            True if this is a primary financial statement
        """
        primary_types = {
            StatementType.BALANCE_SHEET,
            StatementType.INCOME_STATEMENT,
            StatementType.CASH_FLOWS,
            StatementType.EQUITY
        }
        return statement.statement_type in primary_types

    def _statement_table_has_data(self, table) -> bool:
        """Determine whether a matched statement table contains any facts."""
        return any(row.has_data() for row in table.rows)

    def _extract_periods_from_viewer_data(self, viewer_data: Dict[str, Any]) -> List[Period]:
        """Extract periods from viewer data using fact matcher.

        Args:
            viewer_data: Complete viewer JSON structure

        Returns:
            List of Period objects found in facts
        """
        try:
            # Get facts to extract periods from
            facts = self._extract_facts_from_viewer_data(viewer_data)
            if not facts:
                return []

            # Use fact matcher to extract periods
            periods = self.fact_matcher.extract_periods_from_facts(facts)

            logger.info(f"Extracted {len(periods)} periods from viewer data")
            return periods

        except Exception as e:
            logger.error(f"Error extracting periods: {e}")
            return []

    def _extract_facts_from_viewer_data(self, viewer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract facts from viewer data.

        Args:
            viewer_data: Complete viewer JSON structure

        Returns:
            Facts dictionary from viewer data
        """
        try:
            # Navigate to facts in sourceReports structure
            target_report = viewer_data['sourceReports'][0]['targetReports'][0]
            facts = target_report.get('facts', {})

            logger.debug(f"Extracted {len(facts)} facts from viewer data")
            return facts

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Could not extract facts from viewer data: {e}")

            # Try legacy format
            legacy_facts = viewer_data.get('facts', {})
            if legacy_facts:
                logger.info(f"Found {len(legacy_facts)} facts in legacy format")
                return legacy_facts

            return {}

    def _convert_statement_tables_to_legacy_format(self, tables: List[StatementTable]) -> List[Statement]:
        """Convert StatementTable objects to legacy Statement format."""

        legacy_statements: List[Statement] = []

        for table in tables:
            legacy_rows: List[Row] = []

            for stmt_row in table.rows:
                legacy_row = Row(
                    label=stmt_row.node.label,
                    concept=stmt_row.node.concept,
                    is_abstract=stmt_row.node.abstract,
                    depth=stmt_row.node.depth,
                    cells=dict(stmt_row.cells)
                )

                # Preserve presentation metadata for Excel generator enhancements
                legacy_row.presentation_node = stmt_row.node
                legacy_rows.append(legacy_row)

            legacy_statements.append(
                Statement(
                    name=table.statement.statement_name,
                    short_name=table.statement.get_short_name(),
                    periods=table.periods,
                    rows=legacy_rows
                )
            )

        return legacy_statements

    def _parse_statements(self, data: Dict[str, Any]) -> List[Statement]:
        """Parse financial statements from viewer data."""
        statements = []

        # Handle new sourceReports format (Arelle 2.37+)
        if 'sourceReports' in data:
            logger.info("Processing new Arelle sourceReports format")
            statements = self._parse_source_reports_format(data)
        else:
            # Handle older format with direct roles
            logger.info("Processing legacy role-based format")
            statements = self._parse_legacy_format(data)

        return statements

    def _parse_source_reports_format(self, data: Dict[str, Any]) -> List[Statement]:
        """Parse the new sourceReports format from Arelle 2.37+"""
        statements = []

        source_reports = data.get('sourceReports', [])
        if not source_reports:
            return statements

        # Get the target report data
        first_report = source_reports[0]
        target_reports = first_report.get('targetReports', [])
        if not target_reports:
            return statements

        target_data = target_reports[0]
        facts = target_data.get('facts', {})

        logger.info(f"Found {len(facts)} facts in sourceReports format")

        if not facts:
            return statements

        # Decode facts and group by statement type
        decoded_facts = self._decode_facts(facts)
        periods = self._extract_periods_from_facts(decoded_facts)

        # Build statements from grouped facts
        statements = self._build_statements_from_facts(decoded_facts, periods)

        return statements

    def _parse_legacy_format(self, data: Dict[str, Any]) -> List[Statement]:
        """Parse the legacy format with direct roles"""
        statements = []
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

    def _decode_facts(self, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decode compressed facts from new Arelle format"""
        decoded_facts = []

        for fact_id, fact_data in facts.items():
            for concept_key, concept_data in fact_data.items():
                if isinstance(concept_data, dict):
                    decoded_fact = {
                        'fact_id': fact_id,
                        'concept_key': concept_key,
                        'concept': concept_data.get('c', ''),  # concept name
                        'entity': concept_data.get('e', ''),   # entity
                        'measure': concept_data.get('m', ''),  # measure/unit
                        'period': concept_data.get('p', ''),   # period
                        'value': concept_data.get('v'),        # value
                        'decimals': concept_data.get('d'),     # decimals
                        'raw_data': concept_data
                    }
                    decoded_facts.append(decoded_fact)

        logger.debug(f"Decoded {len(decoded_facts)} facts")
        return decoded_facts

    def _extract_periods_from_facts(self, decoded_facts: List[Dict[str, Any]]) -> List[Period]:
        """Extract unique periods from decoded facts"""
        period_map = {}

        for fact in decoded_facts:
            period_id = fact['period']
            if period_id and period_id not in period_map:
                # Create period based on period ID pattern
                # This is simplified - real implementation might need more context
                period_map[period_id] = Period(
                    label=f"Period {period_id}",
                    end_date=period_id,
                    instant=True  # Simplified assumption
                )

        periods = list(period_map.values())
        logger.debug(f"Found {len(periods)} unique periods")
        return periods

    def _build_statements_from_facts(self, decoded_facts: List[Dict[str, Any]],
                                   periods: List[Period]) -> List[Statement]:
        """Build financial statements from decoded facts"""
        statements = []

        # Group facts by statement type based on concept names
        statement_groups = self._group_facts_by_statement_type(decoded_facts)

        for stmt_type, stmt_facts in statement_groups.items():
            if not stmt_facts:
                continue

            # Create statement
            statement_name = self._get_statement_name(stmt_type)
            short_name = self._get_short_name(statement_name)

            # Build rows from facts
            rows = self._build_rows_from_facts(stmt_facts, periods)

            if rows:
                statement = Statement(
                    name=statement_name,
                    short_name=short_name,
                    periods=periods,
                    rows=rows
                )
                statements.append(statement)

        logger.info(f"Built {len(statements)} statements from facts")
        return statements

    def _group_facts_by_statement_type(self, decoded_facts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group facts by financial statement type"""
        groups = {
            'balance_sheet': [],
            'income_statement': [],
            'cash_flows': [],
            'equity': [],
            'other': []
        }

        for fact in decoded_facts:
            concept = fact['concept'].lower()

            if any(term in concept for term in ['asset', 'liability', 'equity', 'stockholder']):
                groups['balance_sheet'].append(fact)
            elif any(term in concept for term in ['revenue', 'income', 'expense', 'cost', 'loss', 'gain']):
                groups['income_statement'].append(fact)
            elif any(term in concept for term in ['cash', 'financing', 'investing', 'operating']):
                groups['cash_flows'].append(fact)
            elif 'equity' in concept or 'stockholder' in concept:
                groups['equity'].append(fact)
            else:
                groups['other'].append(fact)

        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    def _get_statement_name(self, stmt_type: str) -> str:
        """Get full statement name from type"""
        names = {
            'balance_sheet': 'Consolidated Balance Sheets',
            'income_statement': 'Consolidated Statements of Operations',
            'cash_flows': 'Consolidated Statements of Cash Flows',
            'equity': 'Consolidated Statements of Stockholders Equity',
            'other': 'Other Financial Data'
        }
        return names.get(stmt_type, 'Financial Statement')

    def _build_rows_from_facts(self, facts: List[Dict[str, Any]], periods: List[Period]) -> List[Row]:
        """Build statement rows from facts"""
        rows = []

        # Group facts by concept to create rows
        concept_groups = {}
        for fact in facts:
            concept = fact['concept']
            if concept not in concept_groups:
                concept_groups[concept] = []
            concept_groups[concept].append(fact)

        # Create rows
        for concept, concept_facts in concept_groups.items():
            # Get label from first fact or use concept name
            first_fact = concept_facts[0]
            label = self._get_concept_label(concept)

            # Build cells for each period
            cells = {}
            for period in periods:
                # Find fact for this period
                period_fact = None
                for fact in concept_facts:
                    if fact['period'] == period.end_date:
                        period_fact = fact
                        break

                if period_fact and period_fact['value'] is not None:
                    formatted_value = self.formatter.format_cell_value(
                        period_fact['value'],
                        period_fact['measure'],
                        period_fact['decimals'],
                        concept
                    )

                    cell = Cell(
                        value=formatted_value,
                        raw_value=period_fact['value'],
                        unit=period_fact['measure'],
                        decimals=period_fact['decimals'],
                        period=period.label
                    )
                else:
                    cell = Cell(
                        value="—",
                        raw_value=None,
                        unit=None,
                        decimals=None,
                        period=period.label
                    )

                cells[period.label] = cell

            row = Row(
                label=label,
                concept=concept,
                is_abstract=False,  # Simplified
                depth=0,  # Simplified
                cells=cells
            )
            rows.append(row)

        return rows

    def _get_concept_label(self, concept: str) -> str:
        """Get human-readable label from concept name"""
        # Clean up concept name for display
        if ':' in concept:
            concept = concept.split(':')[-1]

        # Convert camelCase to Title Case
        import re
        label = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept)
        label = label.replace('_', ' ').title()

        return self.formatter.clean_label(label)

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
