# 08 - CLI Interface Specification

## Overview

The command-line interface provides user-friendly access to the SEC data extraction functionality. The system consists of two main CLI tools:

1. **`download_filings.py`** - Download SEC filings from EDGAR database
2. **`render_viewer_to_xlsx.py`** - Process iXBRL filings into Excel format

These can be used independently or in combination for a complete download-to-Excel workflow.

## Integrated Workflow (Recommended)

### Complete Download-to-Excel Process

```bash
# Step 1: Download SEC filing
python download_filings.py --ticker AAPL --form 10-K --count 1

# Step 2: Process downloaded filing to Excel
python render_viewer_to_xlsx.py \
  --filing downloads/AAPL/10-K_2023-09-30/aapl-20230930.htm \
  --out apple-financials.xlsx
```

### One-Line Batch Processing
```bash
# Download and process in sequence
python download_filings.py --ticker MSFT --form 10-K --count 1 && \
python render_viewer_to_xlsx.py \
  --filing downloads/MSFT/10-K_*/msft-*.htm \
  --out msft-financials.xlsx
```

## Download Module (download_filings.py)

### Basic Usage
```bash
python download_filings.py --ticker <TICKER> --form <FORM_TYPE>
```

### Common Examples
```bash
# Download latest 10-K
python download_filings.py --ticker AAPL --form 10-K

# Download multiple quarters
python download_filings.py --ticker MSFT --form 10-Q --count 4

# Download by date range
python download_filings.py --ticker GOOGL --form 10-K \
  --start-date 2020-01-01 --end-date 2023-12-31

# Batch download from file
python download_filings.py --input-file tickers.txt --form 10-K,10-Q
```

### Key Download Options
- `--ticker` / `--cik` / `--input-file`: Company identifier or batch file
- `--form`: Form types (10-K, 10-Q, etc.)
- `--count`: Maximum filings per company
- `--start-date` / `--end-date`: Date range filtering
- `--output-dir`: Output directory (default: ./downloads)
- `--max-parallel`: Concurrent downloads (default: 3)
- `--include-amendments`: Include 10-K/A, 10-Q/A filings

## Processing Module (render_viewer_to_xlsx.py)

### Basic Usage
```bash
python render_viewer_to_xlsx.py --filing <SOURCE> --out <OUTPUT_FILE>
```

### Full Command Syntax
```bash
python render_viewer_to_xlsx.py \
  --filing <FILING_SOURCE> \
  --out <OUTPUT_FILE> \
  [--one-period] \
  [--periods <PERIOD_LIST>] \
  [--currency <CURRENCY>] \
  [--scale-millions | --scale-none] \
  [--dimension-breakdown | --collapse-dimensions] \
  [--include-disclosures] \
  [--label-style {terse,standard}] \
  [--dump-role-map <CSV>] \
  [--save-viewer-json <PATH>] \
  [--no-scale-hint] \
  [--verbose] \
  [--temp-dir <DIRECTORY>] \
  [--keep-temp] \
  [--timeout <SECONDS>]
```

## Command-Line Arguments

### Required Arguments

#### `--filing` (required)
Specifies the source of the iXBRL filing.

**Accepted formats:**
- SEC EDGAR URL: `https://www.sec.gov/Archives/edgar/data/...`
- Local iXBRL file: `./filings/company-10k.htm`
- ZIP archive: `./downloads/filing-documents.zip`

**Examples:**
```bash
# SEC EDGAR URL
--filing "https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm"

# Local file
--filing "./data/apple-2023-10k.htm"

# ZIP archive
--filing "./downloads/0000320193-24-000007.zip"
```

#### `--out` (required)
Output file path for the generated Excel file.

**Examples:**
```bash
--out financials_aligned.xlsx
--out "./output/apple-2023-financials.xlsx"
--out "/Users/analyst/reports/quarterly-results.xlsx"
```

### Optional Arguments

#### `--one-period`
Generate single-period statements showing only the most recent period.

**Default:** Multi-period (shows all available periods)

