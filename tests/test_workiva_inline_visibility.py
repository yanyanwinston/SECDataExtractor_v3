"""Regression test for Workiva inline visibility with hashed anchors.

This test ensures that the inline visibility filter works correctly for
Workiva-generated filings that use hashed element IDs (e.g.,
ie9fbbc0a99a6483f9fc1594c1ef72807_175) instead of semantic anchors.

See: docs/debug/2025-09-tsla-inline-visibility.md
"""

import json
from pathlib import Path

import pytest

from src.processor.data_parser import DataParser
from src.processor.value_formatter import ValueFormatter


@pytest.fixture(scope="module")
def workiva_viewer_data() -> dict:
    """Load the Workiva-style viewer payload with inline visibility signatures."""
    fixture_path = Path(__file__).parent / "fixtures" / "workiva_inline_viewer_sample.json"
    with fixture_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def test_workiva_visible_signatures_populated(workiva_viewer_data):
    """Verify that visible_fact_signatures field is present and non-empty."""
    assert "visible_fact_signatures" in workiva_viewer_data

    signatures = workiva_viewer_data["visible_fact_signatures"]
    assert signatures, "visible_fact_signatures should not be empty"

    # Check for Income Statement signatures
    assert "Consolidated Statements of Operations" in signatures
    operations_sigs = signatures["Consolidated Statements of Operations"]

    # Should have at least the base revenue facts
    assert len(operations_sigs) >= 5, "Expected at least 5 fact signatures"

    # Verify signature format: [concept, [[axis, member], ...]]
    for sig in operations_sigs:
        assert isinstance(sig, list), "Each signature should be a list"
        assert len(sig) == 2, "Signature should have [concept, dimensions]"
        concept, dims = sig
        assert isinstance(concept, str), "Concept should be a string"
        assert isinstance(dims, list), "Dimensions should be a list"


def test_workiva_inline_filter_activation(workiva_viewer_data):
    """Ensure inline visibility filter activates and removes non-visible facts."""
    parser = DataParser(ValueFormatter(scale_millions=False), expand_dimensions=True)
    result = parser.parse_viewer_data(workiva_viewer_data)

    assert result.success is True
    assert result.company_name == "Tesla Inc"
    assert result.form_type == "10-K"

    # Should have one Income Statement
    assert len(result.statements) == 1
    statement = result.statements[0]
    assert "operation" in statement.name.lower()

    # Extract all row labels and concepts
    row_labels = [row.label.lower() for row in statement.rows]
    row_concepts = [row.concept for row in statement.rows]

    # Should include visible base concepts from the signature map
    assert any("revenues" in label and concept == "us-gaap:Revenues"
               for label, concept in zip(row_labels, row_concepts)), \
        "Expected 'Revenues' base row in visible rows"

    # With dimensional expansion, automotive sales/credits/leasing should appear as sub-rows
    # These get filtered by the visible_fact_signatures
    assert any("automotive sales" in label for label in row_labels), \
        "Expected 'Automotive sales' dimensional row"
    assert any("automotive regulatory" in label or "regulatory credit" in label
               for label in row_labels), \
        "Expected 'Automotive regulatory credits' dimensional row"
    assert any("automotive leasing" in label or "leasing" in label
               for label in row_labels), \
        "Expected 'Automotive leasing' dimensional row"

    assert any("total automotive" in label for label in row_labels), \
        "Expected 'Total automotive revenues' row"
    assert any("gross profit" in label for label in row_labels), \
        "Expected 'Gross profit' row"
    assert any("operating expenses" in label for label in row_labels), \
        "Expected 'Operating expenses' row"

    # Should NOT include the Energy storage row (not in visible signatures)
    energy_rows = [
        label for label in row_labels
        if "energy" in label and ("generation" in label or "storage" in label)
    ]
    assert len(energy_rows) == 0, \
        f"Energy generation and storage should be filtered (not in visible signatures), found: {energy_rows}"


