# 11 - Refactor Specification: SEC Data Extractor v3.1

## Executive Summary

Refactor the current implementation to properly leverage Arelle's iXBRLViewerPlugin output. Instead of reconstructing statements from raw facts, we will parse and use the presentation structure that Arelle has already built for us in the viewer JSON.

### The Problem
The current implementation tries to reconstruct financial statements by grouping facts based on concept name patterns. This approach:
- Ignores the presentation linkbase structure that defines statement layout
- Uses wrong labels (concept names instead of preferred labels)
- Loses the intended row ordering from the filer
- Misses the hierarchical structure (indentation, abstract rows)
- Produces output that doesn't match the iXBRL viewer

### The Solution
Leverage Arelle's existing presentation structure parsing:
- Parse presentation relationships from viewer JSON
- Follow the presentation tree for correct row order and hierarchy
- Use preferred labels from presentation context
- Match facts to presentation cells using concept and period
- Generate Excel that exactly matches the iXBRL viewer

---

## PHASE 1: Understanding the Viewer JSON Structure

### Step 1.1: Document the Viewer JSON Schema

The iXBRLViewerPlugin generates a complex JSON structure embedded in the viewer HTML. Key components:

```javascript
{
  "sourceReports": [{
    "targetReports": [{
      "roleDefs": {
        // Role definitions - maps role IDs to statement information
        "ns8": {
          "label": "00000001 - Document - Cover Page",
          "uri": "http://apple.com/role/CoverPage"
        },
        "ns9": {
          "label": "00000002 - Statement - Balance Sheets",
          "uri": "http://apple.com/role/BalanceSheets"
        }
      },
      "rels": {
        "pres": {
          // Presentation relationships by role
          "ns9": {  // Balance Sheet role
            "rootElts": ["us-gaap:StatementOfFinancialPositionAbstract"],
            "elrs": {
              "http://apple.com/role/BalanceSheets": {
                "us-gaap:StatementOfFinancialPositionAbstract": {
                  "order": 1,
                  "children": {
                    "us-gaap:AssetsAbstract": {
                      "order": 2,
                      "preferredLabel": "terseLabel",
                      "children": {
                        "us-gaap:CashAndCashEquivalentsAtCarryingValue": {
                          "order": 3,
                          "preferredLabel": "terseLabel"
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      },
      "facts": {
        // Compressed fact storage - facts are indexed and compressed
        "f-123": {
          "a": {  // First context/period combination
            "c": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "v": 29965000000,  // value
            "d": -6,           // decimals (-6 means divide by 1,000,000)
            "u": "usd",        // unit
            "p": "2023-09-30"  // period
          },
          "b": { /* another period for same concept */ }
        }
      },
      "concepts": {
        // Concept definitions with labels
        "us-gaap:CashAndCashEquivalentsAtCarryingValue": {
          "l": "Cash and Cash Equivalents",  // standard label
          "labels": {
            "terseLabel": "Cash and cash equivalents",
            "totalLabel": "Total cash and cash equivalents",
            "verboseLabel": "Cash and Cash Equivalents at Carrying Value"
          }
        }
      }
    }]
  }]
}
```

### Step 1.2: Create Test Suite for JSON Parsing

**Files to create:**
- `tests/test_viewer_json_structure.py` - Validate JSON parsing functions
- `tests/fixtures/sample_viewer.json` - Sample viewer data for testing
- `tests/test_presentation_extraction.py` - Test presentation tree building

---

## PHASE 2: New Data Models

### Step 2.1: Create Presentation-Based Data Models

**File:** `src/processor/presentation_models.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum

class StatementType(Enum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOWS = "cash_flows"
    EQUITY = "equity"
    OTHER = "other"

@dataclass
class PresentationNode:
    """A node in the presentation tree"""
    concept: str                        # XBRL concept name
    label: str                         # Display label (using preferredLabel)
    order: float                       # Presentation order
    depth: int                         # Tree depth for indentation
    abstract: bool                     # Is this a header/section?
    children: List['PresentationNode'] # Child nodes
    preferred_label_role: Optional[str] # e.g., "terseLabel", "totalLabel"

    def get_all_nodes_flat(self) -> List[Tuple['PresentationNode', int]]:
        """Return all nodes in presentation order with depth"""
        result = [(self, self.depth)]
        for child in sorted(self.children, key=lambda x: x.order):
            result.extend(child.get_all_nodes_flat())
        return result

@dataclass
class PresentationStatement:
    """A financial statement from presentation linkbase"""
    role_uri: str                      # Full role URI
    role_id: str                       # Short role ID (e.g., "ns9")
    statement_name: str                # e.g., "Consolidated Balance Sheets"
    statement_type: StatementType      # Classified statement type
    root_nodes: List[PresentationNode] # Top-level nodes

    def get_all_nodes_flat(self) -> List[Tuple[PresentationNode, int]]:
        """Return all nodes in presentation order with depth"""
        result = []
        for root in sorted(self.root_nodes, key=lambda x: x.order):
            result.extend(root.get_all_nodes_flat())
        return result

@dataclass
class StatementTable:
    """Ready-to-render statement with facts matched to presentation"""
    statement: PresentationStatement
    periods: List['Period']            # From existing data_models.py
    rows: List['StatementRow']         # Ordered by presentation

@dataclass
class StatementRow:
    """A single row in the statement with presentation info"""
    node: PresentationNode            # Presentation information
    cells: Dict[str, 'Cell']          # period_id -> Cell (from existing models)

    # Properties for compatibility with existing Excel generator
    @property
    def label(self) -> str:
        return self.node.label

    @property
    def is_abstract(self) -> bool:
        return self.node.abstract

    @property
    def depth(self) -> int:
        return self.node.depth

    @property
    def concept(self) -> str:
        return self.node.concept
```

