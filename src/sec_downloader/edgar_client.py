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
from typing import Dict, List, Optional, Any, Sequence
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
        self._ticker_cache: Dict[str, Company] = {}
        self._ticker_index_loaded = False

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
        })

        logger.info(f"Initialized EDGAR client with User-Agent: {self.user_agent}")

    def _make_request(
        self,
        url: str,
        allowed_status: Optional[Sequence[int]] = None,
        **kwargs
    ) -> requests.Response:
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

            if allowed_status and response.status_code in allowed_status:
                return response

            response.raise_for_status()
            return response

        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise EdgarError(f"Failed to fetch {url}: {e}")

    def _ensure_ticker_index(self) -> None:
        """Load the SEC ticker index once and cache the results."""

        if self._ticker_index_loaded:
            return

        urls = [
            f"{self.BASE_URL}/files/company_tickers.json",
            f"{self.DATA_URL}/company_tickers.json",
            f"{self.BASE_URL}/Archives/edgar/cik-lookup-data.txt",
        ]

        last_error: Optional[Exception] = None

        for url in urls:
            try:
                response = self._make_request(url)

                if url.endswith('.json'):
                    try:
                        data = response.json()
                    except json.JSONDecodeError as exc:
                        last_error = exc
                        continue

                    entries = data.values() if isinstance(data, dict) else data
                    for entry in entries:
                        ticker_value = (entry.get('ticker') or '').upper().strip()
                        if not ticker_value:
                            continue

                        cik_value = str(entry.get('cik_str') or entry.get('cik') or '').strip()
                        if not cik_value:
                            continue

                        company = Company(
                            cik=cik_value.zfill(10),
                            ticker=ticker_value,
                            name=entry.get('title'),
                            exchange=entry.get('exchange')
                        )
                        self._ticker_cache[ticker_value] = company

                    self._ticker_index_loaded = True
                    return

                # Fallback plain-text format (pipe-delimited)
                text = response.text
                for line in text.splitlines():
                    parts = [part.strip() for part in line.split('|')]
                    if len(parts) < 3:
                        continue
                    cik_value, ticker_value, name_value = parts[:3]
                    if not ticker_value:
                        continue

                    ticker_upper = ticker_value.upper()
                    company = Company(
                        cik=cik_value.zfill(10),
                        ticker=ticker_upper,
                        name=name_value
                    )
                    self._ticker_cache[ticker_upper] = company

                if self._ticker_cache:
                    self._ticker_index_loaded = True
                    return

            except EdgarError as err:
                last_error = err
                continue

        if not self._ticker_index_loaded:
            if last_error:
                raise EdgarError(str(last_error))
            raise EdgarError("Could not access any company tickers endpoint")

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

        cached = self._ticker_cache.get(ticker)
        if cached:
            logger.debug(f"Using cached company lookup for {ticker}")
            return cached

        try:
            self._ensure_ticker_index()
        except EdgarError as e:
            logger.error(f"Error looking up ticker {ticker}: {e}")
            raise EdgarError(f"Failed to lookup ticker {ticker}: {e}")

        company = self._ticker_cache.get(ticker)
        if company:
            logger.info(f"Found company: {company}")
            return company

        logger.warning(f"No company found for ticker: {ticker}")
        return None

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
        """Get submission metadata for a company via the structured submissions API."""

        cik = normalize_cik(cik)
        logger.info(f"Getting submissions for CIK: {cik}")

        submissions_url = f"{self.DATA_URL}/submissions/CIK{cik}.json"

        try:
            response = self._make_request(submissions_url, allowed_status=(404,))
            if response.status_code == 404:
                logger.warning(
                    "Submissions endpoint returned 404 for CIK %s; falling back to legacy feed",
                    cik
                )
                return self._get_company_submissions_atom(cik)
            return response.json()
        except Exception as e:
            logger.error(f"Error getting submissions for CIK {cik}: {e}")
            raise EdgarError(f"Failed to get submissions for CIK {cik}: {e}")

    def _get_company_submissions_atom(self, cik: str) -> Dict[str, Any]:
        """Fallback to the legacy ATOM feed when the submissions API is unavailable."""

        import xml.etree.ElementTree as ET

        atom_url = (
            f"{self.BASE_URL}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
            "&type=&dateb=&owner=exclude&count=100&output=atom"
        )

        try:
            response = self._make_request(atom_url)
            atom_text = response.text
            root = ET.fromstring(atom_text)
            ns = '{http://www.w3.org/2005/Atom}'

            filings: List[Dict[str, Any]] = []

            for entry in root.findall(f'.//{ns}entry'):
                title_elem = entry.find(f'.//{ns}title')
                link_elem = entry.find(f'.//{ns}link')
                updated_elem = entry.find(f'.//{ns}updated')

                if title_elem is None or link_elem is None:
                    continue

                title = title_elem.text or ''
                href = link_elem.get('href', '')
                filing_date = ''
                if updated_elem is not None and updated_elem.text:
                    filing_date = updated_elem.text.split('T')[0]

                accession = ''
                if '/Archives/edgar/data/' in href:
                    parts = href.split('/')
                    for part in parts:
                        if len(part) == 20 and part.replace('-', '').isdigit():
                            accession = part
                            break

                form = ''
                for category in entry.findall(f'.//{ns}category'):
                    term = (category.get('term') or '').strip()
                    label = (category.get('label') or '').lower()
                    if not term:
                        continue
                    if label and 'form' not in label:
                        continue
                    form = term.upper()
                    if form:
                        break

                if not form:
                    title_upper = title.upper()
                    for candidate in ('10-K/A', '10-Q/A', '10-K', '10-Q'):
                        if candidate in title_upper:
                            form = candidate
                            break

                primary_doc = href.split('/')[-1] if href else ''

                filings.append({
                    'accessionNumber': accession,
                    'filingDate': filing_date,
                    'form': form,
                    'primaryDocument': primary_doc,
                })

            return {
                'cik': cik,
                'filings': {
                    'recent': {
                        'accessionNumber': [f['accessionNumber'] for f in filings],
                        'filingDate': [f['filingDate'] for f in filings],
                        'form': [f['form'] for f in filings],
                        'primaryDocument': [f['primaryDocument'] for f in filings],
                    }
                }
            }

        except Exception as e:
            logger.error(f"Failed to fetch ATOM submissions for CIK {cik}: {e}")
            raise EdgarError(f"Failed to fetch submissions for CIK {cik}: {e}")

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
                accession_clean = filing.accession_clean
                if accession_clean:
                    filing.filing_url = f"{self.ARCHIVES_URL}/{filing.cik_padded}/{accession_clean}/"
                else:
                    filing.filing_url = f"{self.ARCHIVES_URL}/{filing.cik_padded}/"

                filings.append(filing)

                if max_results and len(filings) >= max_results:
                    break

            logger.info(f"Found {len(filings)} filings")
            return filings

        except Exception as e:
            logger.error(f"Error searching filings: {e}")
            raise EdgarError(f"Failed to search filings: {e}")

    def get_filing_documents(self, filing: Filing) -> Dict[str, str]:
        """Return a map of document names → URLs for the given filing."""

        logger.info(f"Getting documents for filing: {filing.accession_number}")

        documents: Dict[str, str] = {}

        try:
            # Primary index (lists core submission artifacts)
            index_url = f"{filing.base_edgar_url}/index.json"
            try:
                index_data = self._make_request(index_url).json()
                documents.update(self._extract_documents_from_index(index_data, filing))
            except EdgarError as exc:
                logger.warning(f"Primary index fetch failed: {exc}")

            # Attempt to fetch viewer-specific resources (contains ixviewer.zip)
            viewer_index_urls = [
                f"{filing.base_edgar_url}/index.json?type=viewer",
                f"{filing.base_edgar_url}/index.json?type=download"
            ]
            for viewer_url in viewer_index_urls:
                try:
                    viewer_data = self._make_request(viewer_url).json()
                    docs = self._extract_documents_from_index(viewer_data, filing)
                    if docs:
                        logger.debug(f"Found {len(docs)} viewer documents for {filing.accession_number}")
                    documents.update(docs)
                except EdgarError:
                    continue

            if not documents and filing.primary_document:
                logger.warning("No index JSON documents discovered; falling back to primary document only")
                documents[filing.primary_document] = f"{filing.base_edgar_url}/{filing.primary_document}"

            return documents

        except Exception as e:
            logger.error(f"Error getting filing documents: {e}")
            raise EdgarError(f"Failed to get filing documents: {e}")

    def _extract_documents_from_index(self, index_data: Dict[str, Any], filing: Filing) -> Dict[str, str]:
        """Extract file entries from an EDGAR index.json structure."""

        documents: Dict[str, str] = {}

        if not index_data:
            return documents

        directory = index_data.get('directory', {})
        for item in directory.get('item', []):
            item_type = (item.get('type') or '').lower()
            if item_type == 'dir':
                # Skip nested directories for now – viewer assets live at the root
                continue

            name = item.get('name') or ''
            href = item.get('href') or name
            lower_name = name.lower()

            if not name or lower_name == 'index.json':
                continue

            if href.endswith('/'):
                # Defensive check in case type metadata is missing but href points to a directory
                continue

            if lower_name.endswith(('.md5', '.idx', '.sig')):
                continue

            # Capture common inline XBRL assets (viewer, submission packages, XML, HTML, JSON, ZIP)
            if not lower_name.endswith((
                '.htm', '.html', '.xml', '.json', '.zip', '.xsd', '.xbrl'
            )) and lower_name not in {
                'fullsubmission.txt', 'financial_report.xlsx'
            }:
                # Keep primary documents and ixviewer assets, skip md5/checksum files
                if lower_name.endswith(('.txt', '.csv')):
                    continue

            documents[name] = f"{filing.base_edgar_url}/{href}"

        return documents

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
