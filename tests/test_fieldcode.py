import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fieldcode as fc  # noqa: E402

PROJECT = Path(fc.__file__).resolve().parent
NOTE = """---
site: Test Fell
agency: Police B
date: 2024-01-01
---

# Heading is not a passage

First passage about the radio.

Second passage about a form.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "notes").mkdir()
        (self.root / "notes" / "a.md").write_text(NOTE)

    def tearDown(self):
        self.tmp.cleanup()

    def corpus(self):
        return fc.Corpus(self.root / "notes", self.root)


class ParseTests(Base):
    def test_front_matter_and_passages(self):
        n = self.corpus().note("a.md")
        self.assertEqual((n.site, n.agency, n.date), ("Test Fell", "Police Force B", "2024-01-01"))
        self.assertEqual(len(n.passages), 2)

    def test_unknown_agency(self):
        self.assertEqual(fc.normalise_agency("Coastguard"), fc.UNKNOWN)
        self.assertEqual(fc.normalise_agency("mountain_rescue"), "Mountain Rescue")


class TagTests(Base):
    def test_roundtrip_and_permissions(self):
        fc.tag_passage(self.corpus(), "a.md", 1, ["sop"], ["  Odd  Thing "])
        tags = self.root / "notes" / "a.tags.json"
        self.assertEqual(oct(tags.stat().st_mode & 0o777), "0o600")
        data = json.loads(tags.read_text())["passages"]["1"]
        self.assertEqual((data["codes"], data["free"]), (["sop"], ["odd thing"]))
        self.assertEqual(self.corpus().note("a.md").keys_for(1), ["sop", "free:odd thing"])

    def test_untag_removes_empty_entry(self):
        fc.tag_passage(self.corpus(), "a.md", 1, ["sop"])
        fc.tag_passage(self.corpus(), "a.md", 1, ["sop"], remove=True)
        self.assertEqual(self.corpus().note("a.md").tags, {})

    def test_unknown_fixed_code_rejected(self):
        with self.assertRaises(SystemExit):
            fc.check_codes(["sopp"])

    def test_stale_detection(self):
        fc.tag_passage(self.corpus(), "a.md", 1, ["sop"])
        p = self.root / "notes" / "a.md"
        p.write_text(p.read_text().replace("radio", "pager"))
        c = self.corpus()
        self.assertEqual(c.note("a.md").stale(), [1])
        self.assertEqual(list(c.tagged()), [])
        self.assertTrue(any("stale" in x for x in fc.check(c)))
        with self.assertRaises(SystemExit):
            fc.tag_passage(c, "a.md", 1, ["technology"])


class OutputTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "notes" / "b.md").write_text(NOTE.replace("Police B", "Mountain Rescue").replace("Test Fell", "Other Fell"))
        c = self.corpus()
        fc.tag_passage(c, "a.md", 1, ["technology"], ["x"])
        fc.tag_passage(c, "b.md", 1, ["technology"])
        fc.tag_passage(c, "b.md", 2, ["sop"])

    def test_summary(self):
        header, rows = fc.build_summary(self.corpus())
        self.assertEqual(header, ["agency", "Mountain Rescue", "Police Force B", "total"])
        by_name = {r[0]: r[1:] for r in rows}
        self.assertEqual(by_name["technology"], [1, 1, 2])
        self.assertEqual(by_name["sop"], [1, 0, 1])
        self.assertEqual(by_name["TOTAL tagged passages"], [2, 1, 3])

    def test_export_grouping_order(self):
        md = fc.export_markdown(self.corpus())
        self.assertLess(md.index("## sop"), md.index("## technology"))
        tech = md[md.index("## technology"):md.index("## x (free)")]
        self.assertLess(tech.index("Other Fell — Mountain Rescue"), tech.index("Test Fell — Police Force B"))
        self.assertIn("a.md §1", tech)

    def test_search(self):
        c = self.corpus()
        self.assertEqual(len(fc.search(c, "radio")), 2)
        self.assertEqual(len(fc.search(c, "radio", agency="police force b")), 1)
        self.assertEqual(len(fc.search(c, "x", code="free:x")), 1)
        self.assertEqual(len(fc.search(c, r"for[m]\b", regex=True)), 2)


class SafetyTests(Base):
    def test_outside_root_refused(self):
        with self.assertRaises(SystemExit):
            fc.Corpus("/tmp", self.root)
        with self.assertRaises(SystemExit):
            fc.require_inside(self.root / ".." / "x", self.root)

    def test_symlink_escape_skipped(self):
        outside = tempfile.TemporaryDirectory()
        try:
            (Path(outside.name) / "evil.md").write_text(NOTE)
            os.symlink(Path(outside.name) / "evil.md", self.root / "notes" / "evil.md")
            self.assertEqual([n.name for n in self.corpus().notes], ["a.md"])
        finally:
            outside.cleanup()

    def test_export_out_is_private(self):
        out = self.root / "exports" / "e.md"
        fc.write_private(out, "x")
        self.assertEqual(oct(out.stat().st_mode & 0o777), "0o600")

    def test_no_network_imports(self):
        banned = r"^\s*(import|from)\s+(socket|ssl|http|urllib|ftplib|smtplib|telnetlib|requests|httpx|aiohttp|xmlrpc|asyncio|subprocess)\b"
        src = (PROJECT / "fieldcode.py").read_text()
        self.assertIsNone(re.search(banned, src, re.M))

    def test_html_page_is_offline(self):
        html = (PROJECT / "fieldcode.html").read_text()
        self.assertIn("default-src 'none'", html)
        self.assertIsNone(re.search(r"https?://|<script[^>]*\bsrc=|<link[^>]*href=|@import|url\(", html))
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "localStorage", "sessionStorage", "indexedDB", "EventSource"):
            self.assertNotIn(banned, html)

    def test_sample_notes_are_clean(self):
        c = fc.Corpus(PROJECT / "sample_notes", PROJECT)
        self.assertEqual(fc.check(c), [])


if __name__ == "__main__":
    unittest.main()
