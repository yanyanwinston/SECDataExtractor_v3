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


# 03-normalization-and-canonical-schema.md

## Step 3 — Concept Normalization & Canonical Schema (Design Spec)

**Goal**  
Map raw XBRL concepts (standard + extensions) into a compact **canonical schema** with consistent signs, units, and period semantics for cross‑company analysis and valuation.

---

### Canonical Data Model

**Gold layer artifacts**
- Wide tables: `fs_income_statement_wide`, `fs_balance_sheet_wide`, `fs_cash_flows_wide` (one row per entity×period).
- Audit trail: `normalized_fact_long` (normalized item ↔ actual concept(s) used, plus transformation notes).

**Keys & metadata**
- Keys: `entity_cik`, `period_end`, `fiscal_year`, `fiscal_period (FY/Q1–Q4)`
- Meta: `filing_id`, `accession_no`, `taxonomy_version`, `tool_versions`, `source_role_id`.

---

### Canonical Concept Dictionary (CCD)

A versioned YAML/JSON that defines how to source each normalized item.

```yaml
Revenue:
  prefer: [us-gaap:SalesRevenueNet, us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax]
  allow:  [us-gaap:Revenues]
  dimensions:
    accept: consolidated_only
  period: duration
COGS:
  prefer: [us-gaap:CostOfGoodsSold, us-gaap:CostOfSales]
OperatingIncome:
  prefer: [us-gaap:OperatingIncomeLoss]
NetIncome:
  prefer: [us-gaap:NetIncomeLoss]
CFO:
  prefer: [us-gaap:NetCashProvidedByUsedInOperatingActivities]
Capex:
  prefer: [us-gaap:PaymentsToAcquirePropertyPlantAndEquipment]
TotalAssets:
  prefer: [us-gaap:Assets]
TotalLiabilities:
  prefer: [us-gaap:Liabilities]
Equity:
  prefer: [us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest, us-gaap:StockholdersEquity]
EPSBasic:
  prefer: [us-gaap:EarningsPerShareBasic]
EPSDiluted:
  prefer: [us-gaap:EarningsPerShareDiluted]
SharesBasic:
  prefer: [us-gaap:WeightedAverageNumberOfSharesOutstandingBasic]
SharesDiluted:
  prefer: [us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding]
OCI:
  prefer: [us-gaap:OtherComprehensiveIncomeLossNetOfTax]
DividendsPaid:
  prefer: [us-gaap:PaymentsOfDividends]
Buybacks:
  prefer: [us-gaap:PaymentsForRepurchaseOfCommonStock]
```

**Overrides**
- Per‑company mapping files under `config/overrides/<cik>.yaml` for recurring extensions (e.g., custom `OperatingIncome`).

---

### Normalization Pipeline

1) **Filter to consolidated**  
Drop facts with non‑default dimension members unless a normalized item explicitly requests a dimension.

2) **Concept matching**  
For each normalized item, search `prefer` list, then `allow`. Persist the **actual concept used** for provenance.

3) **Unit & sign normalization**  
- Currency: store in USD (assume USD filers; if not, convert or flag).
- Signs: apply taxonomy balance + label/negated‑label roles to enforce: **revenues/gains positive; expenses/outflows negative**. Record `sign_source` (`balance|negated_label|rule`).

4) **Period normalization**  
- Income & Cash Flow → duration aligned to the fiscal period. 
- Balance Sheet → instant at `period_end`.
- 10‑Q policy: default **single‑quarter** values (derive from YTD if necessary and unambiguous); allow `--use-ytd` mode.

5) **Derived items**  
- `GrossProfit = Revenue − COGS` (if absent). 
- `FCF = CFO − Capex`. 
- `OCI` fallback: ΔAOCI if direct concept missing.

6) **Emit wides + trail**  
Pivot selected items to wide tables; write `normalized_fact_long` with: normalized item, value, unit, sign applied, underlying concept(s), dimension info, and notes.

---

### Contracts (selected columns)

**Income (fs_income_statement_wide)**  
Keys +: `Revenue, COGS, GrossProfit, R&D, SG&A, OperatingIncome, InterestExpense, OtherIncome, PretaxIncome, TaxExpense, NetIncome, EPSBasic, EPSDiluted, SharesBasic, SharesDiluted`

**Balance (fs_balance_sheet_wide)**  
Keys +: `Cash, Receivables, Inventory, PP&E, TotalAssets, CurrentLiabilities, LongTermDebt, TotalLiabilities, AOCI, Equity`

**Cash Flow (fs_cash_flows_wide)**  
Keys +: `CFO, CFI, CFF, Capex, DividendsPaid, Buybacks, NetChangeInCash`

**normalized_fact_long**  
`normalized_item, value_usd, unit, sign_applied, concept_qname, statement_type, role_id, dimension_json, provenance_note`

---

### Testing & DoD
- Golden tests: AAPL/MSFT/TSLA/JPM 10‑K cover ≥95% of core items across last 4 FYs.
- Reconciliations: Assets ≈ Liabilities+Equity; CFO+CFI+CFF ≈ ΔCash.
- No unintended dimension leakage in consolidated wides.

---


# 04-storage-and-ops.md

## Step 4 — Storage, Indexing & Operationalization (Design Spec)

**Goal**  
Persist bronze→silver→gold layers with metadata for reproducibility, fast queries, and simple handoff to valuation.

