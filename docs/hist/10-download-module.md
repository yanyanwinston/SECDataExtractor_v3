# 10 - SEC Filing Download Module

## Overview

The SEC Filing Download Module is a comprehensive system for downloading SEC filings (10-K, 10-Q) directly from the EDGAR database. This module serves as the data acquisition layer for the SECDataExtractor_v3 pipeline, providing reliable, SEC-compliant access to financial filings.

## Architecture

### Module Structure
```
src/sec_downloader/
├── __init__.py              # Module exports and version info
├── models.py                # Data models (Filing, Company, Config)
├── utils.py                 # Utility functions and rate limiter
├── edgar_client.py          # Low-level EDGAR API client
├── filing_search.py         # High-level search functionality
└── filing_download.py       # Download engine with progress tracking

download_filings.py          # Command-line interface
```

### Component Interaction
```
CLI Interface (download_filings.py)
    ↓
FilingSearch → EdgarClient ← FilingDownload
    ↓              ↓              ↓
SearchFilters   Company      DownloadResult
Filing          Filing       DownloadConfig
```

## Core Components

### 1. EdgarClient (`edgar_client.py`)

**Purpose**: Low-level SEC EDGAR API communication

**Key Features**:
- **SEC Compliance**: Proper User-Agent headers and rate limiting (8 req/sec)
- **Robust HTTP**: Automatic retries with exponential backoff
- **Company Lookup**: Search by ticker symbol or CIK
- **Filing Retrieval**: Get filing lists with metadata
- **Document Download**: Download individual filing documents

**Example Usage**:
```python
from sec_downloader import EdgarClient

client = EdgarClient()

# Look up Apple by ticker
company = client.lookup_company_by_ticker("AAPL")
print(f"Found: {company.name} (CIK: {company.cik})")

# Get recent filings
filings = client.search_filings(
    cik=company.cik,
    form_types=["10-K"],
    max_results=5
)
```

### 2. FilingSearch (`filing_search.py`)

**Purpose**: High-level filing search interface

**Key Features**:
- **Smart Detection**: Auto-detect ticker vs CIK input
- **Advanced Filtering**: Date ranges, form types, amendments
- **Convenience Methods**: Latest filings, annual/quarterly reports
- **Batch Operations**: Search multiple companies

**Search Filters**:
- `form_types`: List of forms to search (10-K, 10-Q, etc.)
- `start_date`/`end_date`: Date range filtering
- `include_amendments`: Include 10-K/A, 10-Q/A filings
- `max_results`: Limit number of results

**Example Usage**:
```python
from sec_downloader import FilingSearch
from sec_downloader.models import SearchFilters
from datetime import datetime

search = FilingSearch()

# Search with filters
filters = SearchFilters(
    form_types=["10-K"],
    start_date=datetime(2020, 1, 1),
    end_date=datetime(2023, 12, 31),
    max_results=10
)

filings = search.search_by_ticker("AAPL", filters)
print(f"Found {len(filings)} Apple 10-K filings")

# Get latest quarterly report
latest_q = search.get_latest_filing("MSFT", "10-Q")
if latest_q:
    print(f"Latest 10-Q: {latest_q.display_name}")
```

### 3. FilingDownload (`filing_download.py`)

**Purpose**: Multi-threaded filing download engine

**Key Features**:
- **Parallel Downloads**: Configurable concurrency (default: 3)
- **Progress Tracking**: Visual progress bars with tqdm
- **Retry Logic**: Automatic retry with exponential backoff
- **File Organization**: Structured output directories
- **Metadata Preservation**: JSON metadata for each filing
- **Validation**: File integrity checking

**Download Configuration**:
```python
from sec_downloader.models import DownloadConfig
from pathlib import Path

config = DownloadConfig(
    output_dir=Path("./downloads"),
    create_subdirs=True,           # Create ticker/filing subdirectories
    include_exhibits=False,        # Skip exhibit files
    max_parallel=3,                # Concurrent downloads
    retry_attempts=3,              # Retry failed downloads
    timeout_seconds=30,            # Per-file timeout
    verify_downloads=True          # Validate downloaded files
)
```