---

## PHASE 3: Presentation Parser Implementation

### Step 3.1: Create Presentation Parser

**File:** `src/processor/presentation_parser.py`

```python
import logging
from typing import Dict, List, Optional, Any
from .presentation_models import (
    PresentationNode, PresentationStatement, StatementType
)

logger = logging.getLogger(__name__)

class PresentationParser:
    """Parse presentation relationships from viewer JSON"""

    def parse_presentation_statements(self, viewer_data: dict) -> List[PresentationStatement]:
        """Extract all financial statements from presentation linkbase"""
        statements = []

        try:
            # Navigate to presentation relationships
            target_report = viewer_data['sourceReports'][0]['targetReports'][0]
            pres_rels = target_report['rels']['pres']
            role_defs = target_report['roleDefs']
            concepts = target_report['concepts']

            for role_id, role_data in pres_rels.items():
                # Check if this is a financial statement role
                role_def = role_defs.get(role_id, {})
                if self._is_financial_statement_role(role_def):
                    try:
                        statement = self._parse_single_statement(
                            role_id, role_data, role_def, concepts
                        )
                        statements.append(statement)
                        logger.info(f"Parsed statement: {statement.statement_name}")
                    except Exception as e:
                        logger.warning(f"Failed to parse statement {role_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error parsing presentation statements: {e}")

        return statements

    def _is_financial_statement_role(self, role_def: dict) -> bool:
        """Check if this role represents a financial statement"""
        label = role_def.get('label', '').lower()

        # Look for financial statement indicators
        financial_keywords = [
            'balance sheet', 'balance sheets',
            'income statement', 'income statements',
            'operations', 'comprehensive income',
            'cash flow', 'cash flows',
            'equity', 'stockholder'
        ]

        return any(keyword in label for keyword in financial_keywords)

    def _parse_single_statement(self, role_id: str, role_data: dict,
                               role_def: dict, concepts: dict) -> PresentationStatement:
        """Parse a single statement's presentation tree"""

        # Extract root elements
        root_elts = role_data.get('rootElts', [])
        if not root_elts:
            raise ValueError(f"No root elements found for role {role_id}")

        # Get the ELR (Extended Link Role) relationships
        elrs = role_data.get('elrs', {})
        if not elrs:
            raise ValueError(f"No ELR relationships found for role {role_id}")

        # Build presentation tree from relationships
        root_nodes = []
        for root_concept in root_elts:
            try:
                node = self._build_presentation_tree(
                    root_concept, elrs, concepts, depth=0
                )
                root_nodes.append(node)
            except Exception as e:
                logger.warning(f"Failed to build tree for {root_concept}: {e}")
                continue

        if not root_nodes:
            raise ValueError(f"No valid presentation trees built for role {role_id}")

        # Determine statement type and clean name
        statement_name = self._extract_statement_name(role_def.get('label', ''))
        statement_type = self._determine_statement_type(statement_name)

        return PresentationStatement(
            role_id=role_id,
            role_uri=role_def.get('uri', ''),
            statement_name=statement_name,
            statement_type=statement_type,
            root_nodes=root_nodes
        )

    def _build_presentation_tree(self, concept: str, elrs: dict,
                                concepts: dict, depth: int) -> PresentationNode:
        """Recursively build presentation tree from ELR relationships"""

        # Find the relationship data for this concept
        rel_data = self._find_concept_in_elrs(concept, elrs)
        if not rel_data:
            # If no relationship found, create a leaf node
            return PresentationNode(
                concept=concept,
                label=self._get_concept_label(concept, concepts),
                order=0,
                depth=depth,
                abstract=self._is_abstract_concept(concept, concepts),
                children=[],
                preferred_label_role=None
            )

        # Build children recursively
        children = []
        children_data = rel_data.get('children', {})

        for child_concept, child_data in children_data.items():
            try:
                child_node = self._build_presentation_tree(
                    child_concept, elrs, concepts, depth + 1
                )
                # Update child properties from relationship data
                child_node.order = child_data.get('order', child_node.order)
                child_node.preferred_label_role = child_data.get('preferredLabel')

                # Update label if preferred label is specified
                if child_node.preferred_label_role:
                    preferred_label = self._get_preferred_label(
                        child_concept, child_node.preferred_label_role, concepts
                    )
                    if preferred_label:
                        child_node.label = preferred_label

                children.append(child_node)

            except Exception as e:
                logger.warning(f"Failed to build child {child_concept}: {e}")
                continue

        # Sort children by order
        children.sort(key=lambda x: x.order)

        return PresentationNode(
            concept=concept,
            label=self._get_concept_label(concept, concepts),
            order=rel_data.get('order', 0),
            depth=depth,
            abstract=self._is_abstract_concept(concept, concepts),
            children=children,
            preferred_label_role=rel_data.get('preferredLabel')
        )

    def _find_concept_in_elrs(self, concept: str, elrs: dict) -> Optional[dict]:
        """Find concept relationship data within ELRs"""
        for elr_uri, elr_data in elrs.items():
            if concept in elr_data:
                return elr_data[concept]

        # Also check if concept appears as child in any relationship
        for elr_uri, elr_data in elrs.items():
            for parent_concept, parent_data in elr_data.items():
                children = parent_data.get('children', {})
                if concept in children:
                    return children[concept]

        return None

    def _get_concept_label(self, concept: str, concepts: dict) -> str:
        """Get the best available label for a concept"""
        concept_data = concepts.get(concept, {})

        # Try standard label first
        if 'l' in concept_data and concept_data['l']:
            return concept_data['l']

        # Try labels dictionary
        labels = concept_data.get('labels', {})
        for label_type in ['terseLabel', 'verboseLabel', 'label']:
            if label_type in labels and labels[label_type]:
                return labels[label_type]

        # Fallback to concept name
        return self._humanize_concept_name(concept)

    def _get_preferred_label(self, concept: str, preferred_role: str,
                            concepts: dict) -> Optional[str]:
        """Get preferred label for concept in specific role"""
        concept_data = concepts.get(concept, {})
        labels = concept_data.get('labels', {})

        return labels.get(preferred_role)

    def _is_abstract_concept(self, concept: str, concepts: dict) -> bool:
        """Determine if concept is abstract (header/section)"""
        concept_data = concepts.get(concept, {})

        # Check if explicitly marked as abstract
        if concept_data.get('abstract', False):
            return True

        # Heuristic: concepts ending in "Abstract" are usually abstract
        return concept.endswith('Abstract')

    def _humanize_concept_name(self, concept: str) -> str:
        """Convert concept name to human-readable label"""
        # Remove namespace prefix
        if ':' in concept:
            concept = concept.split(':', 1)[1]

        # Convert camelCase to Title Case
        import re
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept).split()
        return ' '.join(word.capitalize() for word in words)

    def _extract_statement_name(self, role_label: str) -> str:
        """Clean up role label to get statement name"""
        if not role_label:
            return "Financial Statement"

        # Remove common prefixes like "00000002 - Statement - "
        import re
        cleaned = re.sub(r'^\d+\s*-\s*(Statement\s*-\s*)?', '', role_label)

        return cleaned.strip() or "Financial Statement"

    def _determine_statement_type(self, statement_name: str) -> StatementType:
        """Classify statement type from name"""
        name_lower = statement_name.lower()

        if any(term in name_lower for term in ['balance', 'position', 'financial position']):
            return StatementType.BALANCE_SHEET
        elif any(term in name_lower for term in ['income', 'operations', 'earnings', 'comprehensive']):
            return StatementType.INCOME_STATEMENT
        elif any(term in name_lower for term in ['cash', 'flow']):
            return StatementType.CASH_FLOWS
        elif any(term in name_lower for term in ['equity', 'stockholder', 'shareholder']):
            return StatementType.EQUITY
        else:
            return StatementType.OTHER
```

