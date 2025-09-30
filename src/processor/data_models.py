"""
Data models for SEC filing processing.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class Period:
    """Represents a reporting period."""

    label: str
    end_date: str
    instant: bool = False


@dataclass
class Cell:
    """Represents a single data cell."""

    value: Optional[str]
    raw_value: Optional[float]
    unit: Optional[str]
    decimals: Optional[int]
    period: str


@dataclass
class Row:
    """Represents a single row in a financial statement."""

    label: str
    concept: Optional[str]
    is_abstract: bool
    depth: int
    cells: Dict[str, Cell]  # period_label -> Cell
    presentation_node: Optional[Any] = None
    dimension_signature: Optional[Tuple[Tuple[str, str], ...]] = None


@dataclass
class Statement:
    """Represents a complete financial statement."""

    name: str
    short_name: str
    periods: List[Period]
    rows: List[Row]


@dataclass
class DimensionHierarchy:
    """Stores dimensional parent-child relationships for semantic matching.

    This data structure captures the XBRL presentation relationships between
    dimension members, enabling semantic matching across filings where a company
    may use different levels of granularity (e.g., broad member vs. specific children).
    """

    # Map from normalized member to set of its direct children
    children: Dict[str, Set[str]] = field(default_factory=dict)
    # Map from normalized member to SET of its direct parents (can have multiple)
    parents: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_relationship(self, parent: str, child: str) -> None:
        """Add a parent-child relationship."""
        parent_norm = self._normalize(parent)
        child_norm = self._normalize(child)
        self.children.setdefault(parent_norm, set()).add(child_norm)
        self.parents[child_norm].add(parent_norm)

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """Check if ancestor is an ancestor of descendant (recursive).

        Handles multiple parent paths by checking all possible ancestor chains.
        """
        ancestor_norm = self._normalize(ancestor)
        descendant_norm = self._normalize(descendant)

        if ancestor_norm == descendant_norm:
            return False  # Not counting self

        # BFS through all parent paths
        queue = [descendant_norm]
        visited = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            parents_set = self.parents.get(current, set())
            for parent in parents_set:
                if parent == ancestor_norm:
                    return True
                if parent not in visited:
                    queue.append(parent)

        return False

    def get_all_descendants(self, member: str) -> Set[str]:
        """Get all descendants of a member (recursive)."""
        member_norm = self._normalize(member)
        descendants = set()
        queue = [member_norm]
        while queue:
            current = queue.pop(0)
            children = self.children.get(current, set())
            for child in children:
                if child not in descendants:
                    descendants.add(child)
                    queue.append(child)
        return descendants

    @staticmethod
    def _normalize(member: str) -> str:
        """Normalize member name (strip namespace, lowercase)."""
        if not member:
            return ""
        return member.split(":", 1)[-1].lower()


@dataclass
class ProcessingResult:
    """Result of processing a filing."""

    statements: List[Statement]
    company_name: str
    filing_date: str
    form_type: str
    success: bool
    error: Optional[str] = None
    warnings: Optional[List[str]] = None
    dimension_hierarchy: Optional[DimensionHierarchy] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
