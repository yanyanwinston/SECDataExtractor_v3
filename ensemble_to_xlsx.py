#!/usr/bin/env python3
"""Assemble multiple SEC filings into a single multi-period workbook."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


# Ensure src/ is importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sec_downloader import EdgarClient, FilingDownload, FilingSearch  # type: ignore  # noqa: E402
from sec_downloader.models import DownloadConfig, DownloadResult, Filing, SearchFilters  # type: ignore  # noqa: E402

from src.processor import (  # noqa: E402
    ArelleProcessor,
    DataParser,
    FilingSlice,
    InputHandler,
    ValueFormatter,
    ViewerDataExtractor,
    ExcelGenerator,
    build_ensemble_result,
)


logger = logging.getLogger(__name__)


@dataclass
class PipelineOptions:
    """Configuration for converting a single filing into a ProcessingResult."""

    currency: str = "USD"
    scale_millions: bool = True
    include_disclosures: bool = False
    label_style: str = "terse"
    use_scale_hint: bool = True
    expand_dimensions: bool = True
    timeout: int = 300
    temp_dir: Optional[Path] = None
    keep_temp: bool = False


def setup_logging(verbose: bool) -> None:
    """Configure logging output."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    if not verbose:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("openpyxl").setLevel(logging.WARNING)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download multiple SEC filings and combine them into a single Excel workbook",
    )

    identifier_group = parser.add_mutually_exclusive_group(required=True)
    identifier_group.add_argument("--ticker", help="Ticker symbol to process (e.g., TSLA)")
    identifier_group.add_argument("--cik", help="CIK to process (10-digit, zero padded if needed)")

    parser.add_argument("--form", default="10-K", help="Form type to aggregate (default: 10-K)")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of filings to include (default: 5)",
    )
    parser.add_argument(
        "--include-amendments",
        action="store_true",
        help="Allow form amendments (e.g., 10-K/A) in addition to base form",
    )

    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("./downloads"),
        help="Directory to store downloaded filings (default: ./downloads)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Reuse previously downloaded filings in --download-dir instead of contacting EDGAR",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=2,
        help="Parallel download workers (default: 2)",
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=30,
        help="Download timeout per file in seconds (default: 30)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry attempts for failed downloads (default: 3)",
    )

    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output Excel file path",
    )

    parser.add_argument(
        "--currency",
        default="USD",
        help="Currency code for display formatting (default: USD)",
    )
    parser.add_argument(
        "--scale-none",
        action="store_true",
        help="Display raw currency values (skip millions scaling)",
    )
    parser.add_argument(
        "--include-disclosures",
        action="store_true",
        help="Include disclosure/detail presentation roles",
    )
    parser.add_argument(
        "--collapse-dimensions",
        action="store_true",
        help="Collapse dimensional expansions into parent line items",
    )
    parser.add_argument(
        "--label-style",
        choices=["terse", "standard"],
        default="terse",
        help="Preferred concept label style (default: terse)",
    )
    parser.add_argument(
        "--no-scale-hint",
        action="store_true",
        help="Ignore XBRL decimals when inferring scale",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Arelle processing timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        help="Custom temporary directory for intermediate artifacts",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary directories used during processing",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    return parser.parse_args(argv)


def select_filings(
    identifier: str,
    form: str,
    count: int,
    include_amendments: bool,
    search: FilingSearch,
) -> List[Filing]:
    """Fetch filings for the identifier and select the newest N."""

    filters = SearchFilters(
        form_types=[form],
        include_amendments=include_amendments,
        max_results=max(count * 2, count),
    )

    filings = search.search(identifier, filters)
    if not filings:
        return []

    def form_matches(value: str) -> bool:
        if value.upper() == form.upper():
            return True
        if include_amendments and value.upper() == f"{form.upper()}/A":
            return True
        return False

    filtered = [filing for filing in filings if form_matches(filing.form_type)]
    filtered.sort(key=lambda f: f.filing_date, reverse=True)
    return filtered[:count]


def download_filings(
    filings: Iterable[Filing],
    download_dir: Path,
    max_parallel: int,
    timeout: int,
    retries: int,
    edgar_client: EdgarClient,
) -> List[DownloadResult]:
    """Download filings to the workspace and return results."""

    download_dir.mkdir(parents=True, exist_ok=True)
    config = DownloadConfig(
        output_dir=download_dir,
        create_subdirs=True,
        include_exhibits=False,
        max_parallel=max_parallel,
        retry_attempts=retries,
        timeout_seconds=timeout,
        verify_downloads=True,
    )

    downloader = FilingDownload(edgar_client)
    return downloader.download_filings(list(filings), config, show_progress=True)


def build_existing_results(
    filings: Iterable[Filing],
    download_dir: Path,
) -> List[DownloadResult]:
    """Construct DownloadResult objects for filings already present on disk."""

    config = DownloadConfig(output_dir=download_dir, create_subdirs=True)
    results: List[DownloadResult] = []

    for filing in filings:
        filing_dir = config.get_filing_dir(filing)
        if not filing_dir.exists():
            logger.error(
                "Expected filing directory missing for %s (%s)",
                filing.display_name,
                filing_dir,
            )
            continue

        metadata_path = filing_dir / "metadata.json"
        if metadata_path.exists():
            try:
                with metadata_path.open("r", encoding="utf-8") as handle:
                    metadata = json.load(handle)
                primary_document = metadata.get("filing_info", {}).get("primary_document")
                if primary_document:
                    filing.primary_document = primary_document
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning(
                    "Failed to read metadata for %s: %s",
                    filing.display_name,
                    exc,
                )

        if not filing.primary_document:
            html_candidates = sorted(filing_dir.glob("*.htm")) + sorted(
                filing_dir.glob("*.html")
            )
            if html_candidates:
                filing.primary_document = html_candidates[0].name

        downloaded_files = [str(path) for path in filing_dir.iterdir() if path.is_file()]

        results.append(
            DownloadResult(
                filing=filing,
                success=True,
                local_path=filing_dir,
                error=None,
                downloaded_files=downloaded_files,
                metadata_path=metadata_path if metadata_path.exists() else None,
            )
        )

    return results


def gather_meta_links(result: DownloadResult) -> List[Path]:
    """Collect potential MetaLinks companions for a downloaded filing."""

    candidates: List[Path] = []
    if result.local_path:
        base_dir = result.local_path
        candidates.extend(
            [
                base_dir / "MetaLinks.json",
                base_dir / "metalink.json",
                base_dir / "metalinks.json",
            ]
        )
        ix_dir = base_dir / "ixviewer"
        candidates.extend(
            [
                ix_dir / "MetaLinks.json",
                ix_dir / "metalink.json",
                ix_dir / "metalinks.json",
            ]
        )

    return [path for path in candidates if path.exists()]


def process_download_result(
    result: DownloadResult,
    pipeline_options: PipelineOptions,
) -> FilingSlice:
    """Convert a downloaded filing into a FilingSlice via the processing pipeline."""

    if not result.success or not result.primary_file_path:
        status = "failed" if not result.success else "missing primary document"
        raise RuntimeError(f"Download result for {result.filing.display_name} {status}")

    temp_root = pipeline_options.temp_dir or Path(tempfile.gettempdir()) / "sec_ensemble"
    temp_root.mkdir(parents=True, exist_ok=True)

    input_handler = InputHandler(temp_root)
    filing_source = input_handler.create_source(str(result.primary_file_path))

    meta_candidates = gather_meta_links(result)

    try:
        if not filing_source.validate():
            raise ValueError("Filing source validation failed")

        filing_path = filing_source.get_path()

        meta_candidates.extend(
            path
            for path in [
                Path(filing_path).with_name("MetaLinks.json"),
                Path(filing_path).with_name("metalink.json"),
                Path(filing_path).with_name("metalinks.json"),
            ]
            if path.exists()
        )

        processor = ArelleProcessor(temp_root, pipeline_options.timeout)
        if not processor.check_arelle_available():
            if not processor.install_arelle():
                raise RuntimeError("Arelle with iXBRL viewer plugin is not available")

        viewer_html = processor.generate_viewer_html(filing_path)

        extractor = ViewerDataExtractor()
        viewer_data = extractor.extract_viewer_data(
            viewer_html, meta_links_candidates=meta_candidates
        )

        formatter = ValueFormatter(
            currency=pipeline_options.currency,
            scale_millions=pipeline_options.scale_millions,
        )

        data_parser = DataParser(
            formatter,
            include_disclosures=pipeline_options.include_disclosures,
            label_style=pipeline_options.label_style,
            use_scale_hint=pipeline_options.use_scale_hint,
            expand_dimensions=pipeline_options.expand_dimensions,
        )

        result_model = data_parser.parse_viewer_data(viewer_data)
        if not result_model.success:
            raise RuntimeError(result_model.error or "Unknown parsing failure")

        return FilingSlice.from_processing_result(result.filing.display_name, result_model)

    finally:
        if not pipeline_options.keep_temp:
            try:
                filing_source.cleanup()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                logger.debug("Cleanup warning: %s", exc)

        if not pipeline_options.keep_temp and pipeline_options.temp_dir is None:
            # Remove transient temp root if empty
            try:
                temp_root.rmdir()
            except OSError:
                # Directory not empty yet – leave for future cleanup
                pass


def convert_to_slices(
    download_results: Iterable[DownloadResult],
    pipeline_options: PipelineOptions,
) -> List[FilingSlice]:
    """Run the processing pipeline for every successful download."""

    slices: List[FilingSlice] = []

    for result in download_results:
        if not result.success:
            logger.error(
                "Download failed for %s: %s",
                result.filing.display_name,
                result.error,
            )
            continue

        try:
            slice_item = process_download_result(result, pipeline_options)
        except Exception as exc:
            logger.error(
                "Processing failed for %s: %s", result.filing.display_name, exc
            )
            continue

        slices.append(slice_item)

    return slices


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    identifier = args.ticker or args.cik
    assert identifier  # For type checkers

    if args.count < 1:
        logger.error("--count must be at least 1")
        return 1

    if args.timeout < 60:
        logger.error("--timeout must be at least 60 seconds")
        return 1

    if args.max_parallel < 1 or args.max_parallel > 6:
        logger.error("--max-parallel must be between 1 and 6")
        return 1

    args.download_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    edgar_client = EdgarClient()
    search = FilingSearch(edgar_client)

    filings = select_filings(
        identifier=identifier,
        form=args.form,
        count=args.count,
        include_amendments=args.include_amendments,
        search=search,
    )

    if not filings:
        logger.error("No %s filings found for %s", args.form, identifier)
        return 1

    logger.info("Selected %d filing(s) for %s", len(filings), identifier)

    if args.no_download:
        download_results = build_existing_results(filings, args.download_dir)
    else:
        download_results = download_filings(
            filings,
            args.download_dir,
            args.max_parallel,
            args.download_timeout,
            args.retries,
            edgar_client,
        )

    options = PipelineOptions(
        currency=args.currency,
        scale_millions=not args.scale_none,
        include_disclosures=args.include_disclosures,
        label_style=args.label_style,
        use_scale_hint=not args.no_scale_hint,
        expand_dimensions=not args.collapse_dimensions,
        timeout=args.timeout,
        temp_dir=args.temp_dir,
        keep_temp=args.keep_temp,
    )

    slices = convert_to_slices(download_results, options)
    if not slices:
        logger.error("All filings failed to process; aborting ensemble generation")
        return 1

    ensemble_result = build_ensemble_result(slices)

    ExcelGenerator().generate_excel(ensemble_result, str(args.out))
    logger.info("✅ Ensemble workbook generated: %s", args.out)
    print(f"✅ Ensemble workbook generated: {args.out}")

    if ensemble_result.warnings:
        print("\nWarnings:")
        for warning in ensemble_result.warnings:
            print(f"  - {warning}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
