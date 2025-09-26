# 05 - Data Models and Structures

## Overview

This document defines the Python data structures used to represent financial statement data extracted from the iXBRL viewer JSON. These models provide a clean interface between the raw JSON data and the Excel generation process.

The implementation follows the MVP philosophy with simple dataclasses that focus on core functionality without over-engineering.

## Core Data Models

### Statement
Represents a complete financial statement (Balance Sheet, Income Statement, or Cash Flows).

```python
from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class Statement:
    """Represents a complete financial statement."""
    name: str           # Full statement name (e.g., "Consolidated Balance Sheets")
    short_name: str     # Short name for Excel sheets (e.g., "Balance Sheet")
    periods: List['Period']
    rows: List['Row']
```

### Period
Represents a reporting period with basic information needed for Excel generation.

```python
@dataclass
class Period:
    """Represents a reporting period."""
    label: str          # Human-readable label (e.g., "2023-09-30")
    end_date: str       # End date string
    instant: bool = False  # True for balance sheet dates, False for period ranges
```

### Row
Represents a single row in a financial statement with cells for each period.

```python
@dataclass
class Row:
    """Represents a single row in a financial statement."""
    label: str                    # Display label for the row
    concept: Optional[str]        # XBRL concept name
    is_abstract: bool            # True for headers/sections
    depth: int                   # Indentation level
    cells: Dict[str, 'Cell']     # period_label -> Cell mapping
```

### Cell
Represents a single data cell with both formatted display value and raw numeric value.

```python
@dataclass
class Cell:
    """Represents a single data cell."""
    value: Optional[str]         # Formatted display value
    raw_value: Optional[float]   # Raw numeric value for calculations
    unit: Optional[str]          # Unit information (USD, shares, etc.)
    decimals: Optional[int]      # Decimal precision
    period: str                  # Period this cell belongs to
```

### ProcessingResult
Contains the complete result of processing an iXBRL filing.

```python
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
```

## New Presentation Models (v3.1)

### PresentationNode
Represents a node in the presentation tree extracted from the viewer JSON.

```python
@dataclass
class PresentationNode:
    """Represents a node in the presentation linkbase tree."""
    concept: str                    # XBRL concept name
    preferred_label: str           # Label to display
    depth: int                     # Tree depth for indentation
    is_abstract: bool              # True for headers/sections
    children: List['PresentationNode'] = field(default_factory=list)
    parent: Optional['PresentationNode'] = None
```

## Data Parser Implementation

The processor now depends exclusively on the presentation metadata emitted by Arelle. Legacy fact-grouping code has been removed; every call flows through the presentation parser and fact matcher.

### DataParser Class

```python
from typing import Dict, Any, List, Optional

from .data_models import Statement, Period, ProcessingResult
from .value_formatter import ValueFormatter
from .presentation_parser import PresentationParser
from .fact_matcher import FactMatcher
from .presentation_models import StatementTable


class DataParser:
    """Convert viewer JSON into the flattened Statement models used by Excel."""

    def __init__(self, formatter: Optional[ValueFormatter] = None):
        self.formatter = formatter or ValueFormatter()
        self.presentation_parser = PresentationParser()
        self.fact_matcher = FactMatcher(self.formatter)

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        company_name = self._extract_company_name(viewer_data)
        filing_date = self._extract_filing_date(viewer_data)
        form_type = self._extract_form_type(viewer_data)

        try:
            statements = self._parse_with_presentation(viewer_data)
        except Exception as exc:
            return ProcessingResult(
                statements=[],
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
                success=False,
                error=str(exc),
            )

        if not statements:
            return ProcessingResult(
                statements=[],
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
                success=False,
                error="No presentation statements with fact data were produced",
            )

        return ProcessingResult(
            statements=statements,
            company_name=company_name,
            filing_date=filing_date,
            form_type=form_type,
            success=True,
        )
```

### Presentation-First Flow

1. **Parse presentation relationships** – `PresentationParser.parse_presentation_statements` walks the viewer JSON and returns `PresentationStatement` trees for every role that looks like a statement, schedule, or disclosure.
2. **Extract periods and facts** – `FactMatcher.extract_periods_from_facts` normalises reporting periods straight from the viewer facts payload, and `_extract_facts_from_viewer_data` pulls the corresponding fact dictionary.
3. **Match facts to presentation nodes** – `FactMatcher.match_facts_to_statement` produces `StatementTable` instances where each presentation row is paired with per-period `Cell` values.
4. **Flatten for Excel** – `_convert_statement_tables_to_legacy_format` converts the presentation-aware structures into the existing `Statement`/`Row` models consumed by the Excel generator.

### Failure Handling