### Step 3.2: Create Fact Matcher

**File:** `src/processor/fact_matcher.py`

```python
import logging
from typing import Dict, List, Optional
from .presentation_models import PresentationStatement, StatementTable, StatementRow
from .data_models import Period, Cell

logger = logging.getLogger(__name__)

class FactMatcher:
    """Match facts to presentation rows"""

    def __init__(self, formatter=None):
        self.formatter = formatter

    def match_facts_to_statement(self, statement: PresentationStatement,
                                facts: dict, periods: List[Period]) -> StatementTable:
        """Create a complete statement table with facts matched to presentation"""

        logger.debug(f"Matching facts for statement: {statement.statement_name}")

        rows = []

        # Flatten presentation tree to get all rows in presentation order
        for node, depth in statement.get_all_nodes_flat():
            # Find facts for this concept across all periods
            cells = {}

            for period in periods:
                fact = self._find_fact_for_concept_and_period(
                    node.concept, period, facts
                )

                if fact:
                    cell = self._create_cell_from_fact(fact, period)
                else:
                    cell = Cell(
                        value="—",
                        raw_value=None,
                        unit=None,
                        decimals=None,
                        period=period.label
                    )

                cells[period.label] = cell

            rows.append(StatementRow(node=node, cells=cells))

        logger.debug(f"Created {len(rows)} rows for statement")

        return StatementTable(
            statement=statement,
            periods=periods,
            rows=rows
        )

    def _find_fact_for_concept_and_period(self, concept: str,
                                         period: Period, facts: dict) -> Optional[dict]:
        """Find the fact matching concept and period"""

        # Search through compressed facts structure
        for fact_id, fact_data in facts.items():
            # Each fact can have multiple contexts (a, b, c, etc.)
            for context_key, context_data in fact_data.items():
                if not isinstance(context_data, dict):
                    continue

                # Check if concept matches
                if context_data.get('c') != concept:
                    continue

                # Check if period matches
                if self._period_matches(period, context_data.get('p')):
                    return context_data

        return None

    def _period_matches(self, period: Period, fact_period: str) -> bool:
        """Check if period matches fact period"""
        if not fact_period:
            return False

        # Handle different period formats
        if period.instant:
            # For instant periods, match end date
            return fact_period == period.end_date
        else:
            # For duration periods, could be in format "2022-09-25/2023-10-01"
            if '/' in fact_period:
                start_date, end_date = fact_period.split('/')
                return end_date == period.end_date
            else:
                # Single date might represent end of period
                return fact_period == period.end_date

    def _create_cell_from_fact(self, fact: dict, period: Period) -> Cell:
        """Create a Cell from fact data"""
        raw_value = fact.get('v')
        unit = fact.get('u')
        decimals = fact.get('d')

        # Apply formatting if formatter is available
        if self.formatter and raw_value is not None:
            formatted_value = self.formatter.format_cell_value(
                raw_value, unit, decimals, fact.get('c', '')
            )
        else:
            formatted_value = str(raw_value) if raw_value is not None else "—"

        return Cell(
            value=formatted_value,
            raw_value=raw_value,
            unit=unit,
            decimals=decimals,
            period=period.label
        )
```

