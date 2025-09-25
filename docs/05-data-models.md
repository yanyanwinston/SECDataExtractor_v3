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

The `DataParser` class in `src/processor/data_parser.py` handles the conversion from iXBRL viewer JSON to our data models using **presentation-based parsing** to maintain exact visual fidelity with the iXBRL viewer. This approach leverages Arelle's presentation relationships instead of grouping facts by concept patterns.

### DataParser Class

```python
from .data_models import Statement, Period, Row, Cell, ProcessingResult
from .value_formatter import ValueFormatter

class DataParser:
    """Parser for converting iXBRL viewer JSON to structured data models."""

    def __init__(self, formatter: Optional[ValueFormatter] = None):
        self.formatter = formatter or ValueFormatter()

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        """Main entry point - parse viewer JSON into ProcessingResult."""
        try:
            # Extract metadata
            company_name = self._extract_company_name(viewer_data)
            filing_date = self._extract_filing_date(viewer_data)
            form_type = self._extract_form_type(viewer_data)

            # Parse statements
            statements = self._parse_statements(viewer_data)

            return ProcessingResult(
                statements=statements,
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
                success=True
            )
        except Exception as e:
            return ProcessingResult(
                statements=[], company_name="", filing_date="",
                form_type="", success=False, error=str(e)
            )
```

### Presentation-Based Parsing (v3.1 Approach)

The parser uses the presentation relationships from the viewer JSON to build statements in the exact order they appear in the iXBRL viewer:

#### 1. New Arelle 2.37+ Format (sourceReports)
```python
def _parse_source_reports_format(self, data: Dict[str, Any]) -> List[Statement]:
    """Parse the new sourceReports format using presentation structure"""
    source_reports = data.get('sourceReports', [])
    target_data = source_reports[0]['targetReports'][0]

    # Extract core components
    role_defs = target_data.get('roleDefs', {})
    relationships = target_data.get('rels', {})
    concepts = target_data.get('concepts', {})
    facts = target_data.get('facts', {})

    statements = []
    for role_id, role_info in role_defs.items():
        # Build presentation tree for this statement
        presentation_tree = self._build_presentation_tree(
            role_id, relationships, concepts
        )

        # Convert tree to statement with fact matching
        statement = self._tree_to_statement(
            presentation_tree, facts, role_info
        )

        if statement and statement.rows:
            statements.append(statement)

    return statements
```

#### 2. Presentation Tree Construction
```python
def _build_presentation_tree(self, role_id: str,
                           relationships: Dict[str, Any],
                           concepts: Dict[str, Any]) -> List[PresentationNode]:
    """Build hierarchical presentation tree from relationships."""

    # Find presentation relationships for this role
    pres_rels = []
    for rel_key, rel_data in relationships.items():
        if rel_data.get('role') == role_id and rel_data.get('arcrole') == 'parent-child':
            pres_rels.append(rel_data)

    # Build tree structure
    root_nodes = []
    node_map = {}

    for rel in sorted(pres_rels, key=lambda r: r.get('order', 0)):
        from_concept = rel.get('from')
        to_concept = rel.get('to')
        preferred_label = rel.get('preferredLabel')

        # Create nodes if not exists
        if to_concept not in node_map:
            concept_info = concepts.get(to_concept, {})
            node_map[to_concept] = PresentationNode(
                concept=to_concept,
                preferred_label=self._get_preferred_label(
                    concept_info, preferred_label
                ),
                depth=0,  # Will be calculated during tree traversal
                is_abstract=concept_info.get('abstract', False)
            )

        # Build parent-child relationships
        if from_concept:
            if from_concept not in node_map:
                from_concept_info = concepts.get(from_concept, {})
                node_map[from_concept] = PresentationNode(
                    concept=from_concept,
                    preferred_label=self._get_preferred_label(
                        from_concept_info, None
                    ),
                    depth=0,
                    is_abstract=from_concept_info.get('abstract', False)
                )

            # Link parent to child
            parent_node = node_map[from_concept]
            child_node = node_map[to_concept]
            child_node.parent = parent_node
            parent_node.children.append(child_node)
        else:
            # Root node
            root_nodes.append(node_map[to_concept])

    # Calculate depths
    self._calculate_tree_depths(root_nodes)

    return root_nodes
```

