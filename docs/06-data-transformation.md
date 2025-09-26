# 06 - Data Transformation and Formatting

## Overview

This document defines the data transformation rules that convert raw XBRL values into properly formatted display values for Excel output. The transformations handle currency scaling, decimal precision, sign conventions, and special formatting requirements.

## Formatting Requirements

### Currency Display Standards
- **Base unit**: USD presented in millions (after restoring the filer’s original magnitude via XBRL `decimals`)
- **Scaling**: Respect XBRL scale hints when available, then divide by 1,000,000 unless `--scale-none`
- **Decimals**: Round to 0 decimal places for display
- **Thousands separators**: Add commas (e.g., 1,234)
- **Negatives**: Use parentheses format (150) instead of -150

### Earnings Per Share (EPS)
- **Precision**: Display with 2 decimal places
- **Scaling**: Keep raw magnitude (no scaling)
- **Negatives**: Use parentheses format

### Share Counts
- **Unit**: Millions of shares
- **Scaling**: Respect `decimals` hints (many filers provide -6 for share counts) and present in millions
- **Decimals**: Round to 0 decimal places
- **Display**: No parentheses (shares are always positive)

### Missing Values
- **Display**: Em dash `—`
- **Conditions**: Null values, empty strings, zero when inappropriate

## Transformation Pipeline

### Step 1: Unit Classification
```python
from enum import Enum
from decimal import Decimal
from typing import Optional

class ValueType(Enum):
    CURRENCY = "currency"
    SHARES = "shares"
    PER_SHARE = "per_share"
    RATIO = "ratio"
    OTHER = "other"

def classify_value_type(cell: 'Cell') -> ValueType:
    """Determine the type of value based on unit and context."""

    if not cell.unit:
        return ValueType.OTHER

    unit_lower = cell.unit.lower()

    # Currency values
    if any(currency in unit_lower for currency in ['usd', 'currency', 'dollar']):
        return ValueType.CURRENCY

    # Share counts
    if 'shares' in unit_lower and 'per' not in unit_lower:
        return ValueType.SHARES

    # Per-share values (EPS, dividends per share, etc.)
    if 'per' in unit_lower and 'share' in unit_lower:
        return ValueType.PER_SHARE

    # Ratios and percentages
    if any(ratio in unit_lower for ratio in ['ratio', 'percent', 'pure']):
        return ValueType.RATIO

    return ValueType.OTHER
```

### Step 2: Value Scaling
```python
def apply_scaling(
    value: Decimal,
    value_type: ValueType,
    decimals: Optional[int],
    *,
    use_scale_hint: bool = True,
    scale_millions: bool = True,
) -> Decimal:
    """Apply appropriate scaling based on metadata and CLI flags."""

    scaled = value

    if use_scale_hint and decimals is not None and decimals < 0:
        # A negative decimals value means the fact was stored in a rounded unit
        # (e.g. -6 → millions). Multiply to recover the true number before applying
        # any presentation scaling.
        scaled *= Decimal(10) ** Decimal(decimals)

    if value_type in {ValueType.CURRENCY, ValueType.SHARES} and scale_millions:
        scaled /= Decimal(1_000_000)

    return scaled
```

> **CLI interplay**
>
> - `render_viewer_to_xlsx.py --no-scale-hint` sets `use_scale_hint=False`, skipping the `decimals` multiplier step above (useful for diagnostics when a filer publishes incorrect metadata).
> - `--scale-none` passes `scale_millions=False`, preserving the recovered raw magnitude in the workbook.

### Step 3: Precision and Rounding
```python
def apply_precision(value: Decimal, value_type: ValueType) -> Decimal:
    """Apply appropriate decimal precision."""

    if value_type == ValueType.CURRENCY:
        # Round to whole millions
        return value.quantize(Decimal('1'))

    elif value_type == ValueType.SHARES:
        # Round to whole millions
        return value.quantize(Decimal('1'))

    elif value_type == ValueType.PER_SHARE:
        # Round to 2 decimal places
        return value.quantize(Decimal('0.01'))

    elif value_type == ValueType.RATIO:
        # Round to 3 decimal places for ratios
        return value.quantize(Decimal('0.001'))

    else:
        # Default to 2 decimal places
        return value.quantize(Decimal('0.01'))
```