---

## PHASE 4: Integration with Existing Pipeline

### Step 4.1: Update Main Data Parser

**File:** `src/processor/data_parser.py` (MAJOR REFACTOR)

```python
import logging
from typing import Dict, Any, List, Optional
from .data_models import Statement, Period, ProcessingResult
from .value_formatter import ValueFormatter
from .presentation_parser import PresentationParser
from .fact_matcher import FactMatcher
from .presentation_models import StatementType

logger = logging.getLogger(__name__)

class DataParser:
    """Updated parser using presentation structure"""

    def __init__(self, formatter: Optional[ValueFormatter] = None):
        self.formatter = formatter or ValueFormatter()
        self.presentation_parser = PresentationParser()
        self.fact_matcher = FactMatcher(formatter)

        # Feature flag for backwards compatibility
        self.use_presentation_parsing = True

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        """Main entry point - now uses presentation structure"""

        try:
            # Extract metadata (keep existing methods)
            company_name = self._extract_company_name(viewer_data)
            filing_date = self._extract_filing_date(viewer_data)
            form_type = self._extract_form_type(viewer_data)

            if self.use_presentation_parsing:
                statements = self._parse_with_presentation(viewer_data)
            else:
                # Fallback to legacy parsing
                statements = self._parse_legacy_format(viewer_data)

            return ProcessingResult(
                statements=statements,
                company_name=company_name,
                filing_date=filing_date,
                form_type=form_type,
                success=True
            )

        except Exception as e:
            logger.error(f"Error parsing viewer data: {e}")
            return ProcessingResult(
                statements=[],
                company_name="Unknown Company",
                filing_date="Unknown Date",
                form_type="Unknown Form",
                success=False,
                error=str(e)
            )

    def _parse_with_presentation(self, viewer_data: Dict[str, Any]) -> List[Statement]:
        """New presentation-based parsing"""

        logger.info("Using presentation-based parsing")

        # Parse presentation structure
        presentation_statements = self.presentation_parser.parse_presentation_statements(
            viewer_data
        )

        if not presentation_statements:
            logger.warning("No presentation statements found, falling back to legacy parsing")
            return self._parse_legacy_format(viewer_data)

        # Extract periods and facts
        periods = self._extract_periods_from_viewer_data(viewer_data)
        facts = self._extract_facts_from_viewer_data(viewer_data)

        # Match facts to presentation for each statement
        statement_tables = []
        for pres_statement in presentation_statements:
            if self._is_primary_statement(pres_statement):
                try:
                    table = self.fact_matcher.match_facts_to_statement(
                        pres_statement, facts, periods
                    )
                    statement_tables.append(table)
                    logger.info(f"Matched facts for: {pres_statement.statement_name}")
                except Exception as e:
                    logger.warning(f"Failed to match facts for {pres_statement.statement_name}: {e}")
                    continue

        # Convert to existing Statement format for compatibility with Excel generator
        statements = self._convert_statement_tables_to_legacy_format(statement_tables)

        logger.info(f"Parsed {len(statements)} statements using presentation structure")
        return statements

    def _is_primary_statement(self, statement) -> bool:
        """Check if this is a primary financial statement"""
        primary_types = {
            StatementType.BALANCE_SHEET,
            StatementType.INCOME_STATEMENT,
            StatementType.CASH_FLOWS,
            StatementType.EQUITY
        }
        return statement.statement_type in primary_types

    def _extract_periods_from_viewer_data(self, viewer_data: Dict[str, Any]) -> List[Period]:
        """Extract periods from viewer data"""
        periods = []

        try:
            # Get facts to extract periods from
            facts = self._extract_facts_from_viewer_data(viewer_data)
            period_map = {}

            # Collect unique periods from facts
            for fact_data in facts.values():
                for context_data in fact_data.values():
                    if not isinstance(context_data, dict):
                        continue

                    period_str = context_data.get('p')
                    if period_str and period_str not in period_map:
                        # Parse period string
                        period = self._parse_period_string(period_str)
                        if period:
                            period_map[period_str] = period

            # Sort periods by date (most recent first)
            periods = list(period_map.values())
            periods.sort(key=lambda p: p.end_date, reverse=True)

        except Exception as e:
            logger.error(f"Error extracting periods: {e}")

        return periods

    def _parse_period_string(self, period_str: str) -> Optional[Period]:
        """Parse period string into Period object"""
        try:
            if '/' in period_str:
                # Duration period: "2022-09-25/2023-10-01"
                start_str, end_str = period_str.split('/')
                return Period(
                    label=f"{start_str} to {end_str}",
                    end_date=end_str,
                    instant=False
                )
            else:
                # Instant period: "2023-09-30"
                return Period(
                    label=period_str,
                    end_date=period_str,
                    instant=True
                )
        except Exception:
            return None

    def _extract_facts_from_viewer_data(self, viewer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract facts from viewer data"""
        try:
            return viewer_data['sourceReports'][0]['targetReports'][0]['facts']
        except (KeyError, IndexError):
            logger.error("Could not extract facts from viewer data")
            return {}

    def _convert_statement_tables_to_legacy_format(self, tables: List) -> List[Statement]:
        """Convert StatementTable objects to legacy Statement format"""

        statements = []

        for table in tables:
            # Create legacy Statement object
            statement = Statement(
                name=table.statement.statement_name,
                short_name=self._get_short_name(table.statement.statement_name),
                periods=table.periods,
                rows=[]  # Will be populated below
            )

            # Convert StatementRow objects to legacy Row format
            from .data_models import Row

            for statement_row in table.rows:
                row = Row(
                    label=statement_row.node.label,
                    concept=statement_row.node.concept,
                    is_abstract=statement_row.node.abstract,
                    depth=statement_row.node.depth,
                    cells=statement_row.cells
                )

                # Add reference to presentation node for Excel generator
                row.presentation_node = statement_row.node

                statement.rows.append(row)

            statements.append(statement)

        return statements

    def _get_short_name(self, statement_name: str) -> str:
        """Get short name for Excel sheet tabs"""
        name_lower = statement_name.lower()

        if any(term in name_lower for term in ['balance', 'position']):
            return "Balance Sheet"
        elif any(term in name_lower for term in ['income', 'operations', 'comprehensive']):
            return "Income Statement"
        elif any(term in name_lower for term in ['cash', 'flow']):
            return "Cash Flows"
        elif any(term in name_lower for term in ['equity', 'stockholder']):
            return "Equity"
        else:
            return statement_name[:20]  # Truncate long names

    # Keep all existing methods for backwards compatibility
    def _parse_legacy_format(self, viewer_data: Dict[str, Any]) -> List[Statement]:
        """Legacy parsing method (existing implementation)"""
        # This would be the current implementation
        # Kept for backwards compatibility during transition
        return self._parse_statements(viewer_data)

    # ... (keep all existing extraction methods for metadata and legacy parsing)
```

