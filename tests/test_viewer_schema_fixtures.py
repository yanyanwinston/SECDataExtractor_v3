#!/usr/bin/env python3
"""
Test viewer JSON schema fixtures

Validates that our extracted fixtures contain the expected structure
and can be used for testing presentation parsing logic.
"""

import json
import pytest
from pathlib import Path


class TestViewerSchemaFixtures:
    """Test the viewer JSON schema fixtures."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = (
            Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        )
        with open(fixtures_path, "r") as f:
            cls.fixtures = json.load(f)

    def test_fixtures_structure(self):
        """Test that fixtures have expected top-level structure."""
        expected_keys = {
            "role_definitions",
            "presentation_relationships",
            "sample_facts",
            "sample_concepts",
        }

        assert set(self.fixtures.keys()) == expected_keys

        # Each fixture should have description and data
        for key, fixture in self.fixtures.items():
            assert "description" in fixture
            assert "data" in fixture
            assert isinstance(fixture["description"], str)
            assert isinstance(fixture["data"], dict)

    def test_role_definitions_fixture(self):
        """Test role definitions fixture."""
        role_defs = self.fixtures["role_definitions"]["data"]

        assert len(role_defs) > 0
        assert "ns9" in role_defs  # Balance Sheet should be present

        # Each role should have expected structure
        for role_id, role_info in role_defs.items():
            assert isinstance(role_id, str)
            assert role_id.startswith("ns")
            assert "en" in role_info
            assert "Statement -" in role_info["en"]

    def test_presentation_relationships_fixture(self):
        """Test presentation relationships fixture."""
        pres_rel = self.fixtures["presentation_relationships"]["data"]

        assert "role_id" in pres_rel
        assert "role_name" in pres_rel
        assert "relationships" in pres_rel

        assert pres_rel["role_id"] == "ns9"
        assert "Balance Sheet" in pres_rel["role_name"]

        # Check relationship structure
        relationships = pres_rel["relationships"]
        assert isinstance(relationships, dict)
        assert len(relationships) > 0

        # Each parent should map to array of children
        for parent_concept, children in relationships.items():
            assert isinstance(parent_concept, str)
            assert isinstance(children, list)

            # Each child should have target concept
            for child in children:
                assert isinstance(child, dict)
                assert "t" in child  # target concept

    def test_sample_facts_fixture(self):
        """Test sample facts fixture."""
        facts = self.fixtures["sample_facts"]["data"]

        assert len(facts) > 0

        # Each fact should have expected structure
        for fact_id, fact_data in facts.items():
            assert fact_id.startswith("f-")
            assert "v" in fact_data  # value

            # Should have at least one context (a, b, c, etc.)
            contexts = [
                k
                for k in fact_data.keys()
                if k != "v" and isinstance(fact_data[k], dict)
            ]
            assert len(contexts) > 0

            # Check context structure
            context = fact_data[contexts[0]]
            assert "c" in context  # concept
            assert "e" in context  # entity
            assert "p" in context  # period

    def test_sample_concepts_fixture(self):
        """Test sample concepts fixture."""
        concepts = self.fixtures["sample_concepts"]["data"]

        assert len(concepts) > 0

        # Should include key concept types
        expected_concepts = {
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "us-gaap:AssetsAbstract",
            "us-gaap:Assets",
            "dei:AmendmentFlag",
        }

        found_concepts = set(concepts.keys())
        assert expected_concepts.issubset(found_concepts)

        # Each concept should have labels
        for concept_name, concept_data in concepts.items():
            assert "labels" in concept_data
            assert isinstance(concept_data["labels"], dict)
            assert len(concept_data["labels"]) > 0

            # Should have standard or ns0 label
            labels = concept_data["labels"]
            assert "std" in labels or "ns0" in labels

    def test_can_simulate_presentation_parsing(self):
        """Test that fixtures can be used to simulate presentation parsing."""
        # Get Balance Sheet relationships
        pres_data = self.fixtures["presentation_relationships"]["data"]["relationships"]

        # Find root concepts (not children of others)
        all_children = set()
        for parent, children in pres_data.items():
            for child in children:
                all_children.add(child["t"])

        root_concepts = [c for c in pres_data.keys() if c not in all_children]

        assert len(root_concepts) > 0

        # Should be able to traverse the tree
        def count_total_concepts(concept_name, visited=None):
            if visited is None:
                visited = set()

            if concept_name in visited:
                return 0

            visited.add(concept_name)
            count = 1

            if concept_name in pres_data:
                for child in pres_data[concept_name]:
                    count += count_total_concepts(child["t"], visited.copy())

            return count

        total_concepts = sum(count_total_concepts(root) for root in root_concepts)
        assert total_concepts > 10  # Should have substantial tree

    def test_fact_concept_matching(self):
        """Test that facts can be matched to concepts."""
        facts = self.fixtures["sample_facts"]["data"]
        concepts = self.fixtures["sample_concepts"]["data"]

        # Find facts that match our sample concepts
        matched_facts = []

        for fact_id, fact_data in facts.items():
            contexts = [
                k
                for k in fact_data.keys()
                if k != "v" and isinstance(fact_data[k], dict)
            ]
            for context_key in contexts:
                context = fact_data[context_key]
                concept = context.get("c")

                if concept in concepts:
                    matched_facts.append(
                        {
                            "fact_id": fact_id,
                            "concept": concept,
                            "value": fact_data.get("v"),
                            "period": context.get("p"),
                        }
                    )

        # Should find at least some matches
        assert len(matched_facts) > 0

        # Each match should have required fields
        for match in matched_facts:
            assert all(key in match for key in ["fact_id", "concept", "value"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
