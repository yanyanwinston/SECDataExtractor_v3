# 05 - Data Models and Structures

## Overview

This document defines the Python data structures used to represent financial statement data extracted from the iXBRL viewer JSON. These models provide a clean interface between the raw JSON data and the Excel generation process.

## Core Data Models

### Statement
Represents a complete financial statement (Balance Sheet, Income Statement, or Cash Flows).

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

class StatementType(Enum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOWS = "cash_flows"
    OTHER = "other"

@dataclass
class Statement:
    """Represents a financial statement."""
    id: str
    title: str
    role_uri: str
    statement_type: StatementType
    tables: List['Table']

    def get_primary_table(self) -> 'Table':
        """Get the main table for this statement."""
        if not self.tables:
            raise ValueError(f"No tables found in statement {self.id}")
        return self.tables[0]

    def get_periods(self) -> List['Period']:
        """Get all periods referenced in this statement."""
        if not self.tables:
            return []
        return self.tables[0].periods
```

### Table
Represents a table within a statement (most statements have one primary table).

```python
@dataclass
class Table:
    """Represents a table within a financial statement."""
    title: str
    periods: List['Period']
    rows: List['Row']

    def get_period_by_id(self, period_id: str) -> Optional['Period']:
        """Find a period by its ID."""
        return next((p for p in self.periods if p.id == period_id), None)

    def get_row_by_concept(self, concept: str) -> Optional['Row']:
        """Find a row by its concept name."""
        return next((r for r in self.rows if r.concept_qname == concept), None)

    def get_abstract_rows(self) -> List['Row']:
        """Get all abstract (header) rows."""
        return [r for r in self.rows if r.abstract]

    def get_data_rows(self) -> List['Row']:
        """Get all non-abstract (data) rows."""
        return [r for r in self.rows if not r.abstract]
```

### Row
Represents a single row in a financial statement table.

```python
@dataclass
class Row:
    """Represents a row in a financial statement table."""
    label: str
    depth: int
    abstract: bool
    concept_qname: Optional[str]
    preferred_label: Optional[str]
    cells: Dict[str, 'Cell']  # period_id -> Cell

    def get_cell_for_period(self, period_id: str) -> Optional['Cell']:
        """Get the cell value for a specific period."""
        return self.cells.get(period_id)

    def has_data(self) -> bool:
        """Check if this row has any non-empty cells."""
        return any(cell.has_value() for cell in self.cells.values())

    def is_total_row(self) -> bool:
        """Determine if this appears to be a total/summary row."""
        if self.preferred_label and 'total' in self.preferred_label.lower():
            return True
        return 'total' in self.label.lower()
```

### Cell
Represents a single cell value in the financial statement.

```python
from decimal import Decimal

@dataclass
class Cell:
    """Represents a cell value in a financial statement."""
    raw_value: Optional[str]
    unit: Optional[str]
    decimals: Optional[int]
    fact_id: Optional[str]

    def has_value(self) -> bool:
        """Check if this cell contains a meaningful value."""
        return self.raw_value is not None and self.raw_value.strip() != ""

    def get_numeric_value(self) -> Optional[Decimal]:
        """Convert raw value to Decimal for calculations."""
        if not self.has_value():
            return None

        try:
            # Remove commas and other formatting
            clean_value = self.raw_value.replace(',', '').replace('$', '').strip()

            # Handle parentheses for negatives
            if clean_value.startswith('(') and clean_value.endswith(')'):
                clean_value = '-' + clean_value[1:-1]

            return Decimal(clean_value)
        except (ValueError, TypeError):
            return None

    def is_currency(self) -> bool:
        """Check if this cell represents a currency value."""
        return self.unit and ('usd' in self.unit.lower() or 'currency' in self.unit.lower())

    def is_shares(self) -> bool:
        """Check if this cell represents share count."""
        return self.unit and 'shares' in self.unit.lower()

    def is_per_share(self) -> bool:
        """Check if this cell represents per-share value (like EPS)."""
        return self.unit and ('per' in self.unit.lower() and 'share' in self.unit.lower())
```

### Period
Represents a reporting period (quarter, year, etc.).

```python
from datetime import date

@dataclass
class Period:
    """Represents a reporting period."""
    id: str
    start_date: Optional[date]
    end_date: Optional[date]
    instant: bool
    label: str

    def is_annual(self) -> bool:
        """Check if this is an annual period."""
        if not self.start_date or not self.end_date:
            return False
        return (self.end_date - self.start_date).days >= 350

    def is_quarterly(self) -> bool:
        """Check if this is a quarterly period."""
        if not self.start_date or not self.end_date:
            return False
        days = (self.end_date - self.start_date).days
        return 80 <= days <= 100

    def get_year(self) -> Optional[int]:
        """Get the year for this period."""
        return self.end_date.year if self.end_date else None

    def __str__(self) -> str:
        return self.label
```

## Factory Functions

### Statement Factory
```python
def create_statement_from_json(stmt_id: str, stmt_data: dict,
                             facts_data: dict, periods_data: dict) -> Statement:
    """Create a Statement object from viewer JSON data."""

    # Determine statement type
    statement_type = determine_statement_type(stmt_data.get('title', ''),
                                            stmt_data.get('role', ''))

    # Create tables
    tables = []
    for table_data in stmt_data.get('tables', []):
        table = create_table_from_json(table_data, facts_data, periods_data)
        tables.append(table)

    return Statement(
        id=stmt_id,
        title=stmt_data.get('title', ''),
        role_uri=stmt_data.get('role', ''),
        statement_type=statement_type,
        tables=tables
    )

def determine_statement_type(title: str, role: str) -> StatementType:
    """Determine statement type from title and role."""
    title_lower = title.lower()
    role_lower = role.lower()

    if 'balance' in title_lower or 'position' in title_lower:
        return StatementType.BALANCE_SHEET
    elif 'income' in title_lower or 'operations' in title_lower or 'earnings' in title_lower:
        return StatementType.INCOME_STATEMENT
    elif 'cash' in title_lower and 'flow' in title_lower:
        return StatementType.CASH_FLOWS
    else:
        return StatementType.OTHER
```

### Table Factory
```python
def create_table_from_json(table_data: dict, facts_data: dict,
                          periods_data: dict) -> Table:
    """Create a Table object from viewer JSON data."""

    # Create periods
    periods = []
    for period_id in table_data.get('periods', []):
        if period_id in periods_data:
            period = create_period_from_json(period_id, periods_data[period_id])
            periods.append(period)

    # Create rows
    rows = []
    for row_data in table_data.get('rows', []):
        row = create_row_from_json(row_data, facts_data, periods)
        rows.append(row)

    return Table(
        title=table_data.get('title', ''),
        periods=periods,
        rows=rows
    )
```

### Row Factory
```python
def create_row_from_json(row_data: dict, facts_data: dict,
                        periods: List[Period]) -> Row:
    """Create a Row object from viewer JSON data."""

    # Create cells for each period
    cells = {}
    for period in periods:
        cell_data = row_data.get('cells', {}).get(period.id)
        if cell_data and cell_data in facts_data:
            fact_data = facts_data[cell_data]
            cell = create_cell_from_fact(fact_data, cell_data)
            cells[period.id] = cell

    return Row(
        label=row_data.get('label', ''),
        depth=row_data.get('depth', 0),
        abstract=row_data.get('abstract', False),
        concept_qname=row_data.get('concept'),
        preferred_label=row_data.get('preferredLabel'),
        cells=cells
    )
```

### Cell Factory
```python
def create_cell_from_fact(fact_data: dict, fact_id: str) -> Cell:
    """Create a Cell object from fact data."""
    return Cell(
        raw_value=fact_data.get('value'),
        unit=fact_data.get('unit'),
        decimals=fact_data.get('decimals'),
        fact_id=fact_id
    )
```

### Period Factory
```python
from datetime import datetime

def create_period_from_json(period_id: str, period_data: dict) -> Period:
    """Create a Period object from viewer JSON data."""

    start_date = None
    if period_data.get('startDate'):
        start_date = datetime.strptime(period_data['startDate'], '%Y-%m-%d').date()

    end_date = None
    if period_data.get('endDate'):
        end_date = datetime.strptime(period_data['endDate'], '%Y-%m-%d').date()

    return Period(
        id=period_id,
        start_date=start_date,
        end_date=end_date,
        instant=period_data.get('instant', False),
        label=period_data.get('label', period_id)
    )
```

## Data Processing Pipeline

### Complete Parsing Function
```python
def parse_viewer_data(viewer_data: dict) -> List[Statement]:
    """Parse complete viewer JSON into Statement objects."""

    statements = []
    statements_data = viewer_data.get('statements', {})
    facts_data = viewer_data.get('facts', {})
    periods_data = viewer_data.get('periods', {})

    for stmt_id, stmt_data in statements_data.items():
        try:
            statement = create_statement_from_json(
                stmt_id, stmt_data, facts_data, periods_data
            )
            statements.append(statement)
        except Exception as e:
            print(f"Warning: Failed to parse statement {stmt_id}: {e}")
            continue

    return statements
```

### Statement Filtering
```python
def filter_primary_statements(statements: List[Statement]) -> List[Statement]:
    """Filter to keep only primary financial statements."""

    primary_types = {
        StatementType.BALANCE_SHEET,
        StatementType.INCOME_STATEMENT,
        StatementType.CASH_FLOWS
    }

    return [s for s in statements if s.statement_type in primary_types]
```

## Validation and Quality Checks

### Data Validation
```python
def validate_statement(statement: Statement) -> bool:
    """Validate that a statement has required data."""

    if not statement.tables:
        raise ValueError(f"Statement {statement.id} has no tables")

    primary_table = statement.get_primary_table()

    if not primary_table.periods:
        raise ValueError(f"Statement {statement.id} has no periods")

    if not primary_table.rows:
        raise ValueError(f"Statement {statement.id} has no rows")

    # Check that at least some rows have data
    data_rows = [r for r in primary_table.rows if r.has_data()]
    if not data_rows:
        raise ValueError(f"Statement {statement.id} has no rows with data")

    return True

def validate_all_statements(statements: List[Statement]) -> List[Statement]:
    """Validate all statements and return only valid ones."""

    valid_statements = []
    for statement in statements:
        try:
            validate_statement(statement)
            valid_statements.append(statement)
        except ValueError as e:
            print(f"Warning: Skipping invalid statement {statement.id}: {e}")

    return valid_statements
```

## Usage Example

```python
# Parse viewer data into structured models
def process_filing(viewer_data: dict) -> List[Statement]:
    """Complete processing pipeline."""

    # Parse all statements
    all_statements = parse_viewer_data(viewer_data)
    print(f"Parsed {len(all_statements)} statements")

    # Filter to primary statements
    primary_statements = filter_primary_statements(all_statements)
    print(f"Found {len(primary_statements)} primary statements")

    # Validate statements
    valid_statements = validate_all_statements(primary_statements)
    print(f"Validated {len(valid_statements)} statements")

    return valid_statements
```

## Next Steps

These data models provide the foundation for:

1. **Data Transformation** (06-data-transformation.md) - Apply formatting rules to cell values
2. **Excel Generation** (07-excel-generation.md) - Convert models to XLSX format
3. **Testing** (09-testing-strategy.md) - Validate model behavior and data integrity