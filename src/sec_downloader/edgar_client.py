"""
EDGAR API client for SEC data access.

Handles communication with SEC EDGAR database including:
- Company lookups
- Filing searches
- Document downloads
- Rate limiting and proper headers
"""

import json
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Company, Filing
from .utils import RateLimiter, get_user_agent, normalize_cik, normalize_ticker


logger = logging.getLogger(__name__)


class EdgarError(Exception):
    """Base exception for EDGAR API errors."""
    pass


class EdgarClient:
    """
    Client for accessing SEC EDGAR database.

    Provides methods for:
    - Looking up companies by ticker or CIK
    - Retrieving filing information
    - Downloading filing documents
    """

    BASE_URL = "https://www.sec.gov"
    DATA_URL = "https://data.sec.gov"
    ARCHIVES_URL = f"{BASE_URL}/Archives/edgar/data"

    def __init__(self, user_agent: Optional[str] = None, requests_per_second: int = 8):
        """
        Initialize EDGAR client.

        Args:
            user_agent: Custom user agent string (SEC requires identification)
            requests_per_second: Rate limit (SEC allows 10/sec, we use 8 for safety)
        """
        self.user_agent = user_agent or get_user_agent()
        self.rate_limiter = RateLimiter(max_requests=requests_per_second)

        # Configure requests session with retries
        self.session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set required headers
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov',
        })

        logger.info(f"Initialized EDGAR client with User-Agent: {self.user_agent}")

    def _make_request(self, url: str, **kwargs) -> requests.Response:
        """
        Make rate-limited HTTP request.

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            EdgarError: If request fails
        """
        self.rate_limiter.wait_if_needed()

        try:
            logger.debug(f"Making request to: {url}")
            response = self.session.get(url, timeout=30, **kwargs)
            response.raise_for_status()
            return response

        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise EdgarError(f"Failed to fetch {url}: {e}")

    def lookup_company_by_ticker(self, ticker: str) -> Optional[Company]:
        """
        Look up company information by ticker symbol.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Company object if found, None otherwise
        """
        ticker = normalize_ticker(ticker)
        logger.info(f"Looking up company by ticker: {ticker}")

        try:
            # Try multiple possible endpoints for company tickers
            urls = [
                f"{self.BASE_URL}/files/company_tickers.json",
                f"{self.DATA_URL}/company_tickers.json",
                f"{self.BASE_URL}/Archives/edgar/cik-lookup-data.txt"
            ]

            response = None
            for url in urls:
                try:
                    response = self._make_request(url)
                    break
                except EdgarError:
                    continue

            if response is None:
                raise EdgarError("Could not access any company tickers endpoint")

            tickers_data = response.json()

            # Search for the ticker
            for entry in tickers_data.values():
                if entry.get('ticker', '').upper() == ticker:
                    cik = str(entry['cik_str']).zfill(10)
                    company = Company(
                        cik=cik,
                        ticker=ticker,
                        name=entry.get('title', ''),
                        exchange=entry.get('exchange', '')
                    )
                    logger.info(f"Found company: {company}")
                    return company

            logger.warning(f"No company found for ticker: {ticker}")
            return None

        except Exception as e:
            logger.error(f"Error looking up ticker {ticker}: {e}")
            raise EdgarError(f"Failed to lookup ticker {ticker}: {e}")

    def lookup_company_by_cik(self, cik: str) -> Optional[Company]:
        """
        Look up company information by CIK.

        Args:
            cik: Central Index Key

        Returns:
            Company object if found, None otherwise
        """
        cik = normalize_cik(cik)
        logger.info(f"Looking up company by CIK: {cik}")

        try:
            # Get company facts to retrieve basic info
            url = f"{self.DATA_URL}/api/xbrl/companyfacts/CIK{cik}.json"
            response = self._make_request(url)
            facts_data = response.json()

            company_info = facts_data.get('entityName', '')
            ticker = None

            # Try to get ticker from recent filings
            # This is a best effort - not all companies have tickers
            if 'facts' in facts_data:
                # Look for trading symbol in company facts
                pass  # Complex logic could go here

            company = Company(
                cik=cik,
                ticker=ticker,
                name=company_info
            )
            logger.info(f"Found company: {company}")
            return company

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"No company found for CIK: {cik}")
                return None
            raise
        except Exception as e:
            logger.error(f"Error looking up CIK {cik}: {e}")
            raise EdgarError(f"Failed to lookup CIK {cik}: {e}")

    def get_company_submissions(self, cik: str) -> Dict[str, Any]:
        """
        Get all submissions for a company.

        Args:
            cik: Central Index Key

        Returns:
            Submissions data dictionary
        """
        cik = normalize_cik(cik)
        logger.info(f"Getting submissions for CIK: {cik}")

        try:
            # Use the ATOM feed which is more stable
            atom_url = f"{self.BASE_URL}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb=&owner=exclude&count=40&output=atom"
            response = self._make_request(atom_url)
            return self._parse_atom_feed(response.text, cik)

        except Exception as e:
            logger.error(f"Error getting submissions for CIK {cik}: {e}")
            raise EdgarError(f"Failed to get submissions for CIK {cik}: {e}")

    def _parse_atom_feed(self, atom_text: str, cik: str) -> Dict[str, Any]:
        """Parse ATOM feed format into submissions structure."""
        import xml.etree.ElementTree as ET

        try:
            # Debug: log the ATOM feed content
            logger.debug(f"ATOM feed content: {atom_text[:1000]}...")

            root = ET.fromstring(atom_text)

            # Extract entries from ATOM feed
            filings = []
            for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                title_elem = entry.find('.//{http://www.w3.org/2005/Atom}title')
                link_elem = entry.find('.//{http://www.w3.org/2005/Atom}link')
                updated_elem = entry.find('.//{http://www.w3.org/2005/Atom}updated')

                if title_elem is not None and link_elem is not None:
                    title = title_elem.text or ""
                    href = link_elem.get('href', '')

                    # Extract filing date and accession number from title or link
                    filing_date = ""
                    if updated_elem is not None:
                        filing_date = updated_elem.text.split('T')[0]

                    # Extract accession number from URL
                    accession = ""
                    if '/Archives/edgar/data/' in href:
                        parts = href.split('/')
                        for part in parts:
                            if len(part) == 20 and part.replace('-', '').isdigit():
                                accession = part
                                break

                    # Determine form type from title
                    form = "10-K"  # Default to 10-K for now
                    if "10-Q" in title.upper():
                        form = "10-Q"
                    elif "10-K" in title.upper():
                        form = "10-K"

                    filings.append({
                        'accessionNumber': accession,
                        'filingDate': filing_date,
                        'form': form,
                        'primaryDocument': href.split('/')[-1] if href else "",
                        'primaryDocDescription': title
                    })

            # Return in the format expected by the rest of the code
            return {
                'cik': cik,
                'filings': {
                    'recent': {
                        'accessionNumber': [f.get('accessionNumber', '') for f in filings],
                        'filingDate': [f.get('filingDate', '') for f in filings],
                        'form': [f.get('form', '') for f in filings],
                        'primaryDocument': [f.get('primaryDocument', '') for f in filings],
                        'primaryDocDescription': [f.get('primaryDocDescription', '') for f in filings]
                    }
                }
            }

        except Exception as e:
            logger.error(f"Error parsing ATOM feed: {e}")
            raise EdgarError(f"Failed to parse ATOM feed for CIK {cik}: {e}")

    def search_filings(
        self,
        cik: str,
        form_types: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> List[Filing]:
        """
        Search for filings by company and form type.

        Args:
            cik: Central Index Key
            form_types: List of form types to search for (e.g., ['10-K', '10-Q'])
            start_date: Earliest filing date to include
            end_date: Latest filing date to include
            max_results: Maximum number of results to return

        Returns:
            List of Filing objects
        """
        cik = normalize_cik(cik)
        logger.info(f"Searching filings for CIK {cik}, forms: {form_types}")

        try:
            submissions = self.get_company_submissions(cik)
            filings = []

            recent_filings = submissions.get('filings', {}).get('recent', {})
            if not recent_filings:
                return filings

            # Process recent filings
            forms = recent_filings.get('form', [])
            dates = recent_filings.get('filingDate', [])
            accessions = recent_filings.get('accessionNumber', [])
            report_dates = recent_filings.get('reportDate', [])
            primary_docs = recent_filings.get('primaryDocument', [])

            for i in range(len(forms)):
                form_type = forms[i]
                if form_type not in form_types:
                    continue

                filing_date = datetime.strptime(dates[i], '%Y-%m-%d')

                # Apply date filters
                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue

                report_date = None
                if i < len(report_dates) and report_dates[i]:
                    report_date = datetime.strptime(report_dates[i], '%Y-%m-%d')

                primary_doc = primary_docs[i] if i < len(primary_docs) else None

                filing = Filing(
                    cik=cik,
                    accession_number=accessions[i],
                    form_type=form_type,
                    filing_date=filing_date,
                    report_date=report_date,
                    primary_document=primary_doc,
                    ticker=submissions.get('tickers', [None])[0] if submissions.get('tickers') else None,
                    company_name=submissions.get('name', '')
                )

                # Build document URLs
                filing.filing_url = f"{self.ARCHIVES_URL}/{filing.cik_padded}/{filing.accession_clean}/"

                filings.append(filing)

                if max_results and len(filings) >= max_results:
                    break

            logger.info(f"Found {len(filings)} filings")
            return filings

        except Exception as e:
            logger.error(f"Error searching filings: {e}")
            raise EdgarError(f"Failed to search filings: {e}")

    def get_filing_documents(self, filing: Filing) -> Dict[str, str]:
        """
        Get document list for a filing.

        Args:
            filing: Filing object

        Returns:
            Dictionary mapping document names to URLs
        """
        logger.info(f"Getting documents for filing: {filing.accession_number}")

        try:
            # Try to get the filing index page
            index_url = f"{filing.base_edgar_url}/index.json"

            try:
                response = self._make_request(index_url)
                index_data = response.json()

                documents = {}
                for item in index_data.get('directory', {}).get('item', []):
                    if item.get('type') == 'file':
                        name = item.get('name', '')
                        if name.endswith(('.htm', '.html', '.xml')):
                            documents[name] = f"{filing.base_edgar_url}/{name}"

                return documents

            except EdgarError:
                # Fall back to primary document if available
                if filing.primary_document:
                    return {
                        filing.primary_document: f"{filing.base_edgar_url}/{filing.primary_document}"
                    }

                return {}

        except Exception as e:
            logger.error(f"Error getting filing documents: {e}")
            raise EdgarError(f"Failed to get filing documents: {e}")

    def download_file(self, url: str, local_path: str) -> bool:
        """
        Download a file from EDGAR.

        Args:
            url: URL to download
            local_path: Local path to save file

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Downloading {url} to {local_path}")

        try:
            response = self._make_request(url, stream=True)

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Successfully downloaded to {local_path}")
            return True

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return False