- Missing presentation roles, reporting periods, or facts now raise `ValueError` from `_parse_with_presentation`; the top-level `parse_viewer_data` turns those into `ProcessingResult(success=False, error=...)` responses.
- When a role parses successfully but contains no populated cells, the parser logs the condition and omits the statement, surfacing an error if this leaves the result empty.

This tighter contract removes the silent legacy fallback and makes failures explicit so we can diagnose problematic filings faster.

## Usage in Pipeline

The models are used in the main processing pipeline (`render_viewer_to_xlsx.py`):

```python
def process_filing(args) -> None:
    """Process filing through complete pipeline."""

    # Steps 1-3: Input handling, Arelle processing, JSON extraction
    # ... (handled by other components)

    # Step 4: Data parsing
    formatter = ValueFormatter(
        currency=args.currency,
        scale_millions=not args.scale_none,
    )
    data_parser = DataParser(
        formatter,
        include_disclosures=args.include_disclosures,
        label_style=args.label_style,
        use_scale_hint=not args.no_scale_hint,
    )
    result = data_parser.parse_viewer_data(viewer_data)

    if not result.success:
        raise ValueError(f"Data parsing failed: {result.error}")

    # Step 5: Excel generation
    excel_generator = ExcelGenerator()
    excel_generator.generate_excel(result, str(args.out),
                                 single_period=args.one_period)
```

## Key Features

### Presentation-Based Processing
- **Exact Fidelity**: Uses presentation relationships to match iXBRL viewer exactly
- **Tree Traversal**: Builds hierarchical structure from Arelle's presentation data
- **Preferred Labels**: Pulls MetaLinks label roles (defaults to `terseLabel`, configurable via CLI)
- **Automatic Format Detection**: Handles both sourceReports and legacy formats

### Smart Statement Processing
- **Role-Based Detection**: Uses XBRL role definitions to identify statement types
- **Presentation Order**: Maintains the exact row order from the presentation linkbase
- **Hierarchical Structure**: Preserves indentation levels and section headers
- **Flexible Naming**: Handles various statement naming conventions automatically

### Value Formatting
- Integrates with `ValueFormatter` for consistent number presentation
- Honours XBRL decimal scale hints unless `--no-scale-hint` is passed (still scales to millions by default)
- Applies finance-friendly conventions (parentheses for negatives, em dash for missing values, EPS precision)
- Preserves both raw and formatted values for calculations and display

### Error Handling
- Graceful handling of missing or malformed data
- Comprehensive error reporting through `ProcessingResult`
- Warning collection for non-critical issues

## Key Architecture Change (v3.1)

### From Fact-Based to Presentation-Based

**Previous Approach (v3.0 - WRONG)**:

```python
# ❌ Grouped facts by concept patterns
balance_sheet_concepts = ['Assets', 'Liabilities', 'Equity']
income_concepts = ['Revenue', 'Expenses', 'NetIncome']
# This created arbitrary ordering and missed the presentation structure
```

**New Approach (v3.1 - CORRECT)**:

```python
# ✅ Uses presentation relationships from viewer JSON
presentation_tree = build_tree_from_relationships(role_relationships)
statement_rows = traverse_tree_and_match_facts(presentation_tree, facts)
# This preserves the exact viewer structure and ordering
```

**Why This Matters**:

- **Exact Visual Match**: Excel output matches the iXBRL viewer pixel-perfect
- **Correct Row Order**: Uses the filer's intended presentation sequence
- **Proper Labels**: Shows preferred labels, not just concept names
- **Section Headers**: Preserves abstract elements and indentation

## Implementation Philosophy

This implementation follows the project's MVP philosophy:

- **Simple Dataclasses**: No complex inheritance or unnecessary methods
- **Focused Functionality**: Each class has a clear, single responsibility
- **Presentation Fidelity**: Leverages Arelle's structure instead of rebuilding it
- **Real-world Tested**: Handles actual SEC filings (tested with Apple, others)
- **Extensible**: Easy to add new fields or modify existing ones as needed

## Next Steps

These data models provide the foundation for:

1. **Refactor Implementation** (11-refactor-spec-v3.1.md) - Complete migration guide
2. **Value Formatting** (06-data-transformation.md) - Apply display formatting rules
3. **Excel Generation** (07-excel-generation.md) - Convert models to XLSX format
4. **Testing** (09-testing-strategy.md) - Validate with real filings

## Migration Path

For implementation details of the presentation-based approach, see:
- **docs/11-refactor-spec-v3.1.md** - Complete refactor specification with code examples
- **Phase 2**: New data models including PresentationNode
- **Phase 3**: PresentationParser and FactMatcher implementation
