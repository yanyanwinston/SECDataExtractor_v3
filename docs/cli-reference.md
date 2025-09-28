# CLI Reference

This reference covers the supported entry points: `download_filings.py`,
`render_viewer_to_xlsx.py`, `download_and_render.py`, and `ensemble_to_xlsx.py`.
Each script supports `--help` for inline documentation; the tables below
highlight the arguments that impact behaviour most.

## download_filings.py
Download 10-K/10-Q filings from EDGAR.

### Usage
```bash
python download_filings.py [--ticker AAPL | --cik 0000320193 | --input-file tickers.txt] \
  [--form 10-K,10-Q] [--count 4] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] \
  [--include-amendments] [--output-dir downloads] [--include-exhibits] \
  [--flat-structure] [--max-parallel 3] [--timeout 30] [--retries 3] [--verbose]
```

### Notable options
- `--ticker`, `--cik`, `--input-file` – choose one. Files may contain comments using
  `#` prefixes.
- `--form` – comma separated (default `10-K,10-Q`). `--include-amendments` adds `/A`
  filings to the result set.
- `--count` – cap per identifier; combine with date ranges for fine control.
- `--output-dir` – root directory for downloads. Subdirectories for each ticker and
  filing are created unless `--flat-structure` is passed.
- `--include-exhibits` – pull exhibit attachments (increases download volume).
- `--max-parallel`, `--timeout`, `--retries` – network tuning knobs.
- `--quiet` suppresses progress and summary noise; `--verbose` enables debug logging.

## render_viewer_to_xlsx.py
Convert a single iXBRL filing into an Excel workbook using the presentation-first
pipeline.

### Usage
```bash
python render_viewer_to_xlsx.py --filing <PATH|URL|ZIP> --out output.xlsx \
  [--one-period | --periods "2024,2023"] [--currency USD] \
  [--scale-millions | --scale-none] [--label-style {terse,standard}] \
  [--dimension-breakdown | --collapse-dimensions] [--include-disclosures] \
  [--dump-role-map roles.csv] [--save-viewer-json viewer.json] \
  [--no-scale-hint] [--temp-dir tmpdir] [--keep-temp] [--timeout 300] [--verbose]
```

### Notable options
- `--filing` accepts SEC URLs, local HTML files, or ZIP archives. ZIP inputs are
  unpacked and the largest HTML file is used as the primary document.
- `--scale-millions` is enabled by default; pass `--scale-none` for raw numbers.
- `--no-scale-hint` disables decimals-based adjustments from the XBRL facts.
- `--label-style` controls which concept labels the presentation parser prefers.
- `--dimension-breakdown` (default) expands axis/member combinations; use
  `--collapse-dimensions` for a rolled-up view.
- `--include-disclosures` surfaces roles with MetaLinks group types that are not
  primary statements.
- `--dump-role-map` / `--save-viewer-json` persist intermediate outputs for triage.
- `--one-period` keeps the latest period per statement; `--periods` accepts a
  comma-separated list of period labels or years and takes precedence when provided.
- `--temp-dir`, `--keep-temp`, and `--timeout` let you manage Arelle behaviour.

## download_and_render.py
End-to-end downloader + renderer for portfolios.

### Usage
```bash
python download_and_render.py [--ticker TSLA --ticker NFLX | --cik 0001318605] \
  [--input-file watchlist.txt] [--k-count 3] [--q-count 6] [--include-amendments] \
  [--download-dir downloads] [--excel-dir output] [--max-parallel 3] \
  [--download-timeout 30] [--retries 3] [--exhibits include|exclude] [--skip-verify] \
  [--label-style terse] [--collapse-dimensions] [--include-disclosures] \
  [--currency USD] [--scale-none] [--no-scale-hint] [--one-period] [--periods LIST] \
  [--render-timeout 300] [--render-temp-dir tmp] [--keep-temp] \
  [--dump-role-map roles.csv] [--save-viewer-json viewer.json] [--overwrite] \
  [--quiet] [--verbose]
```

### Notable options
- `--ticker/--cik/--input-file` mirror the downloader; arguments can repeat to build
  a portfolio.
- `--k-count` & `--q-count` define how many annual vs quarterly filings to fetch per
  identifier. `--q-count` now defaults to 0, so opt-in when you need 10-Q workbooks.
- `--download-dir` and `--excel-dir` let you separate raw filings from Excel output.
- Rendering flags (label style, dimensional behaviour, disclosures, period filters,
  scaling) are passed directly to the renderer.
- `--overwrite` replaces existing Excel files; otherwise previously generated files
  are skipped.
- `--dump-role-map` and `--save-viewer-json` operate per filing—results are stored
  alongside each Excel workbook.

## ensemble_to_xlsx.py
Create a single workbook that stitches multiple filings together column-by-column.

### Usage
```bash
python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 5 --out output/TSLA-ensemble.xlsx \
  [--include-amendments] [--download-dir downloads] [--max-parallel 2] \
  [--download-timeout 30] [--retries 3] [--currency USD] [--scale-none] \
  [--collapse-dimensions] [--include-disclosures] [--label-style terse] \
  [--no-scale-hint] [--timeout 300] [--temp-dir tmp] [--keep-temp] [--verbose]
```

### Notable options
- `--ticker`/`--cik` – choose a single identifier; the newest filing becomes the
  anchor that defines row ordering and labels.
- `--form` & `--count` – limit the form type (default `10-K`) and the number of
  filings to combine. Pass `--include-amendments` to allow `/A` variants.
- `--download-dir`, `--max-parallel`, `--download-timeout`, `--retries` – mirror the
  downloader controls for where and how filings are fetched.
- `--scale-none`, `--no-scale-hint`, `--collapse-dimensions`, `--include-disclosures`,
  `--label-style` – forwarded to the presentation-first parser so the ensemble
  matches single-filing workbooks.
- `--timeout`, `--temp-dir`, `--keep-temp` – manage Arelle execution and cleanup.
- Output workbook columns are sorted newest → oldest with one period per filing.

## Logging & environment tips
- Combine `--verbose` with `--keep-temp` during debugging to retain Arelle artefacts.
- Ensure the SEC user agent in `src/sec_downloader/` matches your email address when
  running in production environments.
- When scripting, check exit codes: all CLIs return non-zero when a fatal error
  occurs, allowing integration with cron or CI.
