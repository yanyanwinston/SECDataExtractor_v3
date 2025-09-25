# Repository Guidelines

## Project Structure & Module Organization
- `src/sec_downloader/` hosts EDGAR clients, retry helpers, and download models; keep network code there.
- `src/processor/` provides presentation parsing, Arelle adapters, and Excel generation utilities.
- Root scripts (`download_filings.py`, `render_viewer_to_xlsx.py`) orchestrate full runs; add new executables beside them.
- Documentation lives in `docs/` and `SPEC.md`; fixtures in `tests/fixtures/`; generated data stays in `downloads/`, `output/`, and `temp/`.

## Build, Test, and Development Commands
- `./setup.sh` builds the virtualenv, installs `requirements.txt`, and prepares working directories.
- `source venv/bin/activate && pip install -r requirements.txt` keeps dependencies current during iterative work.
- `python download_filings.py --ticker AAPL --form 10-K --count 1` downloads sample filings.
- `python render_viewer_to_xlsx.py --filing downloads/.../viewer.json --out output/sample.xlsx` validates processing end-to-end.
- `pytest` runs the suite; use `pytest tests/test_presentation_models.py -k row` for focused cases.

## Coding Style & Naming Conventions
- Follow PEP 8 with four-space indentation; prefer `snake_case` names and `PascalCase` dataclasses or enums.
- Preserve type hints and short docstrings, mirroring patterns in `src/processor/presentation_models.py`.
- Format with `black .`; lint via `flake8 src tests`; run `mypy src` when types change.
- Mirror filename patterns (`*_processor.py`, `*_parser.py`, `*_generator.py`) so modules surface their role.

## Testing Guidelines
- Build pytest modules under `tests/` using `test_<feature>.py` names and descriptive function titles.
- Share samples through `tests/fixtures/viewer_schema_samples.json`; update fixtures instead of inlining payloads.
- Add regression tests whenever parser logic, Excel layout, or downloader behavior shifts.
- Aim to leave coverage steady or higher; capture new failure modes with targeted parametrized tests.

## Commit & Pull Request Guidelines
- Use `type(scope): summary` commit subjects (e.g., `feat(refactor): integrate presentation parser`) in imperative mood.
- Keep subject lines ≤72 characters and elaborate in the body when necessary.
- PRs should state context, approach, and validation; attach viewer JSON snippets or workbook diffs when helpful.
- Run `pytest`, `black`, `flake8`, and relevant scripts locally before requesting review.

## Security & Configuration Tips
- Do not commit secrets or raw filings; `downloads/`, `output/`, and `temp/` are git-ignored scratch directories.
- Manage Arelle and iXBRL versions through `requirements.txt`; document upgrades in `docs/` and adjust `setup.sh` if flags change.
- Surface any new environment variables in documentation and provide safe defaults in automation scripts.
