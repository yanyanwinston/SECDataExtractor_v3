#!/usr/bin/env python3
"""
Viewer JSON Analysis Script

Analyzes the structure of iXBRL viewer JSON data to understand:
- Financial statement roles and their content
- Presentation tree hierarchy
- Fact distribution and statistics
- Concept labels and types

Usage:
    python scripts/analyze_viewer_json.py <path_to_viewer_json>
    python scripts/analyze_viewer_json.py output/viewer-data.json
"""

import json
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Any, Tuple


class ViewerJSONAnalyzer:
    """Analyzes iXBRL viewer JSON structure."""

    def __init__(self, json_path: str):
        """Load and parse viewer JSON file."""
        self.json_path = Path(json_path)

        with open(self.json_path, "r") as f:
            self.data = json.load(f)

        # Extract target data (main content)
        self.target = self.data["sourceReports"][0]["targetReports"][0]

        self.role_defs = self.target.get("roleDefs", {})
        self.rels_pres = self.target.get("rels", {}).get("pres", {})
        self.facts = self.target.get("facts", {})
        self.concepts = self.target.get("concepts", {})

    def analyze_statements(self) -> Dict[str, Any]:
        """Analyze financial statement structure."""
        statements = {}

        for role_id, role_info in self.role_defs.items():
            role_name = role_info.get("en", "")

            if "Statement -" in role_name:
                statement_type = self._classify_statement(role_name)
                presentation_data = self.rels_pres.get(role_id, {})

                statements[role_id] = {
                    "name": role_name,
                    "type": statement_type,
                    "root_concepts": list(presentation_data.keys()),
                    "total_concepts": self._count_concepts_in_tree(presentation_data),
                    "has_presentation": bool(presentation_data),
                }

        return statements

    def analyze_presentation_tree(self, role_id: str) -> Dict[str, Any]:
        """Analyze presentation tree structure for a specific role."""
        if role_id not in self.rels_pres:
            return {"error": f"No presentation data for role {role_id}"}

        pres_data = self.rels_pres[role_id]

        # Find root nodes (not referenced as children)
        all_children = set()
        for parent, children in pres_data.items():
            for child in children:
                all_children.add(child["t"])

        root_concepts = [c for c in pres_data.keys() if c not in all_children]

        # Build tree structure
        tree_info = {
            "root_concepts": root_concepts,
            "total_parent_concepts": len(pres_data),
            "total_child_relationships": sum(
                len(children) for children in pres_data.values()
            ),
            "max_depth": self._calculate_max_depth(pres_data, root_concepts),
            "tree_structure": {},
        }

        # Generate detailed tree for first root (sample)
        if root_concepts:
            tree_info["sample_tree"] = self._build_tree_structure(
                root_concepts[0], pres_data, max_depth=3
            )

        return tree_info

    def analyze_facts(self) -> Dict[str, Any]:
        """Analyze fact distribution and structure."""
        fact_stats = {
            "total_facts": len(self.facts),
            "concepts_with_facts": set(),
            "periods_found": set(),
            "entities_found": set(),
            "units_found": Counter(),
            "fact_types": Counter(),
        }

        for fact_id, fact_data in self.facts.items():
            # Handle different context formats (a, b, c, etc.)
            contexts = [
                k
                for k in fact_data.keys()
                if k != "v" and isinstance(fact_data[k], dict)
            ]

            for context_key in contexts:
                context = fact_data[context_key]
                if isinstance(context, dict):
                    concept = context.get("c")
                    period = context.get("p")
                    entity = context.get("e")
                    unit = context.get("m")

                    if concept:
                        fact_stats["concepts_with_facts"].add(concept)
                    if period:
                        fact_stats["periods_found"].add(period)
                    if entity:
                        fact_stats["entities_found"].add(entity)
                    if unit:
                        fact_stats["units_found"][str(unit)] += 1

                    # Classify fact type
                    if concept:
                        if "Abstract" in concept:
                            fact_stats["fact_types"]["abstract"] += 1
                        elif unit == "usd":
                            fact_stats["fact_types"]["monetary"] += 1
                        elif unit == "shares":
                            fact_stats["fact_types"]["shares"] += 1
                        elif unit is False or unit == "pure":
                            fact_stats["fact_types"]["dimensionless"] += 1
                        else:
                            fact_stats["fact_types"]["other"] += 1

        # Convert sets to lists for JSON serialization
        fact_stats["concepts_with_facts"] = len(fact_stats["concepts_with_facts"])
        fact_stats["periods_found"] = sorted(fact_stats["periods_found"])
        fact_stats["entities_found"] = list(fact_stats["entities_found"])
        fact_stats["units_found"] = dict(fact_stats["units_found"].most_common(10))

        return fact_stats

    def analyze_concepts(self) -> Dict[str, Any]:
        """Analyze concept definitions and labels."""
        concept_stats = {
            "total_concepts": len(self.concepts),
            "label_types": Counter(),
            "data_types": Counter(),
            "balance_types": Counter(),
            "sample_concepts": {},
        }

        for concept_name, concept_data in self.concepts.items():
            # Analyze labels
            labels = concept_data.get("labels", {})
            for label_type in labels.keys():
                concept_stats["label_types"][label_type] += 1

            # Analyze data types
            data_type = concept_data.get("dt", "unknown")
            concept_stats["data_types"][data_type] += 1

            # Analyze balance types
            balance = concept_data.get("b", "none")
            concept_stats["balance_types"][balance] += 1

        # Get sample concepts
        sample_concepts = dict(list(self.concepts.items())[:5])
        for concept_name, concept_data in sample_concepts.items():
            concept_stats["sample_concepts"][concept_name] = {
                "labels": concept_data.get("labels", {}),
                "data_type": concept_data.get("dt", "unknown"),
                "balance": concept_data.get("b", "none"),
            }

        return concept_stats

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive analysis report."""
        return {
            "file_info": {
                "path": str(self.json_path),
                "size_mb": round(self.json_path.stat().st_size / 1024 / 1024, 2),
            },
            "statements": self.analyze_statements(),
            "facts": self.analyze_facts(),
            "concepts": self.analyze_concepts(),
            "sample_presentation_tree": None,
        }

    def _classify_statement(self, role_name: str) -> str:
        """Classify statement type from role name."""
        name_lower = role_name.lower()

        if "balance sheet" in name_lower:
            return "balance_sheet"
        elif "operations" in name_lower:
            return "income_statement"
        elif "cash flow" in name_lower:
            return "cash_flows"
        elif "comprehensive income" in name_lower:
            return "comprehensive_income"
        elif "equity" in name_lower or "shareholders" in name_lower:
            return "equity"
        else:
            return "other"

    def _count_concepts_in_tree(self, pres_data: Dict[str, Any]) -> int:
        """Count total concepts in presentation tree."""
        concepts = set(pres_data.keys())
        for children in pres_data.values():
            for child in children:
                concepts.add(child["t"])
        return len(concepts)

    def _calculate_max_depth(
        self, pres_data: Dict[str, Any], root_concepts: List[str]
    ) -> int:
        """Calculate maximum depth of presentation tree."""

        def get_depth(concept: str, visited: set, depth: int = 0) -> int:
            if concept in visited:
                return depth

            visited.add(concept)
            max_child_depth = depth

            if concept in pres_data:
                for child in pres_data[concept]:
                    child_concept = child["t"]
                    child_depth = get_depth(child_concept, visited.copy(), depth + 1)
                    max_child_depth = max(max_child_depth, child_depth)

            return max_child_depth

        return (
            max(get_depth(root, set()) for root in root_concepts)
            if root_concepts
            else 0
        )

    def _build_tree_structure(
        self,
        concept: str,
        pres_data: Dict[str, Any],
        depth: int = 0,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """Build tree structure for visualization."""
        if depth >= max_depth or concept not in pres_data:
            return {"concept": concept, "children": []}

        children = []
        for child_rel in pres_data.get(concept, [])[:5]:  # Limit to first 5 children
            child_concept = child_rel["t"]
            child_tree = self._build_tree_structure(
                child_concept, pres_data, depth + 1, max_depth
            )
            children.append(child_tree)

        return {"concept": concept, "children": children}


def print_report(report: Dict[str, Any]):
    """Print formatted analysis report."""
    print("=" * 80)
    print("iXBRL VIEWER JSON ANALYSIS REPORT")
    print("=" * 80)

    # File info
    file_info = report["file_info"]
    print(f"\nFile: {file_info['path']}")
    print(f"Size: {file_info['size_mb']} MB")

    # Statements
    print(f"\nFINANCIAL STATEMENTS FOUND:")
    print("-" * 40)
    statements = report["statements"]
    for role_id, stmt_info in statements.items():
        print(f"  {role_id}: {stmt_info['name']}")
        print(f"    Type: {stmt_info['type']}")
        print(f"    Root concepts: {len(stmt_info['root_concepts'])}")
        print(f"    Total concepts: {stmt_info['total_concepts']}")
        print()

    # Facts
    print("FACTS ANALYSIS:")
    print("-" * 40)
    facts = report["facts"]
    print(f"  Total facts: {facts['total_facts']:,}")
    print(f"  Concepts with facts: {facts['concepts_with_facts']:,}")
    print(f"  Periods found: {len(facts['periods_found'])}")
    print(f"  Entities: {len(facts['entities_found'])}")
    print(f"  Top units: {list(facts['units_found'].keys())[:5]}")
    print(f"  Fact types: {dict(facts['fact_types'])}")

    # Concepts
    print(f"\nCONCEPTS ANALYSIS:")
    print("-" * 40)
    concepts = report["concepts"]
    print(f"  Total concepts: {concepts['total_concepts']:,}")
    print(f"  Label types: {list(concepts['label_types'].keys())}")
    print(f"  Data types: {list(concepts['data_types'].keys())[:5]}")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python analyze_viewer_json.py <path_to_viewer_json>")
        sys.exit(1)

    json_path = sys.argv[1]

    if not Path(json_path).exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    try:
        analyzer = ViewerJSONAnalyzer(json_path)
        report = analyzer.generate_report()
        print_report(report)

        # Optionally save detailed report
        output_path = Path(json_path).parent / "analysis_report.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nDetailed report saved to: {output_path}")

    except Exception as e:
        print(f"Error analyzing file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
