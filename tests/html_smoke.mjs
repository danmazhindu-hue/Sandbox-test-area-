// Optional browser check for fieldcode.html (needs Node + Playwright with Chromium installed).
//   node tests/html_smoke.mjs
// Loads the invented sample notes and verifies the page agrees with fieldcode.py
// (hashes, counts, markdown export), that editing works, and that no request leaves the page.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const samples = path.join(root, "sample_notes");
const shot = process.env.SHOT_DIR;

let failed = 0;
const check = (ok, msg) => { console.log((ok ? "PASS " : "FAIL ") + msg); if (!ok) failed++; };

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const requests = [];
page.on("request", r => requests.push(r.url()));
const errors = [];
page.on("pageerror", e => errors.push(e.message));

await page.goto("file://" + path.join(root, "fieldcode.html"));
await page.setInputFiles("#folderInput", samples);
await page.waitForSelector(".card");

check(await page.evaluate(() => state.notes.length) === 8, "loads 8 sample notes");
check(await page.evaluate(() => state.notes.every(n => staleSet(n).size === 0)),
  "JS hashes match Python hashes (no stale tags)");

// Byte-for-byte: re-serialising each loaded tag file reproduces what Python wrote.
const same = await page.evaluate(() => state.notes.map(n => [n.name, serialize(n)]));
const identical = same.every(([name, text]) => text === readFileSync(path.join(samples, name.replace(/\.md$/, ".tags.json")), "utf8"));
check(identical, "tag JSON round-trips identically to the Python-written files");

// Markdown export matches the CLI.
const jsMd = (await page.evaluate(() => exportMarkdown(""))).trimEnd();
const pyMd = execFileSync("python3", ["fieldcode.py", "--notes-dir", "sample_notes", "export"], { cwd: root, encoding: "utf8" }).trimEnd();
check(jsMd === pyMd, "markdown export identical to `fieldcode.py export`");

// Summary totals match the CLI table.
const sum = await page.evaluate(() => buildSummary("agency", false).rows.map(r => [r.name, ...r.cells]));
const pySum = execFileSync("python3", ["fieldcode.py", "--notes-dir", "sample_notes", "summary"], { cwd: root, encoding: "utf8" });
const pyRows = pySum.trimEnd().split("\n").slice(2).map(l => l.trim().split(/\s+/).filter(t => /^\d+$/.test(t)).join(","));
const jsRows = sum.map(r => [...r.slice(1), r.slice(1).reduce((a, b) => a + b, 0)].join(","));
check(pyRows.length === jsRows.length && pyRows.every((r, i) => r === jsRows[i]), "summary table numbers match `fieldcode.py summary`");

// Editing: toggle a code and add/remove a free-text code through the UI.
await page.click('.nitem[data-note="lr_brackenmere_02.md"]');
const before = await page.evaluate(() => Object.keys(state.current.tags).length);
await page.click('.card[data-n="1"] .chip[data-code="technology"]');
await page.fill('.card[data-n="1"] .freeinput', "  New   Idea ");
await page.press('.card[data-n="1"] .freeinput', "Enter");
const e1 = await page.evaluate(() => state.current.tags[1]);
check(Object.keys(e1).join() === "sha,codes,free" && e1.codes.join() === "technology" && e1.free.join() === "new idea", "tag + free-text code recorded and normalised");
check(await page.evaluate(() => Object.keys(state.current.tags).length) === before + 1, "tagged count updates");
await page.focus('.card[data-n="1"]');
await page.keyboard.press("1");
check(await page.evaluate(() => state.current.tags[1].codes.join()) === "technology,sop", "keyboard shortcut 1 toggles sop");
await page.click('.card[data-n="1"] [data-act="rmfree"]');
await page.click('.card[data-n="1"] .chip[data-code="technology"]');
await page.click('.card[data-n="1"] .chip[data-code="sop"]');
check(await page.evaluate(() => state.current.tags[1] === undefined), "removing every code deletes the entry");
check(await page.evaluate(() => state.notes.find(n => n.name === "lr_brackenmere_02.md").dirty), "fallback mode marks note as unsaved");

// Stale handling: simulate an edited passage.
await page.evaluate(() => { const n = state.current; n.hashes[1] = "deadbeef0000"; render(); });
check(await page.locator(".card.stale").count() === 1, "edited passage is flagged stale");
await page.click('.card.stale [data-act="reattach"]');
check(await page.locator(".card.stale").count() === 0, "stale tags can be re-attached explicitly");

