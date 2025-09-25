# 04 - JSON Extraction from iXBRL Viewer

## Overview

The Arelle iXBRLViewerPlugin generates an HTML file with embedded JavaScript containing all the financial statement data in JSON format. This component extracts and parses that JSON data for further processing.

## HTML Structure Analysis

### Generated HTML Pattern
The iXBRL viewer HTML contains a script tag with the viewer data:

```html
<script type="text/javascript">
    window.ixv = {
        "statements": [...],
        "facts": {...},
        "periods": [...],
        "units": {...},
        "languages": {...},
        "prefixes": {...}
    };
</script>
```

### Alternative Patterns
Some versions may use different variable assignments:
```javascript
// Pattern 1: Direct assignment
window.ixv = {...};

// Pattern 2: Function call
window.ixv = createViewerData({...});

// Pattern 3: Deferred assignment
var viewerData = {...};
window.ixv = viewerData;
```

## Extraction Implementation

### Step 1: HTML File Reading
```python
def read_viewer_html(file_path: str) -> str:
    """Read the generated iXBRL viewer HTML file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
```

### Step 2: Script Tag Location
```python
import re

def find_viewer_script(html_content: str) -> str:
    """Locate the script tag containing viewer data."""

    # Pattern to find script tag with window.ixv assignment
    pattern = r'<script[^>]*>.*?window\.ixv\s*=\s*({.*?});.*?</script>'

    match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)

    raise ValueError("Viewer data script not found in HTML")
```

### Step 3: JSON Cleaning and Parsing
```python
import json
import re

def extract_json_data(script_content: str) -> dict:
    """Extract and parse JSON from script content."""

    # Remove JavaScript comments
    script_content = re.sub(r'//.*?$', '', script_content, flags=re.MULTILINE)
    script_content = re.sub(r'/\*.*?\*/', '', script_content, flags=re.DOTALL)

    # Handle trailing semicolons and whitespace
    script_content = script_content.strip().rstrip(';')

    try:
        return json.loads(script_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse viewer JSON: {e}")
```

## Robust Extraction Strategy

### Multi-Pattern Search
```python
def extract_viewer_data(html_content: str) -> dict:
    """Extract viewer data using multiple fallback patterns."""

    patterns = [
        # Pattern 1: Direct window.ixv assignment
        r'window\.ixv\s*=\s*({.*?});',

        # Pattern 2: Variable then assignment
        r'var\s+\w+\s*=\s*({.*?});\s*window\.ixv\s*=',

        # Pattern 3: Function call result
        r'window\.ixv\s*=\s*\w+\(({.*?})\)',

        # Pattern 4: Multi-line with whitespace
        r'window\s*\.\s*ixv\s*=\s*({.*?})\s*;'
    ]

    for pattern in patterns:
        match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                json_str = match.group(1)
                return extract_json_data(json_str)
            except ValueError:
                continue

    raise ValueError("Could not extract viewer data from any known pattern")
```

## Expected JSON Structure

### Top-Level Keys
```json
{
  "statements": {
    "statement_id_1": {...},
    "statement_id_2": {...}
  },
  "facts": {
    "fact_id_1": {...},
    "fact_id_2": {...}
  },
  "periods": {
    "period_id_1": {...},
    "period_id_2": {...}
  },
  "units": {
    "unit_id_1": {...}
  },
  "languages": ["en-US"],
  "prefixes": {...}
}
```

### Statement Structure
```json
{
  "statement_id": {
    "title": "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "role": "http://company.com/role/ConsolidatedStatementsOfOperations",
    "tables": [
      {
        "title": "Income Statement",
        "periods": ["period_1", "period_2"],
        "rows": [
          {
            "label": "Revenue",
            "abstract": false,
            "depth": 0,
            "concept": "us-gaap:Revenues",
            "preferredLabel": null,
            "cells": {
              "period_1": "fact_id_123",
              "period_2": "fact_id_456"
            }
          }
        ]
      }
    ]
  }
}
```

