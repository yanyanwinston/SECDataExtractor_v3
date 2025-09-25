# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SECDataExtractor_v3 is a specialized tool for extracting SEC financial statements and converting them to Excel format while preserving the original presentation structure. The tool leverages Arelle's iXBRLViewerPlugin to maintain exact visual fidelity with the SEC filings.

### Core Objective
Generate Excel financial statements that **match the filer's HTML/iXBRL presentation** (row order, section headers, labels) by using Arelle's iXBRLViewerPlugin to produce viewer JSON and rendering it to XLSX with consistent number formatting.

## Architecture Overview

The system follows a linear processing pipeline:
```
iXBRL Filing → Arelle Processing → Viewer JSON → Data Models → Excel Output
```

### Key Components
1. **Input Handler** - Accepts URLs, local files, and ZIP archives
2. **Arelle Processor** - Generates iXBRL viewer HTML with embedded JSON
3. **JSON Extractor** - Parses HTML and extracts viewer data
4. **Data Parser** - Transforms JSON into structured data models
5. **Value Formatter** - Applies display formatting rules
6. **Excel Generator** - Creates formatted XLSX files with openpyxl

## Technology Stack

### Primary Language
- **Python** - Core implementation language for all components

### Key Dependencies
- **arelle-release** - SEC filing processing and XBRL handling
- **ixbrl-viewer** - Generates viewer HTML with embedded JSON data
- **openpyxl** - Excel file generation and formatting
- **argparse** - Command-line interface implementation

### Processing Tools
- **Arelle CntlrCmdLine** with iXBRLViewerPlugin for viewer generation
- **HTML/JSON parsing** for data extraction
- **Custom formatters** for financial number presentation

## Project Structure

### Documentation
- `docs/` - Comprehensive technical documentation (9 files covering all aspects)
- `SPEC.md` - Detailed project specification and requirements
- `CLAUDE.md` - This guidance file

### Key Documentation Files
- `01-project-overview.md` - Problem statement and solution approach
- `02-system-architecture.md` - Processing pipeline and component design
- `03-arelle-setup.md` - Arelle installation and configuration
- `04-json-extraction.md` - Viewer data parsing techniques
- `05-data-models.md` - Data structure definitions
- `06-data-transformation.md` - Value formatting and processing rules
- `07-excel-generation.md` - XLSX output generation
- `08-cli-interface.md` - Command-line interface specification
- `09-testing-strategy.md` - Testing approach and scenarios

## Core Features

### Input Processing
- **SEC EDGAR URLs** - Direct filing processing from SEC website
- **Local iXBRL files** - Single HTML file processing
- **ZIP archives** - SEC filing document bundles
- **Format validation** - Ensure proper iXBRL structure

### Output Generation
- **Multi-sheet Excel workbooks** - Balance Sheet, Income Statement, Cash Flows
- **Visual fidelity preservation** - Exact match to iXBRL viewer presentation
- **Proper formatting** - Currency scaling, EPS precision, share counts
- **Professional styling** - Bold headers, indentation, borders

### Data Processing
- **Currency display** - USD in millions with thousands separators
- **Negative values** - Parentheses format (150.5) instead of -150.5
- **EPS values** - 2 decimal places precision
- **Share counts** - Millions, no decimal places
- **Missing values** - Em dash `—`

## Command-Line Interface

### Main Script
`render_viewer_to_xlsx.py` - Primary entry point

### Basic Usage
```bash
python render_viewer_to_xlsx.py --filing <SOURCE> --out <OUTPUT_FILE>
```

### Key Options
- `--filing` - iXBRL filing source (URL/local file/ZIP)
- `--out` - Output Excel file path
- `--one-period` - Single-period output
- `--periods` - Specific period selection
- `--currency` - Currency display preference
- `--verbose` - Detailed logging
- `--timeout` - Arelle processing timeout

## Development Guidelines

### Code Organization
- Follow the linear processing pipeline architecture
- Implement proper error handling for each processing stage
- Use defensive programming for JSON parsing (viewer format may vary)
- Maintain separation between data models and presentation logic

### Testing Requirements
- **Visual fidelity tests** - Row labels and order match iXBRL viewer
- **Data accuracy tests** - Values match after display scaling
- **Format validation** - Currency, EPS, and share formatting correctness
- **Edge case handling** - Missing data, non-USD currency, large filings

### Performance Considerations
- **Arelle processing** - Typically 30-60 seconds for large filings
- **Memory management** - Stream processing for large JSON files
- **Temporary file cleanup** - Automatic cleanup unless --keep-temp specified

## Current Implementation Status

Based on the documentation review, the project has:
- ✅ Complete technical specification (SPEC.md)
- ✅ Comprehensive documentation suite (9 detailed files)
- ❌ No implementation code yet
- ❌ No package configuration (requirements.txt, setup.py)
- ❌ No test files

## Development Priorities

1. **Core Implementation** - Build the main processing pipeline
2. **CLI Interface** - Implement render_viewer_to_xlsx.py
3. **Data Models** - Create Statement, Row, Period, Cell classes
4. **Value Formatting** - Implement currency and number formatting rules
5. **Excel Generation** - Build openpyxl-based output generation
6. **Testing Suite** - Implement comprehensive test coverage

## Development Environment

### Virtual Environment Setup

This project uses a Python virtual environment to isolate dependencies and protect your system Python installation.

#### Creating and Using the Virtual Environment

```bash
# Create virtual environment (already done)
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

#### For Claude Code Usage

**IMPORTANT**: When running any Python commands in this project, always ensure the virtual environment is activated first:

1. **Always activate first**: `source venv/bin/activate`
2. **Then run Python commands**: `python download_filings.py --ticker AAPL --form 10-K`
3. **All pip installs must be done within the activated venv**
4. **When done, deactivate**: `deactivate`

#### Quick Setup Script

Use the provided setup script for initial environment setup:
```bash
chmod +x setup.sh
./setup.sh
```

### Dependencies Management

- **requirements.txt** - Contains all project dependencies with versions
- **Virtual environment isolation** - Prevents conflicts with system Python packages
- **Reproducible installs** - Exact dependency versions for consistent behavior

## Non-Goals

- **Data validation** - Don't verify mathematical accuracy of reported values
- **Cell merging** - Keep simple cell structure for easy editing
- **Total recalculation** - Display reported values as-is, don't recompute
- **Custom styling** - Beyond basic formatting for readability