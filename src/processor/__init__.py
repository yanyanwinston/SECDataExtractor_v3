"""
SEC filing processor module.

Transforms iXBRL filings into Excel format while preserving
the original presentation structure.
"""

from .input_handler import InputHandler, FilingSource
from .arelle_processor import ArelleProcessor
from .json_extractor import ViewerDataExtractor
from .data_models import Statement, Period, Row, Cell, ProcessingResult
from .presentation_models import (
    StatementType,
    PresentationNode,
    PresentationStatement,
    StatementRow,
    StatementTable,
    classify_statement_type,
)
from .presentation_parser import PresentationParser
from .fact_matcher import FactMatcher
from .data_parser import DataParser
from .value_formatter import ValueFormatter
from .excel_generator import ExcelGenerator
from .ensemble import FilingSlice, build_ensemble_result

__all__ = [
    "InputHandler",
    "FilingSource",
    "ArelleProcessor",
    "ViewerDataExtractor",
    "Statement",
    "Period",
    "Row",
    "Cell",
    "ProcessingResult",
    "StatementType",
    "PresentationNode",
    "PresentationStatement",
    "StatementRow",
    "StatementTable",
    "classify_statement_type",
    "PresentationParser",
    "FactMatcher",
    "DataParser",
    "ValueFormatter",
    "ExcelGenerator",
    "FilingSlice",
    "build_ensemble_result",
]
