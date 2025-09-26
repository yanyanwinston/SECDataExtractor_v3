#!/usr/bin/env python3
"""
Test presentation-based data models

Tests the new presentation models that represent XBRL presentation structure
for exact visual fidelity with the original filing presentation.
"""

import pytest
from src.processor.presentation_models import (
    StatementType,
    PresentationNode,
    PresentationStatement,
    StatementRow,
    StatementTable,
    classify_statement_type,
)
from src.processor.data_models import Period, Cell


class TestStatementType:
    """Test StatementType enum."""

    def test_statement_type_values(self):
        """Test that all statement types have correct values."""
        assert StatementType.BALANCE_SHEET.value == "balance_sheet"
        assert StatementType.INCOME_STATEMENT.value == "income_statement"
        assert StatementType.CASH_FLOWS.value == "cash_flows"
        assert StatementType.COMPREHENSIVE_INCOME.value == "comprehensive_income"
        assert StatementType.EQUITY.value == "equity"
        assert StatementType.OTHER.value == "other"

    def test_classify_statement_type(self):
        """Test statement type classification from names."""
        # Balance sheet variations
        assert (
            classify_statement_type("Consolidated Balance Sheets")
            == StatementType.BALANCE_SHEET
        )
        assert (
            classify_statement_type("Statement of Financial Position")
            == StatementType.BALANCE_SHEET
        )
        assert classify_statement_type("balance sheet") == StatementType.BALANCE_SHEET

        # Income statement variations
        assert (
            classify_statement_type("Consolidated Statements of Operations")
            == StatementType.INCOME_STATEMENT
        )
        assert (
            classify_statement_type("Income Statement")
            == StatementType.INCOME_STATEMENT
        )
        assert (
            classify_statement_type("Statement of Income")
            == StatementType.INCOME_STATEMENT
        )

        # Cash flows
        assert (
            classify_statement_type("Consolidated Statements of Cash Flows")
            == StatementType.CASH_FLOWS
        )
        assert (
            classify_statement_type("Cash Flow Statement") == StatementType.CASH_FLOWS
        )

        # Comprehensive income
        assert (
            classify_statement_type("Consolidated Statements of Comprehensive Income")
            == StatementType.COMPREHENSIVE_INCOME
        )

        # Equity
        assert (
            classify_statement_type("Consolidated Statements of Shareholders' Equity")
            == StatementType.EQUITY
        )
        assert (
            classify_statement_type("Statement of Stockholders' Equity")
            == StatementType.EQUITY
        )

        # Other
        assert (
            classify_statement_type("Notes to Financial Statements")
            == StatementType.OTHER
        )
        assert classify_statement_type("Unknown Statement") == StatementType.OTHER


class TestPresentationNode:
    """Test PresentationNode data model."""

    def test_create_node(self):
        """Test creating a basic presentation node."""
        node = PresentationNode(
            concept="us-gaap:Assets",
            label="Assets",
            order=1.0,
            depth=0,
            abstract=True,
            preferred_label_role="totalLabel",
        )

        assert node.concept == "us-gaap:Assets"
        assert node.label == "Assets"
        assert node.order == 1.0
        assert node.depth == 0
        assert node.abstract is True
        assert node.preferred_label_role == "totalLabel"
        assert len(node.children) == 0

    def test_add_child(self):
        """Test adding child nodes."""
        parent = PresentationNode("us-gaap:Assets", "Assets", 1.0, 0, True)
        child1 = PresentationNode(
            "us-gaap:CurrentAssets", "Current Assets", 1.0, 0, True
        )
        child2 = PresentationNode("us-gaap:Cash", "Cash", 2.0, 0, False)

        parent.add_child(child1)
        parent.add_child(child2)

        assert len(parent.children) == 2
        assert child1.depth == 1
        assert child2.depth == 1
        assert child1 in parent.children
        assert child2 in parent.children

    def test_get_all_nodes_flat(self):
        """Test flattening presentation tree."""
        # Build tree: Assets -> Current Assets -> Cash
        root = PresentationNode("us-gaap:Assets", "Assets", 1.0, 0, True)
        current = PresentationNode(
            "us-gaap:CurrentAssets", "Current Assets", 1.0, 0, True
        )
        cash = PresentationNode("us-gaap:Cash", "Cash", 1.0, 0, False)

        root.add_child(current)
        current.add_child(cash)

        # Flatten tree
        flat_nodes = root.get_all_nodes_flat()

        assert len(flat_nodes) == 3
        assert flat_nodes[0] == (root, 0)
        assert flat_nodes[1] == (current, 1)
        assert flat_nodes[2] == (cash, 2)

    def test_node_string_representation(self):
        """Test string representation of nodes."""
        abstract_node = PresentationNode("us-gaap:Assets", "Assets", 1.0, 0, True)
        concrete_node = PresentationNode("us-gaap:Cash", "Cash", 1.0, 1, False)

        assert "Assets (abstract)" in str(abstract_node)
        assert "Cash" in str(concrete_node)
        assert "(abstract)" not in str(concrete_node)


