#!/usr/bin/env node
/**
 * Hex ratchet (UI-UX-PLAYBOOK section 9, phase 1; DES-08).
 *
 * Counts hard-coded colour literals (#hex, rgb()/rgba(), hsl()/hsla()) in
 * frontend/src, outside the one file allowed to hold them
 * (src/styles/brand-tokens.css), and compares the count with the baseline in
 * frontend/.hex-baseline. The count may go down, never up.
 *
 * Test files (*.test.*, *.spec.*, src/test/) are excluded: they assert on
 * colours rather than style the product.
 *
 * Usage (from frontend/):
 *   node scripts/hex-ratchet.mjs            check against the baseline
 *   node scripts/hex-ratchet.mjs --update   write the current count as the new baseline
 *   node scripts/hex-ratchet.mjs --list     also print per-file counts
 *
 * Exit codes: 0 = count <= baseline, 1 = count grew, 2 = setup error.
 */
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC_DIR = join(FRONTEND_DIR, 'src');
const BASELINE_FILE = join(FRONTEND_DIR, '.hex-baseline');
const ALLOWED_FILE = 'styles/brand-tokens.css';
const SCANNED_EXTENSIONS = ['.css', '.ts', '.tsx', '.js', '.jsx'];
const TEST_FILE_PATTERN = /(\.test\.|\.spec\.|^test\/)/;

// `#` not preceded by a word char or `&` (skips HTML entities such as &#123;),
// 3/4/6/8 hex digits, not followed by a word char or `-`.
const HEX_PATTERN = /(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g;
const FUNCTION_PATTERN = /\b(?:rgba?|hsla?)\(/g;

function listFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return listFiles(path);
    return SCANNED_EXTENSIONS.some((ext) => entry.name.endsWith(ext)) ? [path] : [];
  });
}

function countLiterals(text) {
  const hex = text.match(HEX_PATTERN)?.length ?? 0;
  const fn = text.match(FUNCTION_PATTERN)?.length ?? 0;
  return hex + fn;
}

function collectCounts() {
  return listFiles(SRC_DIR)
    .map((path) => ({ file: relative(SRC_DIR, path).split('\\').join('/'), path }))
    .filter(({ file }) => file !== ALLOWED_FILE && !TEST_FILE_PATTERN.test(file))
    .map(({ file, path }) => ({ file, count: countLiterals(readFileSync(path, 'utf8')) }))
    .filter(({ count }) => count > 0);
}

function readBaseline() {
  if (!existsSync(BASELINE_FILE)) return null;
  const value = Number.parseInt(readFileSync(BASELINE_FILE, 'utf8').trim(), 10);
  if (!Number.isFinite(value) || value < 0) {
    console.error(`hex-ratchet: ${BASELINE_FILE} does not hold a non-negative integer`);
    process.exit(2);
  }
  return value;
}

const args = new Set(process.argv.slice(2));
const counts = collectCounts();
const total = counts.reduce((sum, { count }) => sum + count, 0);

if (args.has('--list')) {
  [...counts]
    .sort((a, b) => b.count - a.count)
    .forEach(({ file, count }) => console.log(`${String(count).padStart(5)}  ${file}`));
}

if (args.has('--update')) {
  writeFileSync(BASELINE_FILE, `${total}\n`);
  console.log(`hex-ratchet: baseline set to ${total}`);
  process.exit(0);
}

const baseline = readBaseline();
if (baseline === null) {
  console.error('hex-ratchet: no .hex-baseline found; run with --update to create it');
  process.exit(2);
}

if (total > baseline) {
  console.error(
    `hex-ratchet: FAIL, ${total} colour literals outside ${ALLOWED_FILE} (baseline ${baseline}, +${total - baseline}).`,
  );
  console.error('Use semantic tokens from src/styles/brand-tokens.css instead of hex, rgb() or hsl().');
  process.exit(1);
}

const note = total < baseline ? ` (down ${baseline - total}; run --update to lock in the gain)` : '';
console.log(`hex-ratchet: OK, ${total} colour literals (baseline ${baseline})${note}`);
