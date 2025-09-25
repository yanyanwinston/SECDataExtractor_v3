# 07 - Excel Generation with openpyxl

## Overview

This document describes the Excel generation process using the openpyxl library to create formatted XLSX files from transformed financial statement data. The output preserves the visual structure and formatting of the original iXBRL presentation.

## openpyxl Setup

### Installation
```bash
pip install openpyxl
```

### Required Imports
```python
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from typing import List, Dict
```

## Workbook Structure

### Sheet Organization
Each financial statement becomes a separate worksheet:
- **"Balance Sheet"** - Statement of Financial Position
- **"Income Statement"** - Statement of Operations
- **"Cash Flows"** - Statement of Cash Flows

### Column Layout
```
A          B          C          D          E
Label      2024       2023       2022       2021
```

## Excel Generation Pipeline

### Step 1: Create Workbook and Sheets
```python
def create_workbook(statements: List['Statement']) -> Workbook:
    """Create Excel workbook with sheets for each statement."""

    wb = Workbook()

    # Remove default sheet
    wb.remove(wb.active)

    # Create sheets for each statement
    for statement in statements:
        sheet_name = get_sheet_name(statement.statement_type)
        ws = wb.create_sheet(title=sheet_name)

        # Add statement title as first row
        ws['A1'] = statement.title
        ws['A1'].font = Font(bold=True, size=14)

    return wb

def get_sheet_name(statement_type: 'StatementType') -> str:
    """Get standardized sheet name for statement type."""

    name_mapping = {
        StatementType.BALANCE_SHEET: "Balance Sheet",
        StatementType.INCOME_STATEMENT: "Income Statement",
        StatementType.CASH_FLOWS: "Cash Flows"
    }

    return name_mapping.get(statement_type, "Other Statement")
```

### Step 2: Write Headers
```python
def write_headers(ws: Worksheet, periods: List['Period'], start_row: int = 2) -> int:
    """Write period headers starting from specified row."""

    # Column A is for labels
    ws.cell(row=start_row, column=1, value="")

    # Write period headers in subsequent columns
    for col_idx, period in enumerate(periods, start=2):
        ws.cell(row=start_row, column=col_idx, value=period.label)

        # Style header
        cell = ws.cell(row=start_row, column=col_idx)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    return start_row + 1
```

### Step 3: Write Statement Data
```python
def write_statement_data(ws: Worksheet, statement: 'Statement', start_row: int) -> int:
    """Write statement data to worksheet."""

    table = statement.get_primary_table()
    current_row = start_row

    for row in table.rows:
        # Write row label in column A
        ws.cell(row=current_row, column=1, value=row.label)

        # Apply row formatting
        format_row(ws, row, current_row, table.periods)

        # Write data cells
        for col_idx, period in enumerate(table.periods, start=2):
            cell_value = ""
            if period.id in row.cells:
                cell = row.cells[period.id]
                cell_value = cell.raw_value or ""

            ws.cell(row=current_row, column=col_idx, value=cell_value)

            # Format data cell
            format_data_cell(ws, current_row, col_idx, row)

        current_row += 1

    return current_row
```

## Styling and Formatting

### Row Styling
```python
def format_row(ws: Worksheet, row: 'Row', row_num: int, periods: List['Period']) -> None:
    """Apply formatting to an entire row."""

    # Get label cell
    label_cell = ws.cell(row=row_num, column=1)

    if row.abstract:
        # Bold for abstract/header rows
        label_cell.font = Font(bold=True)

        # No indentation for abstract rows
        label_cell.alignment = Alignment(horizontal='left')

    else:
        # Regular font for data rows
        label_cell.font = Font(bold=False)

        # Apply indentation based on depth
        indent_level = row.depth
        label_cell.alignment = Alignment(horizontal='left', indent=indent_level)

    # Add bottom border for total rows
    if row.is_total_row():
        add_bottom_border(ws, row_num, len(periods) + 1)

def add_bottom_border(ws: Worksheet, row_num: int, num_cols: int) -> None:
    """Add thin bottom border to row."""

    thin_border = Border(bottom=Side(style='thin'))

    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.border = thin_border
```