**Example Usage**:
```python
from sec_downloader import FilingDownload
from sec_downloader.models import DownloadConfig

downloader = FilingDownload()
config = DownloadConfig(output_dir=Path("./filings"))

# Download single filing
result = downloader.download_filing(filing, config)
if result.success:
    print(f"Downloaded to: {result.local_path}")

# Batch download with progress
results = downloader.download_filings(filings, config)
summary = downloader.get_download_summary(results)
print(f"Success rate: {summary['success_rate']:.1f}%")
```

## Data Models

### Filing
```python
@dataclass
class Filing:
    cik: str
    accession_number: str
    form_type: str
    filing_date: datetime
    report_date: Optional[datetime]
    ticker: Optional[str]
    company_name: Optional[str]
    document_urls: Dict[str, str]
    primary_document: Optional[str]
    filing_url: Optional[str]
```

### Company
```python
@dataclass
class Company:
    cik: str
    ticker: Optional[str]
    name: Optional[str]
    exchange: Optional[str]
```

### DownloadResult
```python
@dataclass
class DownloadResult:
    filing: Filing
    success: bool
    local_path: Optional[Path]
    error: Optional[str]
    downloaded_files: List[str]
    metadata_path: Optional[Path]
```

## Command-Line Interface

### Basic Usage
```bash
# Download latest 10-K for Tesla
python download_filings.py --ticker TSLA --form 10-K

# Download multiple quarters for Microsoft
python download_filings.py --ticker MSFT --form 10-Q --count 4

# Download by date range
python download_filings.py --ticker GOOGL --form 10-K \
  --start-date 2020-01-01 --end-date 2023-12-31
```

### Advanced Options
```bash
# Batch download from file
python download_filings.py --input-file tickers.txt \
  --form 10-K,10-Q --output-dir ./filings/

# Include amendments and exhibits
python download_filings.py --ticker AMZN --form 10-K \
  --include-amendments --include-exhibits

# Custom parallel settings
python download_filings.py --ticker TSLA --form 10-Q \
  --max-parallel 5 --timeout 60 --retries 5
```

### Input File Format
```
# tickers.txt - One ticker per line, comments supported
AAPL
MSFT
GOOGL
AMZN
# TSLA  # Commented out
```

## Output Structure

### Directory Organization
```
downloads/
├── AAPL/
│   ├── 10-K_2023-09-30/
│   │   ├── aapl-20230930.htm      # Primary iXBRL document
│   │   ├── metadata.json          # Filing metadata
│   │   └── exhibits/              # Exhibit files (if requested)
│   │       ├── ex-21_1.htm
│   │       └── ex-31_1.htm
│   └── 10-Q_2023-12-31/
│       └── ...
└── MSFT/
    └── ...
```

### Metadata Format
```json
{
  "filing_info": {
    "cik": "0000320193",
    "accession_number": "0000320193-23-000077",
    "form_type": "10-K",
    "filing_date": "2023-11-03T00:00:00",
    "report_date": "2023-09-30T00:00:00",
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "primary_document": "aapl-20230930.htm"
  },
  "documents": {
    "aapl-20230930.htm": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
  },
  "download_info": {
    "downloaded_at": "2024-01-15T10:30:00",
    "edgar_url": "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000077"
  }
}
```

## Integration with Main Pipeline

### Sequential Processing
```bash
# Step 1: Download filing
python download_filings.py --ticker AAPL --form 10-K --count 1

# Step 2: Process with main extraction tool
python render_viewer_to_xlsx.py \
  --filing downloads/AAPL/10-K_2023-09-30/aapl-20230930.htm \
  --out financials.xlsx
```

### Programmatic Integration
```python
from sec_downloader import FilingSearch, FilingDownload
from sec_downloader.models import SearchFilters, DownloadConfig

# Search and download
search = FilingSearch()
downloader = FilingDownload()

# Get latest 10-K
latest_10k = search.get_latest_filing("AAPL", "10-K")
if latest_10k:
    # Download
    config = DownloadConfig(output_dir=Path("./temp"))
    result = downloader.download_filing(latest_10k, config)

    if result.success and result.primary_file_path:
        # Process with main pipeline
        primary_file = result.primary_file_path
        # ... call render_viewer_to_xlsx.py logic
```

## Error Handling

