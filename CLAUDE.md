# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`fieldcode.py` is a single-file, standard-library-only, local-only CLI for coding ethnographic fieldnotes (see README.md for usage and the privacy design).

- Test: `python3 -m unittest discover -s tests` (one test: `python3 -m unittest tests.test_fieldcode.TagTests.test_stale_detection`)
- Try it on the invented data: `python3 fieldcode.py --notes-dir sample_notes summary`

Constraints that must be preserved:
- No network access and no third-party dependencies (a test scans the imports).
- All file access goes through `require_inside`/`inside_root`; files are written with `write_private` (mode 0600).
- Real data lives only in `notes/` and `exports/` (git-ignored). Never read, create or commit real fieldnotes; use only the invented `sample_notes/`.
- Tags are keyed by passage number plus a text hash. Editing a passage makes its tags stale on purpose, so do not renumber or "heal" tags automatically.
- Fixed codes are `FIXED_CODES`; free-text codes are stored lowercase and addressed as `free:<text>`.

`fieldcode.html` is a second, self-contained front end over the same `.tags.json` files (no build step). It re-implements the parsing, SHA-256 passage hash, summary and markdown export in JS, so any change to those in `fieldcode.py` must be mirrored there. Keep its CSP (`default-src 'none'`), and do not add `fetch`, browser storage, external scripts/styles/fonts or any URL. `node tests/html_smoke.mjs` (needs Playwright; set `PLAYWRIGHT_MODULE` to its path if not resolvable) checks it against the Python output.
