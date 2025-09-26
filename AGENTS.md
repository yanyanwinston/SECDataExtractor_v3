# Repository Guidelines

## Architecture Snapshot
- Pipeline: filing → Arelle viewer plugin → viewer JSON → presentation models → Excel.
- Lean on `arelle-release`, `ixbrl-viewer`, and `openpyxl`; consume the viewer JSON directly instead of rebuilding statements from facts.
- Follow the MVP discipline in `CLAUDE.md`: solve the immediate problem first, then refine.

## Project Structure & Ownership
- `src/sec_downloader/` owns EDGAR networking; `src/processor/` owns presentation parsing, fact matching, and Excel output.
- CLI entry points live at the repo root (`download_filings.py`, `render_viewer_to_xlsx.py`); keep new tools beside them.
- Long-form docs are under `docs/` (see `11-refactor-spec-v3.1.md`), fixtures under `tests/fixtures/`, and scratch results in `downloads/`, `output/`, and `temp/`.

## Build & Run Essentials
- `./setup.sh` creates the venv, installs dependencies, and scaffolds working directories.
- Activate with `source venv/bin/activate`; rerun `pip install -r requirements.txt` after dependency edits.
- Fetch a sample filing via `python download_filings.py --ticker AAPL --form 10-K --count 1`.
- Validate the pipeline with `python render_viewer_to_xlsx.py --filing downloads/<ticker>/<viewer>.json --out output/sample.xlsx`.
- Test with `PYTHONPATH=. pytest`; narrow scope using `-k` filters when iterating.

## Coding Style & Conventions
- PEP 8, four-space indentation, rich type hints; dataclasses/enums stay `PascalCase`, everything else `snake_case`.
- Keep helpers lightweight and purposeful—only add layers when the current path fails a concrete need.
- Format with `black .`, lint via `flake8 src tests`, and run `mypy src` when typing surfaces new contracts.

## Testing & Validation
- Mirror existing layout: `tests/test_<area>.py` plus shared payloads in `tests/fixtures/viewer_schema_samples.json`.
- Extend regression coverage whenever presentation traversal, fact matching, or Excel layout changes; prefer parametrized cases.
- `test_processor.py` remains a skipped manual harness—rely on the automated suite for CI.

## Workflow & PRs
- Commit subjects follow `type(scope): summary` (e.g., `feat(refactor): align fact matcher`), ≤72 chars, imperative mood.
- PRs outline context, approach, and validation commands; attach viewer JSON snippets or Excel diffs when clarifying impact.
- Before review, run `PYTHONPATH=. pytest`, `black`, `flake8`, plus anything specific to changed modules, and document config shifts in `docs/` or CLI help.

- Phases 1–2 shipped: viewer schema captured in `docs/11-refactor-spec-v3.1.md`; presentation models live in `src/processor/presentation_models.py`.
- Phase 3.1–3.2 integrated: `PresentationParser`, `FactMatcher`, and `DataParser` run the presentation-first path, applying the MetaLinks `groupType` strategy you surfaced so we keep the primary financial statements and drop disclosure-only roles, then pick periods per statement using `DocumentPeriodEndDate` fallbacks.
- Phase 3.3 additions: CLI now exposes `--label-style`, `--save-viewer-json`, and `--no-scale-hint`; `FactMatcher` applies XBRL scale hints only for negative decimals while `ValueFormatter` stays in millions by default; label defaults remain `terseLabel` but are switchable.
- Phase 4 prep: Excel generator consumes the new tables, but column header polish (calendar-aware labels) and quarterly vs annual configuration remain open; compare TSLA workbook against `Financial_Report.xlsx` once headers are fixed.
- Regression status: updated suites in `tests/test_presentation_parser.py`, `tests/test_integration_presentation.py`, and `tests/test_excel_generator.py` cover statement filtering, label toggles, and scaling; live filing sweep + period header assertions still pending before release tagging.
