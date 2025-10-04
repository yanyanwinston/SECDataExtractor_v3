# 02-parsing-to-structured-tables.md

## Step 2 - Parse iXBRL -> Structured Tables (Design Spec)

**Goal**  
Transform Arelle's iXBRL viewer output (HTML with embedded viewer JSON + MetaLinks.json) into machine-usable, statement-aligned tables **and** a canonical long "facts" table for storage and downstream normalization. Maintain fidelity with filing layout and periods while adding data contracts for modeling.

**Assumptions / Current State**
- The Excel exporter already runs on a presentation-first traversal with MetaLinks-aware filtering, period selection, and dimensional expansion.
- We have rich in-memory objects (`PresentationStatement`, `StatementRow`, `Cell`) with raw versus display values separated for Excel formatting.
- Storage today stops at the Excel workbook; no first-class Parquet/CSV exports exist yet.

### Status Snapshot
- [x] Modular viewer JSON + MetaLinks extraction via `ViewerDataExtractor`, including role maps and concept label lookups.
- [x] Presentation-first traversal, statement classification, and MetaLinks filters through `PresentationParser` and `DataParser` powering current Excel output.
- [x] Fact matching with context-aware period policy, dimensional expansion, and raw/display value split via `FactMatcher` feeding the workbook generator.
- [ ] Persist `statement_lines`, `statement_facts`, and `fact_long` as bronze/silver artifacts with schema metadata.
- [ ] Capture filing metadata (`filing_id`, `entity_cik`, accession, taxonomy) and persist viewer payloads under `data/bronze/`.
- [ ] Ship `export_tables.py` CLI (flags for disclosures, period policy, dimension collapsing, viewer JSON export) and wire QC logging/tests.

### Current Implementation Notes
- `ViewerDataExtractor.extract_viewer_data` already finds embedded viewer payloads, loads MetaLinks, and builds role/concept lookup maps reused by presentation parsing.
- `DataParser` orchestrates presentation parsing, period selection, and fact matching, returning `ProcessingResult` objects for the Excel path.
- `FactMatcher` expands dimensional members into additional rows, keeps raw numeric values separate from formatted strings, and reuses axis metadata.
- `PresentationParser` classifies statements, attaches MetaLinks metadata (groupType/subGroupType/order), and keeps stable DFS ordering for line construction.
- `ExcelGenerator` consumes the above state; we still need dedicated writers that emit tables while leaving the XLSX workflow untouched.

### Remaining Scope for Step 2
- Materialize `statement_lines`, `statement_facts`, and `fact_long` DataFrames/Parquet with the columns below, including `line_order`, `dimension_json`, `dimension_hash`, `is_consolidated`, and provenance fields.
- Attach filing-level metadata (CIK, accession, filing_id, taxonomy, tool versions) and persist raw viewer JSON/MetaLinks in `data/bronze/` for audit.
- Design exporters that reuse existing presentation/fact matching code paths without regressing Excel output; ensure bronze/silver writes are opt-in until stable.
- Build `export_tables.py` CLI that mirrors Excel CLI ergonomics, exposes `--include-disclosures`, `--collapse-dimensions`, `--periods`, `--use-ytd`, and optional viewer JSON save switches.
- Extend tests (presentation parser, integration) with assertions over the new table outputs, and add smoke scripts to compare Excel vs. Parquet totals for reference filings.

---

### Inputs & Contracts

**A. Viewer JSON (embedded payload)**
- **Key blocks**: `concepts`, `facts`, `roleDefs`, `rels.pres` (presentation arcs).
- **Facts (compressed)**: value `v`; attributes object (e.g., `a`) holding concept qname (`c`), period (`p`), unit/measure (`m`), entity (`e`). Some facts expose multiple context variants (`a`, `b`, `c`).
- **Presentation**: `rels.pres[roleId]` arrays define parent->children and order.
- **Role definitions**: `roleDefs[roleId] -> { roleURI, definition }` (e.g., "Statement - Consolidated Balance Sheets").

_Status_: Already parsed for Excel; needs to be persisted to `data/bronze/` alongside the derived tables and extended to support multiple `sourceReports` where present.

**B. MetaLinks.json**
- Use to map roles to high-level `groupType/subgroupType` (e.g., `statement`, `disclosure`). Default: include `statement` roles; disclosures are opt-in.

_Status_: Ingested via `ViewerDataExtractor` and attached to `PresentationStatement`. We must propagate this metadata into table exports and handle filings lacking MetaLinks gracefully.

---

### Outputs

1) **`statement_lines`** (presentation-aligned rows; one per line item per statement)
- `filing_id`, `entity_cik`
- `statement_role_id`, `role_name`, `statement_type` (`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOWS`, `COMPREHENSIVE_INCOME`, `EQUITY`, `OTHER`)
- `line_order` (stable order from traversal)
- `concept_qname`, `label_terse`, `label_standard`
- `is_abstract` (bool), `preferred_label_role`
- `metalink_group_type`, `metalink_subgroup_type`

_Status_: Presentation nodes already capture ordering, abstraction, and labels. Missing pieces are persistent IDs (`filing_id`), dual label capture, and an exporter that emits one row per node.

