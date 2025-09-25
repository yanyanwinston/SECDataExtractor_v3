"""
Data models for SEC filing processing.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class Period:
    """Represents a reporting period."""
    label: str
    end_date: str
    instant: bool = False


@dataclass
class Cell:
    """Represents a single data cell."""
    value: Optional[str]
    raw_value: Optional[float]
    unit: Optional[str]
    decimals: Optional[int]
    period: str


@dataclass
class Row:
    """Represents a single row in a financial statement."""
    label: str
    concept: Optional[str]
    is_abstract: bool
    depth: int
    cells: Dict[str, Cell]  # period_label -> Cell


@dataclass
class Statement:
    """Represents a complete financial statement."""
    name: str
    short_name: str
    periods: List[Period]
    rows: List[Row]


@dataclass
class ProcessingResult:
    """Result of processing a filing."""
    statements: List[Statement]
    company_name: str
    filing_date: str
    form_type: str
    success: bool
    error: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []