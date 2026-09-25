// W4 phase 4: every stylesheet except styles/brand-tokens.css paints with
// semantic tokens only, so each page follows the Hell / Dunkel theme switch.
// Same literal patterns as scripts/hex-ratchet.mjs; named white/black count
// too, because they do not flip in dark mode either.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const TOKEN_FILE = 'styles/brand-tokens.css';

/**
 * Stylesheets allowed to keep colour literals, with the reason. Empty today:
 * add an entry only for a value that must not follow the theme (for example
 * print-only CSS), and say why.
 */
const ALLOWLIST: Readonly<Record<string, string>> = {};

const HEX = /(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g;
const FUNCTION = /\b(?:rgba?|hsla?)\(/g;
const NAMED = /:[^;{}]*?(?<![\w-])(?:white|black)(?![\w-])/g;

function listStylesheets(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return listStylesheets(path);
    return entry.name.endsWith('.css') ? [path] : [];
  });
}

function findLiterals(css: string): string[] {
  const code = css.replace(/\/\*[\s\S]*?\*\//g, '');
  return [HEX, FUNCTION, NAMED].flatMap((pattern) => code.match(pattern) ?? []);
}

const stylesheets = listStylesheets(SRC_DIR)
  .map((path) => ({ file: relative(SRC_DIR, path).split('\\').join('/'), path }))
  .filter(({ file }) => file !== TOKEN_FILE && !(file in ALLOWLIST));

describe('stylesheets use semantic colour tokens only', () => {
  it('finds the stylesheets', () => {
    expect(stylesheets.length).toBeGreaterThan(20);
  });

  it.each(stylesheets.map(({ file, path }) => [file, path]))(
    '%s has no colour literal',
    (_file, path) => {
      expect(findLiterals(readFileSync(path, 'utf8'))).toEqual([]);
    },
  );

  it('detects hex, rgb(), hsl() and named literals', () => {
    const sample = '.a { color: #fff; background: rgba(0, 0, 0, 0.1); border-color: hsl(0 0% 0%); fill: white; }';
    expect(findLiterals(sample)).toHaveLength(4);
    expect(findLiterals('.a { white-space: nowrap; color: var(--color-text); } /* #fff */')).toEqual([]);
  });
});
