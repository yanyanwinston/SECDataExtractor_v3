#!/usr/bin/env python3
"""
SEC Filing to Excel Converter

Converts iXBRL filings to Excel format while preserving the original
presentation structure using Arelle's iXBRLViewerPlugin.

Usage:
    python render_viewer_to_xlsx.py --filing <source> --out <output.xlsx>

Examples:
    # Process local file
    python render_viewer_to_xlsx.py --filing filing.htm --out output.xlsx

    # Process SEC URL
    python render_viewer_to_xlsx.py --filing "https://www.sec.gov/..." --out output.xlsx

    # Single period only
    python render_viewer_to_xlsx.py --filing filing.htm --out output.xlsx --one-period
"""

import argparse
import csv
import json
import logging
import sys
import tempfile
from pathlib import Path

from src.processor import (
    InputHandler,
    ArelleProcessor,
    ViewerDataExtractor,
    DataParser,
    ValueFormatter,
    ExcelGenerator,
)


logger = logging.getLogger(__name__)


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Suppress verbose output from external libraries
    if not verbose:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("openpyxl").setLevel(logging.WARNING)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert SEC iXBRL filings to Excel format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --filing "https://sec.gov/edgar/..." --out results.xlsx
  %(prog)s --filing local-10k.htm --out output.xlsx --one-period
  %(prog)s --filing filing.zip --out quarterly.xlsx --periods "2024,2023"
        """,
    )

    # Required arguments
    parser.add_argument(
        "--filing", required=True, help="iXBRL filing source (URL, local file, or ZIP)"
    )

    parser.add_argument(
        "--out", required=True, type=Path, help="Output Excel file path"
    )

    # Period selection
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--one-period", action="store_true", help="Include only the most recent period"
    )

    period_group.add_argument(
        "--periods", help="Comma-separated list of periods to include"
    )

    # Formatting options
    parser.add_argument(
        "--currency", default="USD", help="Expected currency for display (default: USD)"
    )

    scaling_group = parser.add_mutually_exclusive_group()
    scaling_group.add_argument(
        "--scale-millions",
        action="store_true",
        default=True,
        help="Scale currency values to millions (default)",
    )

    scaling_group.add_argument(
        "--scale-none", action="store_true", help="Display raw values without scaling"
    )

    parser.add_argument(
        "--include-disclosures",
        action="store_true",
        help="Include disclosure/detail presentation roles in the workbook",
    )

    parser.add_argument(
        "--dump-role-map",
        type=Path,
        help="Write MetaLinks role metadata to CSV for inspection",
    )

    parser.add_argument(
        "--label-style",
        choices=["terse", "standard"],
        default="terse",
        help="Preferred concept label style for Excel output (default: terse)",
    )

    dimension_group = parser.add_mutually_exclusive_group()
    dimension_group.add_argument(
        "--dimension-breakdown",
        dest="expand_dimensions",
        action="store_true",
        help="Expand axis/member dimensions into separate rows (default)",
    )
    dimension_group.add_argument(
        "--collapse-dimensions",
        dest="expand_dimensions",
        action="store_false",
        help="Collapse dimensional facts into their parent line items",
    )
    parser.set_defaults(expand_dimensions=True)

    parser.add_argument(
        "--no-scale-hint",
        action="store_true",
        help="Ignore XBRL decimals when scaling numeric values",
    )

    parser.add_argument(
        "--save-viewer-json",
        type=Path,
        help="Write the extracted viewer JSON payload to disk",
    )

    # Processing options
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    parser.add_argument("--temp-dir", type=Path, help="Directory for temporary files")

    parser.add_argument(
        "--keep-temp", action="store_true", help="Keep temporary files after processing"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout for Arelle processing in seconds (default: 300)",
    )

    return parser


def _dump_role_map(role_map, output_path: Path) -> None:
    """Write MetaLinks role metadata to CSV for analysis."""
    if not role_map:
        logger.warning("Role metadata not available; skipping dump")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "role_uri",
        "r_id",
        "groupType",
        "subGroupType",
        "longName",
        "shortName",
        "order",
        "isDefault",
    ]

    try:
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

            for role_uri, metadata in sorted(
                role_map.items(), key=lambda item: item[1].get("order") or float("inf")
            ):
                row = {"role_uri": role_uri}
                row.update(
                    {key: metadata.get(key) for key in fieldnames if key != "role_uri"}
                )
                writer.writerow(row)

        logger.info("Role metadata written to %s", output_path)
    except Exception as exc:
        logger.warning("Failed to write role metadata CSV: %s", exc)


def _dump_viewer_json(viewer_data, output_path: Path) -> None:
    """Persist the extracted viewer JSON payload."""
    if not viewer_data:
        logger.warning("Viewer data not available; skipping save")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(viewer_data, handle)
        logger.info("Viewer JSON written to %s", output_path)
    except Exception as exc:
        logger.warning("Failed to write viewer JSON: %s", exc)


def validate_arguments(args) -> None:
    """Validate command-line arguments."""
    from urllib.parse import urlparse

    # Validate filing source
    if args.filing.startswith("http"):
        # URL validation
        parsed = urlparse(args.filing)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL: {args.filing}")
    else:
        # File path validation
        if not Path(args.filing).exists():
            raise FileNotFoundError(f"Filing not found: {args.filing}")

    # Validate output directory
    output_dir = args.out.parent
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # Validate periods format
    if args.periods:
        periods = [p.strip() for p in args.periods.split(",")]
        if not periods:
            raise ValueError("Periods list cannot be empty")

    # Validate temp directory
    if args.temp_dir:
        if args.temp_dir.exists() and not args.temp_dir.is_dir():
            raise ValueError(f"Temp path is not a directory: {args.temp_dir}")

    # Validate timeout
    if args.timeout < 60:
        raise ValueError("Timeout must be at least 60 seconds")


def process_filing(args) -> None:
    """Process the filing through the complete pipeline."""

    # Create temporary directory
    temp_dir = args.temp_dir or Path(tempfile.gettempdir()) / "sec_processor"
    temp_dir.mkdir(exist_ok=True)

    filing_source = None

    try:
        logger.info(f"Starting processing of: {args.filing}")

        # Step 1: Input validation and handling
        logger.info("Step 1: Validating and preparing input...")
        input_handler = InputHandler(temp_dir)
        filing_source = input_handler.create_source(args.filing)

        if not filing_source.validate():
            raise ValueError("Filing source validation failed")

        filing_path = filing_source.get_path()
        meta_links_candidates = []

        # Include explicit candidates provided by the caller (e.g., original download directory)
        extra_meta_links = getattr(args, "meta_links_candidates", None)
        if extra_meta_links:
            for candidate in extra_meta_links:
                candidate_path = Path(candidate)
                if candidate_path.exists():
                    meta_links_candidates.append(candidate_path)

        original_meta_links = Path(filing_path).with_name("MetaLinks.json")
        if original_meta_links.exists():
            meta_links_candidates.append(original_meta_links)

        legacy_meta_links = Path(filing_path).with_name("metalink.json")
        if legacy_meta_links.exists():
            meta_links_candidates.append(legacy_meta_links)

        if not input_handler.validate_filing(filing_path):
            logger.warning("File does not appear to be a valid iXBRL filing")

        logger.info(f"Input prepared: {filing_path}")

        # Step 2: Arelle processing
        logger.info("Step 2: Processing with Arelle...")
        arelle_processor = ArelleProcessor(temp_dir, args.timeout)

        # Check if Arelle is available
        if not arelle_processor.check_arelle_available():
            logger.warning("Arelle not found, attempting installation...")
            if not arelle_processor.install_arelle():
                raise RuntimeError(
                    "Failed to install Arelle. Please install manually: pip install arelle"
                )

        viewer_html_path = arelle_processor.generate_viewer_html(filing_path)
        logger.info(f"Arelle processing complete: {viewer_html_path}")

        # Step 3: JSON extraction
        logger.info("Step 3: Extracting viewer data...")
        json_extractor = ViewerDataExtractor()
        viewer_data = json_extractor.extract_viewer_data(
            viewer_html_path, meta_links_candidates=meta_links_candidates
        )

        if args.dump_role_map:
            _dump_role_map(viewer_data.get("role_map"), args.dump_role_map)

        if args.save_viewer_json:
            _dump_viewer_json(viewer_data, args.save_viewer_json)

        logger.info("Viewer data extracted successfully")

        # Step 4: Data parsing
        logger.info("Step 4: Parsing financial data...")
        formatter = ValueFormatter(
            currency=args.currency, scale_millions=not args.scale_none
        )
        data_parser = DataParser(
            formatter,
            include_disclosures=args.include_disclosures,
            label_style=args.label_style,
            use_scale_hint=not args.no_scale_hint,
            expand_dimensions=args.expand_dimensions,
        )
        result = data_parser.parse_viewer_data(viewer_data)

        if not result.success:
            raise ValueError(f"Data parsing failed: {result.error}")

        logger.info(f"Parsed {len(result.statements)} financial statements")

        # Step 5: Excel generation
        logger.info("Step 5: Generating Excel file...")
        excel_generator = ExcelGenerator()
        excel_generator.generate_excel(
            result, str(args.out), single_period=args.one_period
        )

        logger.info(f"✅ Excel file generated: {args.out}")

        # Print summary
        print(f"✅ Excel file generated: {args.out}")
        if args.verbose:
            print(f"\nProcessing Summary:")
            print(f"  Company: {result.company_name}")
            print(f"  Form Type: {result.form_type}")
            print(f"  Filing Date: {result.filing_date}")
            print(f"  Statements: {len(result.statements)}")

            for statement in result.statements:
                print(
                    f"    - {statement.name}: {len(statement.periods)} periods, {len(statement.rows)} rows"
                )

            if result.warnings:
                print(f"\nWarnings:")
                for warning in result.warnings:
                    print(f"  - {warning}")

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        print(f"❌ Processing failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)

    finally:
        # Cleanup
        if filing_source and not args.keep_temp:
            try:
                filing_source.cleanup()
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")

        if not args.keep_temp and temp_dir.exists():
            try:
                import shutil

                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Temp directory cleanup warning: {e}")


def main():
    """Main CLI entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Configure logging
    setup_logging(args.verbose)

    try:
        # Validate arguments
        validate_arguments(args)

        # Process filing
        process_filing(args)

    except KeyboardInterrupt:
        print("\n❌ Processing cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
