# Architecture & Pipeline

This document describes how SECDataExtractor v3 transforms iXBRL filings into Excel
workbooks. Treat it as the current source of truth for the Phase 3+ pipeline.

## High-level flow
1. **Source normalisation** – `InputHandler` turns URLs, local files, and ZIP
   archives into a validated local path on disk. ZIP inputs are extracted to a temp
   folder; URLs are downloaded with a compliant SEC user agent.
2. **Viewer generation** – `ArelleProcessor` shells out to
   `python -m arelle.CntlrCmdLine --plugins iXBRLViewerPlugin` and writes
   `ixbrl-viewer.htm` plus `MetaLinks.json` to the working directory.
3. **Viewer extraction** – `ViewerDataExtractor` locates the embedded viewer JSON in
   the HTML, loads companion `MetaLinks.json` files (including any supplied via
   `--save-viewer-json` or download directories), and builds:
   - `role_map`: MetaLinks role metadata keyed by URI, long name, and normalised text
   - `concept_labels`: preferred label map per concept for `terse`/`standard`
4. **Presentation parsing** – `PresentationParser` walks
   `sourceReports[0].targetReports[0]` to produce `PresentationStatement` trees with
   the exact ordering, indentation, and labels from the filing. MetaLinks
   `groupType`/`subGroupType` metadata is attached when available.
5. **Fact matching** – `FactMatcher` aligns viewer facts to presentation nodes.
   - Period detection prioritises instants/durations tied to the statement and uses
     `DocumentPeriodEndDate` fallbacks when the context is ambiguous.
   - Dimensional members are expanded into separate rows by default; pass
     `--collapse-dimensions` to fold them back.
   - Scale hints from XBRL decimals apply only when negative (e.g. `-3` → thousands);
     otherwise `ValueFormatter` keeps the values in millions.
6. **Excel generation** – `ExcelGenerator` converts `StatementTable` objects into
   worksheets, applies indentation/bold/lines for totals, writes a summary sheet when
   multiple statements exist, and honours `--one-period` or explicit `--periods`.

## Component ownership
- `src/sec_downloader/`
  - `filing_search.py`, `models.py`: EDGAR search API integration
  - `filing_download.py`: download orchestration, retries, exhibit handling
  - `edgar_client.py`: shared HTTP client with SEC-compliant headers
- `src/processor/`
  - `input_handler.py`: wraps local/URL/ZIP sources
  - `arelle_processor.py`: viewer HTML generation and health-check/installation
  - `json_extractor.py`: viewer JSON + MetaLinks extraction
  - `presentation_parser.py`: converts presentation relationships to trees
  - `fact_matcher.py`: context, dimension, and scale-aware fact placement
  - `value_formatter.py`: millions-based currency formatting and unit heuristics
  - `data_parser.py`: end-to-end presentation-first parsing and filtering
  - `excel_generator.py`: workbook writer using openpyxl

## Data products
- **Viewer HTML** (`ixbrl-viewer.htm`) – contains the JSON payload emitted by Arelle.
- **Viewer JSON payload** – includes `sourceReports`, `facts`, and `concepts`.
- **MetaLinks.json** – upstream role metadata produced by Arelle; `role_map` is
  derived from this file.
- **ProcessingResult** – dataclass with company metadata, statements, and warnings.
- **Excel workbook** – one sheet per statement plus optional summary sheet.

## External dependencies
- **Arelle** (`arelle-release`) for the iXBRL viewer plugin (installed automatically
  if missing).
- **ixbrl-viewer** file structure – relied upon for `sourceReports`/`targetReports`.
- **openpyxl** for Excel output, `requests`/`urllib3` for HTTP transport.

## Design decisions & filters
- **Presentation-first**: we never rebuild statements from the fact list; fidelity to
  the filing layout is maintained.
- **MetaLinks `groupType` filter**: by default we keep primary financial statements
  (`groupType == "statement"`). Pass `--include-disclosures` to surface schedules,
  cover pages, and other roles.
- **Period strategy**: prefer periods aligned with document end dates, with fallbacks
  to the most-populated contexts per statement type. When necessary we collapse to
  one period (`--one-period`) or accept a comma-separated list via `--periods`.
- **Dimensional handling**: axis/member combinations expand into distinct rows to
  preserve totals; optional collapse is available for summary style reports.

## Known gaps
- Column header polishing (calendar-aware labels) remains open – compare the TSLA
  workbook against `Financial_Report.xlsx` when iterating.
- Full regression sweep is pending ahead of release tagging; keep running
  `PYTHONPATH=. pytest` plus targeted live filing checks when modifying presentation
  traversal or Excel formatting.