#### 3. Tree to Statement Conversion
```python
def _tree_to_statement(self, presentation_tree: List[PresentationNode],
                      facts: Dict[str, Any], role_info: Dict[str, Any]) -> Statement:
    """Convert presentation tree to Statement with fact matching."""

    # Extract statement metadata
    statement_name = role_info.get('definition', 'Unknown Statement')
    short_name = self._get_short_name(statement_name)

    # Extract periods from facts
    periods = self._extract_periods_from_facts(facts)

    # Traverse tree and create rows
    rows = []
    for root_node in presentation_tree:
        self._traverse_node(root_node, rows, facts, periods)

    return Statement(
        name=statement_name,
        short_name=short_name,
        periods=periods,
        rows=rows
    )

def _traverse_node(self, node: PresentationNode, rows: List[Row],
                  facts: Dict[str, Any], periods: List[Period]) -> None:
    """Recursively traverse presentation node and create rows."""

    # Create cells by matching facts to this concept
    cells = {}
    for period in periods:
        cell = self._match_fact_to_concept(node.concept, period, facts)
        if cell:
            cells[period.label] = cell

    # Create row
    row = Row(
        label=node.preferred_label,
        concept=node.concept,
        is_abstract=node.is_abstract,
        depth=node.depth,
        cells=cells
    )
    rows.append(row)

    # Recursively process children
    for child in node.children:
        self._traverse_node(child, rows, facts, periods)
```

#### 4. Legacy Format (roles-based)
```python
def _parse_legacy_format(self, data: Dict[str, Any]) -> List[Statement]:
    """Parse the legacy format using presentation structure when available"""
    statements = []
    roles = data.get('roles', {})

    for role_id, role_data in roles.items():
        # Try presentation-based parsing first
        if 'relationships' in data:
            statement = self._parse_statement_with_presentation(
                role_id, role_data, data
            )
        else:
            # Fallback to fact-based parsing for older formats
            statement = self._parse_single_statement(role_id, role_data, data)

        if statement and statement.rows:
            statements.append(statement)

    return statements
```

### Statement Type Detection

```python
def _get_short_name(self, full_name: str) -> str:
    """Get short name for Excel sheet tabs."""
    name_lower = full_name.lower()

    if 'balance' in name_lower or 'position' in name_lower:
        return "Balance Sheet"
    elif any(term in name_lower for term in ['income', 'operations', 'comprehensive']):
        return "Income Statement"
    elif 'cash' in name_lower and 'flow' in name_lower:
        return "Cash Flows"
    elif 'equity' in name_lower or 'stockholder' in name_lower:
        return "Equity"
    else:
        return full_name[:20]  # Truncate long names
```

### Fact Matching and Value Formatting

The presentation-based parser matches facts to presentation nodes and formats values:

```python
def _match_fact_to_concept(self, concept: str, period: Period,
                         facts: Dict[str, Any]) -> Optional[Cell]:
    """Match a fact to a presentation concept for a specific period."""

    # Search facts for matching concept and period
    for fact_id, fact_data in facts.items():
        fact_attrs = fact_data.get('a', {})

        if (fact_attrs.get('c') == concept and
            self._period_matches(fact_attrs.get('p'), period)):

            # Extract fact value
            raw_value = fact_attrs.get('v')
            unit = fact_attrs.get('m')
            decimals = fact_attrs.get('d')

            if raw_value is not None:
                # Apply formatting
                formatted_value = self.formatter.format_cell_value(
                    raw_value, unit, decimals, concept
                )

                return Cell(
                    value=formatted_value,
                    raw_value=raw_value,
                    unit=unit,
                    decimals=decimals,
                    period=period.label
                )

    return None  # No matching fact found

def _get_preferred_label(self, concept_info: Dict[str, Any],
                        preferred_label_ref: Optional[str]) -> str:
    """Get the preferred label for a concept."""

    labels = concept_info.get('labels', {})

    # Try preferred label first
    if preferred_label_ref and preferred_label_ref in labels:
        return labels[preferred_label_ref]

    # Fallback to standard label
    if 'std' in labels:
        return labels['std']

    # Last resort: use concept name
    return concept_info.get('name', 'Unknown')
```

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
        scale_millions=not args.scale_none
    )
    data_parser = DataParser(formatter)
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
- **Preferred Labels**: Uses the correct labels as they appear in the viewer
- **Automatic Format Detection**: Handles both sourceReports and legacy formats

### Smart Statement Processing
- **Role-Based Detection**: Uses XBRL role definitions to identify statement types
- **Presentation Order**: Maintains the exact row order from the presentation linkbase
- **Hierarchical Structure**: Preserves indentation levels and section headers
- **Flexible Naming**: Handles various statement naming conventions automatically

### Value Formatting
- Integrates with `ValueFormatter` for consistent number presentation
- Handles currency scaling (millions), negative values (parentheses), EPS formatting
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
