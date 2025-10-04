"""Tests for bronze layer writer utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.processor.bronze_writer import (
    BronzeFilingMetadata,
    BronzeWriter,
)


def _sample_viewer_payload() -> dict:
    return {
        "meta": {
            "companyName": "Example Corporation",
            "formType": "10-K",
            "filingDate": "2023-12-31",
            "toolVersions": {"exporter": "0.1.0"},
        },
        "facts": {
            "f-entity-cik": {
                "a": {"c": "dei:EntityCentralIndexKey", "v": "123456789"}
            },
            "f-entity-name": {
                "a": {"c": "dei:EntityRegistrantName", "v": "Example Corporation"}
            },
            "f-document-type": {
                "a": {"c": "dei:DocumentType", "v": "10-K"}
            },
            "f-period-end": {
                "a": {"c": "dei:DocumentPeriodEndDate", "v": "2023-12-31"}
            },
        },
        "meta_links": {"instance": {}},
        "role_map": {},
    }


def test_metadata_from_viewer_payload_extracts_provenance():
    viewer_data = _sample_viewer_payload()

    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data, accession_number="000162828025003063"
    )

    assert metadata.entity_cik == "0123456789"
    assert metadata.accession_number == "0001628280-25-003063"
    assert metadata.filing_id == "0123456789-000162828025003063"
    assert metadata.company_name == "Example Corporation"
    assert metadata.form_type == "10-K"
    assert metadata.filing_date == "2023-12-31"
    assert metadata.tool_versions == {"exporter": "0.1.0"}


def test_bronze_writer_emits_expected_files(tmp_path):
    viewer_data = _sample_viewer_payload()
    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data, accession_number="000162828025003063"
    )

    writer = BronzeWriter(base_dir=tmp_path / "bronze")
    result = writer.write(viewer_data, metadata)

    assert result.viewer_json_path.exists()
    assert result.metadata_path.exists()
    assert result.metalinks_path and result.metalinks_path.exists()
    assert result.fact_long_path is None

    with result.viewer_json_path.open("r", encoding="utf-8") as handle:
        viewer_payload = json.load(handle)
    assert "meta_links" not in viewer_payload

    with result.metadata_path.open("r", encoding="utf-8") as handle:
        stored_metadata = json.load(handle)

    assert stored_metadata["filing_id"] == metadata.filing_id
    assert stored_metadata["entity_cik"] == metadata.entity_cik
    assert stored_metadata["accession_number"] == metadata.accession_number

    expected_dir = Path(tmp_path) / "bronze" / metadata.entity_cik / metadata.accession_number
    assert result.base_path == expected_dir


def test_bronze_writer_writes_fact_long(tmp_path):
    pytest.importorskip("pyarrow")

    viewer_data = _sample_viewer_payload()
    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data, accession_number="000162828025003063"
    )

    fact_long_df = pd.DataFrame(
        [
            {
                "filing_id": metadata.filing_id,
                "concept_qname": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            }
        ]
    )

    writer = BronzeWriter(base_dir=tmp_path / "bronze")
    result = writer.write(viewer_data, metadata, fact_long_df=fact_long_df)

    assert result.fact_long_path is not None
    assert result.fact_long_path.exists()

    loaded = pd.read_parquet(result.fact_long_path)
    assert loaded.iloc[0]["concept_qname"] == "us-gaap:CashAndCashEquivalentsAtCarryingValue"