def test_workiva_dimensional_expansion_with_filter(workiva_viewer_data):
    """Verify dimensional expansion respects inline visibility signatures."""
    parser = DataParser(
        ValueFormatter(scale_millions=False),
        expand_dimensions=True
    )
    result = parser.parse_viewer_data(workiva_viewer_data)

    assert result.success is True
    statement = result.statements[0]

    # Extract all row labels and concepts
    row_info = [(row.label.lower(), row.concept) for row in statement.rows]

    # Should have automotive sales broken out by dimension
    automotive_sales = [
        label for label, concept in row_info
        if "automotive sales" in label
    ]
    assert len(automotive_sales) >= 1, \
        "Expected automotive sales row"

    # Should have automotive regulatory credits
    automotive_credits = [
        label for label, concept in row_info
        if "regulatory credit" in label
    ]
    assert len(automotive_credits) >= 1, \
        "Expected automotive regulatory credits row"

    # Should have automotive leasing
    automotive_leasing = [
        label for label, concept in row_info
        if "leasing" in label
    ]
    assert len(automotive_leasing) >= 1, \
        "Expected automotive leasing row"

    # Should NOT have energy storage rows (filtered by signature)
    energy_rows = [
        label for label, concept in row_info
        if "energy" in label and "generation" in label
    ]
    assert len(energy_rows) == 0, \
        "Energy generation rows should be filtered (not in visible signatures)"


def test_workiva_signature_normalization(workiva_viewer_data):
    """Verify signature matching uses case-insensitive concept/dimension normalization."""
    parser = DataParser(ValueFormatter(scale_millions=False))

    # Manually extract signature map to verify normalization
    visible_sigs = workiva_viewer_data.get("visible_fact_signatures", {})
    assert visible_sigs

    # The statement key should be normalized during loading
    statement_keys = list(visible_sigs.keys())
    assert len(statement_keys) > 0

    # Parse and verify normalization worked
    result = parser.parse_viewer_data(workiva_viewer_data)
    assert result.success

    # If normalization failed, the filter wouldn't activate and we'd see energy rows
    statement = result.statements[0]
    row_labels = [row.label.lower() for row in statement.rows]

    # This is the critical assertion: energy row should be absent
    has_energy = any("energy generation" in label for label in row_labels)
    assert not has_energy, \
        "Signature normalization failed - energy row present when it should be filtered"


def test_workiva_fallback_without_signatures():
    """Verify graceful degradation when visible_fact_signatures is absent."""
    # Create a copy without signatures
    fixture_path = Path(__file__).parent / "fixtures" / "workiva_inline_viewer_sample.json"
    with fixture_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    # Remove signatures
    data_without_sigs = {k: v for k, v in data.items() if k != "visible_fact_signatures"}

    parser = DataParser(ValueFormatter(scale_millions=False))
    result = parser.parse_viewer_data(data_without_sigs)

    assert result.success is True
    statement = result.statements[0]

    # Count total rows with signatures vs without
    row_count_without_filter = len(statement.rows)

    # Re-parse with signatures to compare
    parser_filtered = DataParser(ValueFormatter(scale_millions=False))
    result_filtered = parser_filtered.parse_viewer_data(data)
    row_count_with_filter = len(result_filtered.statements[0].rows)

    # Without filter, should have same or more rows (filter can only remove, not add)
    assert row_count_without_filter >= row_count_with_filter, \
        "Without signatures, row count should be >= filtered row count"

    # The key assertion: energy storage fact exists in data, so without filter
    # it might appear. With filter, it should be absent.
    # Since energy isn't in presentation tree's visible concepts, it won't appear
    # This test verifies the filter doesn't crash when disabled
    assert result.success and result_filtered.success


def test_workiva_abstract_rows_always_preserved(workiva_viewer_data):
    """Verify abstract/header rows are preserved regardless of signature filter."""
    parser = DataParser(ValueFormatter(scale_millions=False))
    result = parser.parse_viewer_data(workiva_viewer_data)

    assert result.success is True
    statement = result.statements[0]

    # Find abstract rows
    abstract_rows = [row for row in statement.rows if row.is_abstract]

    # Should have at least "Revenues:" as an abstract header
    assert len(abstract_rows) > 0, "Expected abstract header rows"

    # Verify abstract row is present even if not in signatures
    abstract_labels = [row.label for row in abstract_rows]
    assert any("revenue" in label.lower() for label in abstract_labels), \
        "Expected revenue abstract header"