### Step 4: Display Formatting
```python
def format_for_display(value: Decimal, value_type: ValueType) -> str:
    """Format value for Excel display."""

    if value.is_zero():
        # Handle zero values
        if value_type in [ValueType.CURRENCY, ValueType.SHARES]:
            return "—"  # Em dash for missing/zero
        else:
            return "0.00"

    # Handle negative values
    is_negative = value < 0
    abs_value = abs(value)

    # Format based on type
    if value_type == ValueType.CURRENCY:
        formatted = f"{abs_value:,.0f}"
    elif value_type == ValueType.SHARES:
        formatted = f"{abs_value:,.0f}"
    elif value_type == ValueType.PER_SHARE:
        formatted = f"{abs_value:.2f}"
    elif value_type == ValueType.RATIO:
        formatted = f"{abs_value:.3f}"
    else:
        formatted = f"{abs_value:.2f}"

    # Apply negative formatting
    if is_negative:
        return f"({formatted})"
    else:
        return formatted
```

## Complete Transformation Function

```python
from typing import Optional

def transform_cell_value(cell: 'Cell') -> str:
    """Complete transformation pipeline for a cell value."""

    # Handle empty/null values
    if not cell.has_value():
        return "—"

    # Get numeric value
    numeric_value = cell.get_numeric_value()
    if numeric_value is None:
        return "—"

    # Classify value type
    value_type = classify_value_type(cell)

    # Apply scaling
    scaled_value = apply_scaling(numeric_value, value_type, cell.decimals)

    # Apply precision
    precise_value = apply_precision(scaled_value, value_type)

    # Format for display
    return format_for_display(precise_value, value_type)
```

## Sign Handling and Label Context

### Viewer Sign Corrections
```python
def check_viewer_sign_flip(row: 'Row') -> bool:
    """Check if viewer already flipped signs based on preferred label."""

    if not row.preferred_label:
        return False

    # Common label roles that indicate sign flipping
    sign_flip_roles = [
        'negatedLabel',
        'negatedPeriodEndLabel',
        'negatedPeriodStartLabel',
        'negatedTotalLabel'
    ]

    return any(role in row.preferred_label for role in sign_flip_roles)

def apply_sign_correction(value: Decimal, row: 'Row') -> Decimal:
    """Apply sign correction if needed."""

    # If viewer already flipped the sign, don't flip again
    if check_viewer_sign_flip(row):
        return value

    # Apply business logic sign corrections
    # (This would include statement-specific rules)
    return value
```

### Statement-Specific Sign Rules
```python
def get_expected_sign(concept: str, statement_type: 'StatementType') -> int:
    """Get expected sign for a concept in a statement type."""

    # Income Statement rules
    if statement_type == StatementType.INCOME_STATEMENT:
        if any(term in concept.lower() for term in ['revenue', 'income', 'gain']):
            return 1  # Positive
        elif any(term in concept.lower() for term in ['expense', 'cost', 'loss']):
            return -1  # Negative (but displayed as positive)

    # Balance Sheet rules
    elif statement_type == StatementType.BALANCE_SHEET:
        if any(term in concept.lower() for term in ['asset', 'cash', 'receivable']):
            return 1  # Positive
        elif any(term in concept.lower() for term in ['liability', 'debt', 'payable']):
            return 1  # Positive (liabilities are positive balances)

    # Cash Flow rules
    elif statement_type == StatementType.CASH_FLOWS:
        # Most cash flows should be positive when they increase cash
        return 1

    return 1  # Default to positive
```

## Special Cases and Edge Conditions

