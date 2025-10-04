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
- `src/api/` – FastAPI data endpoints and service layer for `/data`
- `src/sec_downloader/` – EDGAR search, models, download orchestration
- `src/processor/` – presentation-first parsing pipeline and Excel generator
- `download_filings.py`, `render_viewer_to_xlsx.py`, `download_and_render.py` – CLI
  entry points at the repository root
- `tests/` – automated regression suites (`pytest`)
- `docs/` – long-form documentation (this file, architecture, user guide, CLI)
- `downloads/`, `output/`, `temp/` – working directories created by CLIs

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

## Data API prototype
- The FastAPI application in `src/api/app.py` exposes `/data/{ticker}/filings` and
  `/data/{ticker}/filings/latest` for retrieving cached SEC filings.
- Requests surface local filings first; cache misses trigger on-demand downloads
  through the existing downloader stack.
- Consult `docs/openapi/data-api.yaml` for the OpenAPI 3.0 contract and sample
  payloads.
- Run the service locally with `uvicorn api.app:app --reload` (requires the
  `fastapi` and `uvicorn` dependency from `requirements.txt`).
- Import `docs/postman/data-api.postman_collection.json` into Postman for quick
  requests against a running instance.
- The filing and statement services keep in-memory caches (~5 minute default);
  adjust `cache_ttl` when constructing `FilingRetrievalService` or
  `StatementRetrievalService` for different horizons.
- Container workflow:
  ```bash
  docker build -t secdataextractor-api .
  docker run --rm -p 8000:8000 secdataextractor-api
  # or, with live volumes
  docker compose up --build
  ```
- Concept labels merge MetaLinks metadata with the local label linkbase. When MetaLinks
  omits issuer-specific captions, the extractor reads `*_lab.xml` to repopulate terse and
  total labels before parsing presentation trees.
- Fact matching collapses single-dimension concept facts back to the base line item when the
  dimension fingerprint is the same for every context. This prevents generic member names from
  replacing concept captions in legacy filings (e.g., TSLA 2022 automotive revenues).

## Working with Arelle
- `ArelleProcessor.check_arelle_available()` verifies installation; the renderer will
  attempt to `pip install arelle` automatically if needed.
- Use `--verbose --keep-temp` to retain the temp directory where `ixbrl-viewer.htm`
  and `MetaLinks.json` are stored.
- When debugging failing filings, start by inspecting the saved `viewer.json` file
  produced via `--save-viewer-json`.

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
