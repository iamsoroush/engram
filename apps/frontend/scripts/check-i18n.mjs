#!/usr/bin/env node
//
// check-i18n.mjs — a hardcoded-string ratchet for the authenticated app.
//
// Scans src/features/**/*.tsx for user-facing strings that bypass the i18n seam (raw JSX text and
// raw placeholder/aria-label/title/alt attribute values) and compares them against a committed
// baseline. It FAILS on any string that is NOT already in the baseline — so once a surface is
// translated and the baseline shrunk, a later change can never silently re-introduce English chrome.
//
//   node scripts/check-i18n.mjs            # check; exit 1 if a NEW hardcoded string appears
//   node scripts/check-i18n.mjs --update   # regenerate the baseline from the current tree (exit 0)
//
// The baseline is keyed on (file + normalized string), NOT per-file: adding a brand-new literal to a
// file that already has baselined strings still fails. Scope is src/features/** by design (the
// app-shell chrome in src/app/App.tsx is tracked separately for later stories). The matcher is a
// deterministic heuristic — false positives are harmless (they live in the baseline); the gate is
// "no NEW leak", not a perfect parser.

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = dirname(SCRIPT_DIR);
const FEATURES_DIR = join(FRONTEND_ROOT, "src", "features");
const BASELINE_PATH = join(SCRIPT_DIR, "i18n-baseline.json");

const UPDATE = process.argv.includes("--update");

/** Recursively collect *.tsx files (skipping test/spec files) under a directory. */
function collectTsxFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectTsxFiles(full));
    } else if (full.endsWith(".tsx") && !/\.(test|spec)\.tsx$/.test(full)) {
      out.push(full);
    }
  }
  return out;
}

/** Collapse whitespace + trim, so "Confirm\n  dose" and "Confirm dose" are the same offender. */
function normalize(text) {
  return text.replace(/\s+/g, " ").trim();
}

/** True when a candidate is genuine user-facing text (has a real word), not punctuation/code/digits. */
function isUserFacing(text) {
  if (!/[A-Za-z]{2,}/.test(text)) return false; // needs at least one real word
  if (/[{}<>]/.test(text)) return false; // leftover code/markup — not plain text
  // Reject code fragments the heuristic can splice out of TS generics / JSX expressions that span a
  // closing `>` and the next `<` (e.g. `useState<Foo>(null); const … = React.…`). Real chrome text
  // does not contain assignments, statements, or hook calls.
  if (/[;=`]|=>|\bReact\.|\b(?:const|let|var|return|function|typeof|null|undefined|use[A-Z]\w+)\b/.test(text)) {
    return false;
  }
  if (/^[A-Za-z][\w-]*$/.test(text) && !/[a-z]/.test(text)) return false; // ALLCAPS_CONST-ish
  return true;
}

/** Extract the hardcoded user-facing strings from one .tsx file's source. */
function extractStrings(source) {
  const found = new Set();

  // 1) JSX text nodes: text sitting directly between a closing `>` and the next opening `<`, with no
  //    braces (so `{t("…")}` and other expressions are skipped — only literal text is flagged).
  for (const match of source.matchAll(/>([^<>{}]+)</g)) {
    const text = normalize(match[1]);
    if (isUserFacing(text)) found.add(text);
  }

  // 2) Literal user-facing attribute values (dynamic `={…}` values have no quote, so are skipped).
  for (const match of source.matchAll(/\b(?:placeholder|aria-label|title|alt)\s*=\s*"([^"]*)"/g)) {
    const text = normalize(match[1]);
    if (isUserFacing(text)) found.add(text);
  }
  for (const match of source.matchAll(/\b(?:placeholder|aria-label|title|alt)\s*=\s*'([^']*)'/g)) {
    const text = normalize(match[1]);
    if (isUserFacing(text)) found.add(text);
  }

  return [...found].sort();
}

/** Build the { relPath: [strings] } map for the whole features tree. */
function scan() {
  const map = {};
  for (const file of collectTsxFiles(FEATURES_DIR).sort()) {
    const rel = relative(FRONTEND_ROOT, file);
    const strings = extractStrings(readFileSync(file, "utf8"));
    if (strings.length) map[rel] = strings;
  }
  return map;
}

function loadBaseline() {
  try {
    return JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
  } catch {
    return {};
  }
}

const current = scan();

if (UPDATE) {
  // Stable serialization (sorted keys) so diffs are reviewable.
  const sorted = {};
  for (const key of Object.keys(current).sort()) sorted[key] = current[key];
  writeFileSync(BASELINE_PATH, JSON.stringify(sorted, null, 2) + "\n");
  const total = Object.values(sorted).reduce((n, arr) => n + arr.length, 0);
  console.log(`i18n baseline updated: ${total} string(s) across ${Object.keys(sorted).length} file(s).`);
  process.exit(0);
}

const baseline = loadBaseline();
const violations = [];
for (const [file, strings] of Object.entries(current)) {
  const allowed = new Set(baseline[file] ?? []);
  for (const str of strings) {
    if (!allowed.has(str)) violations.push({ file, str });
  }
}

if (violations.length) {
  console.error(`\n✗ i18n guard: ${violations.length} NEW hardcoded user-facing string(s) in src/features/** —`);
  console.error("  route every chrome string through the i18n seam (useT()/t()), never a raw literal.\n");
  for (const { file, str } of violations) {
    console.error(`  ${file}\n    → ${JSON.stringify(str)}`);
  }
  console.error("\n  If you intentionally translated a surface, run: npm run i18n:guard -- --update\n");
  process.exit(1);
}

const total = Object.values(current).reduce((n, arr) => n + arr.length, 0);
console.log(`✓ i18n guard: no new hardcoded strings (${total} baselined across ${Object.keys(current).length} file(s)).`);
process.exit(0);