**Examples:**
```bash
# Multi-period (default)
python render_viewer_to_xlsx.py --filing filing.htm --out output.xlsx

# Single-period
python render_viewer_to_xlsx.py --filing filing.htm --out output.xlsx --one-period
```

#### `--periods <PERIOD_LIST>`
Specify which periods to include in the output.

**Format:** Comma-separated list of years or period labels
**Examples:**
```bash
# Specific years
--periods "2024,2023,2022"

# Period labels
--periods "Year Ended December 31, 2024,Year Ended December 31, 2023"

# Single period
--periods "2024"
```

#### `--currency <CURRENCY>`
Specify the expected currency for display.

**Default:** USD
**Examples:**
```bash
--currency USD
--currency EUR
--currency CAD
```

#### `--scale-millions`
Explicitly enable scaling to millions (default behavior).

**Default:** True
**Alternative:** `--scale-none` (disable scaling)

**Examples:**
```bash
# Scale to millions (default)
--scale-millions

# Show raw values
--scale-none
```

#### `--dimension-breakdown`
Expand dimensional data into additional rows (default). When a concept carries axis/member facts—for example, Tesla’s automotive versus energy revenue mix—the workbook shows one row per member, indented beneath the parent line item.

#### `--collapse-dimensions`
Collapse dimensional facts into their parent line item, restoring the pre-expansion behaviour.

#### `--include-disclosures`
Include disclosure/detail presentation roles in addition to the primary statements. Useful when you need the narrative notes or tables that accompany the core financials.

