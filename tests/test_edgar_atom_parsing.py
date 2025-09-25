"""Tests for EDGAR ATOM feed parsing and filing filtering."""

from datetime import datetime

import pytest

from src.sec_downloader.edgar_client import EdgarClient


ATOM_FEED_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Company Filings</title>
  <entry>
    <title>10-K/A - Tesla, Inc.</title>
    <category term="10-K/A" label="form type" />
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/0001318605/0000950170-23-004105/0000950170-23-004105-index.htm" />
    <updated>2023-02-13T12:00:00-04:00</updated>
  </entry>
  <entry>
    <title>10-K - Tesla, Inc.</title>
    <category term="10-K" label="form type" />
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/0001318605/0000950170-23-001234/0000950170-23-001234-index.htm" />
    <updated>2023-01-31T12:00:00-04:00</updated>
  </entry>
</feed>
"""


def test_parse_atom_feed_preserves_amendment_form():
    """Ensure the ATOM parser distinguishes between base and amended forms."""
    client = EdgarClient()

    submissions = client._parse_atom_feed(ATOM_FEED_SAMPLE, cik="0001318605")

    forms = submissions["filings"]["recent"]["form"]
    assert forms[0] == "10-K/A"
    assert forms[1] == "10-K"


def test_search_filings_excludes_amendments(monkeypatch):
    """Verify search_filings honours requested form types when amendments exist."""
    client = EdgarClient()

    submissions = client._parse_atom_feed(ATOM_FEED_SAMPLE, cik="0001318605")
    submissions.update({
        "name": "Tesla, Inc.",
        "tickers": ["TSLA"],
    })

    # Patch network call so search_filings uses our synthetic data
    monkeypatch.setattr(client, "get_company_submissions", lambda cik: submissions)

    # Request only the base form - amended filing should be filtered out
    filings = client.search_filings(
        cik="1318605",
        form_types=["10-K"],
        max_results=5,
    )

    assert len(filings) == 1
    assert filings[0].form_type == "10-K"
    assert filings[0].filing_date == datetime(2023, 1, 31)


def test_search_filings_can_return_amendments(monkeypatch):
    """Ensure callers can explicitly request amended filings when needed."""
    client = EdgarClient()

    submissions = client._parse_atom_feed(ATOM_FEED_SAMPLE, cik="0001318605")
    monkeypatch.setattr(client, "get_company_submissions", lambda cik: submissions)

    filings = client.search_filings(
        cik="1318605",
        form_types=["10-K/A"],
        max_results=5,
    )

    assert len(filings) == 1
    assert filings[0].form_type == "10-K/A"
    assert filings[0].filing_date == datetime(2023, 2, 13)
