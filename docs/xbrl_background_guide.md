# XBRL Background Knowledge for Programmatic Parsing & Error Resolution
**Audience:** Developers/agents building pipelines on SEC 10‑K/10‑Q XBRL (US GAAP, Inline XBRL).  
**Goal:** Provide a compact, practical reference that helps an automated agent understand XBRL building blocks, choose the right facts, normalize concepts, and resolve common parsing/validation issues.

---

## 0) TL;DR – Agent Quick‑Start Checklist
- **Anchor on period & scope**
  - Use `dei:DocumentPeriodEndDate` to anchor the reporting period.
  - Prefer **consolidated, entity‑wide** facts: contexts *without* dimensions (axes/members) or with **default members** only.
- **Pick the correct context type**
  - **Instant** (balance sheet): “as of” date (e.g., `Assets` at `YYYY‑MM‑DD`).
  - **Duration** (income/cash flow): start & end (e.g., year ended `YYYY‑MM‑DD`).
- **Units & scaling**
  - Monetary: `iso4217:USD`. Shares: `shares`. Ratios/percent: `xbrli:pure`.
  - Inline XBRL may include `scale` and formatted strings—**always read the numeric value from the XBRL attributes**, not from rendered text.
- **Prefer standard concepts (us‑gaap, dei)**; map extensions to standard equivalents where possible.
- **Validate basics**
  - Balance sheet: `Assets ≈ Liabilities + Equity` (tolerate small rounding).
  - Cash flow: `ΔCash = CFO + CFI + CFF` (plus FX/other reconciling items).
- **Common pitfalls to detect & handle**
  - Sign conventions (expenses/losses/CF outflows may be negative).
  - Duplicate facts for same (concept, context, unit) → choose the **most precise** (`decimals` closest to actual, or latest in filing if amended).
  - Mixing **quarter** vs **YTD** in 10‑Q.
  - Missing or unexpected **dimensions** (segment, geography, product).

---

## 1) Core Concepts & Anatomy

### 1.1 Taxonomies & Namespaces
- **Taxonomy** = dictionary of reportable items (concepts/elements) + relationships (linkbases).
- Common namespaces:
  - `us-gaap:` US GAAP financial concepts.
  - `dei:` Document & Entity Information (company metadata, shares outstanding, fiscal year, etc.).
  - Company‑specific prefix (e.g., `aapl:`) = **extension**.
- Taxonomies are versioned annually; filers may use a recent year’s taxonomy.

### 1.2 Concepts (Elements)
- Each **fact** is tagged with a **concept** (e.g., `us-gaap:NetIncomeLoss`).
- Key attributes of a concept:
  - **dataType** (monetary, shares, string, boolean, perShare, pure).
  - **periodType**: `instant` vs `duration`.
  - **balance**: debit/credit (helps with sign expectations).
- Prefer standard concepts; extensions reduce comparability.

### 1.3 Facts
- A **fact** = (concept, value) + metadata (**context**, **unit**, **decimals/precision**, **footnotes**).
- Numeric facts use `decimals` to indicate rounding (e.g., `-6` → rounded to millions). Higher precision (e.g., `-3`) is generally preferred when duplicates exist.

### 1.4 Contexts
- Define **who** (entity) and **when** (period), plus optional **dimensions**.
- **Entity** → CIK or identifier.
- **Period** →
  - `instant`: a single date (e.g., balance sheet date).
  - `duration`: `startDate` + `endDate` (e.g., income/cash flow period).
- **Segment/Scenario** (optional) → **dimensions**; see §1.6.

### 1.5 Units
- Defined once, referenced by `unitRef` in facts.
- Common:
  - `iso4217:USD` (monetary),
  - `shares` (share counts),
  - `xbrli:pure` (ratios/percent; represent e.g., 0.15 for 15%).