### Step 4.2: Update Excel Generator

**File:** `src/processor/excel_generator.py` (MINOR UPDATES for presentation support)

```python
# Add presentation-aware formatting to existing Excel generator

def _write_statement_rows(self, ws, statement: Statement, start_row: int):
    """Write statement rows with presentation-aware formatting"""

    current_row = start_row

    for row in statement.rows:
        # Check if this row has presentation info
        presentation_node = getattr(row, 'presentation_node', None)

        # Apply indentation based on presentation depth
        if presentation_node:
            # Use presentation depth for indentation
            ws.cell(current_row, 1).alignment = Alignment(
                indent=presentation_node.depth
            )

            # Bold for abstract/header rows
            if presentation_node.abstract:
                for col in range(1, len(statement.periods) + 2):
                    cell = ws.cell(current_row, col)
                    cell.font = Font(bold=True)

            # Add border for total rows based on preferred label
            if (presentation_node.preferred_label_role and
                'total' in presentation_node.preferred_label_role.lower()):
                for col in range(2, len(statement.periods) + 2):
                    cell = ws.cell(current_row, col)
                    cell.border = Border(top=Side(style='thin'))
        else:
            # Fallback to existing logic for backwards compatibility
            ws.cell(current_row, 1).alignment = Alignment(
                indent=getattr(row, 'depth', 0)
            )

            if getattr(row, 'is_abstract', False):
                for col in range(1, len(statement.periods) + 2):
                    cell = ws.cell(current_row, col)
                    cell.font = Font(bold=True)

        # Write row label
        ws.cell(current_row, 1, row.label)

        # Write cell values
        for col, period in enumerate(statement.periods, start=2):
            cell_data = row.cells.get(period.label)
            if cell_data and cell_data.value and cell_data.value != "—":
                cell = ws.cell(current_row, col)
                cell.value = cell_data.value

                # Apply number formatting for numeric values
                if cell_data.raw_value is not None:
                    if cell_data.unit and 'usd' in cell_data.unit.lower():
                        # Currency formatting
                        cell.number_format = '#,##0.0_);(#,##0.0)'
                    elif cell_data.unit and 'shares' in cell_data.unit.lower():
                        # Share count formatting
                        cell.number_format = '#,##0'
                    elif cell_data.unit and 'pure' in cell_data.unit.lower():
                        # Ratio/percentage formatting
                        cell.number_format = '0.00'

        current_row += 1

    return current_row
```

