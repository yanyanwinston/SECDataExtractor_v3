# Repository Guidelines

## Project Snapshot
- SECDataExtractor v3 turns SEC iXBRL filings into Excel workbooks using a presentation-first pipeline.
- Flow: filing source → Arelle viewer plugin → viewer JSON + MetaLinks → presentation models → fact matching → Excel.
- Primary modules live under `src/processor/` (parsing, matching, Excel) and `src/sec_downloader/` (EDGAR search + download).

## Entry Points
- `download_filings.py` – search and download 10-K/10-Q filings (tickers, CIKs, or batch files).
- `render_viewer_to_xlsx.py` – convert any iXBRL filing (URL, local HTML, ZIP) into an Excel workbook.
- `download_and_render.py` – orchestrates download + render for portfolios, depositing workbooks in `output/`.

## Working Directories
- `downloads/` – raw filings pulled from EDGAR.
- `output/` – generated Excel files.
- `temp/` – temporary artefacts preserved only when `--keep-temp` is passed.

## Daily Commands
```bash
./setup.sh                        # bootstrap venv and install requirements
source venv/bin/activate          # optional for local shells
PYTHONPATH=. pytest               # run regression suite
black . && flake8 src tests       # formatting + linting
mypy src                          # type checks when contracts change
```
Run at least one live filing before shipping changes:
```bash
python download_filings.py --ticker TSLA --form 10-K --count 1
python render_viewer_to_xlsx.py --filing downloads/TSLA/10-K_*/tsla-*.htm --out output/tsla.xlsx
```

## Coding Standards
- PEP 8, four-space indentation, descriptive names, and rich type hints.
- Dataclasses/enums use PascalCase; everything else stays snake_case.
- Keep helpers lean and purposeful; prefer direct fixes before introducing new abstraction layers.
- Value formatting defaults to millions and respects negative XBRL decimals; add new scaling paths only with clear justification.

## Testing & Validation
- `tests/test_presentation_parser.py` guards statement filtering, label handling, and MetaLinks metadata.
- `tests/test_integration_presentation.py` covers the presentation-first pipeline.
- `tests/test_excel_generator.py` asserts sheet layout, dimensional expansion/collapse, and scaling behaviour.
- `test_processor.py` remains a manual harness (skipped by default).

## Documentation
- Canonical docs live in `docs/`: `architecture.md`, `user-guide.md`, `cli-reference.md`, `developer-guide.md`.
- Historical specs: `docs/11-refactor-spec-v3.1.md`, `SPEC.md`, `CLAUDE.md`.
- Update README and the docs whenever behaviour changes; capture validation commands in PR summaries.

## Release Checklist
1. `PYTHONPATH=. pytest`
2. `black .`, `flake8 src tests`, `mypy src`
3. Run the TSLA end-to-end pipeline and compare headers against `Financial_Report.xlsx` once column polishing lands.
4. Sweep representative 10-K/10-Q filings to confirm dimensional handling, scaling, and disclosures.
5. Refresh documentation and note CLI additions or behaviour changes.
6. Record commands + findings in the release notes before tagging.

## Current Status
- Presentation-first pipeline (Phase 3) is stable; TSLA regression run is green.
- Outstanding polish: calendar-aware column headers and the broader regression sweep before release tagging.
- MetaLinks `groupType` filter keeps primary statements by default; pass `--include-disclosures` to surface schedules and cover pages.
