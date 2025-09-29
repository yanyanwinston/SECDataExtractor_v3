# TSLA Multi-Year Automotive Revenues Duplication

## Observed Issue
- Workbook: `output/tsla-multi-year.xlsx`
- Sheet: `Income Statement`
- Column: `Jan 01, 2023`
- Problem: multiple rows labelled `Automotive Revenues`, each with different figures (e.g., 67,210; 1,776; 2,476; 71,462).

## Source Investigation
- The multi-year column for `Jan 01, 2023` is sourced from the FY2022 10-K export: `output/TSLA/10-K_2022-12-31_000095017023001409.xlsx`.
- That single-filing workbook already includes four separate `Automotive Revenues` rows tied to the segment breakdown (Automotive sales, regulatory credits, leasing, total automotive revenues).
- The SEC-provided `Financial_Report.xlsx` for the same filing contains an identical segmented breakdown under the label `Automotive Revenues [Member]`, so the duplication originates upstream in the facts, not in the ensemble merge.

## Root Cause
- When dimensions are expanded, `_format_dimension_label` (in `src/processor/fact_matcher.py`) derives the caption by chaining `_clean_member_label`, which strips the trailing `[Member]` suffix.
- As a result, dimension-specific rows like `Automotive Revenues [Member]` lose their qualifier and collapse back to the base label `Automotive Revenues`.
- The 2024 anchor filing lacks this dimensional breakdown, so the ensemble logic treats the 2022 rows as "additional" entries and appends them verbatim for that column only (`src/processor/ensemble.py`), leaving distinct values that appear as duplicates because their member qualifier was removed.

## Implications
- The exported figures are correct and faithfully mirror the source facts, but the label normalisation obscures which dimensional member each row represents.
- This affects readability for any statement where member labels collapse to the same base caption; similar issues may surface in other filings with segment disclosures.


## 2024 vs 2022 Filing Differences
- 2024 contexts differentiate the automotive mix by tagging `srt:ProductOrServiceAxis` with member-specific values (e.g., `tsla:AutomotiveSalesMember`, `tsla:AutomotiveRegulatoryCreditsMember`, `tsla:AutomotiveLeasingMember`). Our exporter turns those into clean row labels (`Automotive sales`, `Automotive regulatory credits`, `Automotive leasing`).
- 2022 contexts reuse the generic `tsla:AutomotiveRevenuesMember` for the line item concepts `tsla_AutomotiveSalesRevenue`, `tsla_AutomotiveRegulatoryCredits`, and `tsla_AutomotiveLeasing`. Because the dimension fingerprint is identical, `_format_dimension_label` falls back to that member name, collapsing the captions to `Automotive Revenues`.
- The 2022 statement also surfaces an additional dimensional block (rows such as `AutomotiveLeasingMember`, `AutomotiveRegulatoryCreditsMember`) sourced from `RevenueFromContractWithCustomerExcludingAssessedTax`. Those retain their member-specific labels, which is why only the top-level block appears duplicated.
- Net effect: 2024 has unique member labels at both the concept and `RevenueFromContractWithCustomer` levels; 2022 lacks that granularity for the concept rows, so every dimensional expansion inherits the same `Automotive Revenues` caption.

## Remediation
- Extend `ViewerDataExtractor` so concept labels fall back to the local label linkbase when MetaLinks omits them.
- `FactMatcher` now treats single dimension combinations as part of the base line item, keeping the concept caption instead of reusing the member label (e.g., `Automotive sales` instead of `Automotive Revenues`).
- The parser merges MetaLinks and label-linkbase captions, ensuring historical filings such as TSLA 2022 retain distinct automotive line items across single- and multi-filing exports.

## Proposed Next Steps
1. Inline allow-list: Parsing the iXBRL HTML now yields a concept/dimension signature list for each primary statement (see `visible_fact_signatures` in the viewer JSON). `FactMatcher` uses this allow-list to drop rows that never appear in the HTML table. Verify the behaviour holds for Balance Sheet, Cash Flows, and Equity statements before broadening the change.
2. Regenerate the official outputs (`render_viewer_to_xlsx.py` for 2022 and `ensemble_to_xlsx.py` for the multi-year workbook) so downstream consumers pick up the leaner Income Statement.
3. Evaluate caching or persisting the parsed signature maps; current implementation re-parses the HTML every run which adds overhead for ensemble batches.
