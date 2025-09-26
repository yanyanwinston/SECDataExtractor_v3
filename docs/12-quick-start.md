# 12 - Quick Start Guide

## Overview

This guide walks you through the complete process of downloading SEC filings and converting them to Excel format using SECDataExtractor_v3.

## Prerequisites

### System Requirements
- Python 3.8 or higher
- 2GB+ RAM for processing large filings
- Internet connection for downloading from SEC EDGAR

### Installation

1. **Clone and setup the project**:
   ```bash
   git clone <repository-url>
   cd SECDataExtractor_v3
   ./setup.sh  # This creates virtual environment and installs dependencies
   ```

2. **Activate the virtual environment**:
   ```bash
   source venv/bin/activate
   ```

3. **Verify installation**:
   ```bash
   python download_filings.py --help
   python render_viewer_to_xlsx.py --help
   ```

## Complete Workflow Example

### Example 1: Single Company (Apple)

Download Apple's latest 10-K filing and convert to Excel:

```bash
# Step 1: Download the filing
python download_filings.py --ticker AAPL --form 10-K --count 1 --verbose

# Expected output:
# 📊 Processing 1 identifier(s)
# 🔍 Searching filings for AAPL...
#    Found 1 filing(s)
# 📥 Downloading 1 filing(s)...
# ✅ Downloaded to downloads/AAPL/10-K_2023-09-30/

# Step 2: Process to Excel
python render_viewer_to_xlsx.py \
  --filing downloads/AAPL/10-K_2023-09-30/aapl-20230930.htm \
  --out apple-financials.xlsx \
  --verbose

# Expected output:
# ✅ Excel file generated: apple-financials.xlsx
```

**Result**: You'll have `apple-financials.xlsx` with three sheets:
- Balance Sheet
- Income Statement
- Cash Flows

### Example 2: Multiple Quarters (Microsoft)

Download Microsoft's last 4 quarterly reports:

```bash
# Download multiple 10-Q filings
python download_filings.py \
  --ticker MSFT \
  --form 10-Q \
  --count 4 \
  --output-dir ./quarterly-data

# Process each filing
for filing in quarterly-data/MSFT/10-Q_*/msft-*.htm; do
    if [[ -f "$filing" ]]; then
        quarter=$(basename $(dirname "$filing"))
        echo "Processing $quarter..."
        python render_viewer_to_xlsx.py \
          --filing "$filing" \
          --out "msft-${quarter}.xlsx"
    fi
done
```

### Example 3: Batch Processing Multiple Companies

Create a ticker file and process multiple companies:

1. **Create `companies.txt`**:
   ```
   AAPL
   MSFT
   GOOGL
   AMZN
   TSLA
   ```

2. **Download all filings**:
   ```bash
   python download_filings.py \
     --input-file companies.txt \
     --form 10-K \
     --count 1 \
     --output-dir ./batch-downloads \
     --max-parallel 5
   ```

3. **Process all to Excel**:
   ```bash
   mkdir -p batch-output

   for company_dir in batch-downloads/*/; do
       company=$(basename "$company_dir")
       echo "Processing $company..."

       filing=$(find "$company_dir" -name "*.htm" | head -1)
       if [[ -f "$filing" ]]; then
           python render_viewer_to_xlsx.py \
             --filing "$filing" \
             --out "batch-output/${company}-financials.xlsx" \
             --one-period
       fi
   done
   ```

## Common Use Cases

### Use Case 1: Latest Annual Reports

Download and process the most recent 10-K for analysis:

```bash
# Quick one-liner for latest 10-K
python download_filings.py --ticker NVDA --form 10-K --count 1 && \
python render_viewer_to_xlsx.py \
  --filing downloads/NVDA/10-K_*/nvda-*.htm \
  --out nvda-annual.xlsx
```

### Use Case 2: Historical Analysis

Download multiple years of 10-K filings for trend analysis:

```bash
# Download 5 years of annual reports
python download_filings.py \
  --ticker AMZN \
  --form 10-K \
  --start-date 2019-01-01 \
  --end-date 2023-12-31 \
  --output-dir ./amzn-history

# Process each year
for filing in amzn-history/AMZN/10-K_*/amzn-*.htm; do
    year=$(basename $(dirname "$filing") | cut -d'_' -f2 | cut -d'-' -f1)
    echo "Processing $year..."
    python render_viewer_to_xlsx.py \
      --filing "$filing" \
      --out "amzn-${year}.xlsx" \
      --one-period
done
```

### Use Case 3: Quarterly Tracking

Set up quarterly monitoring for a portfolio:

```bash
#!/bin/bash
# quarterly-update.sh

PORTFOLIO=("AAPL" "MSFT" "GOOGL" "AMZN" "TSLA" "NVDA" "META")

for ticker in "${PORTFOLIO[@]}"; do
    echo "Updating $ticker quarterly data..."

    # Download latest 10-Q
    python download_filings.py \
      --ticker "$ticker" \
      --form 10-Q \
      --count 1 \
      --output-dir "./quarterly/${ticker}"

    # Process to Excel
    latest_filing=$(find "./quarterly/${ticker}" -name "*.htm" -type f | head -1)
    if [[ -f "$latest_filing" ]]; then
        python render_viewer_to_xlsx.py \
          --filing "$latest_filing" \
          --out "./quarterly-excel/${ticker}-latest-10Q.xlsx"
    fi
done
```

