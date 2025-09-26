# Period Selection Debug Notes

## Where periods come from
- `output/viewer-data.json`: Arelle viewer payload saved after `render_viewer_to_xlsx.py` runs (`sourceReports[0].targetReports[0]`).
  - `facts`: compressed fact contexts (`'p'` field holds the period – instant `YYYY-MM-DD` or duration `start/end`).
  - `concepts`: label metadata.
- `downloads/TSLA/10-K_2025-01-29/MetaLinks.json`: role metadata (`groupType`, `subGroupType`) **and** concept label roles (since the latest extractor stores `concept_labels`).

## Code path (per statement)
1. `render_viewer_to_xlsx.py` → `ViewerDataExtractor.extract_viewer_data`
   - Loads MetaLinks, builds `role_map` and `concept_labels`.
2. `PresentationParser.parse_presentation_statements`
   - Builds `PresentationStatement`s with concept lists and MetaLinks metadata.
3. `DataParser._filter_presentation_statements`
   - Keeps `groupType == "statement"` (unless `--include-disclosures`).
4. For each statement (`DataParser._parse_with_presentation`)
   - Collect concepts via `_collect_concepts_from_statement`.
   - `FactMatcher.extract_periods_from_facts` filters facts to those concepts → returns `Period` objects (label, end date, instant flag).
   - `_extract_document_period_end_dates` parses all `dei:DocumentPeriodEndDate` facts → `List[datetime]`.
   - `_select_periods_for_statement`
     - Sorts the statement’s periods (instants vs durations).
     - Tries to match each `DocumentPeriodEndDate` to an instant/duration (±1 day tolerance).
     - Balance sheet → up to 2 instants; other primaries → up to 3 durations.
     - `_format_period_display_label` currently formats as `%b %d, %Y`.
   - `FactMatcher.match_facts_to_statement` builds rows/cells using the selected periods.

## Useful inspection commands
```bash
# 1. Inspect document period end dates in the parsed viewer data
python - <<'PY'
import json
from src.processor.data_parser import DataParser
from src.processor.value_formatter import ValueFormatter
viewer = json.load(open('output/viewer-data.json'))
parser = DataParser(ValueFormatter(scale_millions=False))
print(parser._extract_document_period_end_dates(viewer))
PY
```

```bash
# 2. See which periods were selected for each statement
python - <<'PY'
import json
from src.processor.data_parser import DataParser
from src.processor.value_formatter import ValueFormatter
viewer = json.load(open('output/viewer-data.json'))
parser = DataParser(ValueFormatter(scale_millions=False))
statements = parser._filter_presentation_statements(parser.presentation_parser.parse_presentation_statements(viewer))
facts = parser._extract_facts_from_viewer_data(viewer)
for stmt in statements:
    periods = parser._select_periods_for_statement(
        stmt,
        parser.fact_matcher.extract_periods_from_facts(
            facts,
            parser._collect_concepts_from_statement(stmt)
        ),
        parser._extract_document_period_end_dates(viewer)
    )
    print(stmt.statement_name, [f"{p.label} -> {p.end_date} (instant={p.instant})" for p in periods])
PY
```

```bash
# 3. Inspect raw fact contexts for a concept (e.g., cash & cash equivalents)
python - <<'PY'
import json
viewer = json.load(open('output/viewer-data.json'))
facts = viewer['sourceReports'][0]['targetReports'][0]['facts']
concept = 'us-gaap:CashAndCashEquivalentsAtCarryingValue'
for fact_id, contexts in facts.items():
    for ctx, data in contexts.items():
        if isinstance(data, dict) and data.get('c') == concept:
            print(fact_id, data['p'])
PY
```

These commands help answer:
- Did we read the expected end dates (`Dec 31, 2024`, `Dec 31, 2023`) from the filing?
- Do the balance-sheet facts use instants near those dates (tolerance might need widening)?
- Are there additional axes creating duplicate contexts that should be collapsed earlier?

## Next debugging steps
- If only one `DocumentPeriodEndDate` is present, add a fallback (e.g., use the top two instants when aligning fails).
- Consider widening the tolerance (±7 days) or snapping to known fiscal year ends when differences are small.
- Add logging/diagnostics for cases where `_select_periods_for_statement` returns fewer periods than requested (so we can see why the second instant drops).
- Extend tests to assert the exact end dates once we stabilise the heuristics.
