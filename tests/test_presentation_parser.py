#!/usr/bin/env python3
"""
Test presentation parser and fact matcher

Tests the complete presentation parsing pipeline that extracts presentation
structure from viewer JSON and matches facts to create statement tables.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock

from src.processor.presentation_parser import PresentationParser
from src.processor.fact_matcher import FactMatcher
from src.processor.presentation_models import StatementType
from src.processor.data_models import Period


class TestPresentationParser:
    """Test PresentationParser functionality."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        with open(fixtures_path, 'r') as f:
            cls.fixtures = json.load(f)

        # Create mock viewer JSON structure
        cls.mock_viewer_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": cls.fixtures["role_definitions"]["data"],
                    "rels": {
                        "pres": {
                            "ns9": cls.fixtures["presentation_relationships"]["data"]["relationships"]
                        }
                    },
                    "facts": cls.fixtures["sample_facts"]["data"],
                    "concepts": cls.fixtures["sample_concepts"]["data"],
                    "target": {"some": "metadata"},
                    "localDocs": {}
                }]
            }]
        }

        cls.parser = PresentationParser()

    def test_parse_presentation_statements(self):
        """Test parsing multiple statements from viewer JSON."""
        statements = self.parser.parse_presentation_statements(self.mock_viewer_json)

        assert len(statements) > 0

        # Should identify Balance Sheet statement
        balance_sheet = next((s for s in statements if 'BALANCE' in s.statement_name.upper()), None)
        assert balance_sheet is not None
        assert balance_sheet.statement_type == StatementType.BALANCE_SHEET
        assert balance_sheet.role_id == "ns9"
        assert len(balance_sheet.root_nodes) > 0

    def test_is_financial_statement_role(self):
        """Test identifying financial statement roles."""
        # Test various role types
        balance_sheet_role = {"en": "0000005 - Statement - CONSOLIDATED BALANCE SHEETS"}
        income_role = {"en": "0000013 - Statement - CONSOLIDATED STATEMENTS OF OPERATIONS"}
        cash_flow_role = {"en": "0000011 - Statement - CONSOLIDATED STATEMENTS OF CASH FLOWS"}
        cover_page_role = {"en": "0000001 - Document - Cover Page"}

        assert self.parser._is_financial_statement_role(balance_sheet_role) is True
        assert self.parser._is_financial_statement_role(income_role) is True
        assert self.parser._is_financial_statement_role(cash_flow_role) is True
        assert self.parser._is_financial_statement_role(cover_page_role) is True

    def test_build_presentation_tree(self):
        """Test building presentation tree recursively."""
        role_data = self.fixtures["presentation_relationships"]["data"]["relationships"]
        concepts = self.fixtures["sample_concepts"]["data"]

        # Build tree for root concept
        root_concept = "us-gaap:StatementOfFinancialPositionAbstract"
        tree = self.parser._build_presentation_tree(root_concept, role_data, concepts, depth=0)

        assert tree.concept == root_concept
        assert tree.depth == 0
        assert len(tree.children) > 0

        # Check children have correct depths
        for child in tree.children:
            assert child.depth == 1

            # Check grandchildren if any
            for grandchild in child.children:
                assert grandchild.depth == 2

    def test_get_concept_label(self):
        """Test concept label resolution."""
        concepts = self.fixtures["sample_concepts"]["data"]

        # Test concept with standard label
        concept_with_label = list(concepts.keys())[0]
        label = self.parser._get_concept_label(concept_with_label, concepts)
        assert isinstance(label, str)
        assert len(label) > 0

        # Prefer terse label when available
        custom_concepts = {
            'custom:Example': {
                'labels': {
                    'terseLabel': {'en-us': 'Terse Example'},
                    'std': {'en-us': 'Standard Example'}
                }
            }
        }
        terse_label = self.parser._get_concept_label('custom:Example', custom_concepts)
        assert terse_label == 'Terse Example'

        standard_parser = PresentationParser(label_style='standard')
        standard_label = standard_parser._get_concept_label('custom:Example', custom_concepts)
        assert standard_label == 'Standard Example'

        # Test concept not in definitions (should get humanized name)
        missing_concept = "us-gaap:MissingConceptExample"
        label = self.parser._get_concept_label(missing_concept, concepts)
        assert label == "Missing Concept Example"

    def test_is_abstract_concept(self):
        """Test abstract concept detection."""
        concepts = self.fixtures["sample_concepts"]["data"]

        # Test abstract concept (by naming convention)
        abstract_concept = "us-gaap:StatementOfFinancialPositionAbstract"
        assert self.parser._is_abstract_concept(abstract_concept, concepts) is True

        # Test non-abstract concept
        concrete_concept = "us-gaap:CashAndCashEquivalentsAtCarryingValue"
        # This will depend on the test data - abstract concepts usually end in "Abstract"
        is_abstract = self.parser._is_abstract_concept(concrete_concept, concepts)
        assert isinstance(is_abstract, bool)

    def test_humanize_concept_name(self):
        """Test converting concept names to human-readable labels."""
        test_cases = [
            ("us-gaap:CashAndCashEquivalents", "Cash And Cash Equivalents"),
            ("us-gaap:Assets", "Assets"),
            ("dei:EntityRegistrantName", "Entity Registrant Name"),
            ("SimpleConceptName", "Simple Concept Name")
        ]

        for concept, expected in test_cases:
            result = self.parser._humanize_concept_name(concept)
            assert result == expected

    def test_extract_statement_name(self):
        """Test extracting clean statement names from role labels."""
        test_cases = [
            ("0000005 - Statement - CONSOLIDATED BALANCE SHEETS", "CONSOLIDATED BALANCE SHEETS"),
            ("0000013 - Statement - CONSOLIDATED STATEMENTS OF OPERATIONS", "CONSOLIDATED STATEMENTS OF OPERATIONS"),
            ("CONSOLIDATED BALANCE SHEETS", "CONSOLIDATED BALANCE SHEETS"),
            ("", "Financial Statement")
        ]

        for role_label, expected in test_cases:
            result = self.parser._extract_statement_name(role_label)
            assert result == expected

    def test_parse_single_statement(self):
        """Test parsing a complete single statement."""
        role_id = "ns9"
        role_data = self.fixtures["presentation_relationships"]["data"]["relationships"]
        role_def = self.fixtures["role_definitions"]["data"]["ns9"]
        concepts = self.fixtures["sample_concepts"]["data"]

        statement = self.parser._parse_single_statement(role_id, role_data, role_def, concepts)

        assert statement.role_id == role_id
        assert statement.statement_name == "CONSOLIDATED BALANCE SHEETS"
        assert statement.statement_type == StatementType.BALANCE_SHEET
        assert len(statement.root_nodes) > 0

        # Test flattening the statement
        flat_nodes = statement.get_all_nodes_flat()
        assert len(flat_nodes) > 0

        # Verify depth progression
        for i, (node, depth) in enumerate(flat_nodes):
            assert node.depth == depth
            if i > 0:
                prev_depth = flat_nodes[i-1][1]
                assert depth <= prev_depth + 1  # Depth shouldn't jump by more than 1


