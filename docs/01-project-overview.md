# 01 - Project Overview

## Goal

Generate Excel financial statements that **match the filer's HTML/iXBRL presentation** (row order, section headers, labels) by using **Arelle's iXBRLViewerPlugin** to produce the viewer JSON and then rendering that JSON to XLSX with our own number formatting.

## Problem Statement

Traditional SEC data extraction often results in Excel files that don't match the visual presentation of the original financial statements. This makes it difficult for analysts and users to cross-reference between the Excel output and the original filing documents.

## Solution Approach

The SECDataExtractor_v3 provides a complete end-to-end solution:

### Data Acquisition
- **SEC Filing Downloader** - Automated download of 10-K and 10-Q filings from EDGAR
- **Bulk Processing** - Download multiple companies and periods efficiently
- **SEC Compliance** - Built-in rate limiting and proper API usage

### Data Processing
Instead of parsing raw XBRL data directly, we leverage Arelle's iXBRLViewerPlugin to:

1. **Preserve original presentation** - Use the same rendering logic that creates the HTML viewer
2. **Maintain exact order** - Keep rows and sections in their original sequence
3. **Apply proper formatting** - Implement consistent number formatting suitable for Excel analysis

### Complete Workflow
```
Ticker Symbol → Download Module → Local iXBRL Files → Processing Pipeline → Excel Output
     ↓               ↓                 ↓                    ↓               ↓
   "AAPL"      SEC EDGAR API     downloads/AAPL/      Arelle Viewer    financials.xlsx
              Filing Search      10-K_2023.htm       JSON Extraction   (3 sheets)
```

## Target Inputs

### Filing Sources

The system supports both automated download and direct file processing:

#### Automated Download (Recommended)
- **Ticker symbols**: Download by stock ticker (e.g., AAPL, MSFT, GOOGL)
- **CIK numbers**: Download by Central Index Key
- **Batch files**: Process multiple companies from text file
- **Date filtering**: Specify date ranges for filing searches

#### Direct File Processing
- **URL**: Direct link to an iXBRL filing on SEC EDGAR
- **Local path**: Downloaded iXBRL filing (single HTML file)
- **ZIP archive**: SEC "filing-documents" zip containing multiple files

### Target Financial Statements
- **Balance Sheet (BS)** - Statement of Financial Position
- **Income Statement (IS)** - Statement of Operations/Comprehensive Income
- **Cash Flows (CF)** - Statement of Cash Flows

### Display Configuration
- **Currency display**: USD in millions with thousands separators
- **Negative values**: Parentheses format (e.g., (150.5) instead of -150.5)
- **EPS values**: 2 decimal places precision
- **Share counts**: Millions, no decimal places
- **Missing/unavailable**: Em dash `—`

## Expected Outputs

### Primary Output
`financials_aligned.xlsx` - Multi-sheet Excel workbook with:

- **One sheet per statement** (Balance Sheet, Income Statement, Cash Flows)
- **Multi-period by default** - All available periods shown
- **Single-period option** - `--one-period` flag for latest period only

### Sheet Structure
- **Rows**: Exactly match the iXBRL viewer's table presentation
  - Include abstract/section headers
  - Maintain original ordering
  - Preserve indentation hierarchy
- **Columns**: Correspond to periods shown in viewer (e.g., 2024, 2023, 2022)
- **Styling**:
  - Bold section headers (abstract rows)
  - Indentation based on tree depth
  - Thin bottom border under total rows

## Success Criteria

1. **Visual Fidelity**: Excel output matches iXBRL viewer presentation exactly
2. **Data Accuracy**: All numerical values correctly extracted and formatted
3. **Usability**: Analysts can easily cross-reference between Excel and original filing
4. **Automation**: Minimal manual intervention required for processing

## Non-Goals

- **Data validation**: We don't verify mathematical accuracy of reported values
- **Cell merging**: Keep simple cell structure for easy editing
- **Total recalculation**: Display reported values as-is, don't recompute
- **Custom styling**: Beyond basic formatting for readability