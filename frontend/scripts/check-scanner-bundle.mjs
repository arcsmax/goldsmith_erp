#!/usr/bin/env node
/**
 * Scanner-route bundle-size CI gate (M7, A13 / Slice 13).
 *
 * Enforces the V1.1 spec §14.a metric (f): scanner-route chunk <= 250 KB gzip.
 * Stop-ship threshold is 400 KB gzip (per ship-day calendar Part C row f).
 *
 * Detection strategy
 * ------------------
 * Vite code-splits dynamic imports. We identify a chunk as "scanner-route"
 * if EITHER:
 *   (1) Its filename matches one of SCANNER_CHUNK_PATTERNS (the scanner UI
 *       components' basenames), OR
 *   (2) It is a vendor chunk that contains a scanner-library source in its
 *       sourcemap (the yudiel / barcode-detector / webrtc-adapter deps get
 *       bundled together into a shared index.esm chunk when dynamic-imported
 *       from the scanner tree).
 *
 * This catches the real scanner-route cost which is dominated by the vendor
 * chunk, not the UI chunk. If the detection misses something we'll see a
 * green build with a surprise at runtime; false positives are preferable.
 *
 * The gate is strict-under-FAIL rather than warn-only: per V1.1-TESTABILITY-
 * REVIEW.md §4 row f, flapping between green / red across PRs is itself a
 * deployment blocker (Lena §5 list).
 *
 * Also appends a row to docs/field-test-kit/bundle-trend.csv per
 * SHIP-DAY-CALENDAR Part C (historical sparkline for dashboards).
 *
 * Exit codes
 * ----------
 *   0  under WARN threshold (pass)
 *   1  unexpected runtime error
 *   2  over WARN, under FAIL (breach — fail the PR)
 *   3  over FAIL (stop-ship threshold breached)
 *   4  no scanner chunks found at all (malformed build)
 *
 * Usage: `node frontend/scripts/check-scanner-bundle.mjs`
 * Assumes `yarn build` has already been run. The Makefile target
 * `make check-bundle` runs both steps.
 */
import { readFile, readdir, stat, appendFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');
const DIST_DIR = resolve(REPO_ROOT, 'frontend', 'dist', 'assets');
const TREND_CSV = resolve(
  REPO_ROOT,
  'docs',
  'field-test-kit',
  'bundle-trend.csv',
);

const WARN_BYTES = 250 * 1024; // 250 KB gzip — spec §14.a row f
const FAIL_BYTES = 400 * 1024; // 400 KB gzip — stop-ship threshold

// Chunk-filename patterns for the scanner UI tree.
const SCANNER_CHUNK_PATTERNS = [
  /ScannerPage/i,
  /QrCameraScanner/i,
  /QuickActionModalV2/i,
  /AlloyMismatchModal/i,
  /PunzierungsCheckModal/i,
  /ScanOverlay/i,
  /ScanFab/i,
  /^scanner-/i,
];

// Sourcemap source-path fragments that identify a chunk as carrying
// scanner vendor deps (QR decoding / camera access). We match against
// entries in the sourcemap's `sources` array, NOT free text, so a chunk
// that merely references these module names in a comment or type import
// does not pollute the measurement.
const SCANNER_VENDOR_SOURCE_MARKERS = [
  'node_modules/@yudiel/',
  'node_modules/barcode-detector/',
  'node_modules/webrtc-adapter/',
];

function humanBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

async function readMapMaybe(jsPath) {
  const mapPath = `${jsPath}.map`;
  if (!existsSync(mapPath)) return null;
  try {
    return await readFile(mapPath, 'utf8');
  } catch {
    return null;
  }
}

async function isVendorScannerChunk(jsPath) {
  const raw = await readMapMaybe(jsPath);
  if (!raw) return false;
  let map;
  try {
    map = JSON.parse(raw);
  } catch {
    // Malformed sourcemap — fall back to substring search against the
    // sources field extracted by regex.
    const m = raw.match(/"sources"\s*:\s*(\[[^\]]*\])/);
    if (!m) return false;
    return SCANNER_VENDOR_SOURCE_MARKERS.some(marker => m[1].includes(marker));
  }
  if (!Array.isArray(map.sources)) return false;
  return map.sources.some(src =>
    SCANNER_VENDOR_SOURCE_MARKERS.some(marker => src && src.includes(marker)),
  );
}

