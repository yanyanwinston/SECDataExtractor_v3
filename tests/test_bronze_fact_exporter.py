"""Tests for constructing bronze fact_long tables."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.processor import (
    BronzeFilingMetadata,
    DataParser,
    build_fact_long_dataframe,
)


def _load_sample_viewer() -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "integration_viewer_sample.json"
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_build_fact_long_dataframe_produces_records():
    viewer_data = _load_sample_viewer()
    parser = DataParser()

    result = parser.parse_viewer_data(viewer_data)
    assert result.success

    tables = parser.get_latest_statement_tables()
    assert tables, "Expected statement tables to be captured for bronze export"

    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data, accession_number="000162828025003063"
    )

    fact_long_df = build_fact_long_dataframe(tables, metadata, viewer_data)

    assert not fact_long_df.empty
    assert set(["filing_id", "concept_qname", "value_raw"]).issubset(
        fact_long_df.columns
    )
    assert (fact_long_df["filing_id"] == metadata.filing_id).all()
    assert (fact_long_df["entity_cik"] == metadata.entity_cik).all()

    # Ensure value parsing retained expected numeric data
    cash_facts = fact_long_df[fact_long_df["concept_qname"] == "us-gaap:CashAndCashEquivalentsAtCarryingValue"]
    assert not cash_facts.empty
    assert (cash_facts["unit"] == "USD").all()

    # DataFrame should be parquet round-trippable
    pytest.importorskip("pyarrow", reason="pyarrow required for parquet round-trip")
    temp_path = Path("temp_fact_long.parquet")
    try:
        fact_long_df.to_parquet(temp_path, index=False)
        reloaded = pd.read_parquet(temp_path)
        assert len(reloaded) == len(fact_long_df)
    finally:
        if temp_path.exists():
            temp_path.unlink()