## Advanced Features

### Custom Date Ranges

```bash
# Download specific date range
python download_filings.py \
  --ticker TSLA \
  --form 10-K,10-Q \
  --start-date 2022-01-01 \
  --end-date 2022-12-31 \
  --include-amendments
```

### Performance Optimization

```bash
# High-performance batch download
python download_filings.py \
  --input-file large-company-list.txt \
  --form 10-K \
  --max-parallel 8 \
  --timeout 120 \
  --output-dir ./bulk-downloads
```

### Custom Output Formatting

```bash
# Process with specific formatting options
python render_viewer_to_xlsx.py \
  --filing downloaded-filing.htm \
  --out custom-format.xlsx \
  --periods "2023,2022" \
  --currency USD \
  --label-style standard \
  --dimension-breakdown \
  --save-viewer-json output/custom-viewer.json \
  --one-period

# Need raw decimals for debugging?
python render_viewer_to_xlsx.py \
  --filing downloaded-filing.htm \
  --out custom-format-raw.xlsx \
  --no-scale-hint \
  --scale-none \
  --collapse-dimensions
```

## Troubleshooting

### Common Issues

1. **"No filings found" error**:
   ```bash
   # Check if ticker is correct
   python download_filings.py --ticker AAPL --form 10-K --verbose

   # Try searching by CIK instead
   python download_filings.py --cik 320193 --form 10-K
   ```

2. **Download timeout errors**:
   ```bash
   # Increase timeout and reduce parallelism
   python download_filings.py \
     --ticker AAPL \
     --form 10-K \
     --timeout 300 \
     --max-parallel 2
   ```

3. **Processing errors**:
   ```bash
   # Use verbose mode to see detailed errors
python render_viewer_to_xlsx.py \
  --filing problematic-filing.htm \
  --out output.xlsx \
  --verbose

# Capture the viewer payload for offline inspection
python render_viewer_to_xlsx.py \
  --filing problematic-filing.htm \
  --out output.xlsx \
  --save-viewer-json output/viewer-data.json
   ```

### Debug Mode

Enable detailed logging to troubleshoot issues:

```bash
# Download with full debugging
python download_filings.py \
  --ticker AAPL \
  --form 10-K \
  --verbose

# Processing with debug info
python render_viewer_to_xlsx.py \
  --filing filing.htm \
  --out output.xlsx \
  --verbose \
  --keep-temp  # Keep temporary files for inspection
```

## File Organization

After running the examples above, your directory structure will look like:

```
SECDataExtractor_v3/
├── downloads/                    # Downloaded filings
│   ├── AAPL/
│   │   └── 10-K_2023-09-30/
│   │       ├── aapl-20230930.htm
│   │       └── metadata.json
│   └── MSFT/
│       └── 10-Q_2023-12-31/
├── batch-output/                 # Processed Excel files
│   ├── AAPL-financials.xlsx
│   └── MSFT-financials.xlsx
├── quarterly-excel/              # Quarterly reports
└── temp/                         # Temporary processing files
```

## Integration with Analysis Tools

### Python Analysis

```python
import pandas as pd
import openpyxl

# Read processed Excel file
wb = openpyxl.load_workbook('apple-financials.xlsx')

# Access specific sheet
balance_sheet = wb['Balance Sheet']
income_statement = wb['Income Statement']

# Convert to pandas DataFrame for analysis
df = pd.read_excel('apple-financials.xlsx', sheet_name='Income Statement')
```

### Automated Workflows

Create a script for regular updates:

```bash
#!/bin/bash
# daily-update.sh

# Download latest filings
python download_filings.py --input-file watchlist.txt --form 10-Q --count 1

# Process all new filings
find downloads/ -name "*.htm" -newer last-update.marker | while read filing; do
    company=$(echo "$filing" | cut -d'/' -f2)
    python render_viewer_to_xlsx.py --filing "$filing" --out "latest/${company}.xlsx"
done

# Update marker file
touch last-update.marker
```

## Next Steps

1. **Explore Advanced Features**: Check `docs/10-download-module.md` for detailed API documentation
2. **Customize Processing**: See `docs/06-data-transformation.md` for formatting options
3. **Automate Workflows**: Review `docs/08-cli-interface.md` for scripting examples
4. **Scale Processing**: Read performance optimization guides in the documentation

## Getting Help

- **Documentation**: Complete docs in the `docs/` directory
- **Examples**: More examples in `examples/` directory (if available)
- **Issues**: Report bugs and request features in the project repository

The SECDataExtractor_v3 provides a powerful, automated solution for SEC filing analysis. Start with these basic examples and gradually explore the advanced features to build comprehensive financial analysis workflows.
