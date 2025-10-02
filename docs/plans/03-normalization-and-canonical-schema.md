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