---

## PHASE 5: Testing and Validation

### Step 5.1: Create Comprehensive Test Suite

**File:** `tests/test_presentation_parser.py`

```python
import pytest
import json
from src.processor.presentation_parser import PresentationParser
from src.processor.presentation_models import StatementType

class TestPresentationParser:

    def test_parse_balance_sheet_structure(self, sample_viewer_data):
        """Test parsing of balance sheet presentation structure"""
        parser = PresentationParser()
        statements = parser.parse_presentation_statements(sample_viewer_data)

        balance_sheet = next(
            (s for s in statements if s.statement_type == StatementType.BALANCE_SHEET),
            None
        )

        assert balance_sheet is not None
        assert "Balance" in balance_sheet.statement_name
        assert len(balance_sheet.root_nodes) > 0

        # Test presentation order is preserved
        all_nodes = balance_sheet.get_all_nodes_flat()
        orders = [node.order for node, depth in all_nodes]
        assert orders == sorted(orders)  # Should be in order

    def test_presentation_hierarchy(self, sample_viewer_data):
        """Test that presentation hierarchy is correctly built"""
        parser = PresentationParser()
        statements = parser.parse_presentation_statements(sample_viewer_data)

        statement = statements[0]  # Take first statement
        all_nodes = statement.get_all_nodes_flat()

        # Check that parent depth < child depth
        for i in range(1, len(all_nodes)):
            node, depth = all_nodes[i]
            if node.children:
                # This is a parent node - children should have higher depth
                child_depths = [child.depth for child in node.children]
                assert all(child_depth > depth for child_depth in child_depths)

    def test_abstract_node_identification(self, sample_viewer_data):
        """Test identification of abstract (header) nodes"""
        parser = PresentationParser()
        statements = parser.parse_presentation_statements(sample_viewer_data)

        # Should have some abstract nodes (section headers)
        all_nodes = []
        for statement in statements:
            all_nodes.extend([node for node, depth in statement.get_all_nodes_flat()])

        abstract_nodes = [node for node in all_nodes if node.abstract]
        assert len(abstract_nodes) > 0

        # Abstract nodes typically end with "Abstract"
        for node in abstract_nodes:
            assert node.concept.endswith('Abstract') or 'Abstract' in node.concept

@pytest.fixture
def sample_viewer_data():
    """Sample viewer data for testing"""
    # This would be loaded from tests/fixtures/sample_viewer.json
    with open('tests/fixtures/sample_viewer.json') as f:
        return json.load(f)
```

**File:** `tests/test_fact_matcher.py`

```python
import pytest
from src.processor.fact_matcher import FactMatcher
from src.processor.data_models import Period, Cell

class TestFactMatcher:

    def test_fact_matching_accuracy(self, sample_statement, sample_facts, sample_periods):
        """Test that facts are correctly matched to presentation rows"""
        matcher = FactMatcher()
        table = matcher.match_facts_to_statement(
            sample_statement, sample_facts, sample_periods
        )

        # Should have rows for each presentation node
        expected_row_count = len(sample_statement.get_all_nodes_flat())
        assert len(table.rows) == expected_row_count

        # Each row should have cells for each period
        for row in table.rows:
            assert len(row.cells) == len(sample_periods)

        # Check that some facts were actually matched (not all "—")
        non_empty_cells = 0
        for row in table.rows:
            for cell in row.cells.values():
                if cell.value != "—":
                    non_empty_cells += 1

        assert non_empty_cells > 0  # Should have some actual data

    def test_period_matching_logic(self):
        """Test the period matching logic"""
        matcher = FactMatcher()

        # Test instant period matching
        instant_period = Period(label="2023-09-30", end_date="2023-09-30", instant=True)
        assert matcher._period_matches(instant_period, "2023-09-30")
        assert not matcher._period_matches(instant_period, "2023-09-29")

        # Test duration period matching
        duration_period = Period(
            label="2022-09-25 to 2023-09-30",
            end_date="2023-09-30",
            instant=False
        )
        assert matcher._period_matches(duration_period, "2022-09-25/2023-09-30")
        assert matcher._period_matches(duration_period, "2023-09-30")  # End date match
        assert not matcher._period_matches(duration_period, "2022-09-25/2023-09-29")
```

