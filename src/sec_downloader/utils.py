"""
Utility functions for SEC filing downloader.
"""

import re
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional


def normalize_cik(cik: str) -> str:
    """
    Normalize CIK to standard format (remove leading zeros, then pad to 10 digits).

    Args:
        cik: CIK string in any format

    Returns:
        Normalized CIK string
    """
    # Remove any non-digit characters
    cik_clean = re.sub(r"\D", "", str(cik))

    # Convert to int to remove leading zeros, then back to string
    try:
        cik_int = int(cik_clean)
        return str(cik_int).zfill(10)
    except ValueError:
        raise ValueError(f"Invalid CIK format: {cik}")


def normalize_ticker(ticker: str) -> str:
    """
    Normalize ticker symbol to uppercase.

    Args:
        ticker: Ticker symbol

    Returns:
        Normalized ticker symbol
    """
    return ticker.upper().strip()


def parse_accession_number(accession: str) -> str:
    """
    Parse and validate accession number format.

    Args:
        accession: Accession number (with or without dashes)

    Returns:
        Normalized accession number with dashes
    """
    # Remove all non-alphanumeric characters
    clean = re.sub(r"[^0-9]", "", accession)

    # Should be 20 digits
    if len(clean) != 20:
        raise ValueError(f"Invalid accession number format: {accession}")

    # Format as NNNNNNNNNN-NN-NNNNNN
    return f"{clean[:10]}-{clean[10:12]}-{clean[12:]}"


def get_user_agent() -> str:
    """
    Get appropriate User-Agent header for SEC requests.
    SEC requires identification in User-Agent.

    Returns:
        User-Agent string
    """
    return "SECDataExtractor v3.0 daidaiwahaha@icloud.com"


def create_safe_filename(name: str, max_length: int = 100) -> str:
    """
    Create a safe filename from a string.

    Args:
        name: Original name
        max_length: Maximum filename length

    Returns:
        Safe filename
    """
    # Replace problematic characters
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)

    # Remove multiple spaces and underscores
    safe = re.sub(r"[_\s]+", "_", safe)

    # Trim and ensure it's not too long
    safe = safe.strip("_")[:max_length]

    return safe


def validate_date_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> None:
    """
    Validate date range parameters.

    Args:
        start_date: Start date (optional)
        end_date: End date (optional)

    Raises:
        ValueError: If date range is invalid
    """
    if start_date and end_date:
        if start_date > end_date:
            raise ValueError("Start date must be before end date")

    now = datetime.now()
    if start_date and start_date > now:
        raise ValueError("Start date cannot be in the future")

    if end_date and end_date > now:
        raise ValueError("End date cannot be in the future")


def ensure_directory(path: Path) -> None:
    """
    Ensure directory exists, create if needed.

    Args:
        path: Directory path to ensure exists
    """
    path.mkdir(parents=True, exist_ok=True)


def get_file_size_mb(file_path: Path) -> float:
    """
    Get file size in MB.

    Args:
        file_path: Path to file

    Returns:
        File size in MB
    """
    if not file_path.exists():
        return 0.0

    size_bytes = file_path.stat().st_size
    return size_bytes / (1024 * 1024)


class RateLimiter:
    """
    Simple rate limiter for API requests.
    SEC allows 10 requests per second.
    """

    def __init__(self, max_requests: int = 10, time_window: float = 1.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: list[float] = []
        self._lock = Lock()

    def wait_if_needed(self) -> None:
        """
        Wait if rate limit would be exceeded.
        """
        with self._lock:
            now = time.time()

            # Remove old requests outside the time window
            self.requests = [
                req_time
                for req_time in self.requests
                if now - req_time < self.time_window
            ]

            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0]) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self.requests = [
                        req_time
                        for req_time in self.requests
                        if now - req_time < self.time_window
                    ]

            self.requests.append(now)
