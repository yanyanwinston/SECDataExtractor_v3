# Developer Guide

A reference for contributors extending SECDataExtractor v3. It captures environment
setup, project layout, validation steps, and the release checklist.

## Environment setup
1. Install Python 3.10+ and ensure `python` points at the correct interpreter.
2. Run the bootstrap script (creates `venv/`, installs requirements, prepares
   directories):
   ```bash
   ./setup.sh
   ```
3. Activate the virtual environment when working interactively:
   ```bash
   source venv/bin/activate
   ```
4. After editing dependencies, run `pip install -r requirements.txt` and capture the
   change in the PR description.

## Repository layout
- `src/sec_downloader/` – EDGAR search, models, download orchestration
- `src/processor/` – presentation-first parsing pipeline and Excel generator
- `download_filings.py`, `render_viewer_to_xlsx.py`, `download_and_render.py` – CLI
  entry points at the repository root
- `tests/` – automated regression suites (`pytest`)
- `docs/` – long-form documentation (this file, architecture, user guide, CLI)
- `downloads/`, `output/`, `temp/` – working directories created by CLIs

## Onboarding checklist
- Read `docs/inline-viewer-pipeline.md` to understand how Arelle emits
  `ixbrl-viewer.htm`, how we prioritise MetaLinks sources, and where to inspect
  temp artifacts during triage.

## Coding conventions
- Follow PEP 8 with four-space indentation, descriptive names, and rich type hints.
- Dataclasses and enums use PascalCase; everything else sticks to snake_case.
- Keep helpers lean—prefer direct solutions before introducing abstractions.
- Value formatting defaults to millions; think carefully before introducing new
  scaling behaviours.

## Validation commands
Run the following before submitting a change:
```bash
PYTHONPATH=. pytest
black .
flake8 src tests
mypy src
```
For pipeline changes, include at least one live filing run in the PR description:
```bash
python download_filings.py --ticker TSLA --form 10-K --count 1
python render_viewer_to_xlsx.py --filing downloads/TSLA/10-K_*/tsla-*.htm --out output/tsla.xlsx
```

## Working with Arelle
- `ArelleProcessor.check_arelle_available()` verifies installation; the renderer will
  attempt to `pip install arelle` automatically if needed.
- Use `--verbose --keep-temp` to retain the temp directory where `ixbrl-viewer.htm`
  and `MetaLinks.json` are stored.
- When debugging failing filings, start by inspecting the saved `viewer.json` file
  produced via `--save-viewer-json`.
- Concept labels merge MetaLinks metadata with the local label linkbase. When MetaLinks
  omits issuer-specific captions, the extractor now reads `*_lab.xml` to repopulate terse and
  total labels before parsing presentation trees.

## Tests overview
- `tests/test_presentation_parser.py` – ensures MetaLinks filtering, label handling,
  and statement classification remain stable.
- `tests/test_integration_presentation.py` – presentation-first path integration
  coverage.
- `tests/test_excel_generator.py` – regression tests for sheet layout and scaling.
- `test_processor.py` – manual harness (skipped by default).

## Release checklist
1. Run `PYTHONPATH=. pytest` on a clean workspace.
2. Execute `black`, `flake8`, `mypy` and ensure no warnings remain.
3. Process the TSLA fixture end-to-end and compare column headers against
   `Financial_Report.xlsx`; adjust calendar-aware labels if needed.
4. Sweep a representative set of filings (10-K + 10-Q) to confirm dimensional
   breakdowns and scale hints behave.
5. Update documentation (README, user guide, CLI reference) with any new behaviour.
6. Record validation commands and key findings in the PR summary before tagging a
   release.

## Getting support
- Open issues in this repository for bugs and enhancement requests.
- Cross-reference historical specs in `docs/11-refactor-spec-v3.1.md` and
  `CLAUDE.md` when making architectural changes.
- When in doubt, prioritise the minimal fix that keeps the presentation-first
  pipeline correct, then iterate.