#### `--dump-role-map <CSV>`
Write the MetaLinks role catalogue (R#, `groupType`, etc.) to a CSV file for inspection. Handy when tuning statement allowlists or diagnosing why a sheet was filtered out.

#### `--label-style {terse,standard}`
Choose which XBRL label role to use for row headers. The default `terse` matches the viewer’s compact presentation; `standard` yields the longer GAAP descriptions.

#### `--no-scale-hint`
Ignore XBRL `decimals` metadata when scaling numeric values. Use this when a filing publishes incorrect scale hints and you want the raw fact value before applying the millions display.

#### `--save-viewer-json <PATH>`
Persist the extracted viewer payload to disk. This JSON includes facts, contexts, and label metadata, making it easier to debug period selection or unit issues between runs.

#### `--verbose` / `-v`
Enable detailed logging output.

**Examples:**
```bash
--verbose
-v
```

#### `--temp-dir <DIRECTORY>`
Specify directory for temporary files.

**Default:** System temp directory
**Examples:**
```bash
--temp-dir "./temp"
--temp-dir "/tmp/sec-extractor"
```

#### `--keep-temp`
Keep temporary files after processing (useful for debugging).

**Default:** Clean up temporary files

#### `--timeout <SECONDS>`
Set timeout for Arelle processing.

**Default:** 300 seconds (5 minutes)
**Examples:**
```bash
--timeout 600    # 10 minutes
--timeout 1800   # 30 minutes
```

## Implementation

### Argument Parsing
```python
import argparse
import sys
from pathlib import Path

def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""

    parser = argparse.ArgumentParser(
        description="Extract SEC financial statements to Excel format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --filing "https://sec.gov/edgar/..." --out results.xlsx
  %(prog)s --filing local-10k.htm --out output.xlsx --one-period
  %(prog)s --filing filing.zip --out quarterly.xlsx --periods "2024,2023"
        """
    )

    # Required arguments
    parser.add_argument(
        '--filing',
        required=True,
        help='iXBRL filing source (URL, local file, or ZIP)'
    )

    parser.add_argument(
        '--out',
        required=True,
        type=Path,
        help='Output Excel file path'
    )

    # Period selection
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        '--one-period',
        action='store_true',
        help='Include only the most recent period'
    )

    period_group.add_argument(
        '--periods',
        help='Comma-separated list of periods to include'
    )

    # Formatting options
    parser.add_argument(
        '--currency',
        default='USD',
        help='Expected currency for display (default: USD)'
    )

    scaling_group = parser.add_mutually_exclusive_group()
    scaling_group.add_argument(
        '--scale-millions',
        action='store_true',
        default=True,
        help='Scale currency values to millions (default)'
    )

    scaling_group.add_argument(
        '--scale-none',
        action='store_true',
        help='Display raw values without scaling'
    )

    parser.add_argument(
        '--include-disclosures',
        action='store_true',
        help='Include disclosure/detail presentation roles in the workbook'
    )

    parser.add_argument(
        '--dump-role-map',
        type=Path,
        help='Write MetaLinks role metadata to CSV for inspection'
    )

    parser.add_argument(
        '--label-style',
        choices=['terse', 'standard'],
        default='terse',
        help='Preferred concept label style for Excel output (default: terse)'
    )

    dimension_group = parser.add_mutually_exclusive_group()
    dimension_group.add_argument(
        '--dimension-breakdown',
        dest='expand_dimensions',
        action='store_true',
        help='Expand axis/member dimensions into separate rows (default)'
    )
    dimension_group.add_argument(
        '--collapse-dimensions',
        dest='expand_dimensions',
        action='store_false',
        help='Collapse dimensional facts into their parent line items'
    )
    parser.set_defaults(expand_dimensions=True)

    parser.add_argument(
        '--no-scale-hint',
        action='store_true',
        help='Ignore XBRL decimals when scaling numeric values'
    )

    parser.add_argument(
        '--save-viewer-json',
        type=Path,
        help='Write the extracted viewer JSON payload to disk'
    )

    # Processing options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--temp-dir',
        type=Path,
        help='Directory for temporary files'
    )

    parser.add_argument(
        '--keep-temp',
        action='store_true',
        help='Keep temporary files after processing'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Timeout for Arelle processing in seconds (default: 300)'
    )

    return parser
```

### Main Function
```python
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
        result = process_filing(args)

        if result.success:
            print(f"✓ Excel file generated: {args.out}")
            if args.verbose:
                print_processing_summary(result)
        else:
            print(f"✗ Processing failed: {result.error}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n✗ Processing cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Argument Validation
```python
import os
from urllib.parse import urlparse

def validate_arguments(args) -> None:
    """Validate command-line arguments."""

    # Validate filing source
    if args.filing.startswith('http'):
        # URL validation
        parsed = urlparse(args.filing)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL: {args.filing}")
    else:
        # File path validation
        if not os.path.exists(args.filing):
            raise FileNotFoundError(f"Filing not found: {args.filing}")

    # Validate output directory
    output_dir = args.out.parent
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # Validate periods format
    if args.periods:
        periods = [p.strip() for p in args.periods.split(',')]
        if not periods:
            raise ValueError("Periods list cannot be empty")

    # Validate temp directory
    if args.temp_dir:
        if args.temp_dir.exists() and not args.temp_dir.is_dir():
            raise ValueError(f"Temp path is not a directory: {args.temp_dir}")

    # Validate timeout
    if args.timeout < 60:
        raise ValueError("Timeout must be at least 60 seconds")
```

## Processing Configuration

### Configuration Object
```python
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

@dataclass
class ProcessingConfig:
    """Configuration for filing processing."""
    filing_source: str
    output_path: Path
    single_period: bool
    selected_periods: Optional[List[str]]
    currency: str
    scale_millions: bool
    verbose: bool
    temp_dir: Optional[Path]
    keep_temp: bool
    timeout: int

def create_config_from_args(args) -> ProcessingConfig:
    """Create processing configuration from parsed arguments."""

    selected_periods = None
    if args.periods:
        selected_periods = [p.strip() for p in args.periods.split(',')]

    return ProcessingConfig(
        filing_source=args.filing,
        output_path=args.out,
        single_period=args.one_period,
        selected_periods=selected_periods,
        currency=args.currency,
        scale_millions=not args.scale_none,
        verbose=args.verbose,
        temp_dir=args.temp_dir,
        keep_temp=args.keep_temp,
        timeout=args.timeout
    )
```

## Logging and Output

### Logging Configuration
```python
import logging

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting."""

    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )

    # Suppress verbose output from external libraries
    if not verbose:
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('arelle').setLevel(logging.WARNING)
```

### Progress Reporting
```python
def print_processing_summary(result) -> None:
    """Print summary of processing results."""

    print("\nProcessing Summary:")
    print(f"  Statements processed: {result.statement_count}")
    print(f"  Periods included: {result.period_count}")
    print(f"  Processing time: {result.duration:.1f} seconds")
    print(f"  Output file size: {result.file_size_mb:.1f} MB")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
```

## Error Handling

### Error Types and Messages
```python
class CLIError(Exception):
    """Base exception for CLI-related errors."""
    pass

class FilingNotFoundError(CLIError):
    """Filing source could not be accessed."""
    pass

class ProcessingTimeoutError(CLIError):
    """Processing exceeded timeout limit."""
    pass

class OutputError(CLIError):
    """Error creating output file."""
    pass

def handle_processing_error(error: Exception, verbose: bool) -> str:
    """Convert processing errors to user-friendly messages."""

    if isinstance(error, FileNotFoundError):
        return f"Filing not found: {error}"

    elif isinstance(error, ProcessingTimeoutError):
        return f"Processing timeout exceeded. Try increasing --timeout value."

    elif isinstance(error, OutputError):
        return f"Cannot create output file: {error}"

    else:
        if verbose:
            return f"Processing error: {error}"
        else:
            return "Processing failed. Use --verbose for more details."
```

## Usage Examples

### Basic Usage
```bash
# Simple extraction
python render_viewer_to_xlsx.py \
  --filing "https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm" \
  --out apple-2023.xlsx

# Local file processing
python render_viewer_to_xlsx.py \
  --filing "./filings/company-10k.htm" \
  --out company-financials.xlsx
```

### Advanced Options
```bash
# Single period with custom output location
python render_viewer_to_xlsx.py \
  --filing company-10q.htm \
  --out "/Users/analyst/reports/q3-2024.xlsx" \
  --one-period \
  --verbose

# Specific periods with custom temp directory
python render_viewer_to_xlsx.py \
  --filing filing.zip \
  --out multi-year.xlsx \
  --periods "2024,2023,2022" \
  --temp-dir "./temp" \
  --keep-temp

# Large filing with extended timeout
python render_viewer_to_xlsx.py \
  --filing large-filing.htm \
  --out output.xlsx \
  --timeout 1800 \
  --verbose
```

### Integration Examples

#### Example 1: Downloaded Filing Processing
```bash
# After downloading with download_filings.py
python render_viewer_to_xlsx.py \
  --filing "downloads/AAPL/10-K_2023-09-30/aapl-20230930.htm" \
  --out "apple-2023-financials.xlsx" \
  --one-period
```

#### Example 2: Direct URL Processing (Original)
```bash
# Direct processing from SEC URL
python render_viewer_to_xlsx.py \
  --filing "https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm" \
  --out "apple-direct.xlsx"
```

#### Example 3: Batch Processing After Download
```bash
#!/bin/bash
# Download multiple companies first
python download_filings.py --input-file companies.txt --form 10-K

# Process all downloaded filings
for company_dir in downloads/*/; do
    company=$(basename "$company_dir")
    for filing in "$company_dir"10-K_*/*.htm; do
        if [[ -f "$filing" ]]; then
            echo "Processing $company filing..."
            python render_viewer_to_xlsx.py \
                --filing "$filing" \
                --out "output/${company}-financials.xlsx" \
                --verbose
        fi
    done
done
```

## Integration Points

The CLI interface coordinates with:

1. **Arelle Setup** (03-arelle-setup.md) - Configures Arelle processing parameters
2. **Data Models** (05-data-models.md) - Applies user-specified filtering options
3. **Excel Generation** (07-excel-generation.md) - Controls output formatting
4. **Testing Strategy** (09-testing-strategy.md) - Provides testable interface

## Next Steps

The CLI interface provides the user-facing entry point to the system. It connects to:

1. **Testing Strategy** (09-testing-strategy.md) - Command-line testing scenarios
2. **Edge Cases** (10-edge-cases.md) - Unusual input handling and error conditions
