#!/usr/bin/env python3
"""Download SEC filings and render them to Excel in a single run."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Ensure src/ is importable when this script is executed from the repo root.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sec_downloader import EdgarClient, FilingDownload, FilingSearch
from sec_downloader.models import DownloadConfig, DownloadResult, Filing, SearchFilters
from sec_downloader.utils import validate_date_range

import render_viewer_to_xlsx as renderer


logger = logging.getLogger(__name__)


def setup_logging(verbose: bool) -> None:
    """Configure root logging for the combined workflow."""
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


def read_identifier_file(file_path: Path) -> List[str]:
    """Read ticker/CIK identifiers from a file."""
    with file_path.open("r", encoding="utf-8") as handle:
        return [
            line.strip() for line in handle if line.strip() and not line.startswith("#")
        ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download SEC filings (10-K/10-Q) and render Excel workbooks in a single pass"
    )

    identifier_group = parser.add_mutually_exclusive_group(required=True)
    identifier_group.add_argument(
        "--ticker", action="append", help="Ticker symbol to process (can be repeated)"
    )
    identifier_group.add_argument(
        "--cik", action="append", help="CIK to process (can be repeated)"
    )
    identifier_group.add_argument(
        "--input-file", type=Path, help="File with one ticker/CIK per line"
    )

    parser.add_argument(
        "--k-count",
        type=int,
        default=5,
        help="Number of 10-K filings to download (default: 5)",
    )
    parser.add_argument(
        "--q-count",
        type=int,
        default=10,
        help="Number of 10-Q filings to download (default: 10)",
    )
    parser.add_argument(
        "--include-amendments", action="store_true", help="Include /A amendment filings"
    )
    parser.add_argument(
        "--start-date", type=str, help="Earliest filing date (YYYY-MM-DD)"
    )
    parser.add_argument("--end-date", type=str, help="Latest filing date (YYYY-MM-DD)")

    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("./downloads"),
        help="Directory for downloaded filings (default: ./downloads)",
    )
    parser.add_argument(
        "--excel-dir",
        type=Path,
        default=Path("./output"),
        help="Directory for generated Excel files (default: ./output)",
    )
    parser.add_argument(
        "--max-parallel", type=int, default=3, help="Parallel downloads (default: 3)"
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=30,
        help="Download timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry attempts for failed downloads (default: 3)",
    )
    parser.add_argument(
        "--exhibits",
        choices=["include", "exclude"],
        default=None,
        help="Include or exclude exhibit files (default: exclude)",
    )
    parser.add_argument(
        "--include-exhibits", action="store_true", default=False, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--skip-verify", action="store_true", help="Skip download integrity checks"
    )

    parser.add_argument(
        "--label-style",
        choices=["terse", "standard"],
        default="terse",
        help="Excel label style",
    )
    parser.add_argument(
        "--collapse-dimensions",
        action="store_true",
        help="Collapse dimensional facts in Excel",
    )
    parser.add_argument(
        "--include-disclosures",
        action="store_true",
        help="Include disclosure roles in Excel output",
    )
    parser.add_argument(
        "--currency", default="USD", help="Currency code for display (default: USD)"
    )
    parser.add_argument(
        "--scale-none", action="store_true", help="Display raw values without scaling"
    )
    parser.add_argument(
        "--no-scale-hint", action="store_true", help="Ignore XBRL decimals when scaling"
    )
    parser.add_argument(
        "--one-period",
        action="store_true",
        help="Limit Excel output to the most recent period",
    )
    parser.add_argument(
        "--periods", help="Comma separated list of periods to include in Excel output"
    )
    parser.add_argument(
        "--render-timeout",
        type=int,
        default=300,
        help="Arelle processing timeout (default: 300)",
    )
    parser.add_argument(
        "--render-temp-dir",
        type=Path,
        help="Custom temp directory for Arelle processing",
    )
    parser.add_argument(
        "--keep-temp", action="store_true", help="Preserve temporary render artifacts"
    )
    parser.add_argument(
        "--dump-role-map", type=Path, help="Write MetaLinks role metadata to CSV"
    )
    parser.add_argument(
        "--save-viewer-json",
        type=Path,
        help="Persist extracted viewer JSON for inspection",
    )

    parser.add_argument("--quiet", action="store_true", help="Reduce console output")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing Excel files"
    )

    return parser.parse_args(argv)


def normalize_identifiers(args: argparse.Namespace) -> List[str]:
    identifiers: List[str] = []

    if args.ticker:
        identifiers.extend([value.strip() for value in args.ticker if value.strip()])

    if args.cik:
        identifiers.extend([value.strip() for value in args.cik if value.strip()])

    if args.input_file:
        identifiers.extend(read_identifier_file(args.input_file))

    unique_identifiers = []
    seen = set()
    for identifier in identifiers:
        key = identifier.upper()
        if key not in seen:
            unique_identifiers.append(identifier)
            seen.add(key)

    return unique_identifiers


def build_form_requests(args: argparse.Namespace) -> List[Tuple[str, int]]:
    requests: List[Tuple[str, int]] = []
    if args.k_count > 0:
        requests.append(("10-K", args.k_count))
    if args.q_count > 0:
        requests.append(("10-Q", args.q_count))
    return requests


def parse_date_string(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD") from exc


def make_render_namespace(
    filing_input: Path,
    output_path: Path,
    args: argparse.Namespace,
    meta_links_candidates: Optional[List[Path]] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        filing=str(filing_input),
        out=output_path,
        one_period=args.one_period,
        periods=args.periods,
        currency=args.currency,
        scale_none=args.scale_none,
        scale_millions=not args.scale_none,
        include_disclosures=args.include_disclosures,
        dump_role_map=args.dump_role_map,
        label_style=args.label_style,
        expand_dimensions=not args.collapse_dimensions,
        no_scale_hint=args.no_scale_hint,
        save_viewer_json=args.save_viewer_json,
        verbose=args.verbose,
        temp_dir=args.render_temp_dir,
        keep_temp=args.keep_temp,
        timeout=args.render_timeout,
        meta_links_candidates=(
            [str(path) for path in meta_links_candidates]
            if meta_links_candidates
            else None
        ),
    )


def determine_filing_input(download_result: DownloadResult) -> Optional[Path]:
    if not download_result.success or not download_result.local_path:
        return None

    base_dir = download_result.local_path

    def is_split_report(path: Path) -> bool:
        name = path.name.lower()
        if not name.endswith((".htm", ".html")):
            return False
        if name.startswith("r") and name[1:-4].isdigit():
            return True
        if "index" in name and "10" not in name and "10q" not in name:
            return True
        return False

    def find_first(patterns: Sequence[str]) -> Optional[Path]:
        for pattern in patterns:
            matches = sorted(base_dir.glob(pattern))
            if matches:
                return matches[0]
        return None

    ixviewer_zip = base_dir / "ixviewer.zip"
    if ixviewer_zip.exists():
        return ixviewer_zip

    zip_priority = (
        "*ixbrl.zip",
        "*-ixbrl.zip",
        "*-xbrl.zip",
        "*_ixbrl.zip",
        "*_xbrl.zip",
        "*xbrl.zip",
    )
    prioritized_zip = find_first(zip_priority)
    if prioritized_zip:
        return prioritized_zip

    primary = download_result.primary_file_path
    if primary and primary.exists() and not is_split_report(primary):
        return primary

    html_candidates = sorted(base_dir.glob("*.htm")) + sorted(base_dir.glob("*.html"))
    for html_path in html_candidates:
        if not is_split_report(html_path):
            return html_path

    if primary and primary.exists():
        return primary

    zip_fallback = find_first(("*.zip",))
    if zip_fallback:
        return zip_fallback

    return html_candidates[0] if html_candidates else None


def build_excel_path(base_dir: Path, filing: Filing) -> Path:
    ticker = filing.ticker or f"CIK_{filing.cik}"
    accession_number = getattr(filing, "accession_number", "") or ""
    accession = filing.accession_clean or accession_number.replace("-", "")
    date_str = (
        filing.report_date.strftime("%Y-%m-%d")
        if filing.report_date
        else filing.filing_date.strftime("%Y-%m-%d")
    )
    file_name = (
        f"{filing.form_type}_{date_str}_{accession}.xlsx"
        if accession
        else f"{filing.form_type}_{date_str}.xlsx"
    )
    return base_dir / ticker / file_name


def collect_filings_for_identifier(
    identifier: str,
    search: FilingSearch,
    form_requests: Iterable[Tuple[str, int]],
    include_amendments: bool,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> List[Filing]:
    filings: List[Filing] = []
    for form_type, count in form_requests:
        filters = SearchFilters(
            form_types=[form_type],
            start_date=None,
            end_date=None,
            include_amendments=include_amendments,
            max_results=count,
        )

        filters.start_date = start_date
        filters.end_date = end_date

        logger.info(
            "Searching %s filings for %s (limit %s)", form_type, identifier, count
        )
        try:
            matches = search.search(identifier, filters)
        except Exception as exc:
            logger.error("Failed to search %s for %s: %s", form_type, identifier, exc)
            continue

        if not matches:
            logger.warning("No %s filings found for %s", form_type, identifier)
            continue

        filings.extend(matches[:count])

    # Sort newest first for downstream reporting
    filings.sort(key=lambda f: f.filing_date, reverse=True)
    return filings


def download_filings_for_identifier(
    identifier: str,
    filings: List[Filing],
    downloader: FilingDownload,
    config: DownloadConfig,
    quiet: bool,
) -> List[DownloadResult]:
    if not filings:
        logger.warning("Skipping download for %s (no filings requested)", identifier)
        return []

    if not quiet:
        print(f"\n📥 Downloading {len(filings)} filing(s) for {identifier}...")

    return downloader.download_filings(filings, config, show_progress=not quiet)


def render_downloaded_filings(
    results: List[DownloadResult], args: argparse.Namespace
) -> Dict[str, Path]:
    generated_files: Dict[str, Path] = {}

    for result in results:
        filing = result.filing

        if not result.success:
            logger.error(
                "Download failed for %s: %s", filing.display_name, result.error
            )
            continue

        input_path = determine_filing_input(result)
        if not input_path:
            logger.error("Could not locate filing input for %s", filing.display_name)
            continue

        excel_path = build_excel_path(args.excel_dir, filing)
        excel_path.parent.mkdir(parents=True, exist_ok=True)

        if excel_path.exists() and not args.overwrite:
            logger.info(
                "Excel already exists for %s; skipping (use --overwrite to regenerate)",
                filing.display_name,
            )
            generated_files[filing.display_name] = excel_path
            continue

        meta_candidates: List[Path] = []
        if result.local_path:
            base_dir = result.local_path
            meta_candidates.extend(
                [
                    base_dir / "MetaLinks.json",
                    base_dir / "metalink.json",
                    base_dir / "metalinks.json",
                ]
            )
            meta_candidates.extend(
                [
                    base_dir / "ixviewer" / "MetaLinks.json",
                    base_dir / "ixviewer" / "metalink.json",
                    base_dir / "ixviewer" / "metalinks.json",
                ]
            )

        meta_filtered = [path for path in meta_candidates if path.exists()]

        render_args = make_render_namespace(
            input_path, excel_path, args, meta_links_candidates=meta_filtered
        )

        try:
            renderer.validate_arguments(render_args)
            renderer.process_filing(render_args)
        except SystemExit as exc:
            logger.error(
                "Rendering aborted for %s (exit code %s)", filing.display_name, exc.code
            )
            continue
        except Exception as exc:
            logger.error("Rendering failed for %s: %s", filing.display_name, exc)
            continue

        generated_files[filing.display_name] = excel_path
        logger.info("Generated %s", excel_path)

    return generated_files


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    setup_logging(args.verbose)

    if args.max_parallel < 1 or args.max_parallel > 10:
        raise ValueError("--max-parallel must be between 1 and 10")
    if args.download_timeout < 5:
        raise ValueError("--download-timeout must be at least 5 seconds")
    if args.retries < 0:
        raise ValueError("--retries must be non-negative")
    if args.render_timeout < 60:
        raise ValueError("--render-timeout must be at least 60 seconds")

    start_date = parse_date_string(args.start_date)
    end_date = parse_date_string(args.end_date)
    validate_date_range(start_date, end_date)

    identifiers = normalize_identifiers(args)
    if not identifiers:
        logger.error("No identifiers provided")
        return 1

    form_requests = build_form_requests(args)
    if not form_requests:
        logger.error("No forms requested; set --k-count and/or --q-count above zero")
        return 1

    args.download_dir.mkdir(parents=True, exist_ok=True)
    args.excel_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"📊 Processing {len(identifiers)} identifier(s)")

    edgar_client = EdgarClient()
    search = FilingSearch(edgar_client)
    downloader = FilingDownload(edgar_client)

    exhibits_mode = args.exhibits or ("include" if args.include_exhibits else "exclude")
    include_exhibits = exhibits_mode == "include"
    args.include_exhibits = include_exhibits

    download_config = DownloadConfig(
        output_dir=args.download_dir,
        create_subdirs=True,
        include_exhibits=include_exhibits,
        max_parallel=args.max_parallel,
        retry_attempts=args.retries,
        timeout_seconds=args.download_timeout,
        verify_downloads=not args.skip_verify,
    )

    overall_generated: Dict[str, Path] = {}

    for identifier in identifiers:
        filings = collect_filings_for_identifier(
            identifier,
            search,
            form_requests,
            args.include_amendments,
            start_date,
            end_date,
        )

        if not filings:
            logger.warning("No filings matched criteria for %s", identifier)
            continue

        results = download_filings_for_identifier(
            identifier, filings, downloader, download_config, args.quiet
        )
        generated = render_downloaded_filings(results, args)
        overall_generated.update(generated)

    if not args.quiet and overall_generated:
        print("\n✅ Generated Excel files:")
        for display_name, path in overall_generated.items():
            print(f"   • {display_name} → {path}")

    if not overall_generated:
        logger.warning("No Excel files were generated")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