class TestFactMatcher:
    """Test FactMatcher functionality."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        with open(fixtures_path, 'r') as f:
            cls.fixtures = json.load(f)

        cls.fact_matcher = FactMatcher()
        cls.parser = PresentationParser()

        # Create test statement
        cls.mock_viewer_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": cls.fixtures["role_definitions"]["data"],
                    "rels": {
                        "pres": {
                            "ns9": cls.fixtures["presentation_relationships"]["data"]["relationships"]
                        }
                    },
                    "facts": cls.fixtures["sample_facts"]["data"],
                    "concepts": cls.fixtures["sample_concepts"]["data"]
                }]
            }]
        }

    def test_extract_periods_from_facts(self):
        """Test extracting periods from facts data."""
        facts = self.fixtures["sample_facts"]["data"]

        periods = self.fact_matcher.extract_periods_from_facts(facts)

        assert len(periods) > 0

        # Check period objects are properly created
        for period in periods:
            assert hasattr(period, 'label')
            assert hasattr(period, 'end_date')
            assert hasattr(period, 'instant')
            assert isinstance(period.instant, bool)

    def test_find_fact_for_concept_and_period(self):
        """Test finding specific facts by concept and period."""
        facts = self.fixtures["sample_facts"]["data"]
        periods = self.fact_matcher.extract_periods_from_facts(facts)

        if periods:
            # Try to find a fact for the first available period
            first_period = periods[0]

            # Get first concept from facts
            first_fact = list(facts.values())[0]
            first_context = next(iter([v for k, v in first_fact.items() if k != 'v' and isinstance(v, dict)]))
            test_concept = first_context.get('c')

            if test_concept:
                found_fact = self.fact_matcher._find_fact_for_concept_and_period(
                    test_concept, first_period, facts
                )

                if found_fact:  # May be None if no match
                    assert found_fact.get('c') == test_concept
                    assert 'v' in found_fact

    def test_period_matches(self):
        """Test period matching logic."""
        instant_period = Period(label="2023", end_date="2023-09-30", instant=True)
        duration_period = Period(label="2023", end_date="2023-09-30", instant=False)

        # Test instant period matching
        assert self.fact_matcher._period_matches(instant_period, "2023-09-30") is True
        assert self.fact_matcher._period_matches(instant_period, "2022-09-30") is False

        # Test duration period matching
        assert self.fact_matcher._period_matches(duration_period, "2022-10-01/2023-09-30") is True
        assert self.fact_matcher._period_matches(duration_period, "2023-09-30") is True
        assert self.fact_matcher._period_matches(duration_period, "2023-12-31") is False

    def test_create_cell_from_fact(self):
        """Test creating Cell objects from fact data."""
        test_fact = {
            'c': 'us-gaap:Cash',
            'v': 29965000000,
            'u': 'usd',
            'd': -6,  # Millions
            'p': '2023-09-30'
        }

        period = Period(label="2023", end_date="2023-09-30", instant=True)

        cell = self.fact_matcher._create_cell_from_fact(test_fact, period)

        assert cell.raw_value == 29965.0
        assert cell.unit == 'usd'
        assert cell.decimals == -6
        assert cell.period == period.label
        assert cell.value  # Should have some formatted value

    def test_scale_hint_skips_positive_decimals(self):
        """Ensure positive decimal metadata does not trigger scaling."""
        test_fact = {
            'c': 'custom:RatioMetric',
            'v': 0.1234,
            'u': None,
            'd': 4,
            'p': '2023-09-30'
        }

        period = Period(label="2023", end_date="2023-09-30", instant=False)
        cell = self.fact_matcher._create_cell_from_fact(test_fact, period)

        assert cell.raw_value == pytest.approx(0.1234)
        assert cell.value

    def test_structural_nodes_trimmed_from_rows(self):
        """Fact matcher should drop table/axis/domain/member containers."""
        from src.processor.presentation_models import PresentationNode, PresentationStatement, StatementType

        # Build a tiny tree: root -> table -> axis -> domain -> member -> line items -> data row
        assets_node = PresentationNode(
            concept='us-gaap:Assets',
            label='Total assets',
            order=5,
            depth=5,
            abstract=False,
        )

        line_items = PresentationNode(
            concept='us-gaap:StatementLineItems',
            label='Statement [Line Items]',
            order=4,
            depth=4,
            abstract=False,
            children=[assets_node],
        )

        member = PresentationNode(
            concept='custom:SomeMember',
            label='Some Member',
            order=3,
            depth=3,
            abstract=False,
            children=[line_items],
        )

        domain = PresentationNode(
            concept='us-gaap:SomeDomain',
            label='Some Domain',
            order=2,
            depth=2,
            abstract=False,
            children=[member],
        )

        axis = PresentationNode(
            concept='us-gaap:SomeAxis',
            label='Some Axis',
            order=1,
            depth=1,
            abstract=False,
            children=[domain],
        )

        table = PresentationNode(
            concept='us-gaap:SomeTable',
            label='Statement [Table]',
            order=0,
            depth=1,
            abstract=False,
            children=[axis],
        )

        root = PresentationNode(
            concept='us-gaap:StatementOfFinancialPositionAbstract',
            label='Statement of Financial Position',
            order=0,
            depth=0,
            abstract=True,
            children=[table],
        )

        statement = PresentationStatement(
            role_uri='uri',
            role_id='ns14',
            statement_name='Consolidated Balance Sheets',
            statement_type=StatementType.BALANCE_SHEET,
            root_nodes=[root],
        )

        periods = [Period(label='FY24', end_date='2024-12-31', instant=True)]
        table_result = self.fact_matcher.match_facts_to_statement(statement, {}, periods)

        labels = [row.label for row in table_result.rows]

        assert 'Statement [Table]' not in labels
        assert 'Some Axis' not in labels
        assert 'Some Domain' not in labels
        assert 'Some Member' not in labels
        assert 'Statement [Line Items]' not in labels
        assert 'Total assets' in labels

        assets_row = next(row for row in table_result.rows if row.label == 'Total assets')
        assert assets_row.depth == 1  # Indented beneath the abstract root only

    def test_dimension_rows_expanded(self):
        """Dimensioned facts should materialize as additional child rows."""
        from src.processor.presentation_models import PresentationNode, PresentationStatement, StatementType

        revenue_node = PresentationNode(
            concept='us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
            label='Revenue',
            order=5,
            depth=2,
            abstract=False,
        )

        line_items = PresentationNode(
            concept='us-gaap:StatementLineItems',
            label='Statement [Line Items]',
            order=1,
            depth=1,
            abstract=False,
            children=[revenue_node],
        )

        automotive_member = PresentationNode(
            concept='ns0:AutomotiveSalesMember',
            label='Automotive Sales [Member]',
            order=0,
            depth=3,
            abstract=False,
        )

        energy_member = PresentationNode(
            concept='ns0:EnergyGenerationAndStorageMember',
            label='Energy Generation and Storage [Member]',
            order=1,
            depth=3,
            abstract=False,
        )

        product_domain = PresentationNode(
            concept='srt:ProductsAndServicesDomain',
            label='Product and Service [Domain]',
            order=0,
            depth=2,
            abstract=False,
            children=[automotive_member, energy_member],
        )

        product_axis = PresentationNode(
            concept='srt:ProductOrServiceAxis',
            label='Product and Service [Axis]',
            order=0,
            depth=1,
            abstract=False,
            children=[product_domain],
        )

        table_node = PresentationNode(
            concept='us-gaap:StatementTable',
            label='Statement [Table]',
            order=0,
            depth=0,
            abstract=False,
            children=[product_axis, line_items],
        )

        root = PresentationNode(
            concept='us-gaap:IncomeStatementAbstract',
            label='Income Statement [Abstract]',
            order=0,
            depth=0,
            abstract=True,
            children=[table_node],
        )

        statement = PresentationStatement(
            role_uri='uri',
            role_id='ns20',
            statement_name='Consolidated Statements of Operations',
            statement_type=StatementType.INCOME_STATEMENT,
            root_nodes=[root],
        )

        periods = [
            Period(label='FY24', end_date='2024-12-31', instant=False),
            Period(label='FY23', end_date='2023-12-31', instant=False),
        ]

        facts = {
            'f-total-2024': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2024-01-01/2024-12-31',
                    'u': 'iso4217:USD',
                },
                'v': 1000.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
            'f-total-2023': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2023-01-01/2023-12-31',
                    'u': 'iso4217:USD',
                },
                'v': 900.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
            'f-auto-2024': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2024-01-01/2024-12-31',
                    'u': 'iso4217:USD',
                    'srt:ProductOrServiceAxis': 'ns0:AutomotiveSalesMember',
                },
                'v': 600.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
            'f-auto-2023': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2023-01-01/2023-12-31',
                    'u': 'iso4217:USD',
                    'srt:ProductOrServiceAxis': 'ns0:AutomotiveSalesMember',
                },
                'v': 500.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
            'f-energy-2024': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2024-01-01/2024-12-31',
                    'u': 'iso4217:USD',
                    'srt:ProductOrServiceAxis': 'ns0:EnergyGenerationAndStorageMember',
                },
                'v': 400.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
            'f-energy-2023': {
                'a': {
                    'c': 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
                    'p': '2023-01-01/2023-12-31',
                    'u': 'iso4217:USD',
                    'srt:ProductOrServiceAxis': 'ns0:EnergyGenerationAndStorageMember',
                },
                'v': 400.0,
                'd': 0,
                'u': 'iso4217:USD',
            },
        }

        axis_metadata = self.fact_matcher._extract_axis_metadata(statement)
        grouped = self.fact_matcher._group_facts_by_dimensions(
            'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
            facts,
            axis_metadata,
            {}
        )
        assert any(dim_key for dim_key in grouped.keys())  # ensure dimensional groups present

        table_result = self.fact_matcher.match_facts_to_statement(statement, facts, periods)

        revenue_rows = [
            row for row in table_result.rows
            if row.concept == 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'
        ]

        assert [row.label for row in revenue_rows] == [
            'Revenue',
            'Automotive Sales',
            'Energy Generation and Storage',
        ]

        revenue_row, auto_row, energy_row = revenue_rows

        assert revenue_row.cells['FY24'].raw_value == 1000.0
        assert revenue_row.cells['FY23'].raw_value == 900.0
        assert auto_row.cells['FY24'].raw_value == 600.0
        assert auto_row.cells['FY23'].raw_value == 500.0
        assert energy_row.cells['FY24'].raw_value == 400.0
        assert energy_row.cells['FY23'].raw_value == 400.0

    def test_format_period_label(self):
        """Test period label formatting."""
        test_cases = [
            ("2023-12-31", "2023"),
            ("2023-09-30", "Sep 30, 2023"),
            ("2023-06-30", "Jun 30, 2023")
        ]

        for date_str, expected in test_cases:
            result = self.fact_matcher._format_period_label(date_str)
            assert result == expected

    def test_match_facts_to_statement(self):
        """Test complete fact matching to create statement table."""
        # Parse a statement first
        statements = self.parser.parse_presentation_statements(self.mock_viewer_json)

        if statements:
            statement = statements[0]
            facts = self.fixtures["sample_facts"]["data"]
            periods = self.fact_matcher.extract_periods_from_facts(facts)

            # Match facts to statement
            table = self.fact_matcher.match_facts_to_statement(statement, facts, periods)

            assert table.statement == statement
            assert table.periods == periods
            assert len(table.rows) > 0

            # Each row should have cells (may not match exactly if there are period duplicates)
            for row in table.rows:
                assert len(row.cells) > 0  # Should have at least one cell

                # Each cell should be properly created
                for period_label, cell in row.cells.items():
                    assert cell.period == period_label
                    assert cell.value is not None  # Should have value or "—"

    def test_mock_formatter_integration(self):
        """Test fact matcher with mock formatter."""
        # Create mock formatter
        mock_formatter = Mock()
        mock_formatter.format_cell_value.return_value = "1,000.0"

        mock_formatter.scale_millions = False
        fact_matcher = FactMatcher(formatter=mock_formatter)

        test_fact = {
            'c': 'us-gaap:Cash',
            'v': 1000.0,
            'u': 'usd',
            'd': 0,
            'p': '2023-09-30'
        }

        period = Period(label="2023", end_date="2023-09-30", instant=True)
        cell = fact_matcher._create_cell_from_fact(test_fact, period)

        # Should have called formatter
        mock_formatter.format_cell_value.assert_called_once_with(
            1000.0, 'usd', 0, 'us-gaap:Cash'
        )
        assert cell.value == "1,000.0"


class TestPresentationParserIntegration:
    """Integration tests for presentation parser and fact matcher."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        with open(fixtures_path, 'r') as f:
            cls.fixtures = json.load(f)

        cls.mock_viewer_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": cls.fixtures["role_definitions"]["data"],
                    "rels": {
                        "pres": {
                            "ns9": cls.fixtures["presentation_relationships"]["data"]["relationships"]
                        }
                    },
                    "facts": cls.fixtures["sample_facts"]["data"],
                    "concepts": cls.fixtures["sample_concepts"]["data"]
                }]
            }]
        }

    def test_complete_parsing_pipeline(self):
        """Test complete pipeline from viewer JSON to statement tables."""
        parser = PresentationParser()
        fact_matcher = FactMatcher()

        # Parse presentation statements
        statements = parser.parse_presentation_statements(self.mock_viewer_json)
        assert len(statements) > 0

        # Extract periods from facts
        facts = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]['facts']
        periods = fact_matcher.extract_periods_from_facts(facts)
        assert len(periods) > 0

        # Create statement tables
        tables = []
        for statement in statements:
            table = fact_matcher.match_facts_to_statement(statement, facts, periods)
            tables.append(table)

            # Validate summary structure
            assert table.statement == statement
            assert len(table.periods) == len(periods)
            assert len(table.rows) > 0

        assert len(tables) == len(statements)

    def test_error_handling(self):
        """Test error handling in parsing pipeline."""
        parser = PresentationParser()

        # Test with malformed viewer JSON
        malformed_json = {
            "sourceReports": [{"targetReports": [{}]}]
        }

        # Should handle gracefully and return empty list
        statements = parser.parse_presentation_statements(malformed_json)
        assert statements == []

    def test_empty_presentation_data(self):
        """Test handling empty presentation data."""
        empty_viewer_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": {},
                    "rels": {"pres": {}},
                    "facts": {},
                    "concepts": {}
                }]
            }]
        }

        parser = PresentationParser()
        statements = parser.parse_presentation_statements(empty_viewer_json)
        assert statements == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
