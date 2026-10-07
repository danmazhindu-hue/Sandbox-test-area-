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

## Note format

```markdown
---
site: Aldermoor Fell
agency: Mountain Rescue        # Mountain Rescue | Lowland Rescue | Police Force A | Police Force B
date: 2024-03-02
---

# Headings are ignored

Each blank-line-separated paragraph is one passage, numbered from 1.
```

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

- `fieldcode.py`: the whole tool
- `sample_notes/`: invented notes plus example tags
- `tests/`: unit tests (`python3 -m unittest discover -s tests`)
