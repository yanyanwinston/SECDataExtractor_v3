# 02 - System Architecture

## Overview

The SECDataExtractor_v3 follows a linear processing pipeline that transforms iXBRL filings into Excel format while preserving the original presentation structure.

## Processing Pipeline

```
iXBRL Filing → Arelle Processing → Viewer JSON → Data Models → Excel Output
     ↓              ↓                 ↓           ↓            ↓
  SEC EDGAR     iXBRLViewerPlugin  Extraction   Transform    XLSX File
```

## Component Architecture

### 1. Input Handler
**Purpose**: Accept and validate filing sources
- **Inputs**: URLs, local files, ZIP archives
- **Validation**: File format, accessibility, SEC filing structure
- **Output**: Standardized filing path for Arelle processing

### 2. Arelle Processor
**Purpose**: Generate iXBRL viewer HTML with embedded JSON
- **Tool**: Arelle CmdLine with iXBRLViewerPlugin
- **Process**:
  ```bash
  python -m arelle.CntlrCmdLine \
    --plugins iXBRLViewerPlugin \
    --file <FILING> \
    --save-viewer <OUTPUT>/ixbrl-viewer.htm
  ```
- **Output**: HTML file with embedded viewer JSON

### 3. JSON Extractor
**Purpose**: Parse HTML and extract viewer data
- **Input**: Generated ixbrl-viewer.htm
- **Process**: Locate and parse JavaScript object containing viewer data
- **Output**: Clean JSON object with statement tables

### 4. Data Parser
**Purpose**: Transform viewer JSON into structured data models
- **Input**: Viewer JSON
- **Process**: Create Statement, Row, Period, Cell objects
- **Output**: In-memory data structures

### 5. Value Formatter
**Purpose**: Apply display formatting rules
- **Input**: Raw cell values with units/decimals
- **Process**: Currency scaling, number formatting, sign handling
- **Output**: Display-ready values

### 6. Excel Generator
**Purpose**: Create formatted XLSX file
- **Input**: Formatted data models
- **Process**: Create sheets, apply styling, write data
- **Output**: financials_aligned.xlsx

## Data Flow

### Step 1: Filing Input
```
Input Sources:
├── SEC EDGAR URL (https://sec.gov/...)
├── Local iXBRL file (.htm, .html)
└── SEC filing ZIP archive
```

### Step 2: Arelle Processing
```
iXBRL File
    ↓
Arelle CntlrCmdLine + iXBRLViewerPlugin
    ↓
ixbrl-viewer.htm (contains embedded JSON)
```

### Step 3: JSON Extraction
```
ixbrl-viewer.htm
    ↓
HTML Parsing (locate script tag)
    ↓
Raw JSON Object (viewer data)
```

### Step 4: Data Structure Creation
```
Viewer JSON
    ↓
Parse Tables & Metadata
    ↓
Statement Objects:
├── Balance Sheet (periods, rows, cells)
├── Income Statement (periods, rows, cells)
└── Cash Flows (periods, rows, cells)
```

### Step 5: Value Processing
```
Raw Cell Values
    ↓
Apply Formatting Rules:
├── USD → millions (÷ 1,000,000)
├── EPS → 2 decimals
├── Shares → millions, 0 decimals
└── Negatives → parentheses
    ↓
Display Values
```

### Step 6: Excel Generation
```
Formatted Data
    ↓
openpyxl Processing:
├── Create sheets
├── Apply styling (bold, indent, borders)
├── Write headers & data
└── Save workbook
    ↓
financials_aligned.xlsx
```

## Key Interfaces

### IFilingSource
```python
class IFilingSource:
    def validate() -> bool
    def get_path() -> str
    def cleanup() -> None
```

### IViewerData
```python
class IViewerData:
    def get_statements() -> List[Statement]
    def get_periods() -> List[Period]
    def get_metadata() -> Dict
```

### IFormatter
```python
class IFormatter:
    def format_currency(value, unit) -> str
    def format_shares(value) -> str
    def format_eps(value) -> str
```

### IExcelWriter
```python
class IExcelWriter:
    def create_workbook() -> Workbook
    def add_statement_sheet(statement) -> None
    def apply_styling() -> None
    def save(filepath) -> None
```

## Error Handling Strategy

### Input Validation
- File accessibility checks
- Format validation (iXBRL structure)
- Network connectivity for URLs

### Processing Errors
- Arelle execution failures
- JSON parsing errors
- Missing required statement data

### Output Generation
- Excel file creation failures
- Insufficient disk space
- Permission errors

## Performance Considerations

### Memory Management
- Stream processing for large JSON files
- Lazy loading of statement data
- Cleanup of temporary files

### Processing Time
- Arelle processing typically 30-60 seconds for large filings
- JSON parsing < 5 seconds
- Excel generation < 10 seconds

## Extensibility Points

### Custom Formatters
- Support additional currencies
- Custom number formatting rules
- Industry-specific formatting

### Additional Outputs
- CSV export capability
- PDF generation
- Database storage

### Enhanced Validation
- Mathematical validation of totals
- Cross-statement consistency checks
- Historical comparison features