2) **`statement_facts`** (line<->fact placements)
- Keys: `filing_id`, `statement_role_id`, `concept_qname`, `period_end`, `dimension_hash`, `unit`
- Periods: `period_end`, `period_start` (null for instant), `is_instant`, `period_label`
- Values: `value_raw` (exact string), `value_numeric` (parsed decimal), `decimals_hint` (if provided)
- Dimensionality: `dimension_json` (axis/member pairs), `is_consolidated` (true if no non-default members)
- Meta: `entity`, `is_extension` (namespace not in {`us-gaap`, `dei`, etc.})

_Status_: Fact matching already yields per-period cells with raw/display values and dimension expansion. We need to capture the underlying context attributes, compute hashes, and serialize rows instead of only populating workbook cells.

3) **`fact_long`** (canonical long format; union of all statements)
- All columns in `statement_facts`, plus: `statement_type`, `concept_balance` (`debit`/`credit`/`none`), `concept_datatype`, label flags (e.g., `has_negated_label`).

_Status_: Requires deriving additional concept metadata (balance/datatype/labels) and unifying all statement_facts rows into one table with consistent primary keys.

> **Modeling guidance**: Always compute from `value_numeric` + `unit` (raw, unscaled). Use display scaling only for human-friendly exports.

---

### Processing Flow

1. **Extract viewer payload & MetaLinks**
   - Parse embedded JSON from iXBRL viewer HTML; load MetaLinks.json.
   - _Implementation_: Done via `ViewerDataExtractor`; the exporter should optionally persist raw JSON alongside Step 2 tables.

2. **Select statement roles**
   - From `roleDefs`, keep roles whose definitions start with "Statement - ...".
   - Filter by MetaLinks `groupType == statement` (default). Allow `--include-disclosures` flag to widen scope.
   - _Implementation_: Role filtering and disclosure opt-in already exist inside `PresentationParser`/`DataParser`. CLI flag plumbing and metadata propagation remain.

3. **Build presentation trees**
   - For each role, traverse `rels.pres[roleId]` to compute ordered trees; assign `line_order` with stable DFS order.
   - _Implementation_: DFS traversal is live; we need to expose `line_order` explicitly and persist the flattened rows.

4. **Classify statement types**
   - Map `role_name` patterns to `statement_type` (income/balance/cash flow/comprehensive income/equity/other).
   - _Implementation_: `classify_statement_type` already runs; we must store the classification inside `statement_lines`/`fact_long` outputs.

5. **Match facts to lines**
   - Join facts to concepts by qname. For facts with multi-contexts (e.g., `a`, `b`, `c`), emit one row per context.
   - **Period policy**: prefer contexts aligned to the statement's fiscal focus (e.g., FY for 10-K; single-quarter for 10-Q unless `--use-ytd`). Fallback to DEI `DocumentPeriodEndDate` if ambiguous.
   - **Dimensions**: expand axis/member combinations as separate rows; compute `dimension_hash`. Provide `--collapse-dimensions` to roll up to consolidated totals where safe.
   - _Implementation_: Context joining, period selection, and dimension expansion exist; we must surface context metadata, compute hashes, and support a `--collapse-dimensions` option (can piggyback on `expand_dimensions=False`).

6. **Units & scaling**
   - Persist `unit` exactly; parse numeric `v` to decimal.
   - Optional `value_display` track mirrors existing Excel scaling (e.g., in millions). Raw always wins for storage and math.
   - _Implementation_: Raw vs. formatted values already separated in `Cell`; exporter needs to retain both plus decimals/unit metadata.

7. **Emit tables**
   - Write `statement_lines`, `statement_facts`, `fact_long` to CSV/Parquet. Optionally co-emit existing Excel workbook for validation.
   - _Implementation_: Writing layer and CLI glue still required; ensure Excel path stays untouched and enable opt-in dual export during rollout.

---

### CLI & Module Surface

**CLI**: `export_tables.py`
```
python export_tables.py --filing <PATH|URL|ZIP> --out data/ \
  [--include-disclosures] [--collapse-dimensions] \
  [--periods "2024,2023"] [--use-ytd] [--save-viewer-json viewer.json] \
  [--no-display-scaling] [--verbose]
```

**Core classes**
- `ViewerPayload`: raw blocks (`concepts`, `facts`, `roleDefs`, `rels`).
- `PresentationIndex`: role->ordered line items.
- `FactIndexer`: concept->facts with context/units; helpers for period policy + dimensions.
- `TableExporter`: materializes the three outputs.

_Status_: Classes above remain conceptual; we currently operate with `ViewerDataExtractor`, `PresentationParser`, `FactMatcher`, and `DataParser`. We need a thin orchestration layer (`export_tables.py` + exporter module) that wraps existing components and writes Parquet/CSV without disturbing Excel generation.

---

### Acceptance Criteria
- For reference filings (e.g., AAPL/TSLA 10-K), role counts and line orders match the Excel output.
- `fact_long` contains all primary-statement facts; `is_consolidated` true for no-dimension rows.
- Period selection adheres to policy; fallbacks logged and testable.
- Bronze viewer payload + silver tables replay into Excel with no numeric drift.

---

### Edge Cases
- Multiple `targetReports` -> choose the one with most primary statements (tie-break by role count).
- Text-only concepts or missing units -> skip numeric exports with warnings.
- Missing calc/pres links for some totals -> keep as `is_abstract=true` without facts.
- Filings without MetaLinks -> fall back to viewer heuristics and mark metadata fields as null.