### Data Cell Formatting
```python
def format_data_cell(ws: Worksheet, row_num: int, col_num: int, row: 'Row') -> None:
    """Format individual data cells."""

    cell = ws.cell(row=row_num, column=col_num)

    # Right-align numbers
    cell.alignment = Alignment(horizontal='right')

    # Apply number formatting if not abstract
    if not row.abstract and cell.value and cell.value != "—":
        apply_number_formatting(cell, row)

def apply_number_formatting(cell, row: 'Row') -> None:
    """Apply appropriate number formatting to cell."""

    cell_value = str(cell.value)

    # Detect if value is in parentheses (negative)
    if cell_value.startswith('(') and cell_value.endswith(')'):
        # Format for negative numbers in parentheses
        cell.number_format = '_(* #,##0_);_(* (#,##0);_(* "-"??_);_(@_)'
    else:
        # Format for positive numbers
        cell.number_format = '_(* #,##0_);_(* (#,##0);_(* "-"??_);_(@_)'
```

### Column Sizing
```python
def adjust_column_widths(ws: Worksheet, periods: List['Period']) -> None:
    """Adjust column widths for better appearance."""

    # Column A (labels) - wider for text
    ws.column_dimensions['A'].width = 40

    # Data columns - standard width
    for col_idx in range(2, len(periods) + 2):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 15

def set_row_heights(ws: Worksheet, num_rows: int) -> None:
    """Set consistent row heights."""

    for row_num in range(1, num_rows + 1):
        ws.row_dimensions[row_num].height = 18
```

## Complete Generation Function

```python
def generate_excel_file(statements: List['Statement'], output_path: str) -> None:
    """Generate complete Excel file from statements."""

    # Create workbook
    wb = create_workbook(statements)

    # Process each statement
    for statement in statements:
        sheet_name = get_sheet_name(statement.statement_type)
        ws = wb[sheet_name]

        # Get primary table
        table = statement.get_primary_table()

        # Write statement title
        ws['A1'] = statement.title
        ws['A1'].font = Font(bold=True, size=14)

        # Write headers
        current_row = write_headers(ws, table.periods, start_row=3)

        # Write data
        final_row = write_statement_data(ws, statement, current_row)

        # Apply formatting
        adjust_column_widths(ws, table.periods)
        set_row_heights(ws, final_row)

        # Freeze panes (header row and label column)
        ws.freeze_panes = 'B4'

    # Save workbook
    wb.save(output_path)
    print(f"Excel file saved to: {output_path}")
```

## Advanced Formatting Features

### Conditional Formatting for Negatives
```python
from openpyxl.formatting.rule import Rule
from openpyxl.styles.differential import DifferentialStyle

def apply_conditional_formatting(ws: Worksheet, data_range: str) -> None:
    """Apply conditional formatting for negative values."""

    # Red font for negative values
    red_font = Font(color="FF0000")
    red_fill = DifferentialStyle(font=red_font)

    # Rule for cells containing parentheses
    rule = Rule(type="containsText", operator="containsText", text="(", dxf=red_fill)

    ws.conditional_formatting.add(data_range, rule)
```

### Sheet Protection
```python
def protect_sheets(wb: Workbook) -> None:
    """Protect sheets while allowing data entry in specific areas."""

    for ws in wb.worksheets:
        # Allow users to select cells but not modify structure
        ws.protection.sheet = True
        ws.protection.selectLockedCells = True
        ws.protection.selectUnlockedCells = True
```

