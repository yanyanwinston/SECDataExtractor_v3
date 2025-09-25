# 03 - Arelle Setup and Configuration

## Overview

Arelle is an open-source XBRL processor that provides the foundation for iXBRL viewer generation. The iXBRLViewerPlugin extends Arelle to create interactive HTML viewers with embedded JSON data.

## Installation

### Requirements
- Python 3.8 or higher
- pip package manager
- Internet connection (for downloading packages)

### Install Arelle
```bash
pip install arelle-release
```

### Install iXBRL Viewer Plugin
```bash
pip install ixbrl-viewer
```

### Verify Installation
```bash
python -m arelle.CntlrCmdLine --help
```

Expected output should include plugin loading information.

## iXBRLViewerPlugin Usage

### Basic Command Structure
```bash
python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file <FILING_PATH_OR_URL> \
  --save-viewer <OUTPUT_DIR>/ixbrl-viewer.htm
```

### Command Parameters

#### Required Parameters
- `--plugins iXBRLViewerPlugin`: Loads the iXBRL viewer generation plugin
- `--file <PATH_OR_URL>`: Source filing location
- `--save-viewer <OUTPUT_PATH>`: Where to save the generated viewer HTML

#### Optional Parameters
- `--logLevel INFO`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `--logFile <PATH>`: Write logs to file instead of console
- `--internetConnectivity offline`: Disable internet lookups for faster processing

## Input File Types

### SEC EDGAR URLs
```bash
python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file "https://www.sec.gov/Archives/edgar/data/320193/000032019324000007/aapl-20231230.htm" \
  --save-viewer ./output/apple-2023-viewer.htm
```

### Local iXBRL Files
```bash
python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file "./filings/company-10k.htm" \
  --save-viewer ./output/company-viewer.htm
```

### ZIP Archives
```bash
python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file "./filings/filing-documents.zip" \
  --save-viewer ./output/filing-viewer.htm
```

## Output Structure

### Generated Files
The `--save-viewer` command creates:

#### ixbrl-viewer.htm
- **Self-contained HTML file**
- **Embedded CSS and JavaScript**
- **JSON data in script tag**
- **Interactive viewer interface**

### File Structure Analysis
```html
<!DOCTYPE html>
<html>
<head>
    <!-- CSS styles -->
</head>
<body>
    <!-- HTML structure -->

    <script type="text/javascript">
        // This contains the viewer data we need to extract
        window.ixv = {
            "statements": [...],
            "facts": {...},
            "periods": [...],
            // ... other viewer data
        };
    </script>

    <!-- JavaScript for viewer functionality -->
</body>
</html>
```

## Processing Performance

### Typical Processing Times
- **Small filings (< 1MB)**: 10-30 seconds
- **Medium filings (1-5MB)**: 30-60 seconds
- **Large filings (> 5MB)**: 1-3 minutes

### Memory Requirements
- **Minimum**: 512MB RAM
- **Recommended**: 2GB RAM for large filings
- **Peak usage**: 3-4x the input file size

## Error Handling

### Common Errors and Solutions

#### Plugin Not Found
```
Error: Plugin 'iXBRLViewerPlugin' not found
```
**Solution**: Install ixbrl-viewer package
```bash
pip install ixbrl-viewer
```

#### File Access Errors
```
Error: Unable to load file
```
**Solutions**:
- Verify file path exists
- Check file permissions
- Validate URL accessibility
- Ensure internet connectivity for remote files

#### Memory Errors
```
Error: Memory allocation failed
```
**Solutions**:
- Process smaller filings first
- Increase available system memory
- Close other applications
- Use streaming processing if available

#### Network Timeouts
```
Error: Connection timeout
```
**Solutions**:
- Add `--internetConnectivity offline` for local processing
- Check network connectivity
- Try during off-peak hours
- Use local file if available

## Best Practices

### File Organization
```
project/
├── input/          # Source filings
├── output/         # Generated viewers
├── temp/           # Temporary processing files
└── logs/           # Processing logs
```

### Command Wrapper Script
Create a reusable script for consistent processing:

```bash
#!/bin/bash
# process_filing.sh

FILING_PATH=$1
OUTPUT_NAME=$2
OUTPUT_DIR="./output"
LOG_DIR="./logs"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file "$FILING_PATH" \
  --save-viewer "$OUTPUT_DIR/$OUTPUT_NAME.htm" \
  --logLevel INFO \
  --logFile "$LOG_DIR/$OUTPUT_NAME.log" \
  --internetConnectivity offline
```

Usage:
```bash
./process_filing.sh "company-10k.htm" "company-viewer"
```

### Performance Optimization
1. **Use local files** when possible to avoid network delays
2. **Add logging** to track processing progress
3. **Set offline mode** if internet lookups aren't needed
4. **Process in batches** for multiple filings
5. **Clean up temporary files** after processing

## Troubleshooting

### Debug Mode
For detailed processing information:
```bash
python -m arelle.CntlrCmdLine \
  --plugins iXBRLViewerPlugin \
  --file <FILING> \
  --save-viewer <OUTPUT> \
  --logLevel DEBUG \
  --logFile debug.log
```

### Plugin Verification
List all available plugins:
```bash
python -m arelle.CntlrCmdLine --plugins-list
```

### Version Information
Check Arelle and plugin versions:
```bash
python -m arelle.CntlrCmdLine --about
```

## Integration with SECDataExtractor

### Process Flow
1. **Input validation**: Verify filing source accessibility
2. **Temporary directory**: Create clean workspace
3. **Arelle execution**: Run viewer generation
4. **Output verification**: Confirm successful HTML creation
5. **JSON extraction**: Parse generated HTML for viewer data
6. **Cleanup**: Remove temporary files