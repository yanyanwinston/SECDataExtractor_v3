"""
Presentation parser for extracting XBRL presentation structure from viewer JSON.

This parser extracts presentation linkbase relationships from Arelle's iXBRL viewer
JSON output and builds hierarchical presentation trees that maintain the exact
visual fidelity of the original filing.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple

from .presentation_models import (
    PresentationNode, PresentationStatement, classify_statement_type
)

logger = logging.getLogger(__name__)


class PresentationParser:
    """Parse presentation relationships from viewer JSON data."""

    def parse_presentation_statements(self, viewer_data: dict) -> List[PresentationStatement]:
        """Extract all financial statements from presentation linkbase.

        Args:
            viewer_data: Complete viewer JSON structure from Arelle

        Returns:
            List of PresentationStatement objects representing financial statements
        """
        statements = []

        try:
            # Navigate to presentation relationships in viewer JSON structure
            target_report = viewer_data['sourceReports'][0]['targetReports'][0]
            pres_rels = target_report.get('rels', {}).get('pres', {})
            role_defs = target_report.get('roleDefs', {})
            concepts = target_report.get('concepts', {})

            if not pres_rels:
                logger.warning("No presentation relationships found in viewer data")
                return statements

            logger.info(f"Found {len(pres_rels)} presentation roles")

            # Parse each role that represents a financial statement
            for role_id, role_data in pres_rels.items():
                role_def = role_defs.get(role_id, {})

                if not self._is_financial_statement_role(role_def):
                    continue

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
            raise

        logger.info(f"Successfully parsed {len(statements)} statements")
        return statements

    def _is_financial_statement_role(self, role_def: dict) -> bool:
        """Check if this role represents a financial statement.

        Args:
            role_def: Role definition from roleDefs section

        Returns:
            True if this role represents a financial statement
        """
        label = (
            role_def.get('label')
            or role_def.get('en')
            or role_def.get('en-us')
            or ''
        ).lower()

        # Look for financial statement indicators in role label
        financial_keywords = [
            'balance sheet', 'balance sheets',
            'income statement', 'income statements',
            'operations', 'comprehensive income',
            'cash flow', 'cash flows',
            'equity', 'stockholder', 'shareholder'
        ]

        return any(keyword in label for keyword in financial_keywords)

    def _parse_single_statement(
        self,
        role_id: str,
        role_data: dict,
        role_def: dict,
        concepts: dict
    ) -> PresentationStatement:
        """Parse a single statement's presentation tree.

        Args:
            role_id: Short role ID (e.g., "ns9")
            role_data: Presentation relationships for this role
            role_def: Role definition with URI and label
            concepts: Concept definitions with labels

        Returns:
            Complete PresentationStatement with hierarchical structure
        """
        logger.debug(f"Parsing statement for role {role_id}")

        root_concepts, relationships = self._normalize_role_data(role_data)

        if not root_concepts:
            raise ValueError(f"No root concepts found for role {role_id}")

        logger.debug(f"Found {len(root_concepts)} root concepts: {root_concepts}")

        # Build presentation trees for each root concept
        root_nodes = []
        for root_concept in root_concepts:
            try:
                node = self._build_presentation_tree(
                    root_concept, relationships, concepts, depth=0
                )
                root_nodes.append(node)
            except Exception as e:
                logger.warning(f"Failed to build tree for {root_concept}: {e}")
                continue

        if not root_nodes:
            raise ValueError(f"No valid presentation trees built for role {role_id}")

        # Extract statement name and classify type
        statement_name = self._extract_statement_name(
            role_def.get('label') or role_def.get('en') or role_def.get('en-us') or ''
        )
        statement_type = classify_statement_type(statement_name)

        return PresentationStatement(
            role_uri=role_def.get('uri', ''),
            role_id=role_id,
            statement_name=statement_name,
            statement_type=statement_type,
            root_nodes=root_nodes
        )

    def _normalize_role_data(self, role_data: dict) -> Tuple[List[str], Dict[str, dict]]:
        """Normalize role data into root concept list and relationship map.

        Supports both the viewer JSON structure (rootElts + elrs) and the
        simplified test fixture structure (parent -> [children]).
        """

        # Viewer JSON structure
        if 'rootElts' in role_data:
            root_concepts = list(role_data.get('rootElts', []))
            relationships: Dict[str, dict] = {}

            elrs = role_data.get('elrs', {})
            for elr_uri, elr_data in elrs.items():
                for concept, data in elr_data.items():
                    rel_entry = relationships.setdefault(concept, {
                        'order': data.get('order', 0),
                        'preferredLabel': data.get('preferredLabel'),
                        'children': {}
                    })

                    for child_concept, child_data in data.get('children', {}).items():
                        rel_entry['children'][child_concept] = child_data or {}

            return root_concepts, relationships

        # Some sources wrap relationships under "relationships"
        if 'relationships' in role_data:
            role_data = role_data['relationships']

        # Simplified structure: parent -> list of {"t": child, ...}
        all_children = {
            child.get('t')
            for children in role_data.values()
            for child in children
            if isinstance(child, dict)
        }
        root_concepts = [concept for concept in role_data.keys() if concept not in all_children]

        relationships = {}
        for parent, children in role_data.items():
            entry = relationships.setdefault(parent, {
                'order': 0,
                'preferredLabel': None,
                'children': {}
            })

            for idx, child in enumerate(children):
                if not isinstance(child, dict):
                    continue

                child_concept = child.get('t')
                if not child_concept:
                    continue

                child_entry = {
                    'order': child.get('order', idx),
                    'preferredLabel': child.get('preferredLabel'),
                    'children': child.get('children') or {}
                }
                entry['children'][child_concept] = child_entry

        return root_concepts, relationships

    def _find_root_concepts(self, role_data: dict) -> List[str]:
        """Compatibility helper to expose root concepts for a role."""

        root_concepts, _ = self._normalize_role_data(role_data)
        return root_concepts

    def _build_presentation_tree(self, concept: str, relationships: Dict[str, dict],
                                concepts: dict, depth: int) -> PresentationNode:
        """Recursively build presentation tree from relationships.

        Args:
            concept: XBRL concept name to build tree for
            role_data: Presentation relationships data
            concepts: Concept definitions with labels
            depth: Current tree depth (0 for root)

        Returns:
            PresentationNode with children populated
        """
        logger.debug(f"Building tree for {concept} at depth {depth}")

        # Allow callers to pass the raw viewer relationships map (list based)
        if (
            concept not in relationships
            or isinstance(relationships.get(concept), list)
        ):
            _, relationships = self._normalize_role_data({'relationships': relationships})

        rel_data = relationships.get(concept, {})
        children: List[PresentationNode] = []

        for child_concept, child_data in rel_data.get('children', {}).items():
            try:
                child_node = self._build_presentation_tree(
                    child_concept, relationships, concepts, depth + 1
                )

                # Update child properties from relationship data
                child_node.order = child_data.get('order', child_node.order)
                child_node.preferred_label_role = child_data.get('preferredLabel')

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

        # Sort children based on presentation order
        children.sort(key=lambda node: node.order)

        node = PresentationNode(
            concept=concept,
            label=self._get_concept_label(concept, concepts),
            order=rel_data.get('order', 0),
            depth=depth,
            abstract=self._is_abstract_concept(concept, concepts),
            preferred_label_role=rel_data.get('preferredLabel'),
            children=children
        )

        logger.debug(f"Built node for {concept} with {len(children)} children")
        return node

    def _get_concept_label(self, concept: str, concepts: dict) -> str:
        """Get the best available label for a concept.

        Args:
            concept: XBRL concept name
            concepts: Concept definitions from viewer JSON

        Returns:
            Human-readable label for the concept
        """
        concept_data = concepts.get(concept, {})

        if not concept_data:
            return self._humanize_concept_name(concept)

        # Try canonical label fields (viewer JSON often stores under "l" or "label")
        for key in ('l', 'label', 'en', 'en-us'):
            label_value = concept_data.get(key)
            if isinstance(label_value, str) and label_value.strip():
                return label_value

        # Try labels dictionary (may be nested by role and language)
        labels = concept_data.get('labels', {})
        preferred_order = ['std', 'terseLabel', 'totalLabel', 'verboseLabel', 'label']
        for label_type in preferred_order:
            label_data = labels.get(label_type)
            if isinstance(label_data, dict):
                for lang_key in ('en-us', 'en'):
                    if label_data.get(lang_key):
                        return label_data[lang_key]
            elif label_data:
                return str(label_data)

        # Fallback to humanized concept name
        return self._humanize_concept_name(concept)

    def _get_preferred_label(self, concept: str, preferred_role: str,
                            concepts: dict) -> Optional[str]:
        """Get preferred label for concept in specific role.

        Args:
            concept: XBRL concept name
            preferred_role: Preferred label role (e.g., "terseLabel", "totalLabel")
            concepts: Concept definitions from viewer JSON

        Returns:
            Preferred label if available, None otherwise
        """
        concept_data = concepts.get(concept, {})
        labels = concept_data.get('labels', {})

        label_data = labels.get(preferred_role)
        if isinstance(label_data, dict):
            return label_data.get('en-us', label_data.get('en'))
        else:
            return str(label_data) if label_data else None

    def _is_abstract_concept(self, concept: str, concepts: dict) -> bool:
        """Determine if concept is abstract (header/section).

        Args:
            concept: XBRL concept name
            concepts: Concept definitions from viewer JSON

        Returns:
            True if concept is abstract (no fact values, just a header)
        """
        concept_data = concepts.get(concept, {})

        # Check if explicitly marked as abstract
        if concept_data.get('abstract', False):
            return True

        # Heuristic: concepts ending in "Abstract" are usually abstract
        return concept.endswith('Abstract')

    def _humanize_concept_name(self, concept: str) -> str:
        """Convert concept name to human-readable label.

        Args:
            concept: XBRL concept name (e.g., "us-gaap:CashAndCashEquivalents")

        Returns:
            Human-readable label (e.g., "Cash And Cash Equivalents")
        """
        # Remove namespace prefix
        if ':' in concept:
            concept = concept.split(':', 1)[1]

        # Convert camelCase to Title Case with spaces
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept).split()
        return ' '.join(word.capitalize() for word in words)

    def _extract_statement_name(self, role_label: str) -> str:
        """Clean up role label to get statement name.

        Args:
            role_label: Raw role label from roleDefs

        Returns:
            Cleaned statement name
        """
        if not role_label:
            return "Financial Statement"

        # Remove common prefixes like "00000002 - Statement - "
        cleaned = re.sub(r'^\d+\s*-\s*(Statement\s*-\s*)?', '', role_label)

        return cleaned.strip() or "Financial Statement"