### Percentage Values
```python
def handle_percentage_values(cell: 'Cell') -> str:
    """Handle percentage and ratio values specially."""

    if not cell.unit or 'percent' not in cell.unit.lower():
        return transform_cell_value(cell)

    numeric_value = cell.get_numeric_value()
    if numeric_value is None:
        return "—"

    # Convert to percentage format
    if numeric_value <= 1:
        # Value is in decimal form (0.05 = 5%)
        percentage = numeric_value * 100
    else:
        # Value is already in percentage form
        percentage = numeric_value

    formatted = f"{abs(percentage):.1f}%"
    return f"({formatted})" if percentage < 0 else formatted
```

### Very Large Numbers
```python
def handle_large_numbers(value: Decimal, value_type: ValueType) -> str:
    """Handle exceptionally large numbers."""

    if value_type != ValueType.CURRENCY:
        return format_for_display(value, value_type)

    abs_value = abs(value)

    # If over 1 trillion (in millions), add notation
    if abs_value > 1_000_000:  # 1 trillion in millions
        billions = abs_value / 1_000
        formatted = f"{billions:,.1f}B"
    else:
        formatted = format_for_display(value, value_type)
        return formatted

    return f"({formatted})" if value < 0 else formatted
```

### Data Quality Checks
```python
def validate_transformed_value(original_cell: 'Cell', transformed: str) -> bool:
    """Validate that transformation makes sense."""

    # Check for obviously wrong transformations
    if transformed == "—" and original_cell.has_value():
        numeric = original_cell.get_numeric_value()
        if numeric and not numeric.is_zero():
            return False

    # Check for reasonable magnitude
    if transformed.replace(',', '').replace('(', '').replace(')', '').replace('.', '').isdigit():
        # Ensure we didn't create unreasonably large or small numbers
        pass

    return True
```

## Batch Transformation

### Transform Statement
```python
def transform_statement(statement: 'Statement') -> 'Statement':
    """Transform all values in a statement."""

    transformed_tables = []

    for table in statement.tables:
        transformed_rows = []

        for row in table.rows:
            if row.abstract:
                # Abstract rows don't have values to transform
                transformed_rows.append(row)
                continue

            # Transform all cells in this row
            transformed_cells = {}
            for period_id, cell in row.cells.items():
                transformed_value = transform_cell_value(cell)

                # Create new cell with transformed value
                transformed_cell = Cell(
                    raw_value=transformed_value,
                    unit=cell.unit,
                    decimals=cell.decimals,
                    fact_id=cell.fact_id
                )
                transformed_cells[period_id] = transformed_cell

            # Create new row with transformed cells
            transformed_row = Row(
                label=row.label,
                depth=row.depth,
                abstract=row.abstract,
                concept_qname=row.concept_qname,
                preferred_label=row.preferred_label,
                cells=transformed_cells
            )
            transformed_rows.append(transformed_row)

        # Create new table with transformed rows
        transformed_table = Table(
            title=table.title,
            periods=table.periods,
            rows=transformed_rows
        )
        transformed_tables.append(transformed_table)

    # Create new statement with transformed tables
    return Statement(
        id=statement.id,
        title=statement.title,
        role_uri=statement.role_uri,
        statement_type=statement.statement_type,
        tables=transformed_tables
    )
```

## Usage Example

```python
def process_statements_for_excel(statements: List['Statement']) -> List['Statement']:
    """Transform all statements for Excel output."""

    transformed = []

    for statement in statements:
        try:
            transformed_statement = transform_statement(statement)
            transformed.append(transformed_statement)
            print(f"Transformed {statement.title}")
        except Exception as e:
            print(f"Failed to transform {statement.title}: {e}")

    return transformed
```

## Next Steps

The transformed data models are now ready for:

1. **Excel Generation** (07-excel-generation.md) - Create XLSX output with proper formatting
2. **CLI Interface** (08-cli-interface.md) - Command-line interface for user interaction
3. **Testing** (09-testing-strategy.md) - Validate transformation accuracy
