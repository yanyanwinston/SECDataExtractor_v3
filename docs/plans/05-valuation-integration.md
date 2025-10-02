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
