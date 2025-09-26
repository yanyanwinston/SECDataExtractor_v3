# SECDataExtractor v3

SECDataExtractor v3 turns SEC iXBRL filings into analysis-ready Excel workbooks. The
pipeline leans on Arelle's iXBRL viewer output, preserves the native presentation
structure, and exposes simple CLIs for downloading, inspecting, and exporting
financial statements.

## Why it exists
- Automates the end-to-end "download → viewer JSON → Excel" workflow
- Keeps the statement order, headers, and dimensional breakdown from the official
  filing instead of rebuilding tables from facts
- Ships with download, render, and combined entry points so you can script nightly
  refreshes or ad-hoc pulls in a few commands

## Quickstart in three commands
1. Bootstrap the workspace (creates the venv, installs dependencies, prepares folders):
   ```bash
   ./setup.sh
   ```
2. Grab a sample filing:
   ```bash
   python download_filings.py --ticker AAPL --form 10-K --count 1
   ```
3. Render it to Excel (choose the viewer JSON produced by the downloader):
   ```bash
   python render_viewer_to_xlsx.py \
     --filing downloads/AAPL/10-K_*/aapl-*.htm \
     --out output/aapl-10k.xlsx
   ```

Need everything in one pass? `download_and_render.py` downloads the latest 10-K/10-Q
set for each ticker and stores the generated workbooks under `output/`.

## Pipeline at a glance
1. **Filing intake** (`InputHandler`) normalises URLs, local files, or ZIP archives.
2. **Viewer generation** (`ArelleProcessor`) runs Arelle with the iXBRL viewer plugin
   and emits `ixbrl-viewer.htm` alongside `MetaLinks.json` when available.
3. **JSON extraction** (`ViewerDataExtractor`) pulls the embedded viewer payload,
   stitches in MetaLinks role metadata, and builds the concept label map.
4. **Presentation-first parsing** (`PresentationParser`, `FactMatcher`, `DataParser`)
   filters to primary statements (unless `--include-disclosures` is set), picks
   periods using `DocumentPeriodEndDate` fallbacks, expands dimensional members, and
   formats values in millions by default while respecting negative scale hints.
5. **Workbook generation** (`ExcelGenerator`) writes one sheet per statement, applies
   indentation and bolding based on presentation metadata, and can collapse to the
   latest period with `--one-period`.

## Key entry points
- `download_filings.py` – EDGAR search + download with retry logic and exhibit
  controls
- `render_viewer_to_xlsx.py` – convert any iXBRL filing (URL, local, ZIP) to Excel
- `download_and_render.py` – queue tickers/CIKs and send the results straight to
  `output/`

Each CLI shares a consistent `--verbose` flag and surfaces important toggles such as
`--label-style`, `--dimension-breakdown` / `--collapse-dimensions`, and
`--save-viewer-json`. See the [CLI reference](docs/cli-reference.md) for full syntax.

## Documentation map
- [Architecture & Pipeline](docs/architecture.md)
- [User Guide & Quickstart](docs/user-guide.md)
- [CLI Reference](docs/cli-reference.md)
- [Developer Guide](docs/developer-guide.md)
- Historical design notes: `docs/11-refactor-spec-v3.1.md`, `CLAUDE.md`

## Project status
- Phase 3 presentation-first workflow is live; TSLA end-to-end validation is green.
- Outstanding polish: calendar-aware column headers plus the broad regression sweep
  before release tagging.
- Test suite: `PYTHONPATH=. pytest` covers presentation filtering, dimensional
  expansion/collapse, scaling, and Excel layout. `test_processor.py` remains a manual
  harness.

## Getting help
Open issues in this repository or extend the docs. When editing code, follow PEP 8,
run `black`, `flake8`, and `mypy`, then capture validation commands in your PR body.
