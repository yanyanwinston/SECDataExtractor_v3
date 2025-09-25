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

## Current Refactor Status (v3.1)
- Phases 1 and 2 (viewer JSON analysis and presentation data models) shipped earlier in the cycle.
- Phase 3.1 (presentation parser) and Phase 3.2 (fact matcher) now consume viewer order, preferred labels, and sorted periods.
- Next focus: Phase 3.3 integration into `DataParser`, followed by Excel generator updates (Phase 4+) to close the presentation-first pipeline.
