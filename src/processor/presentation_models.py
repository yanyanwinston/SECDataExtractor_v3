"""
Presentation-based data models for SEC filing processing.

These models represent the presentation structure extracted from iXBRL viewer JSON,
enabling exact visual fidelity with the original filing presentation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum

# Import existing data models for compatibility
from .data_models import Period, Cell


class StatementType(Enum):
    """Classification of financial statement types."""
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOWS = "cash_flows"
    COMPREHENSIVE_INCOME = "comprehensive_income"
    EQUITY = "equity"
    OTHER = "other"


@dataclass
class PresentationNode:
    """A node in the presentation tree representing an XBRL concept."""
    concept: str                        # XBRL concept name (e.g., "us-gaap:Assets")
    label: str                         # Display label (using preferredLabel)
    order: float                       # Presentation order (for sorting siblings)
    depth: int                         # Tree depth for indentation (0 = root)
    abstract: bool                     # Is this a header/section (no fact values)?
    preferred_label_role: Optional[str] = None  # e.g., "terseLabel", "totalLabel"
    children: List['PresentationNode'] = field(default_factory=list)  # Child nodes

    def add_child(self, child: 'PresentationNode') -> None:
        """Add a child node and set its depth."""
        child.depth = self.depth + 1
        self.children.append(child)

    def get_all_nodes_flat(self) -> List[Tuple['PresentationNode', int]]:
        """Return all nodes in presentation order with depth.

        Returns:
            List of (node, depth) tuples in the order they should appear
            in the financial statement.
        """
        result = [(self, self.depth)]

        # Sort children by order and recursively add their nodes
        for child in sorted(self.children, key=lambda x: x.order):
            result.extend(child.get_all_nodes_flat())

        return result

    def find_node_by_concept(self, concept: str) -> Optional['PresentationNode']:
        """Find a node in this subtree by concept name."""
        if self.concept == concept:
            return self

        for child in self.children:
            found = child.find_node_by_concept(concept)
            if found:
                return found

        return None

    def get_all_concepts(self) -> List[str]:
        """Get all concept names in this subtree."""
        concepts = [self.concept]
        for child in self.children:
            concepts.extend(child.get_all_concepts())
        return concepts

    def __str__(self) -> str:
        """String representation showing tree structure."""
        indent = "  " * self.depth
        node_type = " (abstract)" if self.abstract else ""
        return f"{indent}{self.label}{node_type}"


@dataclass
class PresentationStatement:
    """A financial statement built from presentation linkbase."""
    role_uri: str                      # Full role URI from XBRL
    role_id: str                       # Short role ID (e.g., "ns9")
    statement_name: str                # e.g., "Consolidated Balance Sheets"
    statement_type: StatementType      # Classified statement type
    root_nodes: List[PresentationNode] = field(default_factory=list)  # Top-level nodes

    def get_all_nodes_flat(self) -> List[Tuple[PresentationNode, int]]:
        """Return all nodes in presentation order with depth.

        Returns:
            List of (node, depth) tuples representing the complete
            statement in the order rows should appear.
        """
        result = []

        # Sort root nodes by order and get their flattened trees
        for root in sorted(self.root_nodes, key=lambda x: x.order):
            result.extend(root.get_all_nodes_flat())

        return result

    def find_node_by_concept(self, concept: str) -> Optional[PresentationNode]:
        """Find a node by concept name anywhere in the statement."""
        for root in self.root_nodes:
            found = root.find_node_by_concept(concept)
            if found:
                return found
        return None

    def get_all_concepts(self) -> List[str]:
        """Get all concept names in this statement."""
        concepts = []
        for root in self.root_nodes:
            concepts.extend(root.get_all_concepts())
        return concepts

    def add_root_node(self, node: PresentationNode) -> None:
        """Add a root node to this statement."""
        node.depth = 0  # Ensure root nodes have depth 0
        self.root_nodes.append(node)

    def get_short_name(self) -> str:
        """Get short name suitable for Excel sheet tabs."""
        name_lower = self.statement_name.lower()

        if 'balance' in name_lower or 'position' in name_lower:
            return "Balance Sheet"
        elif any(term in name_lower for term in ['income', 'operations']):
            return "Income Statement"
        elif 'cash' in name_lower and 'flow' in name_lower:
            return "Cash Flows"
        elif 'comprehensive' in name_lower and 'income' in name_lower:
            return "Comprehensive Income"
        elif 'equity' in name_lower or 'stockholder' in name_lower:
            return "Equity"
        else:
            # Truncate long names for Excel compatibility
            return self.statement_name[:20] if len(self.statement_name) > 20 else self.statement_name

    def __str__(self) -> str:
        """String representation of the statement structure."""
        lines = [f"{self.statement_name} ({self.statement_type.value})"]
        lines.append(f"Role: {self.role_id}")
        lines.append(f"Root nodes: {len(self.root_nodes)}")

        if self.root_nodes:
            lines.append("Structure:")
            for root in sorted(self.root_nodes, key=lambda x: x.order):
                lines.append(str(root))

        return "\n".join(lines)


@dataclass
class StatementRow:
    """A single row in a financial statement with presentation information."""
    node: PresentationNode            # Presentation information
    cells: Dict[str, Cell] = field(default_factory=dict)  # period_id -> Cell

    # Properties for compatibility with existing Excel generator
    @property
    def label(self) -> str:
        """Row display label."""
        return self.node.label

    @property
    def is_abstract(self) -> bool:
        """Whether this is a header/section row."""
        return self.node.abstract

    @property
    def depth(self) -> int:
        """Indentation depth."""
        return self.node.depth

    @property
    def concept(self) -> str:
        """XBRL concept name."""
        return self.node.concept

    def add_cell(self, period_id: str, cell: Cell) -> None:
        """Add a cell for a specific period."""
        self.cells[period_id] = cell

    def get_cell(self, period_id: str) -> Optional[Cell]:
        """Get cell for a specific period."""
        return self.cells.get(period_id)

    def has_data(self) -> bool:
        """Check if this row has any meaningful cell values."""
        for cell in self.cells.values():
            if cell is None:
                continue

            if cell.raw_value is not None:
                return True

            if cell.value is None:
                continue

            value_str = str(cell.value).strip()
            if not value_str:
                continue

            if value_str == "—":
                continue

            return True

        return False

    def __str__(self) -> str:
        """String representation of the row."""
        indent = "  " * self.depth
        cell_count = len([c for c in self.cells.values() if c.value])
        abstract_marker = " [HEADER]" if self.abstract else ""
        return f"{indent}{self.label}{abstract_marker} ({cell_count} values)"


@dataclass
class StatementTable:
    """Complete statement ready for rendering with facts matched to presentation."""
    statement: PresentationStatement
    periods: List[Period]              # Time periods (from existing data_models.py)
    rows: List[StatementRow] = field(default_factory=list)  # Ordered by presentation

    def add_row(self, row: StatementRow) -> None:
        """Add a row to the statement table."""
        self.rows.append(row)

    def get_row_by_concept(self, concept: str) -> Optional[StatementRow]:
        """Find a row by its concept."""
        return next((row for row in self.rows if row.concept == concept), None)

    def get_abstract_rows(self) -> List[StatementRow]:
        """Get all header/section rows."""
        return [row for row in self.rows if row.is_abstract]

    def get_data_rows(self) -> List[StatementRow]:
        """Get all rows with actual data (non-abstract)."""
        return [row for row in self.rows if not row.is_abstract]

    def get_rows_with_data(self) -> List[StatementRow]:
        """Get all rows that have at least one non-empty cell."""
        return [row for row in self.rows if row.has_data()]

    def validate(self) -> List[str]:
        """Validate the statement table and return any issues."""
        issues = []

        if not self.periods:
            issues.append("No periods defined")

        if not self.rows:
            issues.append("No rows defined")

        # Check for duplicate concepts
        concepts = [row.concept for row in self.rows if row.concept]
        duplicates = [c for c in set(concepts) if concepts.count(c) > 1]
        if duplicates:
            issues.append(f"Duplicate concepts: {duplicates}")

        # Check for rows with invalid depths
        invalid_depths = [row for row in self.rows if row.depth < 0]
        if invalid_depths:
            issues.append(f"Rows with negative depth: {len(invalid_depths)}")

        return issues

    def to_legacy_statement(self) -> 'Statement':
        """Convert to legacy Statement format for backward compatibility."""
        from .data_models import Statement, Row

        legacy_rows = []
        for stmt_row in self.rows:
            legacy_row = Row(
                label=stmt_row.label,
                concept=stmt_row.concept,
                is_abstract=stmt_row.is_abstract,
                depth=stmt_row.depth,
                cells={period_id: cell for period_id, cell in stmt_row.cells.items()}
            )
            legacy_rows.append(legacy_row)

        return Statement(
            name=self.statement.statement_name,
            short_name=self.statement.get_short_name(),
            periods=self.periods,
            rows=legacy_rows
        )

    def __str__(self) -> str:
        """String representation of the complete statement table."""
        lines = [str(self.statement)]
        lines.append(f"Periods: {len(self.periods)}")
        lines.append(f"Rows: {len(self.rows)} ({len(self.get_data_rows())} data, {len(self.get_abstract_rows())} headers)")

        if self.periods:
            period_labels = [p.label for p in self.periods[:3]]
            if len(self.periods) > 3:
                period_labels.append("...")
            lines.append(f"Period labels: {', '.join(period_labels)}")

        return "\n".join(lines)


def classify_statement_type(statement_name: str) -> StatementType:
    """Classify statement type from statement name."""
    name_lower = statement_name.lower()

    if 'balance sheet' in name_lower or 'position' in name_lower:
        return StatementType.BALANCE_SHEET
    elif any(term in name_lower for term in ['operations', 'income']) and 'comprehensive' not in name_lower:
        return StatementType.INCOME_STATEMENT
    elif 'cash flow' in name_lower:
        return StatementType.CASH_FLOWS
    elif 'comprehensive income' in name_lower:
        return StatementType.COMPREHENSIVE_INCOME
    elif 'equity' in name_lower or 'stockholder' in name_lower or 'shareholder' in name_lower:
        return StatementType.EQUITY
    else:
        return StatementType.OTHER


# Export all public classes and functions
__all__ = [
    'StatementType',
    'PresentationNode',
    'PresentationStatement',
    'StatementRow',
    'StatementTable',
    'classify_statement_type'
]
