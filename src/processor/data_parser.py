"""
Data parser for converting viewer JSON to structured data models.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set

from .data_models import Statement, Period, Row, ProcessingResult
from .value_formatter import ValueFormatter
from .presentation_parser import PresentationParser
from .fact_matcher import FactMatcher
from .presentation_models import PresentationStatement, StatementType, StatementTable


logger = logging.getLogger(__name__)


class DataParser:
    """Parser for converting iXBRL viewer JSON to structured data models."""

    def __init__(
        self,
        formatter: Optional[ValueFormatter] = None,
        include_disclosures: bool = False,
        label_style: str = 'terse',
        use_scale_hint: bool = True,
        expand_dimensions: bool = True,
    ):
        """
        Initialize data parser.

        Args:
            formatter: Value formatter for display formatting
            include_disclosures: Whether to retain disclosure/detail roles in output
        """
        self.formatter = formatter or ValueFormatter()
        self.presentation_parser = PresentationParser(label_style=label_style)
        self.fact_matcher = FactMatcher(
            self.formatter,
            use_scale_hint=use_scale_hint,
            expand_dimensions=expand_dimensions,
        )
        self.include_disclosures = include_disclosures

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

            statements = self._parse_with_presentation(viewer_data)

            if not statements:
                error_message = "No presentation statements with fact data were produced"
                logger.error(error_message)
                return ProcessingResult(
                    statements=[],
                    company_name=company_name,
                    filing_date=filing_date,
                    form_type=form_type,
                    success=False,
                    error=error_message
                )

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

        source_reports = data.get('sourceReports') or []
        if isinstance(source_reports, list) and source_reports:
            target_reports = source_reports[0].get('targetReports') or []
            if isinstance(target_reports, list) and target_reports:
                facts = target_reports[0].get('facts', {})
                for fact_entry in facts.values():
                    context = fact_entry.get('a')
                    concept = context.get('c', '') if isinstance(context, dict) else ''
                    if 'entityregistrantname' in concept.lower():
                        company_name = fact_entry.get('v', '')
                        if company_name:
                            break

        if not company_name:
            facts = data.get('facts', {})
            for fact_entry in facts.values():
                concept = fact_entry.get('c', '')
                if 'entityregistrantname' in concept.lower():
                    company_name = fact_entry.get('v', '')
                    break

        if not company_name:
            metadata = data.get('meta', {})
            company_name = metadata.get('entityName', metadata.get('companyName', 'Unknown Company'))

        return str(company_name) if company_name else "Unknown Company"

    def _extract_filing_date(self, data: Dict[str, Any]) -> str:
        """Extract filing date from viewer data."""
        source_reports = data.get('sourceReports') or []
        if isinstance(source_reports, list) and source_reports:
            target_reports = source_reports[0].get('targetReports') or []
            if isinstance(target_reports, list) and target_reports:
                facts = target_reports[0].get('facts', {})
                for fact_entry in facts.values():
                    context = fact_entry.get('a')
                    concept = context.get('c', '') if isinstance(context, dict) else ''
                    if any(term in concept.lower() for term in ['documentdate', 'filingdate', 'periodenddate']):
                        value = fact_entry.get('v')
                        if value:
                            return value

        facts = data.get('facts', {})
        for fact_entry in facts.values():
            concept = fact_entry.get('c', '')
            if any(term in concept.lower() for term in ['documentdate', 'filingdate', 'periodenddate']):
                value = fact_entry.get('v')
                if value:
                    return value

        return data.get('meta', {}).get('filingDate', 'Unknown Date')

    def _extract_form_type(self, data: Dict[str, Any]) -> str:
        """Extract form type from viewer data."""
        source_reports = data.get('sourceReports') or []
        if isinstance(source_reports, list) and source_reports:
            target_reports = source_reports[0].get('targetReports') or []
            if isinstance(target_reports, list) and target_reports:
                facts = target_reports[0].get('facts', {})
                for fact_entry in facts.values():
                    context = fact_entry.get('a')
                    concept = context.get('c', '') if isinstance(context, dict) else ''
                    if 'documenttype' in concept.lower():
                        value = fact_entry.get('v')
                        if value:
                            return value

        facts = data.get('facts', {})
        for fact_entry in facts.values():
            concept = fact_entry.get('c', '')
            if 'documenttype' in concept.lower():
                value = fact_entry.get('v')
                if value:
                    return value

        return data.get('meta', {}).get('formType', 'Unknown Form')

    def _parse_with_presentation(self, viewer_data: Dict[str, Any]) -> List[Statement]:
        """New presentation-based parsing method.

        Args:
            viewer_data: Complete viewer JSON structure from Arelle

        Returns:
            List of Statement objects using presentation structure
        """
        logger.info("Using presentation-based parsing")

        # Parse presentation structure
        presentation_statements = self.presentation_parser.parse_presentation_statements(
            viewer_data
        )

        self.fact_matcher.update_concept_labels(
            self.presentation_parser.concept_label_map
        )

        presentation_statements = self._filter_presentation_statements(presentation_statements)

        if not presentation_statements:
            raise ValueError("No presentation statements found in viewer data")

        facts = self._extract_facts_from_viewer_data(viewer_data)
        if not facts:
            raise ValueError("No facts found in viewer data")

        document_period_end_dates = self._extract_document_period_end_dates(viewer_data)

        # Match facts to presentation for each statement
        primary_tables = []
        supplemental_tables = []

        for pres_statement in presentation_statements:
            try:
                concepts_for_statement = self._collect_concepts_from_statement(pres_statement)

                periods_for_statement = self.fact_matcher.extract_periods_from_facts(
                    facts,
                    concept_filter=concepts_for_statement if concepts_for_statement else None
                )

                periods_for_statement = self._select_periods_for_statement(
                    pres_statement,
                    periods_for_statement,
                    document_period_end_dates
                )

                if not periods_for_statement:
                    logger.debug(
                        "Statement %s has no applicable periods; skipping",
                        pres_statement.statement_name
                    )
                    continue

                table = self.fact_matcher.match_facts_to_statement(
                    pres_statement, facts, periods_for_statement
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
            raise ValueError("Presentation statements contained no matchable fact data")

        # Convert to existing Statement format for compatibility with Excel generator
        statements = self._convert_statement_tables_to_legacy_format(statement_tables)

        logger.info(f"Parsed {len(statements)} statements using presentation structure")
        return statements

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

    def _filter_presentation_statements(
        self,
        statements: List[PresentationStatement]
    ) -> List[PresentationStatement]:
        """Filter statements based on MetaLinks group type metadata."""

        if not statements or self.include_disclosures:
            return statements

        if not any(getattr(stmt, 'group_type', None) for stmt in statements):
            return statements

        allowed_groups = {'statement'}
        primary_types = {
            StatementType.BALANCE_SHEET,
            StatementType.INCOME_STATEMENT,
            StatementType.CASH_FLOWS,
            StatementType.EQUITY,
            StatementType.COMPREHENSIVE_INCOME,
        }

        filtered = []
        for stmt in statements:
            group = (stmt.group_type or '').lower()
            if group in allowed_groups:
                filtered.append(stmt)
            elif (
                not group
                and stmt.statement_type in primary_types
                and not stmt.statement_name.lower().startswith('disclosure')
            ):
                filtered.append(stmt)

        if not filtered:
            return statements

        filtered.sort(key=lambda stmt: stmt.sort_key())
        return filtered

    def _collect_concepts_from_statement(
        self,
        statement: PresentationStatement
    ) -> set:
        """Gather concept names used in a single presentation statement."""
        return {
            node.concept
            for node, _ in statement.get_all_nodes_flat()
            if node.concept
        }

    def _collect_concepts_from_statements(
        self,
        statements: List[PresentationStatement]
    ) -> set:
        """Gather concept names across multiple statements."""
        concepts = set()
        for statement in statements:
            concepts.update(self._collect_concepts_from_statement(statement))
        return concepts

    def _select_periods_for_statement(
        self,
        statement: PresentationStatement,
        periods: List[Period],
        document_end_dates: List[datetime]
    ) -> List[Period]:
        """Select appropriate periods for a specific statement."""
        if not periods:
            return []

        sorted_periods = sorted(periods, key=lambda p: p.end_date, reverse=True)
        instants = [p for p in sorted_periods if p.instant]
        durations = [p for p in sorted_periods if not p.instant]

        statement_type = statement.statement_type

        def find_matching_period(target_date: datetime, require_instant: bool, used: set) -> Optional[Period]:
            candidates = instants if require_instant else durations
            target_iso = target_date.date().isoformat()
            for period in candidates:
                if period.end_date == target_iso and id(period) not in used:
                    return period

            for delta in (1, -1):
                alt_iso = (target_date + timedelta(days=delta)).date().isoformat()
                for period in candidates:
                    if period.end_date == alt_iso and id(period) not in used:
                        return period

            for period in candidates:
                if id(period) not in used:
                    return period

            return None

        targets = document_end_dates or []
        selected: List[Period] = []
        used_periods: set = set()

        if statement_type == StatementType.BALANCE_SHEET:
            desired_count = 2
            desired_targets = list(targets)
            while desired_targets and len(desired_targets) < desired_count:
                last = desired_targets[-1]
                try:
                    desired_targets.append(last.replace(year=last.year - 1))
                except ValueError:
                    desired_targets.append(last - timedelta(days=365))

            if not desired_targets:
                desired_targets = []

            desired = desired_targets[:desired_count]
            for target_date in desired:
                period = find_matching_period(target_date, require_instant=True, used=used_periods)
                if period:
                    period.label = self._format_period_display_label(target_date, is_instant=True)
                    selected.append(period)
                    used_periods.add(id(period))
            if len(selected) < desired_count:
                for period in instants:
                    if id(period) in used_periods:
                        continue
                    period.label = self._format_period_display_label(
                        datetime.strptime(period.end_date, '%Y-%m-%d'),
                        is_instant=True
                    )
                    selected.append(period)
                    used_periods.add(id(period))
                    if len(selected) == desired_count:
                        break
            if not selected:
                selected = instants[:desired_count] or sorted_periods[:desired_count]

        elif statement_type in {
            StatementType.INCOME_STATEMENT,
            StatementType.CASH_FLOWS,
            StatementType.COMPREHENSIVE_INCOME,
            StatementType.EQUITY
        }:
            desired_count = 3
            desired_targets = list(targets)
            while desired_targets and len(desired_targets) < desired_count:
                last = desired_targets[-1]
                try:
                    desired_targets.append(last.replace(year=last.year - 1))
                except ValueError:
                    desired_targets.append(last - timedelta(days=365))

            if not desired_targets:
                desired_targets = []

            desired = desired_targets[:desired_count]
            for target_date in desired:
                period = find_matching_period(target_date, require_instant=False, used=used_periods)
                if period:
                    period.label = self._format_period_display_label(target_date, is_instant=False)
                    selected.append(period)
                    used_periods.add(id(period))
            if len(selected) < desired_count:
                for period in durations + instants:
                    if id(period) in used_periods:
                        continue
                    period.label = self._format_period_display_label(
                        datetime.strptime(period.end_date, '%Y-%m-%d'),
                        is_instant=period.instant
                    )
                    selected.append(period)
                    used_periods.add(id(period))
                    if len(selected) == desired_count:
                        break
            if not selected:
                selected = durations[:desired_count] or instants[:desired_count] or sorted_periods[:desired_count]

        else:
            selected = sorted_periods[:3]

        return selected

    def _extract_document_period_end_dates(self, viewer_data: Dict[str, Any]) -> List[datetime]:
        """Extract document period end dates to help align reporting periods."""
        facts = viewer_data['sourceReports'][0]['targetReports'][0].get('facts', {})
        end_dates: Set[datetime] = set()

        for fact_data in facts.values():
            for context in fact_data.values():
                if not isinstance(context, dict):
                    continue
                concept = context.get('c', '').lower()
                if 'documentperiodenddate' not in concept:
                    continue
                period_str = context.get('p')
                if not period_str:
                    continue
                end_str = period_str.split('/')[-1]
                try:
                    end_dates.add(datetime.strptime(end_str, '%Y-%m-%d'))
                except ValueError:
                    continue

        return sorted(end_dates, reverse=True)

    def _format_period_display_label(self, target_date: datetime, is_instant: bool) -> str:
        """Human-friendly label for a reporting period."""
        return target_date.strftime('%b %d, %Y')

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
