"""
SEC Filing Downloader Module

A comprehensive module for downloading SEC filings (10-K, 10-Q) from EDGAR database.
Integrates with SECDataExtractor_v3 for seamless filing processing pipeline.
"""

__version__ = "1.0.0"
__author__ = "SECDataExtractor_v3"

from .models import Filing, Company
from .edgar_client import EdgarClient
from .filing_search import FilingSearch
from .filing_download import FilingDownload

__all__ = [
    "Filing",
    "Company",
    "EdgarClient",
    "FilingSearch",
    "FilingDownload",
]