### Step 5.2: Integration Testing

**File:** `tests/test_integration_presentation.py`

```python
import pytest
from src.processor.data_parser import DataParser
from src.processor.value_formatter import ValueFormatter

class TestPresentationIntegration:

    def test_end_to_end_presentation_parsing(self, apple_viewer_data):
        """Test complete pipeline with presentation parsing"""
        formatter = ValueFormatter(scale_millions=True)
        parser = DataParser(formatter)
        parser.use_presentation_parsing = True

        result = parser.parse_viewer_data(apple_viewer_data)

        assert result.success
        assert len(result.statements) >= 3  # BS, IS, CF minimum

        # Check statement names are proper
        statement_names = [s.name for s in result.statements]
        assert any("Balance" in name for name in statement_names)
        assert any("Income" in name or "Operations" in name for name in statement_names)
        assert any("Cash" in name for name in statement_names)

        # Check data quality
        for statement in result.statements:
            assert len(statement.periods) > 0
            assert len(statement.rows) > 0

            # Should have some non-empty rows
            data_rows = [r for r in statement.rows if any(
                cell.value != "—" for cell in r.cells.values()
            )]
            assert len(data_rows) > 0

    def test_presentation_vs_legacy_comparison(self, sample_viewer_data):
        """Compare presentation parsing vs legacy parsing"""
        parser = DataParser()

        # Parse with presentation
        parser.use_presentation_parsing = True
        pres_result = parser.parse_viewer_data(sample_viewer_data)

        # Parse with legacy
        parser.use_presentation_parsing = False
        legacy_result = parser.parse_viewer_data(sample_viewer_data)

        # Presentation parsing should produce better structured output
        assert pres_result.success
        assert legacy_result.success

        # Compare statement structure
        pres_statements = {s.short_name: s for s in pres_result.statements}
        legacy_statements = {s.short_name: s for s in legacy_result.statements}

        # Should have same statement types but better organization
        assert set(pres_statements.keys()) >= set(legacy_statements.keys())

        # Presentation should preserve hierarchy better
        if "Balance Sheet" in pres_statements:
            pres_bs = pres_statements["Balance Sheet"]
            # Should have proper indentation levels
            depths = [getattr(row, 'depth', 0) for row in pres_bs.rows]
            assert max(depths) > 0  # Should have some indentation
```

### Step 5.3: Validation Criteria

**File:** `tests/test_output_validation.py`

```python
import pytest
import openpyxl
from src.processor.excel_generator import ExcelGenerator

class TestOutputValidation:

    def test_excel_formatting_accuracy(self, processed_statements, output_file):
        """Test that Excel output matches presentation requirements"""
        generator = ExcelGenerator()
        generator.generate_excel(processed_statements, output_file)

        # Load and validate Excel file
        wb = openpyxl.load_workbook(output_file)

        # Should have sheets for primary statements
        expected_sheets = {"Balance Sheet", "Income Statement", "Cash Flows"}
        actual_sheets = set(wb.sheetnames) - {"Summary"}
        assert expected_sheets.issubset(actual_sheets)

        # Test Balance Sheet structure
        if "Balance Sheet" in wb.sheetnames:
            ws = wb["Balance Sheet"]

            # Should have proper headers
            assert ws.cell(2, 1).value == "Item"  # Row header
            assert ws.cell(2, 2).value is not None  # Period header

            # Check for proper indentation (some cells should be indented)
            indented_rows = 0
            for row in range(3, ws.max_row + 1):
                cell = ws.cell(row, 1)
                if cell.alignment and cell.alignment.indent > 0:
                    indented_rows += 1

            assert indented_rows > 0  # Should have some indented rows

            # Check for bold headers (abstract rows)
            bold_rows = 0
            for row in range(3, ws.max_row + 1):
                cell = ws.cell(row, 1)
                if cell.font and cell.font.bold:
                    bold_rows += 1

            assert bold_rows > 0  # Should have some bold header rows

    def test_value_accuracy_spot_check(self, processed_statements):
        """Spot check that values are correctly formatted"""

        for statement in processed_statements:
            for row in statement.rows:
                for period_label, cell in row.cells.items():
                    if cell.raw_value is not None:
                        # Check number formatting
                        if cell.unit and 'usd' in cell.unit.lower():
                            # Should be formatted in millions with proper scale
                            if abs(cell.raw_value) >= 1000000:
                                # Value should be scaled down
                                expected_display = cell.raw_value / 1000000
                                # Allow some tolerance for rounding
                                assert abs(float(cell.value.replace(',', '')) - expected_display) < 1.0

                        # Negative values should use parentheses
                        if cell.raw_value < 0:
                            assert '(' in cell.value and ')' in cell.value
```

---

## PHASE 6: Migration Strategy

