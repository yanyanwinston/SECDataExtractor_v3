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

## Proposed Next Steps
1. Adjust the member-label cleaning so dimensional qualifiers remain visible (e.g., retain `[Member]`, append the axis short name, or map to a human-readable suffix).
2. Regenerate `tsla-multi-year.xlsx` and verify that the formerly duplicated rows now display distinct labels.
3. Spot-check additional multi-year exports to ensure the updated labelling strategy improves clarity without introducing regressions.