### 1.6 Dimensions (Axes & Members)
- Dimensions add a pivot (e.g., **Segment**, **Product**, **Geography**).
- **Axis** = category; **Member** = value on that axis.
- Context includes zero or more (axis → member) pairs.
- **Default member**: represents “total/all” for an axis; if a default is applied implicitly, the context is often **undimensioned** for consolidated totals.
- For consolidated modeling, prefer **facts with no explicit dimensions** (or the axis default).

### 1.7 Linkbases (Relationships)
- **Presentation**: human‑readable hierarchy (ordering/containment in statements).
- **Calculation**: arithmetic relationships (sums with weights). Useful for QA.
- **Definition**: relationships for dimensions (domain–member, axis structure).
- **Label**: human‑readable labels for concepts (standard, terse, verbose).
- **Reference**: authoritative literature references.

### 1.8 Inline XBRL (iXBRL) specifics
- Facts are embedded in HTML using tags like `ix:nonFraction` (numeric) and `ix:nonNumeric`.
- Pay attention to:
  - `contextRef`, `unitRef`, `name` (QName of concept),
  - `format` (human display), `scale` (10^scale applied to displayed text),
  - Potential splitting across continuation elements (rare edge case).
- Always parse the **machine value**; ignore thousands separators/visual rounding.

### 1.9 DEI (Document & Entity Information)
- Useful DEI facts:
  - `dei:EntityCommonStockSharesOutstanding`
  - `dei:EntityRegistrantName`
  - `dei:EntityCentralIndexKey`
  - `dei:DocumentPeriodEndDate`
  - `dei:CurrentFiscalYearEndDate`
  - `dei:EntityFiscalYearFocus`/`dei:DocumentFiscalYearFocus`
  - `dei:DocumentType` (10‑K, 10‑Q, etc.)

---

## 2) Picking the Right Facts (Heuristics)

### 2.1 Period selection
- **Annual (10‑K):** duration contexts covering the fiscal year; instant at fiscal year end.
- **Quarterly (10‑Q):**
  - Filers often report both **current quarter** and **YTD**. Choose based on your model:
    - For time‑series quarterly analysis → **quarter** facts.
    - For trailing 12‑month or YTD analysis → **YTD** facts.
- Use `dei:DocumentPeriodEndDate` to anchor selection. Match context periods exactly.

### 2.2 Consolidated vs segmented
- Prefer **contexts without dimensions** for consolidated totals.
- If multiple contexts exist for the same concept:
  - Choose the **undimensioned** fact first.
  - If none, prefer contexts with **default members** only (no explicit, non‑default members).
- If assembling **segment analysis**, collect the full set of axis/member facts and ensure members sum (where appropriate) to the consolidated total.

### 2.3 Typical periodType mapping
| Statement            | periodType | Example concepts                                    |
|---------------------|------------|-----------------------------------------------------|
| Balance Sheet       | instant    | `Assets`, `Liabilities`, `StockholdersEquity`       |
| Income Statement    | duration   | `Revenues`, `CostOfRevenue`, `NetIncomeLoss`        |
| Cash Flow Statement | duration   | `NetCashProvidedByUsedInOperatingActivities`        |
| DEI cover data      | instant    | `EntityCommonStockSharesOutstanding` (on a date)    |

---

## 3) Normalization & Mapping

### 3.1 Prefer standard concepts
- Use canonical US‑GAAP elements for cross‑company comparability.
- Map common synonyms/alternatives to your canonical schema.

