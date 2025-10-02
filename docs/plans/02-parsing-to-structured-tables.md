# 02-parsing-to-structured-tables.md

## Step 2 — Parse iXBRL → Structured Tables (Design Spec)

**Goal**  
Transform Arelle’s iXBRL viewer output (HTML with embedded viewer JSON + MetaLinks.json) into machine-usable, statement‑aligned tables **and** a canonical long “facts” table for storage and downstream normalization. Maintain fidelity with filing layout and periods while adding data contracts for modeling.

**Assumptions / Current State**
- You already render filings with Arelle’s iXBRL viewer plugin and can read the embedded **viewer JSON** + **MetaLinks.json**.
- Your parser follows a **presentation‑first** traversal (presentation linkbase order), selects statement roles, and applies a period‑selection policy.
- Value formatting for Excel exists; we now separate **display scaling** from **stored raw values**.

---

### Inputs & Contracts

**A. Viewer JSON (embedded payload)**
- **Key blocks**: `concepts`, `facts`, `roleDefs`, `rels.pres` (presentation arcs).
- **Facts (compressed)**: value `v`; attributes object (e.g., `a`) holding: concept qname (`c`), period (`p`), unit/measure (`m`), entity (`e`). Some facts expose multiple context variants (`a`, `b`, `c`).
- **Presentation**: `rels.pres[roleId]` arrays define parent→children and order.
- **Role definitions**: `roleDefs[roleId] → { roleURI, definition }` (e.g., “Statement — Consolidated Balance Sheets”).

**B. MetaLinks.json**
- Use to map roles to high‑level **groupType/subgroupType** (e.g., `statement`, `disclosure`). Default: include `statement` roles; disclosures are opt‑in.

---

### Outputs

1) **`statement_lines`** (presentation‑aligned rows; one per line item per statement)
- `filing_id`, `entity_cik`
- `statement_role_id`, `role_name`, `statement_type` (`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOWS`, `COMPREHENSIVE_INCOME`, `EQUITY`, `OTHER`)
- `line_order` (stable order from traversal)
- `concept_qname`, `label_terse`, `label_standard`
- `is_abstract` (bool), `preferred_label_role`
- `metalink_group_type`, `metalink_subgroup_type`

2) **`statement_facts`** (line↔fact placements)
- Keys: `filing_id`, `statement_role_id`, `concept_qname`, `period_end`, `dimension_hash`, `unit`
- Periods: `period_end`, `period_start` (null for instant), `is_instant`, `period_label`
- Values: `value_raw` (exact string), `value_numeric` (parsed decimal), `decimals_hint` (if provided)
- Dimensionality: `dimension_json` (axis/member pairs), `is_consolidated` (true if no non‑default members)
- Meta: `entity`, `is_extension` (namespace not in {`us-gaap`, `dei`, etc.})

3) **`fact_long`** (canonical long format; union of all statements)
- All columns in `statement_facts`, plus: `statement_type`, `concept_balance` (`debit`/`credit`/`none`), `concept_datatype`, label flags (e.g., `has_negated_label`).

> **Modeling guidance**: Always compute from `value_numeric` + `unit` (raw, unscaled). Use display scaling only for human‑friendly exports.

---

### Processing Flow

1. **Extract viewer payload & MetaLinks**
   - Parse embedded JSON from iXBRL viewer HTML; load MetaLinks.json.

2. **Select statement roles**
   - From `roleDefs`, keep roles whose definitions start with “Statement — …”.
   - Filter by MetaLinks `groupType == statement` (default). Allow `--include-disclosures` flag to widen scope.

3. **Build presentation trees**
   - For each role, traverse `rels.pres[roleId]` to compute ordered trees; assign `line_order` with stable DFS order.

4. **Classify statement types**
   - Map `role_name` patterns to `statement_type` (income/balance/cash flow/comprehensive income/equity/other).

5. **Match facts to lines**
   - Join facts to concepts by qname. For facts with multi‑contexts (e.g., `a`, `b`, `c`), emit one row per context.
   - **Period policy**: prefer contexts aligned to the statement’s fiscal focus (e.g., FY for 10‑K; single‑quarter for 10‑Q unless `--use-ytd`). Fallback to DEI `DocumentPeriodEndDate` if ambiguous.
   - **Dimensions**: expand axis/member combinations as separate rows; compute `dimension_hash`. Provide `--collapse-dimensions` to roll up to consolidated totals where safe.

6. **Units & scaling**
   - Persist `unit` exactly; parse numeric `v` to decimal. 
   - Optional `value_display` track mirrors existing Excel scaling (e.g., in millions). Raw always wins for storage and math.

7. **Emit tables**
   - Write `statement_lines`, `statement_facts`, `fact_long` to CSV/Parquet. Optionally co‑emit existing Excel workbook for validation.

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
- `PresentationIndex`: role→ordered line items.
- `FactIndexer`: concept→facts with context/units; helpers for period policy + dimensions.
- `TableExporter`: materializes the three outputs.

---

### Acceptance Criteria
- For reference filings (e.g., AAPL/TSLA 10‑K), role counts and line orders match the Excel output.
- `fact_long` contains all primary-statement facts; `is_consolidated` true for no‑dimension rows.
- Period selection adheres to policy; fallbacks logged and testable.

---

### Edge Cases
- Multiple `targetReports` → choose the one with most primary statements (tie‑break by role count).
- Text‑only concepts or missing units → skip numeric exports with warnings.
- Missing calc/pres links for some totals → keep as `is_abstract=true` without facts.

---