async function findScannerChunks() {
  if (!existsSync(DIST_DIR)) {
    console.error(
      `[bundle-gate] FAIL: ${DIST_DIR} does not exist. Run \`yarn build\` first.`,
    );
    process.exit(4);
  }
  const entries = await readdir(DIST_DIR, { withFileTypes: true });
  const jsFiles = entries
    .filter(e => e.isFile() && e.name.endsWith('.js'))
    .map(e => join(DIST_DIR, e.name));

  const matched = [];
  for (const jsPath of jsFiles) {
    const name = jsPath.split('/').pop();
    const matchesName = SCANNER_CHUNK_PATTERNS.some(rx => rx.test(name));
    const matchesVendor = matchesName
      ? false
      : await isVendorScannerChunk(jsPath);
    if (matchesName || matchesVendor) {
      matched.push({
        path: jsPath,
        reason: matchesName ? 'name' : 'vendor-map',
      });
    }
  }
  return matched;
}

async function sizeOf(chunk) {
  const buf = await readFile(chunk.path);
  const raw = buf.byteLength;
  const gz = gzipSync(buf).byteLength;
  const s = await stat(chunk.path);
  return { ...chunk, raw, gz, mtime: s.mtime };
}

async function appendTrendRow(totalGz, totalRaw, chunkCount) {
  const row = [
    new Date().toISOString(),
    String(totalGz),
    String(totalRaw),
    String(chunkCount),
    String(WARN_BYTES),
    String(FAIL_BYTES),
  ].join(',');
  try {
    await mkdir(dirname(TREND_CSV), { recursive: true });
    if (!existsSync(TREND_CSV)) {
      const header =
        'timestamp,scanner_chunk_gzip_bytes,scanner_chunk_raw_bytes,chunk_count,warn_threshold_bytes,fail_threshold_bytes\n';
      await appendFile(TREND_CSV, header, 'utf8');
    }
    await appendFile(TREND_CSV, row + '\n', 'utf8');
  } catch (err) {
    // Don't fail the gate because trend-log append failed. Log and move on.
    console.warn(
      `[bundle-gate] WARN: could not append to trend CSV (${err.message}).`,
    );
  }
}

async function main() {
  const chunks = await findScannerChunks();

  if (chunks.length === 0) {
    console.error(
      '[bundle-gate] FAIL: no scanner-route chunks found in dist/assets/. ' +
        'Build may be broken or chunk names may have changed — update ' +
        'SCANNER_CHUNK_PATTERNS in this script if the latter.',
    );
    process.exit(4);
  }

  const measured = await Promise.all(chunks.map(sizeOf));
  measured.sort((a, b) => b.gz - a.gz);

  const totalGz = measured.reduce((s, c) => s + c.gz, 0);
  const totalRaw = measured.reduce((s, c) => s + c.raw, 0);

  console.log('\n[bundle-gate] Scanner-route chunks (gzip):');
  console.log('  ' + '-'.repeat(70));
  for (const c of measured) {
    const name = c.path.split('/').pop();
    console.log(
      `  ${name.padEnd(42)} ${c.reason.padEnd(10)} ${humanBytes(c.gz).padStart(10)}  (raw ${humanBytes(c.raw)})`,
    );
  }
  console.log('  ' + '-'.repeat(70));
  console.log(
    `  TOTAL (gzip): ${humanBytes(totalGz)}  (raw ${humanBytes(totalRaw)})  across ${measured.length} chunk(s)`,
  );
  console.log(
    `  Thresholds:   WARN ${humanBytes(WARN_BYTES)}  |  FAIL ${humanBytes(FAIL_BYTES)}\n`,
  );

  await appendTrendRow(totalGz, totalRaw, measured.length);

  if (totalGz > FAIL_BYTES) {
    console.error(
      `[bundle-gate] STOP-SHIP: ${humanBytes(totalGz)} exceeds FAIL threshold ${humanBytes(FAIL_BYTES)}. ` +
        'This is a hard ship blocker (SHIP-DAY-CALENDAR Part C row f).',
    );
    process.exit(3);
  }
  if (totalGz > WARN_BYTES) {
    console.error(
      `[bundle-gate] FAIL: ${humanBytes(totalGz)} exceeds WARN threshold ${humanBytes(WARN_BYTES)}. ` +
        'Swap to html5-qrcode or defer non-critical modals out of the scanner ' +
        'chunk — do NOT raise the threshold (V1.1 plan §"What happens if a slice fails").',
    );
    process.exit(2);
  }

  console.log(
    `[bundle-gate] OK: ${humanBytes(totalGz)} <= ${humanBytes(WARN_BYTES)}.`,
  );
  process.exit(0);
}

main().catch(err => {
  console.error('[bundle-gate] unexpected error:', err);
  process.exit(1);
});