### 3.2 Example canonical mapping (non‑exhaustive)
| Canonical Item                     | Preferred Concept(s)                                  | Notes |
|-----------------------------------|--------------------------------------------------------|-------|
| Revenue (Net Sales)               | `us-gaap:Revenues`, `us-gaap:SalesRevenueNet`         | Some filers use one or the other. |
| Cost of Revenue / COGS            | `us-gaap:CostOfGoodsAndServicesSold`                  | Older tags may vary. |
| Gross Profit                      | `us-gaap:GrossProfit`                                 | If absent, compute: Revenue − COGS. |
| Operating Income (Loss)           | `us-gaap:OperatingIncomeLoss`                         | Beware custom “Adjusted Operating Income”. |
| Net Income (Loss)                 | `us-gaap:NetIncomeLoss`                               | Positive for income, negative for loss. |
| Total Assets                      | `us-gaap:Assets`                                      | Balance sheet instant. |
| Total Liabilities                 | `us-gaap:Liabilities`                                 |  |
| Shareholders’ Equity              | `us-gaap:StockholdersEquity`                          | Some use `us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`. |
| Operating Cash Flow               | `us-gaap:NetCashProvidedByUsedInOperatingActivities`  | Sign reflects net in/outflow. |
| Investing Cash Flow               | `us-gaap:NetCashProvidedByUsedInInvestingActivities`  |  |
| Financing Cash Flow               | `us-gaap:NetCashProvidedByUsedInFinancingActivities`  |  |
| Capex                             | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`  | Sometimes split by additions vs accruals. |
| Shares Outstanding                | `dei:EntityCommonStockSharesOutstanding`              | Instant date; may also appear on cover page. |
| OCI (net of tax)                  | `us-gaap:OtherComprehensiveIncomeLossNetOfTax`        | Needed for clean‑surplus RI. |

### 3.3 Handling extensions
- If an extension is a **clear synonym** of a standard concept → map to canonical.
- If an extension is a **component** of a standard total → include as detail but rely on the standard **total** for modeling.
- If an extension is a **non‑GAAP KPI** → store separately; avoid mixing into GAAP totals.

### 3.4 Shares, EPS & per‑share items
- Ensure per‑share measures use consistent **denominators** (basic vs diluted). Prefer standardized GAAP EPS where available.
- Shares outstanding taken at **instant** date can differ from weighted‑average shares used in EPS.

---

## 4) Signs, Units, and Precision

### 4.1 Sign conventions (rules of thumb)
- **Income/Profit** concepts: positive for gains, negative for losses (e.g., `NetIncomeLoss = -100` means loss).
- **Cash flows**: sign indicates direction; “NetCashProvidedBy…” may be negative for net outflow.
- **Expenses**: often reported as **positive** amounts (components) but deducted in totals via calculation weights; totals (e.g., `OperatingIncomeLoss`) already incorporate sign.
- **Equity changes**: dividends (reductions) may appear as **negative** in equity roll‑forward.

> **Guidance:** Use **reported sign**; avoid flipping signs arbitrarily. For display or derived metrics, apply your own conventions consistently (e.g., show expenses as positive visually but subtract in formulas).

### 4.2 Units & scaling
- Parse `unitRef` → resolve to measure (`iso4217:USD`, `shares`, `xbrli:pure`).
- Inline XBRL `scale` affects rendered text, **not** the machine value; rely on the fact’s numeric value.
- Use `decimals` to assess precision; prefer the fact with **highest precision** when duplicates exist.

---

## 5) Validations & QA Checks

- **Arithmetic checks (calc linkbase or recompute):**
  - BS: `Assets ≈ Liabilities + Equity`.
  - CF: `ΔCash = CFO + CFI + CFF + FX/Other`.
  - IS: `GrossProfit = Revenue − COGS`; `OperatingIncome = GrossProfit − Opex` (if tagged).
- **Context coherence:**
  - Ensure every numeric fact has a valid `contextRef` and `unitRef`.
  - Instant vs duration consistency with concept `periodType`.
- **Duplicate fact resolution:**
  - If multiple facts have same (concept, context, unit), prefer **non‑nil** with **greater precision** (smaller absolute `decimals`), or the latest DTS in amendments.
- **Quarter vs YTD checks (10‑Q):**
  - Avoid mixing quarterly and YTD in the same series; label them distinctly.
- **Dimension sanity:**
  - For consolidated totals, ensure no explicit non‑default members are present.
  - For segment tables, verify that members **add to** the consolidated where applicable (allow for “Other/Unallocated”).

---

## 6) Common Error Patterns & Programmatic Remedies

| Symptom / Error                                                                 | Likely Cause                                                             | Programmatic Resolution                                                                                      |
|----------------------------------------------------------------------------------|---------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| `contextRef` on a fact not found in contexts list                                | Context dictionary not built before fact processing                       | First pass: collect **all** `<context>` elements; second pass: resolve facts.                                 |
| `unitRef` missing or unit not declared                                           | Unit dictionary incomplete                                                | Build units map from `<unit>` elements. For non‑numeric facts, `unitRef` is not required.                     |
| Unknown QName/prefix (e.g., `usgaap:` vs `us-gaap:`)                             | Namespace prefix mismatch or not bound                                    | Parse namespace declarations (`xmlns:*`). Resolve QNames to **namespace URIs**; do not rely on raw prefixes.  |
| Duplicate facts for same (concept, context, unit)                                | Multiple appearances (precision/rounding, amendments)                     | Choose most precise (`decimals` nearer 0), or latest DTS. Keep provenance for audit.                          |
| Negative revenue or positive loss unexpectedly                                   | Sign convention misunderstanding or wrong concept                         | Check concept `balance` and calculation relationships. Verify you’re using the **total** concept, not a contra item. |
| Mixing quarter and YTD series                                                    | Context period mis‑classification                                         | Classify contexts: detect if duration equals quarter vs YTD (start at fiscal year start).                     |
| Consolidated numbers missing; only segmented facts found                         | Selecting dimensioned contexts only                                       | Prefer undimensioned contexts; if absent, collapse across dimension members if appropriate (with care).       |
| Parsing Inline XBRL yields text instead of numbers                               | Reading rendered HTML instead of `ix:*` attributes                        | Extract numeric value from `ix:nonFraction/@value` / content; ignore formatted text/`scale`.                   |
| TextBlock elements cause huge strings or parser slowdowns                        | Text blocks (policies, disclosures)                                      | Skip `*TextBlock` concepts for numeric pipeline; process only if needed for NLP.                              |
| Concept not found in a filing where expected                                     | Taxonomy version differences or filer uses alternative concept/extension  | Use label/definition search; fall back to synonyms; check company extensions; or compute from components.      |

---

## 7) 10‑Q vs 10‑K Particulars

- **10‑K (annual):** Focus on full‑year duration contexts and year‑end instant contexts.
- **10‑Q (interim):** Filers typically tag both **current quarter** and **YTD**; also prior‑year comparatives. Build logic to:
  - Identify **quarter duration** (not starting at fiscal year start) vs **YTD duration** (starting at fiscal year start).
  - Prefer quarter facts for quarterly time‑series; use YTD only when required.

---

## 8) Working with Dimensions (When Needed)

- **Identify axes:** From definition linkbase or by scanning contexts’ dimension elements.
- **Default member:** Many axes have a default member representing “All”. Consolidated totals often omit explicit dimensions.
- **Aggregation:** For tables (e.g., revenue by geography), sum members to compare against consolidated totals (mind “Other/Unallocated” buckets).

---

## 9) Minimal Canonical Schema (suggested columns)

For a wide “fundamentals” table (per company, per period):
```
[cik, ticker, fiscal_year, fiscal_period, period_end, is_annual(bool),
 revenue, cogs, gross_profit, operating_income, net_income,
 assets, liabilities, equity,
 cfo, cfi, cff, capex,
 shares_out, oci_net, dividends_paid]