// New note through the dialog, then append text; Python must parse the result identically.
await page.click("#newBtn");
await page.fill("#nSite", "  Testmoor   Pass ");
await page.selectOption("#nAgency", "Police Force B");
await page.fill("#nDate", "2025-02-03");
await page.fill("#nTitle", "Callout: night shift");
await page.fill("#nBody", "First passage, a\nsecond line.\n\nSecond passage: with colon.");
await page.click("#nCreate");
const made = await page.evaluate(() => ({name: state.current.name, raw: state.current.raw, passages: state.current.passages, agency: state.current.agency, site: state.current.site}));
check(made.name === "2025-02-03_testmoor-pass_police-force-b.md" && made.site === "Testmoor Pass" && made.agency === "Police Force B" && made.passages.length === 2,
  "new note created with sensible filename and metadata");
const parseWithPython = raw => JSON.parse(execFileSync("python3", ["-I", "-c",
  "import sys,json; sys.path.insert(0, sys.argv[1]); import fieldcode as fc; print(json.dumps(fc.parse_note(sys.stdin.read())))", root], {input: raw, encoding: "utf8"}));
let [pyMeta, pyPass] = parseWithPython(made.raw);
check(JSON.stringify(pyPass) === JSON.stringify(made.passages) && pyMeta.site === "Testmoor Pass" && pyMeta.agency === "Police Force B", "Python parses the new note identically");
await page.click('.card[data-n="1"] .chip[data-code="sop"]');
await page.click("details.add summary");
await page.fill("#appendText", "Third passage added later.\n\nFourth one.");
await page.click('[data-act="append"]');
const after = await page.evaluate(() => ({n: state.current.passages.length, stale: staleSet(state.current).size, tags: state.current.tags, raw: state.current.raw}));
check(after.n === 4 && after.stale === 0 && after.tags[1].codes.join() === "sop", "appending text keeps existing tags valid");
[pyMeta, pyPass] = parseWithPython(after.raw);
check(pyPass.length === 4 && pyPass[3] === "Fourth one.", "Python still parses the note after appending");
await page.click("#newBtn"); await page.fill("#nSite", "Testmoor Pass"); await page.selectOption("#nAgency", "Police Force B"); await page.fill("#nDate", "2025-02-03");
await page.click("#nCreate");
check(await page.evaluate(() => state.current.name) === "2025-02-03_testmoor-pass_police-force-b-2.md", "second note with same date/site/agency gets a unique name");
await page.click("#newBtn"); await page.fill("#nSite", ""); await page.click("#nCreate");
check((await page.textContent("#nErr")).includes("field site"), "dialog asks for a site if missing");
await page.click("#nCancel");
check(await page.evaluate(() => state.notes.filter(n => n.mdPending).length) === 2, "new notes are marked as needing download in fallback mode");

// Search and views render.
await page.click('#tabs [data-tab="search"]');
await page.fill("#q", "paper");
check((await page.locator(".hit").count()) === 4, "search finds 4 passages for 'paper'");
await page.click('#tabs [data-tab="summary"]');
check((await page.locator("table tr").count()) === 7, "summary table renders");
await page.click('#tabs [data-tab="bycode"]');
check((await page.locator(".group h2").count()) >= 5, "by-code view renders groups");

// HTML escaping.
const esc = await page.evaluate(() => esc('<img src=x onerror=alert(1)>&"'));
check(!esc.includes("<"), "note text is HTML-escaped");

// Privacy: nothing but the page itself was requested.
check(requests.every(u => u.startsWith("file://") || u.startsWith("data:")), "no network requests: " + JSON.stringify(requests));
const blocked = await page.evaluate(() => fetch("https://example.com/").then(() => "reached", () => "blocked"));
check(blocked === "blocked", "CSP blocks fetch() to the internet");
check(errors.length === 0, "no page errors" + (errors.length ? ": " + errors.join("; ") : ""));

if (shot) {
  await page.click('#tabs [data-tab="code"]');
  await page.click('.nitem[data-note="mr_aldermoor_01.md"]');
  await page.screenshot({ path: path.join(shot, "code.png") });
  await page.click('#tabs [data-tab="summary"]');
  await page.screenshot({ path: path.join(shot, "summary.png") });
}
await browser.close();
process.exit(failed ? 1 : 0);
