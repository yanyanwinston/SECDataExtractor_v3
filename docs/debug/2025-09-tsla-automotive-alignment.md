# TSLA multi-year automotive alignment regression

## Context
- Workbook: `output/tsla-multi-year.xlsx`
- Trigger: review of Income Statement tab on 2025-09-30 surfaced misaligned automotive revenue / cost rows for 2025–2021 periods.
- Pipeline: `ensemble_to_xlsx.py` (presentation-first multi-filing aggregation).

## Repro steps
1. Generate the ensemble workbook (already present in `output/tsla-multi-year.xlsx`).
2. Inspect `Income Statement` sheet: rows labelled `Automotive sales`, `Automotive leasing`, `Automotive regulatory credits`, etc. show 2025–2024 values on the anchor rows while 2023–2021 values appear on separate trailing rows.
3. Use openpyxl to dump affected rows:
   ```bash
   python - <<'PY'
   from openpyxl import load_workbook
   wb = load_workbook('output/tsla-multi-year.xlsx', data_only=True)
   ws = wb['Income Statement']
   targets = {
       'Automotive sales',
       'Automotive leasing',
       'Automotive regulatory credits',
       'Automotive Revenues',
       'Total automotive revenues',
       'Automotive Cost of Revenues',
   }
   for r in range(3, ws.max_row + 1):
       label = ws.cell(r, 1).value
       if label in targets:
           row = [ws.cell(r, c).value for c in range(1, 7)]
           if any(row[1:]):
               print(r, row)
   PY
   ```
   Output confirms duplicate rows with single-period coverage for 2023–2021.

## Investigation
- Ensemble alignment logic in `src/processor/ensemble.py:_rows_match` short-circuits when `dimension_signature` differs.
- Anchor filing (2024/2025) embeds `dimension_signature=(('productorserviceaxis', 'automotivesalesmember'), …)` on automotive rows.
- Older filings (2023–2021) expose broader members such as `automotiverevenuesmember` and occasionally add `statementbusinesssegmentsaxis`.
- Because `_rows_match` rejects any signature mismatch, historical rows bypass the anchor skeleton and get appended via `_populate_additional_rows`, producing period islands.
- Confirmed by regenerating viewer JSON for historical filings:
  ```bash
  # 2023
  python -m arelle.CntlrCmdLine --plugins iXBRLViewerPlugin \
    --file temp/analysis_temp/extract_574/tsla-20231231.htm \
    --save-viewer temp/analysis_temp/arelle_output_4604/ixbrl-viewer.htm
  python - <<'PY'
  from src.processor import ViewerDataExtractor, DataParser, ValueFormatter
  extractor = ViewerDataExtractor()
  viewer = extractor.extract_viewer_data('temp/analysis_temp/arelle_output_4604/ixbrl-viewer.htm')
  stmt = next(s for s in DataParser(ValueFormatter()).parse_viewer_data(viewer).statements
              if 'operations' in s.name.lower())
  for row in stmt.rows:
      if row.label and 'Automotive' in row.label:
          print(row.label, row.dimension_signature)
  PY
  ```
  - 2024/2025 rows use member-specific signatures (`automotiveleasingmember`, `automotivesalesmember`).
  - 2023 rows mostly point to `automotiverevenuesmember` for the same labels.
  - 2022/2021 filings mix additional segment axes (`statementbusinesssegmentsaxis`) and extension concepts (`ns0:AutomotiveSalesRevenue`).

## Hypothesis
We need to tolerate controlled cardinality changes on axes like `ProductOrServiceAxis`. When the anchor presents a more granular member but the candidate filing uses a broader one (or vice versa) and other invariants (label depth, parent path) match, we should align them instead of creating extra rows.

## Next steps
- Prototype a relaxed `_rows_match` branch that attempts axis/member normalization before enforcing strict equality (e.g., map `automotiverevenuesmember` ↔︎ child members). Keep scope narrow to avoid collapsing genuinely distinct dimension slices.
- Add an ensemble-focused regression test (2025 anchor + 2023 filing) to ensure automotive lines coalesce onto single rows.
- Sweep remaining statements for similar axis drift (e.g., service/energy segments) once the matcher change lands.
- Document validation by re-running `ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 5 --out output/tsla-multi-year.xlsx` after the fix.