```
Populate from preferred concepts (see §3.2). Keep a **long facts table** alongside (concept, context, unit, value, decimals, dimensions_json) for audit and flexibility.

---

## 10) Extension Mapping Heuristics (Lightweight)

1. **Label match:** If extension’s standard label matches/contains a canonical name → map.
2. **Calc parent/child:** If extension rolls up into a known total (per calc/presentation) → classify as component of that total.
3. **Definition domain:** If extension member belongs to a known axis domain (e.g., a debt instrument member) → treat as **detail**, not a new total.
4. **Fallback:** If uncertain, keep as **auxiliary**; do not pollute canonical totals.

---

## 11) Provenance & Audit Trail (Good Practice)
- Store **filing accession**, **document URI**, **DTS (taxonomy set)**, and **fact identifiers**.
- When deduplicating facts, record the **selection rule** used (e.g., “kept decimals=‑3”).
- Keep a link back to the **inline viewer location** when possible for quick manual verification.

---

## 12) Glossary (quick reference)
- **Taxonomy:** The schema (elements + relationships) for reporting.
- **Concept (Element):** A defined reporting item (e.g., `us-gaap:Assets`).
- **Fact:** A reported value tagged with concept, context, unit.
- **Context:** Who/when (+ optional dimensions).
- **Unit:** Measurement unit (USD, shares, pure).
- **Inline XBRL:** XBRL embedded in HTML (ix tags).
- **Axis/Member (Dimension):** Additional qualifier (segment, geography, product).
- **Linkbase:** Relationship sets (presentation, calculation, definition, label, reference).
- **Extension:** Company‑specific element not in the standard taxonomy.
- **DEI:** Document & Entity Information taxonomy (metadata).

---

## 13) Frequently Needed Concept IDs (cheat sheet)
- Revenue: `us-gaap:Revenues` | `us-gaap:SalesRevenueNet`
- COGS: `us-gaap:CostOfGoodsAndServicesSold`
- Gross Profit: `us-gaap:GrossProfit`
- Operating Income: `us-gaap:OperatingIncomeLoss`
- Net Income: `us-gaap:NetIncomeLoss`
- Assets: `us-gaap:Assets`
- Liabilities: `us-gaap:Liabilities`
- Equity: `us-gaap:StockholdersEquity`
- CFO: `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- CFI: `us-gaap:NetCashProvidedByUsedInInvestingActivities`
- CFF: `us-gaap:NetCashProvidedByUsedInFinancingActivities`
- Capex: `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`
- Shares Out: `dei:EntityCommonStockSharesOutstanding`
- OCI (net): `us-gaap:OtherComprehensiveIncomeLossNetOfTax`

