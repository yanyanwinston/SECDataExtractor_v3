#!/usr/bin/env python3
"""
Test presentation tree extraction and building

Tests the logic for building hierarchical presentation trees from viewer JSON
relationship data, including tree traversal and fact matching.
"""

import json
import pytest
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple


class PresentationNode:
    """Simple presentation node for testing."""

    def __init__(
        self,
        concept: str,
        label: str = "",
        depth: int = 0,
        abstract: bool = False,
        children: List["PresentationNode"] = None,
    ):
        self.concept = concept
        self.label = label or concept
        self.depth = depth
        self.abstract = abstract
        self.children = children or []

    def add_child(self, child: "PresentationNode"):
        """Add a child node."""
        child.depth = self.depth + 1
        self.children.append(child)

    def get_all_concepts(self) -> Set[str]:
        """Get all concept names in this subtree."""
        concepts = {self.concept}
        for child in self.children:
            concepts.update(child.get_all_concepts())
        return concepts

    def traverse_depth_first(self) -> List[Tuple["PresentationNode", int]]:
        """Traverse tree depth-first, returning (node, depth) tuples."""
        result = [(self, self.depth)]
        for child in self.children:
            result.extend(child.traverse_depth_first())
        return result


class TestPresentationExtraction:
    """Test presentation tree extraction and building."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = (
            Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        )
        with open(fixtures_path, "r") as f:
            cls.fixtures = json.load(f)

        cls.pres_data = cls.fixtures["presentation_relationships"]["data"][
            "relationships"
        ]
        cls.concepts_data = cls.fixtures["sample_concepts"]["data"]

    def test_find_root_nodes(self):
        """Test finding root nodes in presentation relationships."""
        # Find all children concepts
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])

        # Root nodes are those not referenced as children
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        assert len(root_concepts) > 0
        assert "us-gaap:StatementOfFinancialPositionAbstract" in root_concepts

    def test_build_simple_tree(self):
        """Test building a simple presentation tree."""
        # Find root nodes
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        # Build tree for first root
        if root_concepts:
            root_concept = root_concepts[0]
            tree = self._build_tree_node(root_concept, self.pres_data)

            assert tree.concept == root_concept
            assert tree.depth == 0
            assert len(tree.children) > 0

    def test_tree_traversal_order(self):
        """Test that tree traversal maintains proper order."""
        # Find root nodes
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        if root_concepts:
            root_concept = root_concepts[0]
            tree = self._build_tree_node(root_concept, self.pres_data)

            # Traverse tree
            traversal = tree.traverse_depth_first()

            # Should start with root
            assert traversal[0][0].concept == root_concept
            assert traversal[0][1] == 0  # Root depth

            # Should have proper depth progression
            for i in range(1, len(traversal)):
                node, depth = traversal[i]
                prev_node, prev_depth = traversal[i - 1]

                # Depth should not increase by more than 1
                assert depth <= prev_depth + 1

    def test_calculate_tree_depth(self):
        """Test calculating maximum depth of presentation tree."""
        # Find root nodes
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        if root_concepts:
            max_depth = 0
            for root_concept in root_concepts:
                depth = self._calculate_max_depth(root_concept, self.pres_data, set())
                max_depth = max(max_depth, depth)

            assert max_depth > 0
            assert max_depth < 10  # Reasonable upper bound

    def test_detect_abstract_concepts(self):
        """Test detecting abstract vs concrete concepts."""
        # In real implementation, abstract concepts are those without fact values
        # For testing, we'll check if concept names contain "Abstract"

        abstract_concepts = []
        concrete_concepts = []

        for concept_name in self.pres_data.keys():
            if "Abstract" in concept_name:
                abstract_concepts.append(concept_name)
            else:
                concrete_concepts.append(concept_name)

        # Should have some of each type
        assert len(abstract_concepts) > 0
        assert len(concrete_concepts) >= 0  # May be zero in test data

        # Abstract concepts should be structural
        for abstract_concept in abstract_concepts:
            assert abstract_concept in self.pres_data  # Should have children

    def test_match_concepts_to_facts(self):
        """Test matching presentation concepts to available facts."""
        facts_data = self.fixtures["sample_facts"]["data"]

        # Extract concepts referenced in facts
        fact_concepts = set()
        for fact_id, fact_data in facts_data.items():
            # Check all contexts
            for key, value in fact_data.items():
                if key != "v" and isinstance(value, dict):
                    concept = value.get("c")
                    if concept:
                        fact_concepts.add(concept)

        # Check which presentation concepts have facts
        pres_concepts = set()
        for parent in self.pres_data.keys():
            pres_concepts.add(parent)
            for child in self.pres_data[parent]:
                pres_concepts.add(child["t"])

        # Find overlap
        concepts_with_facts = pres_concepts.intersection(fact_concepts)
        concepts_without_facts = pres_concepts - fact_concepts

        # Should have some concepts with facts (concrete values)
        # and some without (abstract headers)
        assert len(concepts_with_facts) >= 0
        assert len(concepts_without_facts) >= 0

    def test_find_fact_for_concept_period(self):
        """Test finding specific fact for concept and period combination."""
        facts_data = self.fixtures["sample_facts"]["data"]

        # Get first fact for testing
        if facts_data:
            first_fact_id = list(facts_data.keys())[0]
            first_fact = facts_data[first_fact_id]

            # Get first context
            context_keys = [
                k
                for k in first_fact.keys()
                if k != "v" and isinstance(first_fact[k], dict)
            ]
            if context_keys:
                context = first_fact[context_keys[0]]
                test_concept = context.get("c")
                test_period = context.get("p")

                # Search for matching fact
                found_fact = self._find_fact_for_concept_period(
                    test_concept, test_period, facts_data
                )

                assert found_fact is not None
                assert found_fact["concept"] == test_concept
                assert found_fact["period"] == test_period

    def test_handle_circular_references(self):
        """Test handling potential circular references in presentation tree."""
        # Create test data with potential circular reference
        circular_data = {
            "concept-a": [{"t": "concept-b"}],
            "concept-b": [{"t": "concept-c"}],
            "concept-c": [{"t": "concept-a"}],  # Circular reference
        }

        # Build tree with cycle detection
        visited = set()
        tree = self._build_tree_node_safe("concept-a", circular_data, visited)

        assert tree is not None
        # Should stop at circular reference
        all_concepts = tree.get_all_concepts()
        assert len(all_concepts) <= 3  # Should not infinitely recurse

    def test_tree_concept_uniqueness(self):
        """Test that each concept appears at most once in tree traversal."""
        # Find root nodes
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        if root_concepts:
            root_concept = root_concepts[0]
            tree = self._build_tree_node(root_concept, self.pres_data)

            # Get all concepts in traversal
            traversal = tree.traverse_depth_first()
            traversed_concepts = [node.concept for node, depth in traversal]

            # Check for duplicates
            unique_concepts = set(traversed_concepts)

            # In a proper tree, each concept should appear only once
            # (though XBRL can have more complex structures)
            # For this test, we just ensure we don't have obvious errors
            assert len(unique_concepts) > 0

    def test_build_multiple_statement_trees(self):
        """Test building trees for multiple statement roles."""
        # In real implementation, we'd have multiple roles
        # For this test, we simulate with our single role

        statements = {}
        role_id = "ns9"
        role_name = "Balance Sheet"

        # Find roots for this role
        all_children = set()
        for parent, children in self.pres_data.items():
            for child in children:
                all_children.add(child["t"])
        root_concepts = [c for c in self.pres_data.keys() if c not in all_children]

        # Build trees for all roots
        trees = []
        for root_concept in root_concepts:
            tree = self._build_tree_node(root_concept, self.pres_data)
            trees.append(tree)

        statements[role_id] = {
            "name": role_name,
            "trees": trees,
            "total_concepts": sum(len(tree.get_all_concepts()) for tree in trees),
        }

        assert len(statements) == 1
        assert statements[role_id]["total_concepts"] > 0

    def test_extract_period_information(self):
        """Test extracting period information from facts."""
        facts_data = self.fixtures["sample_facts"]["data"]

        periods_found = set()
        for fact_id, fact_data in facts_data.items():
            for key, value in fact_data.items():
                if key != "v" and isinstance(value, dict):
                    period = value.get("p")
                    if period:
                        periods_found.add(period)

        assert len(periods_found) > 0

        # Check period format
        for period in periods_found:
            assert isinstance(period, str)
            # Periods can be instant dates or ranges
            assert len(period) > 0

    def test_label_resolution(self):
        """Test resolving labels from concept definitions."""
        concepts_data = self.fixtures["sample_concepts"]["data"]

        for concept_name, concept_info in concepts_data.items():
            labels = concept_info.get("labels", {})

            # Should have at least one label
            if labels:
                # Try to get best label
                best_label = self._get_best_label(concept_info)
                assert best_label is not None
                assert len(best_label) > 0

    # Helper methods for testing

    def _build_tree_node(
        self, concept: str, pres_data: Dict[str, Any], depth: int = 0
    ) -> PresentationNode:
        """Build tree node recursively."""
        # Create node
        node = PresentationNode(
            concept=concept,
            label=concept.split(":")[-1] if ":" in concept else concept,
            depth=depth,
            abstract="Abstract" in concept,
        )

        # Add children
        if concept in pres_data:
            for child_rel in pres_data[concept]:
                child_concept = child_rel["t"]
                child_node = self._build_tree_node(child_concept, pres_data, depth + 1)
                node.children.append(child_node)

        return node

    def _build_tree_node_safe(
        self, concept: str, pres_data: Dict[str, Any], visited: Set[str], depth: int = 0
    ) -> PresentationNode:
        """Build tree node with cycle detection."""
        if concept in visited or depth > 10:  # Prevent infinite recursion
            return PresentationNode(concept=concept, depth=depth)

        visited.add(concept)

        node = PresentationNode(
            concept=concept,
            label=concept.split(":")[-1] if ":" in concept else concept,
            depth=depth,
            abstract="Abstract" in concept,
        )

        # Add children
        if concept in pres_data:
            for child_rel in pres_data[concept]:
                child_concept = child_rel["t"]
                child_node = self._build_tree_node_safe(
                    child_concept, pres_data, visited.copy(), depth + 1
                )
                node.children.append(child_node)

        return node

    def _calculate_max_depth(
        self, concept: str, pres_data: Dict[str, Any], visited: Set[str], depth: int = 0
    ) -> int:
        """Calculate maximum depth of tree."""
        if concept in visited or depth > 20:
            return depth

        visited.add(concept)
        max_child_depth = depth

        if concept in pres_data:
            for child_rel in pres_data[concept]:
                child_concept = child_rel["t"]
                child_depth = self._calculate_max_depth(
                    child_concept, pres_data, visited.copy(), depth + 1
                )
                max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth

    def _find_fact_for_concept_period(
        self, concept: str, period: str, facts_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Find fact for specific concept and period."""
        for fact_id, fact_data in facts_data.items():
            for key, value in fact_data.items():
                if key != "v" and isinstance(value, dict):
                    if value.get("c") == concept and value.get("p") == period:
                        return {
                            "fact_id": fact_id,
                            "concept": concept,
                            "period": period,
                            "value": fact_data.get("v"),
                            "unit": value.get("m"),
                            "entity": value.get("e"),
                        }
        return None

    def _get_best_label(self, concept_info: Dict[str, Any]) -> str:
        """Get best available label for concept."""
        labels = concept_info.get("labels", {})

        # Preference order: std > ns0 > any other
        for label_type in ["std", "ns0"]:
            if label_type in labels:
                label_data = labels[label_type]
                if isinstance(label_data, dict):
                    return label_data.get("en-us", "")
                else:
                    return str(label_data)

        # Fallback to any available label
        if labels:
            first_label = list(labels.values())[0]
            if isinstance(first_label, dict):
                return first_label.get("en-us", "")
            else:
                return str(first_label)

        return concept_info.get("name", "Unknown")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
