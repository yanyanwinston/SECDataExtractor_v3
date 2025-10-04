"""Tests for silver layer exporter utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.processor import (
    BronzeFilingMetadata,
    DataParser,
)
from src.processor.silver_exporter import (
    SilverWriter,
    build_statement_facts_dataframe,
    build_statement_lines_dataframe,
)


def _load_sample_viewer() -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "integration_viewer_sample.json"
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_sample_tables():
    viewer_data = _load_sample_viewer()
    parser = DataParser()
    result = parser.parse_viewer_data(viewer_data)
    assert result.success
    tables = parser.get_latest_statement_tables()
    assert tables
    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data, accession_number="000162828025003063"
    )
    return viewer_data, tables, metadata


def test_build_statement_lines_dataframe_contains_expected_columns():
    viewer_data, tables, metadata = _parse_sample_tables()

    df = build_statement_lines_dataframe(tables, metadata, viewer_data)

    assert not df.empty
    expected_columns = {
        "filing_id",
        "entity_cik",
        "accession_number",
        "statement_role_id",
        "role_name",
        "line_order",
        "concept_qname",
        "label",
        "is_abstract",
        "line_depth",
    }
    assert expected_columns.issubset(df.columns)

    first_row = df.iloc[0]
    assert first_row["filing_id"] == metadata.filing_id
    assert first_row["entity_cik"] == metadata.entity_cik


def test_build_statement_facts_dataframe_contains_fact_rows():
    viewer_data, tables, metadata = _parse_sample_tables()

    df = build_statement_facts_dataframe(tables, metadata, viewer_data)

    assert not df.empty
    assert {"value_raw", "period_end", "dimension_hash"}.issubset(df.columns)
    assert (df["filing_id"] == metadata.filing_id).all()

    cash_facts = df[df["concept_qname"] == "us-gaap:CashAndCashEquivalentsAtCarryingValue"]
    assert not cash_facts.empty
    assert (cash_facts["unit"] == "USD").all()


def test_silver_writer_persists_parquet(tmp_path):
    pytest.importorskip("pyarrow")

    viewer_data, tables, metadata = _parse_sample_tables()

    lines_df = build_statement_lines_dataframe(tables, metadata, viewer_data)
    facts_df = build_statement_facts_dataframe(tables, metadata, viewer_data)

    writer = SilverWriter(base_dir=tmp_path / "silver")
    result = writer.write(metadata, lines_df, facts_df)

    assert result.statement_lines_path and result.statement_lines_path.exists()
    assert result.statement_facts_path and result.statement_facts_path.exists()

    loaded_lines = pd.read_parquet(result.statement_lines_path)
    loaded_facts = pd.read_parquet(result.statement_facts_path)

    assert len(loaded_lines) == len(lines_df)
    assert len(loaded_facts) == len(facts_df)
