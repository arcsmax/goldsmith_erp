// ESLint 9 flat config (OPS-13, FE-15, issue #33).
//
// Scope decisions, documented here so they aren't a mystery later:
// - typescript-eslint uses the non-type-checked "recommended" preset (fast,
//   no `parserOptions.project` needed across src/e2e/scripts which aren't
//   all covered by one tsconfig).
// - react-hooks: only `rules-of-hooks` (error) and `exhaustive-deps` (warn)
//   are enabled, NOT the plugin's full v7 "recommended" preset — that preset
//   also ships a dozen React Compiler rules (react-hooks/immutability,
//   set-state-in-render, purity, gating, ...) that assume compiler-oriented
//   code this project was never written against. Enabling them would flood
//   the baseline with unrelated findings.
// - jsx-a11y: only the 6 rules the UI-UX playbook calls out are enabled as
//   errors (click-events-have-key-events, no-static-element-interactions,
//   label-has-associated-control, alt-text, aria-props, no-autofocus), not
//   the plugin's full "recommended" preset. jsx-a11y 6.x's recommended
//   preset sets ~30 rules to "error" (html-has-lang, scope, anchor-is-valid,
//   no-redundant-roles, ...) which is a much larger, separate effort from
//   the playbook-driven set this task fixes.
// - Hex-colour-in-.tsx coverage: `scripts/hex-ratchet.mjs` already scans
//   `.tsx` (and `.ts`/`.js`/`.jsx`/`.css`) for hex/rgb()/hsl() literals
//   outside brand-tokens.css, so no separate ESLint rule is added for it —
//   see `yarn hex-ratchet` / the FRONTEND_LINT.md doc.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'dev-dist/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
      'node_modules/**',
      'public/**',
      'src/api/generated/**',
      '.yarn/**',
    ],
  },
  // App source: browser React/TSX code.
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    plugins: {
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: '18.3' },
    },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...react.configs.flat['jsx-runtime'].rules,
      // TypeScript already enforces prop shapes; PropTypes are unused here.
      'react/prop-types': 'off',

      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      'jsx-a11y/click-events-have-key-events': 'error',
      'jsx-a11y/no-static-element-interactions': [
        'error',
        {
          allowExpressionValues: true,
          handlers: ['onClick', 'onMouseDown', 'onMouseUp', 'onKeyPress', 'onKeyDown', 'onKeyUp'],
        },
      ],
      'jsx-a11y/label-has-associated-control': 'error',
      'jsx-a11y/alt-text': 'error',
      'jsx-a11y/aria-props': 'error',
      'jsx-a11y/no-autofocus': 'error',

      'no-console': ['warn', { allow: ['warn', 'error'] }],

      // Baseline-relaxed until the codebase is swept separately (not part
      // of OPS-13/FE-15): unused vars and `any` are common in this
      // pre-existing code and out of scope for the lint rollout itself.
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  // Unit/component tests: same rules, plus vitest + jsdom-ish globals.
  {
    files: ['src/**/*.{test,spec}.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.vitest },
    },
    rules: {
      'jsx-a11y/click-events-have-key-events': 'off',
      'jsx-a11y/no-static-element-interactions': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
  // Playwright e2e specs: Node + Playwright runner, no React/jsx-a11y.
  {
    files: ['e2e/**/*.ts', 'playwright.config.ts'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.node },
    },
    rules: {
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  // Node build/config scripts.
  {
    files: ['scripts/**/*.mjs', '*.config.ts', '*.config.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.node },
    },
    rules: {
      'no-console': 'off',
    },
  },
);
