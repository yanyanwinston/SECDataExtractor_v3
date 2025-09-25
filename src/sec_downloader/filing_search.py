"""
Filing search functionality for SEC EDGAR database.

Provides high-level interface for searching and filtering SEC filings.
"""

import logging
from datetime import datetime
from typing import List, Optional, Union

from .models import Company, Filing, SearchFilters
from .edgar_client import EdgarClient, EdgarError
from .utils import normalize_ticker, normalize_cik


logger = logging.getLogger(__name__)


class FilingSearchError(Exception):
    """Exception raised during filing search operations."""
    pass


class FilingSearch:
    """
    High-level interface for searching SEC filings.

    Provides methods to search for filings by ticker or CIK,
    with various filtering options.
    """

    def __init__(self, edgar_client: Optional[EdgarClient] = None):
        """
        Initialize filing search.

        Args:
            edgar_client: EDGAR client instance (creates new if None)
        """
        self.client = edgar_client or EdgarClient()

    def search_by_ticker(
        self,
        ticker: str,
        filters: Optional[SearchFilters] = None
    ) -> List[Filing]:
        """
        Search for filings by ticker symbol.

        Args:
            ticker: Stock ticker symbol
            filters: Search filters to apply

        Returns:
            List of Filing objects matching criteria

        Raises:
            FilingSearchError: If search fails or ticker not found
        """
        ticker = normalize_ticker(ticker)
        filters = filters or SearchFilters()

        logger.info(f"Searching filings for ticker {ticker}")

        try:
            # First, look up the company
            company = self.client.lookup_company_by_ticker(ticker)
            if not company:
                raise FilingSearchError(f"Company not found for ticker: {ticker}")

            # Search for filings
            filings = self.client.search_filings(
                cik=company.cik,
                form_types=filters.expanded_form_types,
                start_date=filters.start_date,
                end_date=filters.end_date,
                max_results=filters.max_results
            )

            # Update ticker information in filings
            for filing in filings:
                filing.ticker = ticker
                filing.company_name = company.name

            logger.info(f"Found {len(filings)} filings for {ticker}")
            return filings

        except EdgarError as e:
            logger.error(f"EDGAR error searching for {ticker}: {e}")
            raise FilingSearchError(f"Failed to search filings for {ticker}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error searching for {ticker}: {e}")
            raise FilingSearchError(f"Unexpected error searching for {ticker}: {e}")

    def search_by_cik(
        self,
        cik: str,
        filters: Optional[SearchFilters] = None
    ) -> List[Filing]:
        """
        Search for filings by CIK.

        Args:
            cik: Central Index Key
            filters: Search filters to apply

        Returns:
            List of Filing objects matching criteria

        Raises:
            FilingSearchError: If search fails
        """
        cik = normalize_cik(cik)
        filters = filters or SearchFilters()

        logger.info(f"Searching filings for CIK {cik}")

        try:
            # Look up company info (optional, for enrichment)
            company = self.client.lookup_company_by_cik(cik)

            # Search for filings
            filings = self.client.search_filings(
                cik=cik,
                form_types=filters.expanded_form_types,
                start_date=filters.start_date,
                end_date=filters.end_date,
                max_results=filters.max_results
            )

            # Update company information in filings if available
            if company:
                for filing in filings:
                    filing.ticker = filing.ticker or company.ticker
                    filing.company_name = filing.company_name or company.name

            logger.info(f"Found {len(filings)} filings for CIK {cik}")
            return filings

        except EdgarError as e:
            logger.error(f"EDGAR error searching for CIK {cik}: {e}")
            raise FilingSearchError(f"Failed to search filings for CIK {cik}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error searching for CIK {cik}: {e}")
            raise FilingSearchError(f"Unexpected error searching for CIK {cik}: {e}")

    def search(
        self,
        identifier: str,
        filters: Optional[SearchFilters] = None
    ) -> List[Filing]:
        """
        Search for filings by ticker or CIK (auto-detect).

        Args:
            identifier: Ticker symbol or CIK
            filters: Search filters to apply

        Returns:
            List of Filing objects matching criteria

        Raises:
            FilingSearchError: If search fails
        """
        # Try to determine if it's a CIK or ticker
        if identifier.isdigit() and len(identifier) >= 8:
            # Likely a CIK
            return self.search_by_cik(identifier, filters)
        else:
            # Likely a ticker
            return self.search_by_ticker(identifier, filters)

    def get_latest_filing(
        self,
        identifier: str,
        form_type: str,
        filters: Optional[SearchFilters] = None
    ) -> Optional[Filing]:
        """
        Get the most recent filing of a specific type.

        Args:
            identifier: Ticker symbol or CIK
            form_type: Form type (e.g., '10-K', '10-Q')
            filters: Additional search filters

        Returns:
            Most recent Filing object, or None if not found
        """
        filters = filters or SearchFilters()
        filters.form_types = [form_type]
        filters.max_results = 1

        filings = self.search(identifier, filters)
        return filings[0] if filings else None

    def get_filings_by_year(
        self,
        identifier: str,
        year: int,
        form_types: Optional[List[str]] = None
    ) -> List[Filing]:
        """
        Get all filings for a specific year.

        Args:
            identifier: Ticker symbol or CIK
            year: Year to search
            form_types: List of form types to include

        Returns:
            List of Filing objects for the specified year
        """
        filters = SearchFilters(
            form_types=form_types or ["10-K", "10-Q"],
            start_date=datetime(year, 1, 1),
            end_date=datetime(year, 12, 31)
        )

        return self.search(identifier, filters)

    def get_quarterly_filings(
        self,
        identifier: str,
        year: int,
        quarters: Optional[List[int]] = None
    ) -> List[Filing]:
        """
        Get 10-Q filings for specific quarters.

        Args:
            identifier: Ticker symbol or CIK
            year: Year to search
            quarters: List of quarters (1-4) to include, None for all

        Returns:
            List of 10-Q Filing objects
        """
        filters = SearchFilters(
            form_types=["10-Q"],
            start_date=datetime(year, 1, 1),
            end_date=datetime(year, 12, 31)
        )

        filings = self.search(identifier, filters)

        if quarters is not None:
            # Filter by quarters based on report dates
            filtered_filings = []
            for filing in filings:
                if filing.report_date:
                    quarter = ((filing.report_date.month - 1) // 3) + 1
                    if quarter in quarters:
                        filtered_filings.append(filing)
            filings = filtered_filings

        return filings

    def get_annual_filings(
        self,
        identifier: str,
        years: Optional[List[int]] = None,
        include_amendments: bool = False
    ) -> List[Filing]:
        """
        Get 10-K filings for specific years.

        Args:
            identifier: Ticker symbol or CIK
            years: List of years to include, None for all available
            include_amendments: Whether to include 10-K/A amendments

        Returns:
            List of 10-K Filing objects
        """
        filters = SearchFilters(
            form_types=["10-K"],
            include_amendments=include_amendments
        )

        if years:
            # Search year by year for better control
            all_filings = []
            for year in years:
                year_filters = SearchFilters(
                    form_types=["10-K"],
                    include_amendments=include_amendments,
                    start_date=datetime(year, 1, 1),
                    end_date=datetime(year, 12, 31)
                )
                year_filings = self.search(identifier, year_filters)
                all_filings.extend(year_filings)
            return all_filings
        else:
            return self.search(identifier, filters)

    def find_company(self, identifier: str) -> Optional[Company]:
        """
        Find company information by ticker or CIK.

        Args:
            identifier: Ticker symbol or CIK

        Returns:
            Company object if found, None otherwise
        """
        try:
            if identifier.isdigit() and len(identifier) >= 8:
                return self.client.lookup_company_by_cik(identifier)
            else:
                return self.client.lookup_company_by_ticker(identifier)
        except EdgarError:
            return None