### Print Settings
```python
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagesetup import PageSetup

def configure_print_settings(ws: Worksheet) -> None:
    """Configure print settings for professional output."""

    # Set margins
    ws.page_margins = PageMargins(left=0.7, right=0.7, top=0.75, bottom=0.75)

    # Set orientation and paper size
    ws.page_setup = PageSetup(
        orientation="portrait",
        paperSize=PageSetup.PAPERSIZE_LETTER,
        fitToHeight=0,  # Don't force fit height
        fitToWidth=1    # Fit to one page wide
    )

    # Repeat headers on each page
    ws.print_title_rows = '1:3'  # Repeat first 3 rows
```

## Error Handling and Validation

### Data Validation
```python
def validate_data_for_excel(statements: List['Statement']) -> List[str]:
    """Validate data before Excel generation."""

    errors = []

    for statement in statements:
        table = statement.get_primary_table()

        # Check for empty statements
        if not table.rows:
            errors.append(f"Statement '{statement.title}' has no rows")
            continue

        # Check for periods
        if not table.periods:
            errors.append(f"Statement '{statement.title}' has no periods")
            continue

        # Check for data rows
        data_rows = [r for r in table.rows if not r.abstract and r.has_data()]
        if not data_rows:
            errors.append(f"Statement '{statement.title}' has no data rows")

    return errors
```

### Generation Error Handling
```python
def safe_generate_excel(statements: List['Statement'], output_path: str) -> bool:
    """Generate Excel with error handling."""

    try:
        # Validate input data
        errors = validate_data_for_excel(statements)
        if errors:
            print("Validation errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        # Generate Excel file
        generate_excel_file(statements, output_path)

        # Verify file was created
        import os
        if not os.path.exists(output_path):
            print(f"Error: File was not created at {output_path}")
            return False

        return True

    except Exception as e:
        print(f"Excel generation failed: {e}")
        return False
```

## Multiple Period Handling

### Single Period Option
```python
def filter_to_latest_period(statements: List['Statement']) -> List['Statement']:
    """Filter statements to show only the most recent period."""

    filtered_statements = []

    for statement in statements:
        table = statement.get_primary_table()

        if not table.periods:
            continue

        # Find most recent period
        latest_period = max(table.periods, key=lambda p: p.end_date or p.start_date)

        # Filter rows to only include latest period
        filtered_rows = []
        for row in table.rows:
            if row.abstract:
                # Keep abstract rows as-is
                filtered_rows.append(row)
            else:
                # Filter cells to latest period only
                filtered_cells = {}
                if latest_period.id in row.cells:
                    filtered_cells[latest_period.id] = row.cells[latest_period.id]

                filtered_row = Row(
                    label=row.label,
                    depth=row.depth,
                    abstract=row.abstract,
                    concept_qname=row.concept_qname,
                    preferred_label=row.preferred_label,
                    cells=filtered_cells
                )
                filtered_rows.append(filtered_row)

        # Create filtered table
        filtered_table = Table(
            title=table.title,
            periods=[latest_period],
            rows=filtered_rows
        )

        # Create filtered statement
        filtered_statement = Statement(
            id=statement.id,
            title=statement.title,
            role_uri=statement.role_uri,
            statement_type=statement.statement_type,
            tables=[filtered_table]
        )

        filtered_statements.append(filtered_statement)

    return filtered_statements
```

## Usage Example

```python
def main():
    """Main Excel generation workflow."""

    # Load transformed statements
    statements = load_transformed_statements()

    # Option: Filter to single period
    # statements = filter_to_latest_period(statements)

    # Generate Excel file
    output_path = "financials_aligned.xlsx"

    success = safe_generate_excel(statements, output_path)

    if success:
        print(f"✓ Excel file generated successfully: {output_path}")
    else:
        print("✗ Excel generation failed")

if __name__ == "__main__":
    main()
```

## Next Steps

The Excel generation component provides the final output for the system. It connects to:

1. **CLI Interface** (08-cli-interface.md) - Command-line options for output control
2. **Testing Strategy** (09-testing-strategy.md) - Validation of Excel output quality
3. **Edge Cases** (10-edge-cases.md) - Handling special formatting scenarios