### Step 6.1: Feature Flag Implementation

**File:** `render_viewer_to_xlsx.py` (UPDATE)

```python
def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert SEC iXBRL filings to Excel format",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # ... existing arguments ...

    # NEW: Feature flag for presentation parsing
    parser.add_argument(
        '--use-presentation',
        action='store_true',
        default=True,  # Default to new method
        help='Use presentation linkbase structure (default)'
    )

    parser.add_argument(
        '--use-legacy',
        action='store_true',
        help='Use legacy fact-based parsing'
    )

    return parser

def process_filing(args) -> None:
    """Process the filing through the complete pipeline."""

    # ... existing setup code ...

    # Step 4: Data parsing with method selection
    logger.info("Step 4: Parsing financial data...")
    formatter = ValueFormatter(
        currency=args.currency,
        scale_millions=not args.scale_none
    )
    data_parser = DataParser(formatter)

    # Set parsing method based on arguments
    if args.use_legacy:
        data_parser.use_presentation_parsing = False
        logger.info("Using legacy fact-based parsing")
    else:
        data_parser.use_presentation_parsing = True
        logger.info("Using presentation-based parsing")

    result = data_parser.parse_viewer_data(viewer_data)

    # ... rest of processing ...
```

### Step 6.2: Gradual Migration Plan

1. **Week 1-2**: Implement presentation parsing alongside existing code
2. **Week 3**: Add feature flag and parallel testing
3. **Week 4**: Test with multiple real filings, compare outputs
4. **Week 5**: Make presentation parsing the default
5. **Week 6**: Remove legacy code after validation period

### Step 6.3: Backwards Compatibility

```python
# In data_parser.py
class DataParser:

    def __init__(self, formatter: Optional[ValueFormatter] = None):
        self.formatter = formatter or ValueFormatter()

        # Feature flag - can be set from environment or config
        import os
        self.use_presentation_parsing = os.getenv(
            'SEC_EXTRACTOR_USE_PRESENTATION', 'true'
        ).lower() == 'true'

        # Initialize parsers conditionally
        if self.use_presentation_parsing:
            self.presentation_parser = PresentationParser()
            self.fact_matcher = FactMatcher(formatter)

    def parse_viewer_data(self, viewer_data: Dict[str, Any]) -> ProcessingResult:
        """Parse with method selection"""

        if self.use_presentation_parsing:
            try:
                return self._parse_with_presentation(viewer_data)
            except Exception as e:
                logger.warning(f"Presentation parsing failed: {e}")
                logger.info("Falling back to legacy parsing")
                return self._parse_legacy_format(viewer_data)
        else:
            return self._parse_legacy_format(viewer_data)
```

---

## Success Metrics

### Quantitative Metrics

1. **Accuracy**:
   - Row labels match iXBRL viewer: 100%
   - Row order matches iXBRL viewer: 100%
   - Values in correct cells: >99%

2. **Completeness**:
   - Primary statements extracted: 100% (BS, IS, CF)
   - Secondary statements: >80% (Equity, etc.)
   - Data rows with values: >90%

3. **Performance**:
   - Processing time: <30 seconds for typical 10-K
   - Memory usage: <2GB for largest filings
   - Success rate: >95% of filings process without errors

### Qualitative Metrics

1. **Visual Fidelity**: Excel output looks like professional financial statements
2. **Usability**: Finance professionals can immediately understand the output
3. **Maintainability**: Code is organized and extensible for new requirements

---

## Risk Mitigation

### Risk 1: Complex Presentation Structures
**Issue**: Some filings have deeply nested dimensions or unusual structures
**Mitigation**:
- Start with simple cases, add complexity gradually
- Comprehensive test suite with various filing types
- Fallback to legacy parsing for problematic cases

### Risk 2: Missing Presentation Data
**Issue**: Some concepts might not have proper presentation linkbase info
**Mitigation**:
- Hybrid approach: use presentation where available, fact-based for gaps
- Validate against known good examples
- Manual review process for edge cases

### Risk 3: Performance Degradation
**Issue**: Tree traversal and matching might be slower than current approach
**Mitigation**:
- Profile and optimize critical paths
- Cache presentation trees
- Lazy loading of unused data

### Risk 4: Backwards Compatibility
**Issue**: Existing users depend on current output format
**Mitigation**:
- Feature flag for gradual transition
- Side-by-side testing
- Clear migration documentation

### Risk 5: Data Quality Issues
**Issue**: New approach might introduce new types of errors
**Mitigation**:
- Extensive validation against iXBRL viewer
- Comprehensive test suite with real filings
- Manual review of critical use cases

---

## Next Steps

1. **Immediate**: Start Phase 1 - document viewer JSON structure
2. **Week 1**: Implement presentation models and parser
3. **Week 2**: Build fact matching and integration
4. **Week 3**: Testing and validation
5. **Week 4**: Migration and deployment

This refactor will transform the SEC Data Extractor from a "best guess" approach to a precise, presentation-driven system that exactly matches what filers intended and what the iXBRL viewer displays.