---

### Layered Layout (files)
```
data/
  bronze/
    <cik>/<accession>/viewer.json
    <cik>/<accession>/MetaLinks.json
    <cik>/<accession>/fact_long.parquet
  silver/
    <cik>/<accession>/statement_lines.parquet
    <cik>/<accession>/statement_facts.parquet
  gold/
    fs_income_statement_wide.parquet
    fs_balance_sheet_wide.parquet
    fs_cash_flows_wide.parquet
    normalized_fact_long.parquet
```

**Why**: mirrors presentation‑first artifacts; supports diffing per accession; keeps raw alongside derived for audit.

---

### Minimal Relational Schema (DuckDB/Postgres)

**Tables**
- `entity(entity_cik PK, ticker, name)`
- `filing(filing_id PK, entity_cik FK, accession_no, form, period_end, accepted_at, taxonomy_version, arelle_version, viewer_json_path, metalinks_path)`
- `fact_long(… primary key (filing_id, concept_qname, period_end, dimension_hash, unit))`
- `fs_income_statement_wide / fs_balance_sheet_wide / fs_cash_flows_wide`
- `normalized_fact_long`
- `qc_results(filing_id, check_name, severity, msg, created_at)`

**Indexes**
- `fact_long(entity_cik, concept_qname, period_end)`
- Optional: `normalized_fact_long(entity_cik, normalized_item, period_end)`

**Views**
- `vw_is`, `vw_bs`, `vw_cf`: convenient selects from wides.

---

### Orchestration

**One‑shot**: extend your existing ingress script to call `export_tables.py` so Excel and Parquet are emitted together.

**CLI flags**: reuse Step‑2 flags (`--include-disclosures`, `--collapse-dimensions`, `--use-ytd`, `--periods`).

**Metadata**: stamp `arelle_version`, `taxonomy_version`, tool versions into `filing` rows and Parquet metadata.

---

### Data Quality Gates (post‑export)
- **Balance sheet**: `|Assets − (Liabilities + Equity)| ≤ tol` → warn/error.
- **Cash roll‑forward**: `CFO + CFI + CFF ≈ ΔCash`.
- **Period sanity**: instant vs duration by statement type.
- **Dimension leakage**: consolidated wides must have `is_consolidated = true`.

**QC logging**: write results into `qc_results` with severity (`info|warn|error`).

---

### SLOs (local dev)
- Large‑cap 10‑K parse+export ≤ 45s with `--periods FY-2..FY`.
- Peak RAM ≤ 1.5 GB for mega‑filers.
- Batch of 10 filings end‑to‑end ≤ 12 min @ p95.

---


# 05-valuation-integration.md

## Step 5 — Interfaces for Valuation (RI, DCF, Multiples) (Design Spec)

**Goal**  
Define thin, stable interfaces that convert Gold tables into valuation‑ready inputs with reconciliations and provenance.

---

### What the Valuation Engine Expects

**Residual Income (RI)**
- Inputs: `BVE_Begin`, `NetIncome`, `OCI_NetOfTax`, `DividendsPaid`, `ShareRepurchaseCost` (opt), `SharesOutstanding`.
- Sourcing: `Equity` from BS (lag for `BVE_Begin`), `NetIncome` from IS, `OCI` direct or via ΔAOCI, dividends/buybacks from CF.
- Check: `BVE_End ≈ BVE_Begin + NetIncome + OCI − Dividends ± OtherEquityAdj`.

**DCF**
- Inputs: `CFO`, `Capex`, (optional `WorkingCapitalDelta`), `TaxRate`, `WACC`.
- Sourcing: `CFO` and `Capex` from CF; `FCFF = CFO − Capex`; `NOPAT = OperatingIncome * (1 − tax)` if used.

**Multiples**
- Inputs: `Revenue`, `EBITDA` (if derivable), `NetIncome`, `BookEquity`, `Cash`, `Debt`, `Shares`, `Price`.
- Sourcing: wides + external market data for `Price`.

---

### API Surface (thin wrappers)

```python
get_financials(entity_cik, periods=8) -> {
  'is': DataFrame, 'bs': DataFrame, 'cf': DataFrame, 'trail': DataFrame
}

build_ri_inputs(entity_cik, horizon=12) -> DataFrame
build_dcf_inputs(entity_cik, horizon=12) -> DataFrame
build_multiples_inputs(entity_cik, horizon=8) -> DataFrame
```

- Apply default quarterly policy: single‑quarter for Q1–Q3 unless overridden.
- `strict=True` raises on missing core items; otherwise fill `NaN` + warnings.

---

### Guardrails & Invariants
- **Reconciliations**: Assets ≈ Liabilities+Equity; CFO+CFI+CFF ≈ ΔCash.
- **Signs**: expenses/outflows negative; revenues/inflows positive.
- **Consolidation**: no non‑default members unless explicitly requested.
- **Provenance**: every input carries pointers to `normalized_fact_long` rows.

---

### Test Plan & DoD
- Golden fixtures for AAPL/MSFT/TSLA/JPM: 
  - RI inputs satisfy clean‑surplus within tolerance.
  - DCF inputs reconcile cash roll‑forward.
  - Multiples inputs match presentation totals (spot checks).
- **DoD**: ≥90% of S&P‑100 can be built with default CCD; missing fields degrade gracefully with emitted warnings and provenance.
