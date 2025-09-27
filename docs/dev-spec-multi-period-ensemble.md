# Multi-Filing Period Ensemble (Draft)

## Purpose
Enable analysts to build a single Excel workbook that compares the same financial statements across multiple SEC filings (e.g., the last five 10-Ks for a filer). The workbook should preserve the existing presentation-first layout while expanding the column set to cover periods pulled from different documents.

## Problem Statement
Today each pipeline run emits a workbook tied to one filing. Comparing multi-year trends requires manual copy/paste or separate workbook merges, which is error-prone and breaks alignment with the original presentation trees. We need native support for aggregating several filings into one set of statement tables without losing structure, scaling rules, or metadata.

## Goals & Non-Goals
- **In scope**
  - Accept N>1 filings that represent the same company + statement set and merge their periods into a single workbook.
  - Preserve row ordering, indentation, and label fidelity from the latest (anchor) filing.
  - Include column-level metadata that keeps track of source filing, form type, and period end date.
  - Support both flow-based statements (e.g., Income Statement) and stock-based statements (e.g., Balance Sheet).
  - Expose the feature through a CLI workflow that can fetch the needed filings and emit the aggregated workbook in `output/`.
- **Out of scope (for the first iteration)**
  - Auto-healing major presentation structure drifts (e.g., new sections appearing mid-history). We will surface these rows but not attempt heuristic re-ordering beyond anchor alignment.
  - Mixing different companies or form types in one workbook.
  - Cross-filing dimensional reconciliation beyond reusing the existing expand/collapse options.

## Primary Scenarios
- *Trend workbook from ticker*: Analyst passes a ticker, form type (`10-K`), and count (`5`); tool downloads each filing, renders statements, and outputs one workbook with five annual columns.

## User Experience
- New CLI entry point: `python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 5 --out output/TSLA-multi-year.xlsx`.
- Future iteration: accept alternative inputs via repeated `--filing` flags for explicit paths/URLs or a `--manifest manifest.csv` that describes filing source, label, and override metadata.
- Default column header format: `<statement_period_label>` sorted newest → oldest; each column represents a single period.
- Flags should mirror existing renderer options where possible (`--include-disclosures`, `--collapse-dimensions`, scaling knobs, etc.).

## Functional Requirements
- Reuse the existing single-filing pipeline to obtain a `ProcessingResult` per filing. No changes to core parsing logic for individual filings.
- Introduce a merger that:
  1. Picks an anchor filing (default: newest by `filing_date` or explicit `--anchor-index`).
  2. Builds canonical row identifiers from the anchor statement tree using concept IDs + dimensional context keys.
  3. For each additional filing, maps its rows onto the canonical skeleton; any rows not present in the anchor append at the bottom within their section.
  4. Produces a union of periods for each statement, ensuring the order is consistent across statements (descending by period end by default).
  5. For statements that ship multiple periods per filing (e.g., stock-based statements with current/prior instants, flow-based statements with current/prior durations), include only the primary period for that filing in the ensemble (default: the most recent). Future iteration: allow retaining the additional columns when explicitly requested.
- Maintain value scaling rules (millions by default, decimals hints respected unless `--no-scale-hint` is set) via `ValueFormatter`.
- Surface gaps explicitly: cells that lack data should show as blank/`—` but keep the column placeholder to preserve alignment.
- Carry forward warnings from source runs and surface them in a summary section of the Excel workbook and stdout log.

## Data & Modeling Changes
- Extend `ProcessingResult` or add a new wrapper model `FilingSlice` capturing `processing_result` + filing metadata needed for headers (CIK, accession, filing date, form type).
- Define a `CanonicalRowKey` helper that combines:
  - Concept name (if available)
  - Dimensional signature (axis/member tuple sorted)
  - Presentation depth path (e.g., tuple of parent concept IDs) to reduce collisions.
- Create `MultiPeriodStatement` with:
  - `name`, `short_name`
  - `periods`: ordered list of `AggregatedPeriod` (extends `Period` with `source_filing_id`)
  - `rows`: aligned list retaining anchor ordering but with `cells` covering all aggregated periods
- Update `ExcelGenerator` (or add a small adapter) so it can accept `MultiPeriodStatement` instances without regressing current behavior.

## CLI & Orchestration
- New script `ensemble_to_xlsx.py` orchestrates:
  1. Input resolution (`ticker`/`manifest`/repeat `--filing`).
  2. For ticker-based flows, reuse `download_filings` logic to fetch the latest N filings into `downloads/` and collect viewer paths.
  3. Sequentially run the existing renderer components inside a temporary workspace per filing (honor `--keep-temp`).
  4. Pass the list of `ProcessingResult` objects to the merger and then into `ExcelGenerator`.
- Shared CLI flags should be factored into a helper to avoid duplication with `render_viewer_to_xlsx.py`.
- Manifest format (CSV): `source,label,form_type,filing_date,period_override` to allow ad-hoc labeling when the viewer metadata is messy.

## Implementation Plan (Phase 1)
1. **Input ingestion**: build manifest loader + ticker lookup adapter. Reuse `InputHandler`/`ArelleProcessor` for each filing.
2. **Merging layer**: implement canonical row key derivation, anchor selection, and union logic. Include logging for unmatched rows.
3. **Excel adapter**: extend `ExcelGenerator` to accept aggregated statements (possibly via a thin translator that converts `MultiPeriodStatement` back to the existing `Statement` contract with expanded periods).
4. **CLI**: add `ensemble_to_xlsx.py`, wire shared options, integrate download + render loops, and ensure output lands in `output/`.
5. **Regression coverage**: add targeted tests + golden files for a synthetic multi-filing scenario; ensure existing single-filing tests remain green.

## Testing Strategy
- Unit tests for the merger that feed crafted `Statement` fixtures and assert correct alignment, missing cells handling, and appended rows.
- CLI integration test (pytest) using fixture filings stored under `tests/data/ensemble/` to validate workbook shape and header contents.
- Update or add snapshot-based Excel assertions in `tests/test_excel_generator.py` to confirm aggregated columns render as expected.
- Smoke test script: run `python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 2` and compare against known workbook metadata.

## Observability & Logging
- Add per-filing log entries summarizing included statements and period labels.
- Emit warnings when statements are missing from non-anchor filings (e.g., if a filing skipped Cash Flow, log and include an empty column).
- Include an optional `--dump-manifest` flag to write the resolved manifest so analysts can reuse the same inputs later.

## Risks & Mitigations
- **Presentation drift**: statements change order over time. Mitigate by anchoring to the newest filing and appending unmatched rows with clear section headers.
- **Performance**: sequential rendering of N filings may hit rate limits or timeouts. Allow configurable sleep/backoff and document expected runtime.
- **Memory footprint**: holding multiple `ProcessingResult` objects may grow large for big filings; monitor and release references after merge when possible.

## Open Questions
- Defer mixed-form ensembles (10-K and 10-Q together) to a future iteration; initial scope focuses on a single form type per workbook.

## Validation Plan
- After implementation, rerun the TSLA regression for single filings to confirm no regressions.
- Produce a 5-year TSLA workbook and manually verify column headers, row alignment, and total calculations against individual single-year outputs.
- Document CLI usage in `docs/cli-reference.md` and update the README with an example command + screenshot of the aggregated workbook.