class TestPresentationStatement:
    """Test PresentationStatement data model."""

    def test_create_statement(self):
        """Test creating a presentation statement."""
        stmt = PresentationStatement(
            role_uri="http://example.com/role/BalanceSheet",
            role_id="ns9",
            statement_name="Consolidated Balance Sheets",
            statement_type=StatementType.BALANCE_SHEET,
        )

        assert stmt.role_uri == "http://example.com/role/BalanceSheet"
        assert stmt.role_id == "ns9"
        assert stmt.statement_name == "Consolidated Balance Sheets"
        assert stmt.statement_type == StatementType.BALANCE_SHEET
        assert len(stmt.root_nodes) == 0

    def test_get_all_nodes_flat(self):
        """Test flattening statement with multiple root nodes."""
        stmt = PresentationStatement(
            "", "ns9", "Balance Sheet", StatementType.BALANCE_SHEET
        )

        # Create two root trees
        assets = PresentationNode("us-gaap:Assets", "Assets", 1.0, 0, True)
        cash = PresentationNode("us-gaap:Cash", "Cash", 1.0, 0, False)
        assets.add_child(cash)

        liabilities = PresentationNode(
            "us-gaap:Liabilities", "Liabilities", 2.0, 0, True
        )
        payables = PresentationNode("us-gaap:Payables", "Payables", 1.0, 0, False)
        liabilities.add_child(payables)

        assets.depth = 0
        liabilities.depth = 0
        stmt.root_nodes = [assets, liabilities]

        # Flatten (should respect root node order)
        flat_nodes = stmt.get_all_nodes_flat()

        assert len(flat_nodes) == 4
        # Should be ordered by root node order (Assets=1.0, Liabilities=2.0)
        concepts = [node.concept for node, depth in flat_nodes]
        assert concepts == [
            "us-gaap:Assets",
            "us-gaap:Cash",
            "us-gaap:Liabilities",
            "us-gaap:Payables",
        ]

    def test_get_short_name(self):
        """Test generating short names for Excel sheets."""
        # Test different statement types
        balance_sheet = PresentationStatement(
            "", "", "Consolidated Balance Sheets", StatementType.BALANCE_SHEET
        )
        assert balance_sheet.get_short_name() == "Balance Sheet"

        income_stmt = PresentationStatement(
            "",
            "",
            "Consolidated Statements of Operations",
            StatementType.INCOME_STATEMENT,
        )
        assert income_stmt.get_short_name() == "Income Statement"

        cash_flows = PresentationStatement(
            "", "", "Consolidated Statements of Cash Flows", StatementType.CASH_FLOWS
        )
        assert cash_flows.get_short_name() == "Cash Flows"

        # Test long name truncation
        long_name = PresentationStatement(
            "",
            "",
            "Very Long Statement Name That Exceeds Twenty Characters",
            StatementType.OTHER,
        )
        assert len(long_name.get_short_name()) == 20


class TestStatementRow:
    """Test StatementRow data model."""

    def test_create_row(self):
        """Test creating a statement row."""
        node = PresentationNode(
            "us-gaap:Cash", "Cash and Cash Equivalents", 1.0, 1, False
        )
        row = StatementRow(node=node)

        assert row.node == node
        assert row.label == "Cash and Cash Equivalents"
        assert row.concept == "us-gaap:Cash"
        assert row.depth == 1
        assert row.is_abstract is False
        assert len(row.cells) == 0

    def test_has_data(self):
        """Test detecting rows with data."""
        node = PresentationNode("us-gaap:Cash", "Cash", 1.0, 1, False)
        row = StatementRow(node=node)

        # No cells - no data
        assert row.has_data() is False

        # Empty cells - no data
        empty_cell = Cell(
            value="", raw_value=None, unit=None, decimals=None, period="2023"
        )
        row.cells["2023"] = empty_cell
        assert row.has_data() is False

        # Placeholder dash should not count as data
        dash_cell = Cell(
            value="—", raw_value=None, unit=None, decimals=None, period="2023"
        )
        row.cells["2023-dash"] = dash_cell
        assert row.has_data() is False

        # Cell with data
        data_cell = Cell(
            value="1,000", raw_value=1000.0, unit="usd", decimals=-3, period="2022"
        )
        row.cells["2022"] = data_cell
        assert row.has_data() is True


class TestStatementTable:
    """Test StatementTable data model."""

    def setup_method(self):
        """Setup test data."""
        self.periods = [
            Period(label="2023", end_date="2023-12-31", instant=True),
            Period(label="2022", end_date="2022-12-31", instant=True),
        ]

        self.statement = PresentationStatement(
            role_uri="http://example.com/role/BalanceSheet",
            role_id="ns9",
            statement_name="Consolidated Balance Sheets",
            statement_type=StatementType.BALANCE_SHEET,
        )

    def test_create_table(self):
        """Test creating a statement table."""
        table = StatementTable(statement=self.statement, periods=self.periods)

        assert table.statement == self.statement
        assert table.periods == self.periods
        assert len(table.rows) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
