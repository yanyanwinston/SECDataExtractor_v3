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