### Common Error Scenarios

1. **Network Issues**
   - Automatic retry with exponential backoff
   - Configurable timeout and retry attempts
   - Rate limiting to avoid SEC blocking

2. **Invalid Identifiers**
   - Ticker not found: Returns empty results
   - Invalid CIK: Raises `FilingSearchError`
   - Validation before processing

3. **Download Failures**
   - Individual file failures don't stop batch processing
   - Detailed error reporting in results
   - Partial download recovery

4. **File System Issues**
   - Directory creation with proper permissions
   - Disk space validation
   - Safe filename generation

### Error Messages
```python
# Search errors
try:
    filings = search.search_by_ticker("INVALID")
except FilingSearchError as e:
    print(f"Search failed: {e}")

# Download errors
results = downloader.download_filings(filings, config)
for result in results:
    if not result.success:
        print(f"Failed to download {result.filing.display_name}: {result.error}")
```

## Performance Considerations

### Rate Limiting
- **SEC Compliance**: Maximum 10 requests per second
- **Default Setting**: 8 requests per second for safety margin
- **Configurable**: Adjust based on your needs

### Parallel Downloads
- **Default Concurrency**: 3 parallel downloads
- **Recommended Range**: 1-5 concurrent downloads
- **Memory Usage**: ~50MB per concurrent download

### Caching Strategy
- **No HTTP Caching**: Fresh data on every request
- **Metadata Caching**: Save filing lists to avoid re-searching
- **File Verification**: Check existing files before re-downloading

### Large Filings
- **Streaming Downloads**: Handle files >100MB efficiently
- **Progress Tracking**: Real-time download progress
- **Timeout Management**: Configurable per-file timeouts

## SEC Compliance

### Required Headers
```python
headers = {
    'User-Agent': 'SECDataExtractor v3.0 (contact@company.com)',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}
```

### Rate Limiting
- **Maximum**: 10 requests per second
- **Implementation**: Token bucket algorithm
- **Buffer**: 0.1 second additional delay for safety

### Best Practices
1. **Identify Yourself**: Always use a descriptive User-Agent
2. **Respect Limits**: Don't exceed rate limits
3. **Handle Errors**: Implement proper retry logic
4. **Cache Wisely**: Avoid unnecessary repeat requests

## Troubleshooting

### Common Issues

1. **"No filings found"**
   - Check ticker symbol spelling
   - Verify date range includes filing dates
   - Try searching by CIK instead

2. **Download timeouts**
   - Increase `--timeout` parameter
   - Reduce `--max-parallel` setting
   - Check network connectivity

3. **Rate limit errors**
   - Module handles this automatically
   - If persistent, reduce requests per second

4. **Permission errors**
   - Check write permissions on output directory
   - Ensure sufficient disk space

### Debug Mode
```bash
# Enable verbose logging
python download_filings.py --ticker AAPL --form 10-K --verbose

# Keep temporary files for inspection
python download_filings.py --ticker AAPL --form 10-K --keep-temp
```

### Log Analysis
```python
import logging

# Configure detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('sec_downloader')

# Monitor specific components
logging.getLogger('sec_downloader.edgar_client').setLevel(logging.DEBUG)
logging.getLogger('sec_downloader.filing_download').setLevel(logging.INFO)
```

## Future Enhancements

### Planned Features
1. **Database Storage**: Optional SQLite backend for filing metadata
2. **Incremental Updates**: Download only new filings since last run
3. **XBRL Processing**: Direct XBRL parsing without Arelle dependency
4. **Cloud Storage**: S3/GCS integration for large-scale processing
5. **API Server**: REST API for programmatic access

### Extension Points
1. **Custom Parsers**: Plugin system for additional document types
2. **Storage Backends**: Abstract storage interface
3. **Notification System**: Webhooks for download completion
4. **Monitoring**: Metrics collection and reporting

## Examples and Tutorials

See the `examples/` directory for:
- Basic usage examples
- Batch processing scripts
- Integration patterns
- Performance optimization guides

## API Reference

For detailed API documentation, see:
- `docs/11-api-reference.md` - Complete API documentation
- `docs/12-examples.md` - Usage examples and recipes
- Source code docstrings for inline documentation