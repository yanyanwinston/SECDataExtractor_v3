"""
Presentation-based data models for SEC filing processing.

These models represent the presentation structure extracted from iXBRL viewer JSON,
enabling exact visual fidelity with the original filing presentation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
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

    concept: str  # XBRL concept name (e.g., "us-gaap:Assets")
    label: str  # Display label (using preferredLabel)
    order: float  # Presentation order (for sorting siblings)
    depth: int  # Tree depth for indentation (0 = root)
    abstract: bool  # Is this a header/section (no fact values)?
    preferred_label_role: Optional[str] = None  # e.g., "terseLabel", "totalLabel"
    children: List["PresentationNode"] = field(default_factory=list)  # Child nodes

    def add_child(self, child: "PresentationNode") -> None:
        """Add a child node and set its depth."""
        child.depth = self.depth + 1
        self.children.append(child)

    def get_all_nodes_flat(self) -> List[Tuple["PresentationNode", int]]:
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

    def __str__(self) -> str:
        """String representation showing tree structure."""
        indent = "  " * self.depth
        node_type = " (abstract)" if self.abstract else ""
        return f"{indent}{self.label}{node_type}"


@dataclass
class PresentationStatement:
    """A financial statement built from presentation linkbase."""

    role_uri: str  # Full role URI from XBRL
    role_id: str  # Short role ID (e.g., "ns9")
    statement_name: str  # e.g., "Consolidated Balance Sheets"
    statement_type: StatementType  # Classified statement type
    root_nodes: List[PresentationNode] = field(default_factory=list)  # Top-level nodes
    r_id: Optional[str] = None  # MetaLinks role identifier (e.g., "R3")
    group_type: Optional[str] = (
        None  # MetaLinks groupType (statement/document/disclosure)
    )
    sub_group_type: Optional[str] = (
        None  # MetaLinks subGroupType (tables/parenthetical/...)
    )
    role_order: Optional[float] = None  # MetaLinks order for sorting
    long_name: Optional[str] = None  # MetaLinks longName for sheet naming

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

    def get_short_name(self) -> str:
        """Get short name suitable for Excel sheet tabs."""
        name_source = self.long_name or self.statement_name
        name_lower = name_source.lower()

        if "balance" in name_lower or "position" in name_lower:
            return "Balance Sheet"
        elif any(term in name_lower for term in ["income", "operations"]):
            return "Income Statement"
        elif "cash" in name_lower and "flow" in name_lower:
            return "Cash Flows"
        elif "comprehensive" in name_lower and "income" in name_lower:
            return "Comprehensive Income"
        elif "equity" in name_lower or "stockholder" in name_lower:
            return "Equity"
        else:
            # Truncate long names for Excel compatibility
            return name_source[:20] if len(name_source) > 20 else name_source

    def sort_key(self) -> tuple:
        """Return a tuple for ordering statements consistently."""
        order = self.role_order if self.role_order is not None else float("inf")
        return (order, self.r_id or "", self.statement_name)

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

    node: PresentationNode  # Presentation information
    cells: Dict[str, Cell] = field(default_factory=dict)  # period_id -> Cell
    dimensions: Dict[str, str] = field(default_factory=dict)
    dimension_hash: Optional[str] = None

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
        abstract_marker = " [HEADER]" if self.is_abstract else ""
        return f"{indent}{self.label}{abstract_marker} ({cell_count} values)"


@dataclass
class StatementTable:
    """Complete statement ready for rendering with facts matched to presentation."""

    statement: PresentationStatement
    periods: List[Period]  # Time periods (from existing data_models.py)
    rows: List[StatementRow] = field(default_factory=list)  # Ordered by presentation

    def __str__(self) -> str:
        """String representation of the complete statement table."""
        lines = [str(self.statement)]
        lines.append(f"Periods: {len(self.periods)}")

        abstract_rows = sum(1 for row in self.rows if row.is_abstract)
        data_rows = len(self.rows) - abstract_rows
        lines.append(
            f"Rows: {len(self.rows)} ({data_rows} data, {abstract_rows} headers)"
        )

        if self.periods:
            period_labels = [p.label for p in self.periods[:3]]
            if len(self.periods) > 3:
                period_labels.append("...")
            lines.append(f"Period labels: {', '.join(period_labels)}")

        return "\n".join(lines)


def classify_statement_type(statement_name: str) -> StatementType:
    """Classify statement type from statement name."""
    name_lower = statement_name.lower()

    if "balance sheet" in name_lower or "position" in name_lower:
        return StatementType.BALANCE_SHEET
    elif (
        any(term in name_lower for term in ["operations", "income"])
        and "comprehensive" not in name_lower
    ):
        return StatementType.INCOME_STATEMENT
    elif "cash flow" in name_lower:
        return StatementType.CASH_FLOWS
    elif "comprehensive income" in name_lower:
        return StatementType.COMPREHENSIVE_INCOME
    elif (
        "equity" in name_lower
        or "stockholder" in name_lower
        or "shareholder" in name_lower
    ):
        return StatementType.EQUITY
    else:
        return StatementType.OTHER


# Export all public classes and functions
__all__ = [
    "StatementType",
    "PresentationNode",
    "PresentationStatement",
    "StatementRow",
    "StatementTable",
    "classify_statement_type",
]
