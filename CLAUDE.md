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
- `05-data-models.md` - Data structure definitions (updated for presentation-based approach)
- `06-data-transformation.md` - Value formatting and processing rules
- `07-excel-generation.md` - XLSX output generation
- `08-cli-interface.md` - Command-line interface specification
- `09-testing-strategy.md` - Testing approach and scenarios
- `10-download-module.md` - SEC filing download module documentation
- `11-refactor-spec-v3.1.md` - **CRITICAL: Complete refactor specification for presentation-based approach**
- `12-quick-start.md` - Quick start guide

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

## Development Philosophy: MVP First

### IMPORTANT: Avoid Overengineering
- **Build minimal working solutions first** - Don't create complex architectures upfront
- **One feature at a time** - Implement the simplest version that works
- **Avoid premature optimization** - Make it work, then make it better
- **No unnecessary abstractions** - Use simple functions before creating classes
- **Prefer simple over clever** - Code should be readable and straightforward

### MVP Development Approach
1. **Start with basic functionality** - Get core feature working first
2. **Use existing tools** - Leverage libraries instead of building from scratch
3. **Simple error handling** - Basic try/catch, not complex error hierarchies
4. **Direct solutions** - Don't create layers of abstraction unnecessarily
5. **Hardcode first, parameterize later** - Make it work with simple values first

### Code Organization (Keep Simple)
- **Single-file solutions when possible** - Don't split unnecessarily
- **Basic error handling** - Simple try/catch blocks, not complex error systems
- **Straightforward functions** - Do one thing, return result, handle errors
- **Minimal configuration** - Hardcode reasonable defaults, add options later

### When to Add Complexity
Only add complexity when you have a **concrete, immediate need**:
- ✅ User asks for specific feature
- ✅ Current approach is actually failing
- ✅ Real performance problem with measurable impact
- ❌ "Future flexibility" or "better architecture"
- ❌ "Best practices" without specific benefit
- ❌ "What if" scenarios

## Current Implementation Status

### Completed (MVP v3.0)
- ✅ Download module - Complete SEC filing downloader
- ✅ Virtual environment setup and dependencies
- ✅ Main processing pipeline (render_viewer_to_xlsx.py) - **WORKING**
- ✅ Arelle integration with iXBRLViewerPlugin
- ✅ JSON extraction from viewer HTML
- ✅ Excel generation with formatting
- ✅ End-to-end pipeline tested with Apple 10-K

### Current Issue (Identified September 2024)
**The current implementation produces incorrect output** because it:
- ❌ Ignores presentation linkbase structure from Arelle
- ❌ Groups facts by concept name patterns instead of using presentation tree
- ❌ Uses wrong labels (concept names vs preferred labels)
- ❌ Loses intended row ordering and hierarchy
- ❌ Produces output that doesn't match the iXBRL viewer

### Solution: Refactor to v3.1 (Presentation-Based)
**See `docs/11-refactor-spec-v3.1.md` for detailed plan**

The refactor will:
- ✅ Parse presentation linkbase from Arelle's viewer JSON
- ✅ Follow presentation tree for correct row order and hierarchy
- ✅ Use preferred labels from presentation context
- ✅ Match facts to presentation cells properly
- ✅ Generate Excel that exactly matches iXBRL viewer

### Key Insight
**Arelle already provides 80% of what we need** - the iXBRLViewerPlugin creates complete presentation structure in the viewer JSON. We just need to parse and use it correctly instead of reconstructing from raw facts.

## Development Priorities (v3.1 Refactor)

1. **Phase 1**: Document and understand viewer JSON structure
2. **Phase 2**: Create presentation-based data models
3. **Phase 3**: Implement presentation parser and fact matcher
4. **Phase 4**: Integrate with existing pipeline (feature flag)
5. **Phase 5**: Test and validate against iXBRL viewer output
6. **Phase 6**: Migrate from fact-based to presentation-based approach

## Refactor Architecture (v3.1)

### Current Problem: Fact-Based Reconstruction
```
Facts → Group by Concept → Guess Structure → Excel
❌ Wrong row order, wrong labels, missing hierarchy
```

### New Solution: Presentation-Based Rendering
```
Viewer JSON → Parse Presentation Tree → Match Facts to Tree → Excel
✅ Exact match to iXBRL viewer structure
```

### Key New Components

1. **PresentationParser** (`src/processor/presentation_parser.py`)
   - Extracts presentation relationships from viewer JSON
   - Builds hierarchical tree structure for each statement
   - Preserves order, depth, and preferred labels

2. **FactMatcher** (`src/processor/fact_matcher.py`)
   - Matches facts to presentation nodes by concept and period
   - Handles missing data gracefully
   - Applies proper formatting from ValueFormatter

3. **New Data Models** (`src/processor/presentation_models.py`)
   - PresentationNode - represents tree structure
   - PresentationStatement - complete statement with tree
   - StatementTable - ready-to-render with facts matched

### Migration Strategy
- Feature flag for backwards compatibility
- Parallel implementation during transition
- Comprehensive testing against iXBRL viewer
- Gradual rollout with fallback to legacy approach

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