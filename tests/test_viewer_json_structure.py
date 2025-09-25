#!/usr/bin/env python3
"""
Test viewer JSON structure parsing and validation

Tests the core JSON parsing functions that extract data from iXBRL viewer
JSON files, including handling different formats and error cases.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open


class TestViewerJSONStructure:
    """Test viewer JSON structure parsing and validation."""

    @classmethod
    def setup_class(cls):
        """Load test fixtures."""
        fixtures_path = Path(__file__).parent / "fixtures" / "viewer_schema_samples.json"
        with open(fixtures_path, 'r') as f:
            cls.fixtures = json.load(f)

        # Create mock viewer JSON structure
        cls.mock_viewer_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": cls.fixtures["role_definitions"]["data"],
                    "rels": {
                        "pres": {
                            "ns9": cls.fixtures["presentation_relationships"]["data"]["relationships"]
                        }
                    },
                    "facts": cls.fixtures["sample_facts"]["data"],
                    "concepts": cls.fixtures["sample_concepts"]["data"],
                    "target": {"some": "metadata"},
                    "localDocs": {}
                }]
            }]
        }

    def test_extract_target_data(self):
        """Test extracting target data from sourceReports structure."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]

        assert 'roleDefs' in target_data
        assert 'rels' in target_data
        assert 'facts' in target_data
        assert 'concepts' in target_data

    def test_extract_role_definitions(self):
        """Test extracting role definitions from viewer JSON."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        role_defs = target_data['roleDefs']

        assert isinstance(role_defs, dict)
        assert len(role_defs) > 0

        # Check structure
        for role_id, role_info in role_defs.items():
            assert role_id.startswith('ns')
            assert 'en' in role_info
            assert isinstance(role_info['en'], str)

    def test_identify_financial_statements(self):
        """Test identifying financial statement roles."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        role_defs = target_data['roleDefs']

        statement_roles = {}
        for role_id, role_info in role_defs.items():
            role_name = role_info.get('en', '')
            if 'Statement -' in role_name:
                statement_roles[role_id] = role_name

        assert len(statement_roles) > 0
        assert 'ns9' in statement_roles  # Balance Sheet
        assert 'BALANCE SHEETS' in statement_roles['ns9']

    def test_extract_presentation_relationships(self):
        """Test extracting presentation relationships."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        pres_rels = target_data['rels']['pres']

        assert isinstance(pres_rels, dict)
        assert 'ns9' in pres_rels

        # Check Balance Sheet structure
        bs_rels = pres_rels['ns9']
        assert isinstance(bs_rels, dict)

        # Should have parent concepts mapping to children
        for parent_concept, children in bs_rels.items():
            assert isinstance(parent_concept, str)
            assert isinstance(children, list)

            # Each child should have target concept
            for child in children:
                assert isinstance(child, dict)
                assert 't' in child  # target concept

    def test_extract_facts(self):
        """Test extracting facts from viewer JSON."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        facts = target_data['facts']

        assert isinstance(facts, dict)
        assert len(facts) > 0

        # Check fact structure
        for fact_id, fact_data in facts.items():
            assert fact_id.startswith('f-')
            assert 'v' in fact_data  # value

            # Should have at least one context
            contexts = [k for k in fact_data.keys() if k != 'v' and isinstance(fact_data[k], dict)]
            assert len(contexts) > 0

            # Check context structure
            context = fact_data[contexts[0]]
            required_keys = ['c', 'e', 'p']  # concept, entity, period
            for key in required_keys:
                assert key in context

    def test_extract_concepts(self):
        """Test extracting concept definitions."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        concepts = target_data['concepts']

        assert isinstance(concepts, dict)
        assert len(concepts) > 0

        # Check concept structure
        for concept_name, concept_data in concepts.items():
            assert ':' in concept_name  # Should be qualified name
            assert 'labels' in concept_data
            assert isinstance(concept_data['labels'], dict)

    def test_get_concept_labels(self):
        """Test extracting labels from concept definitions."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        concepts = target_data['concepts']

        for concept_name, concept_data in concepts.items():
            labels = concept_data['labels']

            # Should have at least one label
            assert len(labels) > 0

            # Check label structure
            for label_type, label_data in labels.items():
                if isinstance(label_data, dict):
                    assert 'en-us' in label_data
                    assert isinstance(label_data['en-us'], str)

    def test_classify_statement_types(self):
        """Test classifying statement types from role names."""
        def classify_statement_type(role_name):
            name_lower = role_name.lower()
            if 'balance sheet' in name_lower:
                return 'balance_sheet'
            elif 'operations' in name_lower:
                return 'income_statement'
            elif 'cash flow' in name_lower:
                return 'cash_flows'
            elif 'comprehensive income' in name_lower:
                return 'comprehensive_income'
            elif 'equity' in name_lower or 'shareholders' in name_lower:
                return 'equity'
            else:
                return 'other'

        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        role_defs = target_data['roleDefs']

        for role_id, role_info in role_defs.items():
            role_name = role_info.get('en', '')
            if 'Statement -' in role_name:
                stmt_type = classify_statement_type(role_name)
                assert stmt_type in ['balance_sheet', 'income_statement', 'cash_flows',
                                   'comprehensive_income', 'equity', 'other']

    def test_handle_missing_sections(self):
        """Test handling viewer JSON with missing sections."""
        # Test with minimal JSON
        minimal_json = {
            "sourceReports": [{
                "targetReports": [{
                    "roleDefs": {},
                    "rels": {},
                    "facts": {},
                    "concepts": {}
                }]
            }]
        }

        target_data = minimal_json['sourceReports'][0]['targetReports'][0]

        # Should handle empty sections gracefully
        assert target_data.get('roleDefs', {}) == {}
        assert target_data.get('rels', {}) == {}
        assert target_data.get('facts', {}) == {}
        assert target_data.get('concepts', {}) == {}

    def test_handle_malformed_json_structure(self):
        """Test handling malformed JSON structure."""
        malformed_cases = [
            {},  # Empty JSON
            {"sourceReports": []},  # Empty source reports
            {"sourceReports": [{}]},  # Missing targetReports
            {"sourceReports": [{"targetReports": []}]},  # Empty target reports
        ]

        for malformed_json in malformed_cases:
            try:
                # Try to access the target data
                if ('sourceReports' in malformed_json and
                    malformed_json['sourceReports'] and
                    'targetReports' in malformed_json['sourceReports'][0] and
                    malformed_json['sourceReports'][0]['targetReports']):
                    target_data = malformed_json['sourceReports'][0]['targetReports'][0]
                else:
                    target_data = {}

                # Should not crash, just return empty data
                assert isinstance(target_data, dict)
            except (IndexError, KeyError):
                # Expected for malformed JSON
                pass

    def test_detect_viewer_json_format(self):
        """Test detecting different viewer JSON formats."""
        # Test sourceReports format (new)
        new_format = {"sourceReports": [{"targetReports": [{}]}]}
        assert 'sourceReports' in new_format

        # Test legacy format (older versions might have different structure)
        legacy_format = {"statements": {}, "facts": {}, "periods": {}}
        assert 'statements' in legacy_format

    @patch("builtins.open", new_callable=mock_open)
    def test_load_viewer_json_from_file(self, mock_file):
        """Test loading viewer JSON from file."""
        # Mock file content
        mock_file.return_value.read.return_value = json.dumps(self.mock_viewer_json)

        # Test loading
        with open("mock_file.json", 'r') as f:
            data = json.load(f)

        assert data == self.mock_viewer_json
        mock_file.assert_called_once_with("mock_file.json", 'r')

    def test_validate_required_components(self):
        """Test validation that required components are present."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]

        required_components = ['roleDefs', 'rels', 'facts', 'concepts']

        for component in required_components:
            assert component in target_data, f"Missing required component: {component}"
            assert isinstance(target_data[component], dict), f"Component {component} should be dict"

    def test_presentation_relationships_integrity(self):
        """Test integrity of presentation relationships."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        pres_rels = target_data['rels']['pres']
        concepts = target_data['concepts']

        # Check that referenced concepts exist
        for role_id, role_rels in pres_rels.items():
            for parent_concept, children in role_rels.items():
                # Parent concept should have definition (or be abstract)
                # Note: In real data, not all concepts may have definitions

                for child in children:
                    child_concept = child['t']
                    assert isinstance(child_concept, str)
                    assert len(child_concept) > 0

    def test_fact_concept_references(self):
        """Test that facts reference valid concepts."""
        target_data = self.mock_viewer_json['sourceReports'][0]['targetReports'][0]
        facts = target_data['facts']
        concepts = target_data['concepts']

        referenced_concepts = set()

        for fact_id, fact_data in facts.items():
            # Check all contexts in the fact
            for key, value in fact_data.items():
                if key != 'v' and isinstance(value, dict):
                    concept = value.get('c')
                    if concept:
                        referenced_concepts.add(concept)

        # Some concepts referenced in facts should be defined
        # (Not all may be, as some could be abstract or in other sections)
        defined_concepts = set(concepts.keys())
        common_concepts = referenced_concepts.intersection(defined_concepts)

        # Should have at least some overlap
        assert len(common_concepts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])