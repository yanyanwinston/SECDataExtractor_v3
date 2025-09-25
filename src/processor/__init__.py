"""
SEC filing processor module.

Transforms iXBRL filings into Excel format while preserving
the original presentation structure.
"""

from .input_handler import InputHandler, FilingSource
from .arelle_processor import ArelleProcessor
from .json_extractor import ViewerDataExtractor
from .data_models import Statement, Period, Row, Cell, ProcessingResult
from .data_parser import DataParser
from .value_formatter import ValueFormatter
from .excel_generator import ExcelGenerator

__all__ = [
    'InputHandler',
    'FilingSource',
    'ArelleProcessor',
    'ViewerDataExtractor',
    'Statement',
    'Period',
    'Row',
    'Cell',
    'ProcessingResult',
    'DataParser',
    'ValueFormatter',
    'ExcelGenerator'
]