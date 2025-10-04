#!/usr/bin/env python3
"""Export bronze and silver tables from SEC iXBRL filings."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Mapping, Any

from src.processor import (
    InputHandler,
    ArelleProcessor,
    ViewerDataExtractor,
    DataParser,
    BronzeFilingMetadata,
    BronzeWriter,
    build_fact_long_dataframe,
    SilverWriter,
    build_statement_lines_dataframe,
    build_statement_facts_dataframe,
)

logger = logging.getLogger(__name__)


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export bronze and silver tables from an iXBRL filing",
    )
    parser.add_argument("--filing", required=True, help="Filing source (URL, local file, or ZIP)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data"),
        help="Output root directory (default: data)",
    )
    parser.add_argument(
        "--include-disclosures",
        action="store_true",
        help="Include disclosure/detail roles in the exported tables",
    )
    parser.add_argument(
        "--collapse-dimensions",
        action="store_true",
        help="Collapse dimensional members instead of expanding them",
    )
    parser.add_argument(
        "--label-style",
        choices=["terse", "standard"],
        default="terse",
        help="Preferred concept label style for presentation parsing",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        help="Directory for temporary artefacts",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve temporary artefacts generated during export",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout for Arelle processing (seconds)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    if not verbose:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)


def _collect_meta_links(viewer_path: Path, filing_path: Path) -> List[Path]:
    candidates: List[Path] = []

    # Viewer output locations
    if viewer_path.exists():
        candidates.append(viewer_path.with_name("MetaLinks.json"))
        if viewer_path.parent != viewer_path.parent.parent:
            candidates.append(viewer_path.parent.parent / "MetaLinks.json")

    # Original filing tree
    for ancestor in [filing_path] + list(filing_path.parents):
        candidate = ancestor.with_name("MetaLinks.json") if ancestor.is_file() else ancestor / "MetaLinks.json"
        if candidate not in candidates:
            candidates.append(candidate)

    unique_candidates: List[Path] = []
    seen = set()
    for path in candidates:
        if path in seen:
            continue
        unique_candidates.append(path)
        seen.add(path)

    return unique_candidates


def _load_filing_metadata_overrides(filing_path: Path) -> Mapping[str, Any]:
    """Load filing metadata from metadata.json adjacent to the source when available."""

    for candidate in [filing_path] + list(filing_path.parents):
        metadata_file = candidate / "metadata.json"
        if metadata_file.exists():
            try:
                with metadata_file.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                info = raw.get("filing_info", raw)
                overrides = {
                    "entity_cik": info.get("cik"),
                    "accession_number": info.get("accession_number"),
                    "company_name": info.get("company_name"),
                    "form_type": info.get("form_type"),
                    "filing_date": info.get("filing_date") or info.get("report_date"),
                }
                return {k: v for k, v in overrides.items() if v}
            except Exception as exc:
                logger.debug("Failed to load metadata overrides from %s: %s", metadata_file, exc)
                return {}

    return {}


def export_tables(args: argparse.Namespace) -> None:
    setup_logging(args.verbose)

    input_handler = InputHandler(temp_dir=args.temp_dir)
    source = input_handler.create_source(args.filing)

    if not source.validate():
        raise ValueError(f"Filing source is invalid: {args.filing}")

    filing_path = Path(source.get_path())

    if not input_handler.validate_filing(str(filing_path)):
        raise ValueError(f"Provided filing does not appear to be a valid iXBRL document: {filing_path}")

    arelle = ArelleProcessor(temp_dir=args.temp_dir, timeout=args.timeout)
    viewer_html_path = Path(arelle.generate_viewer_html(filing_path))

    extractor = ViewerDataExtractor()
    meta_link_candidates = _collect_meta_links(viewer_html_path, filing_path)
    viewer_data = extractor.extract_viewer_data(
        str(viewer_html_path), meta_links_candidates=meta_link_candidates
    )

    parser = DataParser(
        include_disclosures=args.include_disclosures,
        label_style=args.label_style,
        expand_dimensions=not args.collapse_dimensions,
    )

    processing_result = parser.parse_viewer_data(viewer_data)
    if not processing_result.success:
        raise RuntimeError(processing_result.error or "Failed to parse viewer data")

    statement_tables = parser.get_latest_statement_tables()
    if not statement_tables:
        raise RuntimeError("No statement tables were produced for export")

    metadata_overrides = _load_filing_metadata_overrides(filing_path)
    metadata = BronzeFilingMetadata.from_viewer_data(
        viewer_data,
        accession_number=metadata_overrides.get("accession_number"),
        overrides=metadata_overrides,
    )
    if not metadata.accession_number:
        logger.warning("Accession number not detected; outputs will use filing_id only")

    bronze_dir = args.out / "bronze"
    silver_dir = args.out / "silver"

    bronze_writer = BronzeWriter(base_dir=bronze_dir)
    fact_long_df = build_fact_long_dataframe(statement_tables, metadata, viewer_data)
    bronze_writer.write(viewer_data, metadata, fact_long_df=fact_long_df)

    silver_writer = SilverWriter(base_dir=silver_dir)
    statement_lines_df = build_statement_lines_dataframe(
        statement_tables, metadata, viewer_data
    )
    statement_facts_df = build_statement_facts_dataframe(
        statement_tables, metadata, viewer_data
    )
    silver_writer.write(metadata, statement_lines_df, statement_facts_df)

    logger.info(
        "Export completed",
        extra={
            "statements": len(statement_tables),
            "fact_long_rows": len(fact_long_df),
            "statement_lines": len(statement_lines_df),
            "statement_facts": len(statement_facts_df),
        },
    )

    if not args.keep_temp:
        source.cleanup()
        try:
            viewer_html_path.unlink()
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = create_argument_parser()
    args = parser.parse_args(argv)

    try:
        export_tables(args)
        return 0
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
