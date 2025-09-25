#!/usr/bin/env python3
"""
SEC Filing Downloader CLI

Command-line interface for downloading SEC filings (10-K, 10-Q) from EDGAR database.
Integrates with SECDataExtractor_v3 for seamless filing processing pipeline.

Usage Examples:
    # Download latest 10-K for a company
    python download_filings.py --ticker AAPL --form 10-K

    # Download multiple quarters
    python download_filings.py --ticker MSFT --form 10-Q --count 4

    # Download by date range
    python download_filings.py --ticker GOOGL --form 10-K --start-date 2020-01-01 --end-date 2023-12-31

    # Batch download from file
    python download_filings.py --input-file tickers.txt --form 10-K,10-Q --output-dir ./filings/
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from sec_downloader import FilingSearch, FilingDownload, EdgarClient
from sec_downloader.models import SearchFilters, DownloadConfig
from sec_downloader.utils import validate_date_range


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

    # Suppress verbose output from external libraries
    if not verbose:
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)


def parse_form_types(form_string: str) -> List[str]:
    """Parse comma-separated form types."""
    return [form.strip().upper() for form in form_string.split(',')]


def parse_date(date_string: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_string, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


def read_ticker_file(file_path: Path) -> List[str]:
    """Read ticker symbols from file (one per line)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
        return [ticker for ticker in tickers if ticker and not ticker.startswith('#')]
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Error reading ticker file {file_path}: {e}")


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Download SEC filings (10-K, 10-Q) from EDGAR database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --ticker AAPL --form 10-K
  %(prog)s --ticker MSFT --form 10-Q --count 4
  %(prog)s --ticker GOOGL --form 10-K --start-date 2020-01-01 --end-date 2023-12-31
  %(prog)s --input-file tickers.txt --form 10-K,10-Q --output-dir ./filings/

Form Types:
  10-K    Annual report
  10-Q    Quarterly report

Note: Use --include-amendments to also download 10-K/A and 10-Q/A filings.
        """
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--ticker',
        help='Company ticker symbol (e.g., AAPL, MSFT)'
    )
    input_group.add_argument(
        '--cik',
        help='Company Central Index Key (CIK)'
    )
    input_group.add_argument(
        '--input-file',
        type=Path,
        help='File containing ticker symbols (one per line)'
    )

    # Filing selection
    parser.add_argument(
        '--form',
        default='10-K,10-Q',
        help='Form types to download (comma-separated, default: 10-K,10-Q)'
    )
    parser.add_argument(
        '--count',
        type=int,
        help='Maximum number of filings to download per company'
    )
    parser.add_argument(
        '--start-date',
        type=parse_date,
        help='Start date for filing search (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=parse_date,
        help='End date for filing search (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--include-amendments',
        action='store_true',
        help='Include amendment filings (10-K/A, 10-Q/A)'
    )

    # Output options
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('./downloads'),
        help='Output directory for downloaded filings (default: ./downloads)'
    )
    parser.add_argument(
        '--include-exhibits',
        action='store_true',
        help='Download exhibit files in addition to primary documents'
    )
    parser.add_argument(
        '--flat-structure',
        action='store_true',
        help='Use flat directory structure instead of company/filing subdirectories'
    )

    # Processing options
    parser.add_argument(
        '--max-parallel',
        type=int,
        default=3,
        help='Maximum parallel downloads (default: 3)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Download timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=3,
        help='Number of retry attempts for failed downloads (default: 3)'
    )

    # Logging and output
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress bars and non-essential output'
    )

    return parser


def validate_arguments(args) -> None:
    """Validate command-line arguments."""
    # Validate date range
    validate_date_range(args.start_date, args.end_date)

    # Validate input file if specified
    if args.input_file and not args.input_file.exists():
        raise ValueError(f"Input file not found: {args.input_file}")

    # Validate output directory
    if not args.output_dir.parent.exists():
        raise ValueError(f"Parent directory does not exist: {args.output_dir.parent}")

    # Validate parallel downloads
    if args.max_parallel < 1 or args.max_parallel > 10:
        raise ValueError("Max parallel downloads must be between 1 and 10")

    # Validate timeout and retries
    if args.timeout < 5:
        raise ValueError("Timeout must be at least 5 seconds")
    if args.retries < 0:
        raise ValueError("Retries must be non-negative")


def main():
    """Main CLI entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Validate arguments
        validate_arguments(args)

        # Get list of identifiers (tickers or CIKs)
        identifiers = []
        if args.ticker:
            identifiers = [args.ticker]
        elif args.cik:
            identifiers = [args.cik]
        elif args.input_file:
            identifiers = read_ticker_file(args.input_file)

        if not identifiers:
            print("❌ No valid identifiers found")
            return 1

        print(f"📊 Processing {len(identifiers)} identifier(s)")

        # Parse form types
        form_types = parse_form_types(args.form)

        # Create search filters
        filters = SearchFilters(
            form_types=form_types,
            start_date=args.start_date,
            end_date=args.end_date,
            include_amendments=args.include_amendments,
            max_results=args.count
        )

        # Create download config
        download_config = DownloadConfig(
            output_dir=args.output_dir,
            create_subdirs=not args.flat_structure,
            include_exhibits=args.include_exhibits,
            max_parallel=args.max_parallel,
            retry_attempts=args.retries,
            timeout_seconds=args.timeout
        )

        # Initialize components
        edgar_client = EdgarClient()
        search = FilingSearch(edgar_client)
        downloader = FilingDownload(edgar_client)

        # Search for filings
        all_filings = []

        for identifier in identifiers:
            if not args.quiet:
                print(f"🔍 Searching filings for {identifier}...")

            try:
                filings = search.search(identifier, filters)
                all_filings.extend(filings)

                if not args.quiet:
                    print(f"   Found {len(filings)} filing(s)")

            except Exception as e:
                logger.error(f"Error searching for {identifier}: {e}")
                if not args.quiet:
                    print(f"   ❌ Error: {e}")

        if not all_filings:
            print("❌ No filings found matching criteria")
            return 1

        print(f"📥 Downloading {len(all_filings)} filing(s)...")

        # Download filings
        results = downloader.download_filings(
            all_filings,
            download_config,
            show_progress=not args.quiet
        )

        # Generate summary
        summary = downloader.get_download_summary(results)

        # Print results
        print("\n📊 Download Summary:")
        print(f"   Total filings: {summary['total_filings']}")
        print(f"   Successful: {summary['successful_downloads']}")
        print(f"   Failed: {summary['failed_downloads']}")
        print(f"   Success rate: {summary['success_rate']:.1f}%")
        print(f"   Total files: {summary['total_files_downloaded']}")
        print(f"   Total size: {summary['total_size_mb']:.1f} MB")

        if summary['failed_downloads'] > 0:
            print(f"\n❌ Failed downloads:")
            for error in summary['errors']:
                print(f"   • {error}")

        # Print successful downloads with paths
        if args.verbose:
            print(f"\n✅ Successful downloads:")
            for result in results:
                if result.success and result.primary_file_path:
                    print(f"   • {result.filing.display_name}")
                    print(f"     → {result.primary_file_path}")

        print(f"\n📁 Files saved to: {args.output_dir.absolute()}")

        # Return appropriate exit code
        return 0 if summary['failed_downloads'] == 0 else 1

    except KeyboardInterrupt:
        print("\n⏹️  Download cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())