---

## 14) Safe Defaults for an Automated Agent
- Default to **standard concepts**; only use extensions after an explicit mapping step.
- Default to **undimensioned** consolidated facts.
- Default to **annual** facts in 10‑K and **quarter** facts in 10‑Q unless explicitly requesting YTD.
- Apply **precision preference** when duplicates exist.
- Run **QA checks** before persisting to production tables; quarantine records that fail.


---

### Appendix A — Example Selection Logic (pseudocode-ish)
1. Load filing → build dictionaries of **contexts**, **units**, **facts**.
2. Identify `period_end` via `dei:DocumentPeriodEndDate` (fallback: latest instant/duration end).
3. For each canonical item:
   - Find **preferred concept(s)** (see §3.2).
   - Filter facts to **matching period type** and **period_end** (and matching annual/quarter intent).
   - Keep **undimensioned** facts first; if none, consider **default‑member** contexts.
   - Resolve duplicates: pick **highest precision**; if tie, prefer **most recent DTS**.
4. Validate **calc checks**; if fail, log and attempt recomputation (e.g., GrossProfit = Revenue − COGS).
5. Persist with **provenance** (accession, contextRef, unitRef, decimals, source URL).

---

### Appendix B — Troubleshooting Playbook
- **Numbers don’t tie:** Recalculate subtotals; check for missing extension components; verify quarter vs YTD mixups.
- **Missing key item (e.g., Operating Income):** Compute from components or map company extension; confirm taxonomy year.
- **Strange sign on cash flow:** Verify that you’re using the **net** line, not a detail with opposite sign; check calculation weights.
- **Multiple revenue concepts present:** Prefer `SalesRevenueNet` or `Revenues` based on company usage; avoid double‑counting both.
- **Segment totals exceed consolidated:** Look for “Unallocated/Elimination” members; not all segment details are strictly additive.


---

*This guide is intentionally concise and implementation‑oriented. It is suitable for embedding alongside parsing code to standardize selection, normalization, and error handling across SEC XBRL filings.*
