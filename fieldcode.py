#!/usr/bin/env python3
"""fieldcode: local-only coding of ethnographic fieldnotes.

Standard library only. No network access. All reads and writes are confined to
the folder containing this file (see ``inside_root``).
"""
import argparse
import difflib
import hashlib
import os
import re
import sys
import tempfile
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FIXED_CODES = ("sop", "expertise_status", "technology", "classification")
AGENCIES = ("Mountain Rescue", "Lowland Rescue", "Police Force A", "Police Force B")
UNKNOWN = "(unknown)"
FREE_PREFIX = "free:"

_AGENCY_ALIASES = {
    "mountain rescue": AGENCIES[0],
    "lowland rescue": AGENCIES[1],
    "police force a": AGENCIES[2],
    "police a": AGENCIES[2],
    "police force b": AGENCIES[3],
    "police b": AGENCIES[3],
}


# --------------------------------------------------------------------------
# Safety helpers
# --------------------------------------------------------------------------

def inside_root(path, root=ROOT):
    """True if ``path`` (symlinks resolved) lies inside ``root``."""
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def require_inside(path, root=ROOT):
    if not inside_root(path, root):
        raise SystemExit(f"refusing to touch {path}: outside the project folder ({root})")
    return Path(path).resolve()


def write_private(path, text):
    """Atomically write ``text`` to ``path`` with owner-only permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# Notes and tags
# --------------------------------------------------------------------------

def normalise_agency(raw):
    key = re.sub(r"[^a-z]+", " ", (raw or "").lower()).strip()
    return _AGENCY_ALIASES.get(key, UNKNOWN)


def clean_free(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def passage_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def parse_note(raw):
    """Split a note into (front-matter dict, list of passage strings).

    Front matter is a leading ``---`` block of ``key: value`` lines. Passages
    are blank-line-separated blocks, excluding markdown headings.
    """
    meta, body = {}, raw
    m = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*\n", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip().lower()] = value.strip()
        body = raw[m.end():]
    blocks = (b.strip() for b in re.split(r"\n[ \t]*\n", body))
    return meta, [b for b in blocks if b and not b.startswith("#")]


class Note:
    def __init__(self, path, name):
        self.path = path
        self.name = name
        meta, self.passages = parse_note(path.read_text(encoding="utf-8"))
        self.site = meta.get("site") or UNKNOWN
        self.agency_raw = meta.get("agency", "")
        self.agency = normalise_agency(self.agency_raw)
        self.date = meta.get("date", "")
        self.tags_path = path.with_suffix(".tags.json")
        self.tags = {}
        if self.tags_path.exists():
            self.tags = json.loads(self.tags_path.read_text(encoding="utf-8")).get("passages", {})

    def save(self):
        data = {"version": 1, "passages": dict(sorted(self.tags.items(), key=lambda kv: int(kv[0])))}
        write_private(self.tags_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def stale(self):
        """Tag entries whose passage is missing or has changed since tagging."""
        out = []
        for key, entry in self.tags.items():
            n = int(key)
            if n < 1 or n > len(self.passages) or entry["sha"] != passage_sha(self.passages[n - 1]):
                out.append(n)
        return sorted(out)

    def keys_for(self, n):
        entry = self.tags.get(str(n))
        if not entry:
            return []
        return list(entry["codes"]) + [FREE_PREFIX + f for f in entry["free"]]


class Corpus:
    def __init__(self, notes_dir, root=ROOT):
        self.root = Path(root).resolve()
        self.dir = require_inside(notes_dir, self.root)
        self.notes = []
        if self.dir.is_dir():
            for p in sorted(self.dir.rglob("*.md")):
                if not inside_root(p, self.root):
                    print(f"skipping {p}: resolves outside the project folder", file=sys.stderr)
                    continue
                self.notes.append(Note(p, str(p.relative_to(self.dir))))

    def note(self, name):
        for n in self.notes:
            if n.name == name:
                return n
        raise SystemExit(f"no such note: {name} (see `list`)")

    def tagged(self):
        """Yield (note, passage number, text, code keys) for every tagged passage."""
        for note in self.notes:
            stale = set(note.stale())
            for key in sorted(note.tags, key=int):
                n = int(key)
                if n in stale:
                    continue
                keys = note.keys_for(n)
                if keys:
                    yield note, n, note.passages[n - 1], keys


def code_order(key):
    if key in FIXED_CODES:
        return (0, FIXED_CODES.index(key), "")
    return (1, 0, key)


def code_label(key):
    return key[len(FREE_PREFIX):] + " (free)" if key.startswith(FREE_PREFIX) else key


def agency_order(a):
    return AGENCIES.index(a) if a in AGENCIES else len(AGENCIES)


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------

def tag_passage(corpus, name, n, codes=(), free=(), remove=False):
    note = corpus.note(name)
    if not 1 <= n <= len(note.passages):
        raise SystemExit(f"{name} has passages 1-{len(note.passages)}, not {n}")
    if n in note.stale():
        raise SystemExit(f"{name} §{n}: existing tags are stale (text changed); run `check`")
    entry = note.tags.setdefault(str(n), {"sha": passage_sha(note.passages[n - 1]), "codes": [], "free": []})
    free = [clean_free(f) for f in free if clean_free(f)]
    for c in codes:
        if remove and c in entry["codes"]:
            entry["codes"].remove(c)
        elif not remove and c not in entry["codes"]:
            entry["codes"].append(c)
    for f in free:
        if remove and f in entry["free"]:
            entry["free"].remove(f)
        elif not remove and f not in entry["free"]:
            entry["free"].append(f)
    if not entry["codes"] and not entry["free"]:
        del note.tags[str(n)]
    note.save()


def check_codes(codes):
    for c in codes:
        if c not in FIXED_CODES:
            hint = difflib.get_close_matches(c, FIXED_CODES, n=1)
            more = f" Did you mean '{hint[0]}'?" if hint else ""
            raise SystemExit(f"unknown code '{c}'. Fixed codes: {', '.join(FIXED_CODES)}. "
                             f"Use --free for free-text codes.{more}")


def build_summary(corpus, by="agency", free_detail=False):
    counts = defaultdict(lambda: defaultdict(int))
    columns = set()
    for note, _n, _t, keys in corpus.tagged():
        col = note.agency if by == "agency" else note.site
        columns.add(col)
        counts["__any"][col] += 1
        if any(k.startswith(FREE_PREFIX) for k in keys):
            counts["__free"][col] += 1
        for k in keys:
            if k in FIXED_CODES or free_detail:
                counts[k][col] += 1
    cols = sorted(columns, key=agency_order if by == "agency" else str.lower)
    rows = [k for k in FIXED_CODES]
    if free_detail:
        rows += sorted((k for k in counts if k.startswith(FREE_PREFIX)))
    else:
        rows.append("__free")
    rows.append("__any")
    names = {"__free": "free-text (any)", "__any": "TOTAL tagged passages"}
    table = [[names.get(r, code_label(r))] + [counts[r][c] for c in cols] + [sum(counts[r].values())]
             for r in rows]
    return [by] + cols + ["total"], table


def render_table(header, rows):
    rows = [[str(c) for c in r] for r in [header] + rows]
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = []
    for i, r in enumerate(rows):
        lines.append("  ".join(c.ljust(widths[0]) if j == 0 else c.rjust(widths[j]) for j, c in enumerate(r)))
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def export_markdown(corpus, only=None):
    groups = defaultdict(lambda: defaultdict(list))
    for note, n, text, keys in corpus.tagged():
        for k in keys:
            if only and k != only:
                continue
            groups[k][(note.site, note.agency)].append((note, n, text, keys))
    if not groups:
        return "# Fieldnote export\n\n_No tagged passages match._\n"
    out = ["# Fieldnote export", ""]
    for k in sorted(groups, key=code_order):
        out += [f"## {code_label(k)}", ""]
        for site, agency in sorted(groups[k], key=lambda sa: (sa[0].lower(), agency_order(sa[1]))):
            out += [f"### {site} — {agency}", ""]
            for note, n, text, keys in groups[k][(site, agency)]:
                others = ", ".join(code_label(o) for o in keys if o != k)
                out += ["> " + text.replace("\n", "\n> "), "",
                        f"— *{note.name} §{n}{', ' + note.date if note.date else ''}*"
                        + (f" · also: {others}" if others else ""), ""]
    return "\n".join(out)


def search(corpus, query, regex=False, code=None, site=None, agency=None):
    pattern = re.compile(query if regex else re.escape(query), re.I)
    want_agency = normalise_agency(agency) if agency else None
    hits = []
    for note in corpus.notes:
        if site and note.site.lower() != site.lower():
            continue
        if want_agency and note.agency != want_agency:
            continue
        stale = set(note.stale())
        for n, text in enumerate(note.passages, 1):
            keys = [] if n in stale else note.keys_for(n)
            if code and code not in keys:
                continue
            if pattern.search(text) or any(pattern.search(k) for k in keys if k.startswith(FREE_PREFIX)):
                hits.append((note, n, text, keys))
    return hits


def check(corpus):
    problems = []
    for note in corpus.notes:
        if note.site == UNKNOWN:
            problems.append(f"{note.name}: no 'site' in front matter")
        if note.agency == UNKNOWN:
            problems.append(f"{note.name}: agency {note.agency_raw!r} not one of {', '.join(AGENCIES)}")
        for n in note.stale():
            problems.append(f"{note.name} §{n}: tag is stale (passage edited, moved or removed)")
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def short(text, width=110):
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def build_parser():
    p = argparse.ArgumentParser(prog="fieldcode", description="Code ethnographic fieldnotes locally.")
    p.add_argument("--notes-dir", default="notes", help="folder of .md notes, inside this project (default: notes)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the (git-ignored) notes/ and exports/ folders")
    sub.add_parser("list", help="list notes with site, agency and tag counts")
    s = sub.add_parser("show", help="show a note's passages and tags")
    s.add_argument("note")
    s = sub.add_parser("tag", help="tag a passage")
    s.add_argument("note")
    s.add_argument("passage", type=int)
    s.add_argument("codes", nargs="*", help=f"any of: {', '.join(FIXED_CODES)}")
    s.add_argument("--free", action="append", default=[], metavar="TEXT", help="free-text code (repeatable)")
    s = sub.add_parser("untag", help="remove codes from a passage")
    s.add_argument("note")
    s.add_argument("passage", type=int)
    s.add_argument("codes", nargs="*")
    s.add_argument("--free", action="append", default=[], metavar="TEXT")
    s = sub.add_parser("export", help="passages per code, grouped by site and agency (markdown)")
    s.add_argument("--code", help="one code: a fixed code, or free:<text>")
    s.add_argument("--out", help="write to this file (must be inside the project) instead of stdout")
    s = sub.add_parser("search", help="search passage text and free-text codes")
    s.add_argument("query")
    s.add_argument("--regex", action="store_true")
    s.add_argument("--code")
    s.add_argument("--site")
    s.add_argument("--agency")
    s = sub.add_parser("summary", help="count table of tagged passages")
    s.add_argument("--by", choices=("agency", "site"), default="agency")
    s.add_argument("--free-detail", action="store_true", help="one row per free-text code")
    sub.add_parser("check", help="report missing metadata and stale tags")
    return p


def main(argv=None, root=ROOT):
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        for d in (args.notes_dir, "exports"):
            require_inside(root / d, root).mkdir(mode=0o700, exist_ok=True)
        print("created notes/ and exports/ (both git-ignored); put real notes in notes/ only")
        return 0
    corpus = Corpus(root / args.notes_dir, root)

    if args.cmd == "list":
        for n in corpus.notes:
            print(f"{n.name:34} {n.site:22} {n.agency:16} {len(n.passages):3} passages {len(n.tags):3} tagged")
    elif args.cmd == "show":
        note = corpus.note(args.note)
        stale = set(note.stale())
        print(f"{note.name} | {note.site} | {note.agency} | {note.date}\n")
        for i, text in enumerate(note.passages, 1):
            keys = note.keys_for(i)
            flag = " [STALE]" if i in stale else ""
            print(f"[{i}] {', '.join(code_label(k) for k in keys) or '-'}{flag}\n{text}\n")
    elif args.cmd in ("tag", "untag"):
        check_codes(args.codes)
        if not args.codes and not args.free:
            raise SystemExit("give at least one code or --free text")
        tag_passage(corpus, args.note, args.passage, args.codes, args.free, remove=args.cmd == "untag")
    elif args.cmd == "export":
        text = export_markdown(corpus, args.code)
        if args.out:
            out = require_inside(root / args.out, root)
            write_private(out, text)
            print(f"wrote {out} (owner-only permissions; contains note text, keep it local)")
        else:
            print(text)
    elif args.cmd == "search":
        hits = search(corpus, args.query, args.regex, args.code, args.site, args.agency)
        for note, n, text, keys in hits:
            tags = f" [{', '.join(code_label(k) for k in keys)}]" if keys else ""
            print(f"{note.name} §{n} ({note.site}, {note.agency}){tags}\n    {short(text)}")
        print(f"\n{len(hits)} passage(s)")
    elif args.cmd == "summary":
        header, rows = build_summary(corpus, args.by, args.free_detail)
        print(render_table(header, rows))
    elif args.cmd == "check":
        problems = check(corpus)
        print("\n".join(problems) if problems else "ok")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
