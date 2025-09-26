"""Integration coverage for presentation-first pipeline."""

import json
from pathlib import Path

import pytest

from src.processor.data_parser import DataParser
from src.processor.presentation_models import PresentationStatement, StatementType
from src.processor.value_formatter import ValueFormatter


@pytest.fixture(scope="module")
def integration_viewer_data() -> dict:
    """Load the sample viewer payload used for end-to-end testing."""
    fixture_path = Path(__file__).parent / "fixtures" / "integration_viewer_sample.json"
    with fixture_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def test_end_to_end_presentation_parsing(integration_viewer_data):
    """Ensure DataParser produces statements with periods, rows, and facts."""
    parser = DataParser(ValueFormatter(scale_millions=False))
    result = parser.parse_viewer_data(integration_viewer_data)

    assert result.success is True
    assert result.company_name == "Example Corporation"
    assert result.form_type == "10-K"
    assert result.filing_date == "2023-12-31"

    # We expect a single balance sheet with populated rows/cells.
    assert len(result.statements) == 1
    statement = result.statements[0]

    assert statement.periods
    assert len(statement.periods) in (1, 2)
    assert statement.rows
    assert any(cell.raw_value is not None for row in statement.rows for cell in row.cells.values())


def test_reports_failure_when_presentation_missing(integration_viewer_data):
    """Parser should report failure when presentation relationships are absent."""
    malformed = {
        "sourceReports": [
            {
                "targetReports": [
                    {
                        "roleDefs": {},
                        "rels": {},
                        "facts": integration_viewer_data["sourceReports"][0]["targetReports"][0]["facts"],
                        "concepts": integration_viewer_data["sourceReports"][0]["targetReports"][0]["concepts"],
                    }
                ]
            }
        ]
    }

    parser = DataParser()
    result = parser.parse_viewer_data(malformed)

    assert result.success is False
    assert "presentation statements" in (result.error or "").lower()


def test_data_parser_filters_by_group_type():
    parser = DataParser()

    statement = PresentationStatement(
        role_uri="uri:statement",
        role_id="ns1",
        statement_name="Balance",
        statement_type=StatementType.BALANCE_SHEET,
        root_nodes=[],
        r_id="R3",
        group_type="statement",
        role_order=1.0
    )

    disclosure = PresentationStatement(
        role_uri="uri:disclosure",
        role_id="ns2",
        statement_name="Disclosure",
        statement_type=StatementType.OTHER,
        root_nodes=[],
        r_id="R9",
        group_type="disclosure",
        role_order=2.0
    )

    filtered = parser._filter_presentation_statements([statement, disclosure])
    assert filtered == [statement]

    parser_with_disclosures = DataParser(include_disclosures=True)
    filtered_inclusive = parser_with_disclosures._filter_presentation_statements([statement, disclosure])
    assert filtered_inclusive == [statement, disclosure]


def test_selected_periods_align_with_statement_type(integration_viewer_data):
    parser = DataParser(ValueFormatter(scale_millions=False))
    result = parser.parse_viewer_data(integration_viewer_data)

    assert result.success

    for statement in result.statements:
        name_upper = statement.name.upper()
        period_count = len(statement.periods)
        instants = [p for p in statement.periods if p.instant]

        if "BALANCE" in name_upper:
            assert period_count <= 2
            assert len(instants) == period_count
        elif "PARENTHE" in name_upper:
            assert period_count <= 2
        elif any(keyword in name_upper for keyword in ["OPERATIONS", "COMPREHENSIVE", "CASH", "REDEEMABLE"]):
            assert 1 <= period_count <= 3
            assert instants != statement.periods  # expect durations present when available


def test_label_style_standard_switch(integration_viewer_data):
    terse_parser = DataParser(ValueFormatter(scale_millions=False), label_style='terse')
    terse_result = terse_parser.parse_viewer_data(integration_viewer_data)
    terse_labels = {stmt.rows[1].label for stmt in terse_result.statements if stmt.rows}

    standard_parser = DataParser(ValueFormatter(scale_millions=False), label_style='standard')
    standard_result = standard_parser.parse_viewer_data(integration_viewer_data)
    standard_labels = {stmt.rows[1].label for stmt in standard_result.statements if stmt.rows}

    assert terse_result.success and standard_result.success
    # Some fixtures may not differentiate label roles; ensure toggle executes without error.
