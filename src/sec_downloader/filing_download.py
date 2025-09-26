"""
Filing download functionality with progress tracking and parallel processing.
"""

import json
import logging
import asyncio
import aiohttp
import aiofiles
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from tqdm import tqdm
import zipfile
from urllib.parse import urlparse
import shutil

from .models import Filing, DownloadConfig, DownloadResult
from .edgar_client import EdgarClient, EdgarError
from .utils import ensure_directory, create_safe_filename, get_file_size_mb


logger = logging.getLogger(__name__)


class FilingDownloadError(Exception):
    """Exception raised during filing download operations."""
    pass


class FilingDownload:
    """
    Handles downloading of SEC filings with progress tracking and parallel processing.
    """

    def __init__(self, edgar_client: Optional[EdgarClient] = None):
        """
        Initialize filing downloader.

        Args:
            edgar_client: EDGAR client instance (creates new if None)
        """
        self.client = edgar_client or EdgarClient()

    def download_filing(
        self,
        filing: Filing,
        config: DownloadConfig
    ) -> DownloadResult:
        """
        Download a single filing with all its documents.

        Args:
            filing: Filing object to download
            config: Download configuration

        Returns:
            DownloadResult object with status and paths
        """
        logger.info(f"Downloading filing: {filing.display_name}")

        try:
            # Create output directory
            filing_dir = config.get_filing_dir(filing)
            ensure_directory(filing_dir)

            # Get document list
            documents = self.client.get_filing_documents(filing)
            if not documents:
                # Try to construct primary document URL
                if filing.primary_document:
                    documents = {
                        filing.primary_document: f"{filing.base_edgar_url}/{filing.primary_document}"
                    }
                else:
                    return DownloadResult(
                        filing=filing,
                        success=False,
                        error="No documents found for filing"
                    )

            downloaded_files = []
            primary_doc_found = False

            ixviewer_zip_path: Optional[Path] = None

            # Download each document
            for doc_name, doc_url in documents.items():
                # Skip non-essential files if not requested
                if not config.include_exhibits and self._is_exhibit(doc_name):
                    continue

                # Create safe filename
                safe_filename = create_safe_filename(doc_name)
                local_path = filing_dir / safe_filename

                # Download the file
                success = self._download_file_with_retry(
                    doc_url,
                    local_path,
                    config.retry_attempts,
                    config.timeout_seconds
                )

                if success:
                    downloaded_files.append(str(local_path))
                    if doc_name == filing.primary_document or doc_name.endswith(('.htm', '.html')):
                        primary_doc_found = True
                    if safe_filename.lower() == 'ixviewer.zip':
                        ixviewer_zip_path = local_path
                    logger.debug(f"Downloaded: {doc_name}")
                else:
                    logger.warning(f"Failed to download: {doc_name}")

            if not downloaded_files:
                return DownloadResult(
                    filing=filing,
                    success=False,
                    error="No files were successfully downloaded"
                )

            # Extract ixviewer.zip so viewer.json is readily available
            if ixviewer_zip_path and ixviewer_zip_path.exists():
                try:
                    self._extract_ixviewer(ixviewer_zip_path, filing_dir)
                except Exception as exc:
                    logger.warning(f"Failed to extract ixviewer.zip for {filing.display_name}: {exc}")

            # Save metadata
            metadata_path = self._save_filing_metadata(filing, filing_dir, documents)

            # Verify downloads if requested
            if config.verify_downloads:
                self._verify_downloads(downloaded_files)

            result = DownloadResult(
                filing=filing,
                success=True,
                local_path=filing_dir,
                downloaded_files=downloaded_files,
                metadata_path=metadata_path
            )

            logger.info(f"Successfully downloaded {len(downloaded_files)} files for {filing.display_name}")
            return result

        except Exception as e:
            logger.error(f"Error downloading filing {filing.display_name}: {e}")
            return DownloadResult(
                filing=filing,
                success=False,
                error=str(e)
            )

    def _extract_ixviewer(self, zip_path: Path, filing_dir: Path) -> None:
        """Extract ixviewer.zip into a dedicated directory."""

        target_dir = filing_dir / 'ixviewer'
        if target_dir.exists():
            logger.debug(f"Removing existing ixviewer directory at {target_dir}")
            shutil.rmtree(target_dir)

        with zipfile.ZipFile(zip_path, 'r') as archive:
            archive.extractall(target_dir)

        logger.info(f"Extracted ixviewer bundle to {target_dir}")

    def download_filings(
        self,
        filings: List[Filing],
        config: DownloadConfig,
        show_progress: bool = True
    ) -> List[DownloadResult]:
        """
        Download multiple filings with progress tracking.

        Args:
            filings: List of Filing objects to download
            config: Download configuration
            show_progress: Whether to show progress bar

        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Starting batch download of {len(filings)} filings")

        results = []
        progress_bar = None

        if show_progress:
            progress_bar = tqdm(
                total=len(filings),
                desc="Downloading filings",
                unit="filing"
            )

        # Use ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=config.max_parallel) as executor:
            # Submit all download tasks
            future_to_filing = {
                executor.submit(self.download_filing, filing, config): filing
                for filing in filings
            }

            # Collect results as they complete
            for future in as_completed(future_to_filing):
                filing = future_to_filing[future]
                try:
                    result = future.result()
                    results.append(result)

                    if progress_bar:
                        status = "✓" if result.success else "✗"
                        progress_bar.set_postfix_str(f"{status} {filing.display_name}")
                        progress_bar.update(1)

                except Exception as e:
                    logger.error(f"Unexpected error downloading {filing.display_name}: {e}")
                    results.append(DownloadResult(
                        filing=filing,
                        success=False,
                        error=f"Unexpected error: {e}"
                    ))

                    if progress_bar:
                        progress_bar.set_postfix_str(f"✗ {filing.display_name}")
                        progress_bar.update(1)

        if progress_bar:
            progress_bar.close()

        # Summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        logger.info(f"Download completed: {successful} successful, {failed} failed")

        return results

    def _download_file_with_retry(
        self,
        url: str,
        local_path: Path,
        max_retries: int,
        timeout_seconds: int
    ) -> bool:
        """
        Download a file with retry logic.

        Args:
            url: URL to download
            local_path: Local path to save
            max_retries: Maximum number of retry attempts
            timeout_seconds: Timeout for each attempt

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries + 1):
            try:
                success = self.client.download_file(str(url), str(local_path))
                if success:
                    return True

            except Exception as e:
                logger.warning(f"Download attempt {attempt + 1} failed for {url}: {e}")

                if attempt < max_retries:
                    # Wait before retrying (exponential backoff)
                    import time
                    time.sleep(2 ** attempt)

        return False

    def _is_exhibit(self, filename: str) -> bool:
        """
        Check if a filename appears to be an exhibit.

        Args:
            filename: Filename to check

        Returns:
            True if likely an exhibit
        """
        filename_lower = filename.lower()

        # Keep core inline XBRL resources even though they share exhibit-style extensions
        essential_names = {
            'filingsummary.xml',
            'metalink.json',  # legacy typo seen in some filings
            'metalinks.json'
        }

        if any(filename_lower.endswith(suffix) for suffix in (
            '_pre.xml', '_cal.xml', '_lab.xml', '_def.xml', '.xsd'
        )):
            return False

        if filename_lower in essential_names:
            return False

        # Common exhibit patterns we want to skip by default
        exhibit_markers = (
            'ex-',
            'exhibit',
            'exh',
        )

        if any(marker in filename_lower for marker in exhibit_markers):
            return True

        # Cover pages/graphics frequently ship as separate attachments we do not need
        graphic_suffixes = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.tif', '.tiff')
        if filename_lower.endswith(graphic_suffixes):
            return True

        # Presentation fragment pattern (R##.htm) – skip when exhibits are disabled
        if re.fullmatch(r'r\d+\.htm(l)?', filename_lower):
            return True

        if 'cover' in filename_lower and filename_lower.endswith('.htm'):
            return True

        return False

    def _save_filing_metadata(
        self,
        filing: Filing,
        filing_dir: Path,
        documents: Dict[str, str]
    ) -> Path:
        """
        Save filing metadata to JSON file.

        Args:
            filing: Filing object
            filing_dir: Directory where filing is saved
            documents: Dictionary of documents and their URLs

        Returns:
            Path to saved metadata file
        """
        metadata = {
            'filing_info': {
                'cik': filing.cik,
                'accession_number': filing.accession_number,
                'form_type': filing.form_type,
                'filing_date': filing.filing_date.isoformat(),
                'report_date': filing.report_date.isoformat() if filing.report_date else None,
                'ticker': filing.ticker,
                'company_name': filing.company_name,
                'primary_document': filing.primary_document
            },
            'documents': documents,
            'download_info': {
                'downloaded_at': datetime.now().isoformat(),
                'edgar_url': filing.base_edgar_url
            }
        }

        metadata_path = filing_dir / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return metadata_path

    def _verify_downloads(self, file_paths: List[str]) -> None:
        """
        Verify that downloaded files are valid.

        Args:
            file_paths: List of file paths to verify

        Raises:
            FilingDownloadError: If verification fails
        """
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                raise FilingDownloadError(f"Downloaded file not found: {file_path}")

            if path.stat().st_size == 0:
                raise FilingDownloadError(f"Downloaded file is empty: {file_path}")

            # Basic content validation for HTML files
            if path.suffix.lower() in ['.htm', '.html']:
                try:
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    if len(content.strip()) < 100:
                        raise FilingDownloadError(f"HTML file appears to be incomplete: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not verify HTML content for {file_path}: {e}")

    def get_download_summary(self, results: List[DownloadResult]) -> Dict[str, Any]:
        """
        Generate download summary statistics.

        Args:
            results: List of download results

        Returns:
            Dictionary with summary statistics
        """
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful

        total_files = sum(len(r.downloaded_files) for r in results if r.success)
        total_size_mb = 0

        for result in results:
            if result.success and result.local_path:
                for file_pattern in ['*.htm', '*.html', '*.xml']:
                    for file_path in result.local_path.glob(file_pattern):
                        total_size_mb += get_file_size_mb(file_path)

        summary = {
            'total_filings': total,
            'successful_downloads': successful,
            'failed_downloads': failed,
            'success_rate': (successful / total * 100) if total > 0 else 0,
            'total_files_downloaded': total_files,
            'total_size_mb': round(total_size_mb, 2),
            'errors': [r.error for r in results if not r.success and r.error]
        }

        return summary
