// Parser for styles/brand-tokens.css used by themeTokens.test.ts (W4-05).
// Reads the token file as text and returns the custom properties of each
// theme layer, so tests can check completeness and compute WCAG contrast.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export type TokenMap = Readonly<Record<string, string>>;

export interface ThemeTokens {
  /** @theme static primitives (--color-brand-* ramps, fonts). */
  primitives: TokenMap;
  /** Every top-level `:root { }` block (semantic + legacy tiers). */
  light: TokenMap;
  /** `:root.dark { }` */
  dark: TokenMap;
  /** `@media (prefers-color-scheme: dark) { :root:not(.light):not(.dark) { } }` */
  systemDark: TokenMap;
}

interface Rule {
  prelude: string[];
  declarations: TokenMap;
}

export const TOKEN_FILE = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  'styles',
  'brand-tokens.css',
);

function parseDeclarations(body: string): TokenMap {
  const entries = body
    .split(';')
    .map((part) => part.trim())
    .filter((part) => part.startsWith('--'))
    .map((part) => {
      const colon = part.indexOf(':');
      return [part.slice(0, colon).trim(), part.slice(colon + 1).trim()] as const;
    });
  return Object.fromEntries(entries);
}

/** Minimal brace scanner: enough for a flat token file, not a CSS parser. */
export function parseRules(css: string): Rule[] {
  const source = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules: Rule[] = [];
  const stack: { prelude: string; body: string }[] = [];
  let buffer = '';
  for (const char of source) {
    if (char === '{') {
      stack.push({ prelude: buffer.trim().split(';').pop()?.trim() ?? '', body: '' });
      buffer = '';
    } else if (char === '}') {
      const frame = stack.pop();
      if (!frame) throw new Error('unbalanced } in token file');
      rules.push({
        prelude: [...stack.map((f) => f.prelude), frame.prelude],
        declarations: parseDeclarations(frame.body),
      });
      buffer = '';
    } else if (stack.length > 0) {
      stack[stack.length - 1].body += char;
      buffer += char;
    } else {
      buffer += char;
    }
  }
  return rules;
}

function merge(rules: Rule[], match: (prelude: string[]) => boolean): TokenMap {
  return Object.assign({}, ...rules.filter((r) => match(r.prelude)).map((r) => r.declarations));
}

const is = (...expected: string[]) => (prelude: string[]): boolean =>
  prelude.length === expected.length && prelude.every((p, i) => p === expected[i]);

export function loadThemeTokens(css: string = readFileSync(TOKEN_FILE, 'utf8')): ThemeTokens {
  const rules = parseRules(css);
  return {
    primitives: merge(rules, is('@theme static')),
    light: merge(rules, is(':root')),
    dark: merge(rules, is(':root.dark')),
    systemDark: merge(rules, is('@media (prefers-color-scheme: dark)', ':root:not(.light):not(.dark)')),
  };
}

const HEX6 = /^#[0-9a-fA-F]{6}$/;
const SINGLE_VAR = /^var\((--[\w-]+)\)$/;

/**
 * Resolve a token to a #rrggbb value for one scheme, following var() chains.
 * Returns null for values that are not a single colour (gradients, color-mix).
 */
export function resolveColour(
  tokens: ThemeTokens,
  name: string,
  scheme: 'light' | 'dark',
  depth = 0,
): string | null {
  if (depth > 10) throw new Error(`var() cycle at ${name}`);
  const value =
    (scheme === 'dark' ? tokens.dark[name] : undefined) ?? tokens.light[name] ?? tokens.primitives[name];
  if (value === undefined) throw new Error(`token ${name} is not defined`);
  if (HEX6.test(value)) return value.toLowerCase();
  const ref = SINGLE_VAR.exec(value);
  return ref ? resolveColour(tokens, ref[1], scheme, depth + 1) : null;
}

/** A light value that only aliases other semantic tokens follows the theme by itself. */
export function isDerived(value: string): boolean {
  return !/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|var\(--color-brand-/.test(value);
}
