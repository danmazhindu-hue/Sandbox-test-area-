# fieldcode

A small, local-only command-line tool for coding ethnographic fieldnotes. Python 3.9+, standard library only.

It reads markdown fieldnotes, lets you tag passages with four fixed codes (`sop`, `expertise_status`, `technology`, `classification`) plus free-text codes, keeps the tags in a JSON file beside each note, and reports passages and counts grouped by **field site** and **agency** (Mountain Rescue, Lowland Rescue, Police Force A, Police Force B).

> Everything under `sample_notes/` is **invented**. No real person, team, force or incident is described.

## Quick start

```bash
python3 fieldcode.py --notes-dir sample_notes list
python3 fieldcode.py --notes-dir sample_notes show mr_aldermoor_01.md
python3 fieldcode.py --notes-dir sample_notes tag mr_aldermoor_01.md 3 expertise_status --free "informal authority"
python3 fieldcode.py --notes-dir sample_notes untag mr_aldermoor_01.md 3 --free "informal authority"
python3 fieldcode.py --notes-dir sample_notes summary                 # code x agency counts
python3 fieldcode.py --notes-dir sample_notes summary --by site --free-detail
python3 fieldcode.py --notes-dir sample_notes export --code sop       # passages by code > site > agency
python3 fieldcode.py --notes-dir sample_notes export --code "free:ritual" --out exports/ritual.md
python3 fieldcode.py --notes-dir sample_notes search "paper map" --agency "Mountain Rescue"
python3 fieldcode.py --notes-dir sample_notes check                   # missing metadata, stale tags
python3 -m unittest discover -s tests
```

For real work: `python3 fieldcode.py init`, put notes in `notes/` (the default `--notes-dir`), and drop the flag.

## Point-and-click page (`fieldcode.html`)

Prefer not to use the terminal? Open `fieldcode.html` by double-clicking it (use **Chrome or Edge** for automatic saving). Click **Open notes folder…**, choose `sample_notes` to try it (or your own `notes/`), then:

- **Start a new log:** click **+ New note**, pick the date, agency and field site (and an optional title), and type or paste what you observed. Leave a blank line between passages, since each paragraph becomes one passage you can code. **Create and start coding** saves it into your folder as `YYYY-MM-DD_site_agency.md`, and you can add more text to the end of a note later with **Add more text to this note**. Existing passages and their tags are never changed by adding text. Starting from an empty folder works too. (Edit older text in a normal text editor, and the page will flag the affected tags as stale.)
- **Code notes:** pick a note on the left; click the code buttons under each passage (or press `1`-`4`; `j`/`k` move between passages). Type a free-text code and press Enter. Every click updates the counts and, in Chrome/Edge, is written straight into the same `.tags.json` files the command-line tool uses, so the two always agree.
- **Summary:** the count table, by agency or by field site.
- **Passages by code:** everything per code, grouped by site and agency. Copy it or download it as markdown.
- **Search:** text or regex, filtered by code, site or agency.

Firefox and Safari can't write into a folder, so there the page works in an edit-in-memory mode and you finish with **Download changed files** (new notes and tag files), then put the downloaded files into your notes folder. If you edit a note's text later, affected passages show a warning and you choose to keep or discard their tags.

How it stays private: it is one self-contained file with no libraries, fonts or images fetched from anywhere. A content-security-policy inside it blocks every network request (`default-src 'none'`), and it never uses browser storage, so your text lives only in the page's memory and the files you choose to save. Note text is always HTML-escaped. Tests check the policy and that the page agrees with the Python tool.

## Note format

```markdown
---
site: Aldermoor Fell
agency: Mountain Rescue
date: 2024-03-02
---

# Headings are ignored

Each blank-line-separated paragraph is one passage, numbered from 1.
```

`agency` must be exactly one of Mountain Rescue, Lowland Rescue, Police Force A, Police Force B (case and punctuation are ignored; no trailing comments on the line). `check` reports anything else.

Tags for `foo.md` live in `foo.tags.json`. Each tagged passage stores its number, a short SHA-256 of its text, and its codes. If you later edit a passage, `check` flags the tag as **stale** and it is excluded from export, summary and tagged search, rather than silently attaching a code to the wrong text. Fixed codes are validated (typos are rejected with a suggestion); anything free-form must go through `--free`.

## Privacy design

Real fieldnotes about named emergency responders, incidents and casualties are sensitive. The design aims to make the safe path the default and the unsafe path hard to take by accident.

**What the code enforces**

- **No network.** The program imports no networking modules and makes no calls; a test fails if one is added. It has no dependencies, so there is nothing to download, no telemetry and no update check.
- **Confined to this folder.** Notes directory, `--out` paths and tag files must resolve (symlinks followed) inside the project folder; anything else is refused. A symlink inside `notes/` that points elsewhere is skipped with a warning.
- **Owner-only files.** Tag files and exports are written atomically with mode `0600`; `init` creates folders as `0700`.
- **No hidden copies.** No logs, caches, history or temp files are left behind (the atomic-write temp file is renamed or deleted). Passage text is never copied into the tag files, only a 12-character hash plus your codes. Exports, which do contain note text, are written only when you ask for them.
- **Git cannot take real data by accident.** `.gitignore` excludes `notes/`, `exports/` and every `*.tags.json` except the invented ones in `sample_notes/`.

**What it does not do (your responsibility)**

- **It does not encrypt.** Protect the folder with full-disk encryption (FileVault, BitLocker, LUKS) or keep it on an encrypted volume. File modes only help on shared Unix machines.
- **`.gitignore` is not a guarantee.** `git add -f` overrides it. Check `git status` before committing.
- **Do not use real notes where the code runs remotely.** This repository has been used in a cloud Claude Code session, where the working copy sits on a remote machine. Real notes should only ever live on your own computer, and you should not paste them into any hosted assistant or ask one to read them unless your ethics approval and data-management plan allow it.
- **Pseudonymise at source.** Use pseudonyms for people and places in the notes, and keep the key elsewhere. Tags and exports are as identifying as the notes they quote.
- **Backups, sync and shared drives.** Cloud-sync folders (Dropbox, OneDrive, iCloud) copy files off the machine. Keep the project folder out of them unless your data-management plan permits it.
- **Retention.** Delete `notes/`, `exports/` and the tag files when the project's retention period ends. `shred`-style deletion is not reliable on SSDs; rely on disk encryption plus key destruction.

Check your institution's ethics approval, consent terms and data-protection obligations (for example UK GDPR) before putting real notes into any tool.

## Layout

- `fieldcode.py`: the command-line tool
- `fieldcode.html`: the point-and-click page (same tag files)
- `sample_notes/`: invented notes plus example tags
- `tests/`: unit tests (`python3 -m unittest discover -s tests`); `tests/html_smoke.mjs` is an optional browser check (`node tests/html_smoke.mjs`, needs Playwright)