### Fact Structure
```json
{
  "fact_id": {
    "value": "1000000000",
    "unit": "usd",
    "decimals": -6,
    "period": "period_id",
    "concept": "us-gaap:Revenues",
    "entity": "company_entity_id"
  }
}
```

### Period Structure
```json
{
  "period_id": {
    "startDate": "2023-01-01",
    "endDate": "2023-12-31",
    "instant": false,
    "label": "Year Ended December 31, 2023"
  }
}
```

## Data Validation

### Structure Validation
```python
def validate_viewer_data(data: dict) -> bool:
    """Validate that extracted data has required structure."""

    required_keys = ['statements', 'facts', 'periods']

    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key: {key}")

    if not isinstance(data['statements'], dict):
        raise ValueError("Statements must be a dictionary")

    if len(data['statements']) == 0:
        raise ValueError("No statements found in viewer data")

    return True
```

### Content Validation
```python
def validate_statement_data(statements: dict) -> bool:
    """Validate statement content structure."""

    for stmt_id, stmt_data in statements.items():
        if 'tables' not in stmt_data:
            raise ValueError(f"Statement {stmt_id} missing tables")

        if not stmt_data['tables']:
            raise ValueError(f"Statement {stmt_id} has no tables")

        for table in stmt_data['tables']:
            if 'rows' not in table:
                raise ValueError(f"Table in {stmt_id} missing rows")

    return True
```

## Error Handling

### Common Issues and Solutions

#### Malformed JSON
```python
def fix_common_json_issues(json_str: str) -> str:
    """Fix common JSON formatting issues."""

    # Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Fix single quotes to double quotes
    json_str = re.sub(r"'([^']*)':", r'"\1":', json_str)

    # Handle undefined values
    json_str = re.sub(r':\s*undefined\b', ': null', json_str)

    return json_str
```

#### Missing Script Tags
```python
def handle_missing_script(html_content: str) -> dict:
    """Handle cases where script tag is not found."""

    # Check if file is actually iXBRL viewer output
    if 'ixbrl-viewer' not in html_content.lower():
        raise ValueError("File does not appear to be an iXBRL viewer")

    # Look for inline JavaScript without script tags
    inline_pattern = r'window\.ixv\s*=\s*({.*?})'
    match = re.search(inline_pattern, html_content, re.DOTALL)

    if match:
        return extract_json_data(match.group(1))

    raise ValueError("No viewer data found in HTML file")
```

## Complete Extraction Function

```python
def extract_viewer_json(viewer_html_path: str, output_json_path: str = None) -> dict:
    """
    Complete function to extract viewer JSON from HTML file.

    Args:
        viewer_html_path: Path to the generated ixbrl-viewer.htm file
        output_json_path: Optional path to save extracted JSON

    Returns:
        Parsed viewer data as dictionary

    Raises:
        FileNotFoundError: If HTML file doesn't exist
        ValueError: If JSON extraction fails
    """

    # Read HTML file
    html_content = read_viewer_html(viewer_html_path)

    # Extract JSON data
    viewer_data = extract_viewer_data(html_content)

    # Validate structure
    validate_viewer_data(viewer_data)
    validate_statement_data(viewer_data['statements'])

    # Optional: Save JSON for debugging
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(viewer_data, f, indent=2, ensure_ascii=False)

    return viewer_data
```

## Usage Example

```python
# Extract viewer data
try:
    viewer_data = extract_viewer_json(
        viewer_html_path='./output/company-viewer.htm',
        output_json_path='./debug/viewer-data.json'
    )

    print(f"Found {len(viewer_data['statements'])} statements")
    print(f"Found {len(viewer_data['facts'])} facts")
    print(f"Found {len(viewer_data['periods'])} periods")

except (FileNotFoundError, ValueError) as e:
    print(f"Extraction failed: {e}")
```

## Next Steps

Once JSON is successfully extracted, the data flows to:
1. **Data Models** (05-data-models.md) - Structure the JSON into Python objects
2. **Data Transformation** (06-data-transformation.md) - Apply formatting rules
3. **Excel Generation** (07-excel-generation.md) - Create the final XLSX output