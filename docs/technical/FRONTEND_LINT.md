# Frontend ESLint (OPS-13, FE-15, issue #33)

`frontend/eslint.config.js` is an ESLint 9 flat config: `@eslint/js` +
`typescript-eslint` recommended, `eslint-plugin-react` (+ `jsx-runtime`),
`eslint-plugin-react-hooks` (only `rules-of-hooks`: error, `exhaustive-deps`:
warn — not the v7 preset's React Compiler rules, which don't apply here), and
six `eslint-plugin-jsx-a11y` rules from the UI-UX playbook as errors
(`click-events-have-key-events`, `no-static-element-interactions`,
`label-has-associated-control`, `alt-text`, `aria-props`, `no-autofocus`), plus
`no-console` (warn, `warn`/`error` allowed). Hex/rgb/hsl colour literals in
`.tsx` are already covered by `scripts/hex-ratchet.mjs` (scans `.ts(x)`/`.js(x)`/`.css`), not a separate ESLint rule.

**Commands:** `yarn lint` (`eslint . --max-warnings 198`, fails on any error or
if warnings exceed the baseline), `yarn lint:fix`, `make lint-frontend` (also
runs inside `make lint-local`). CI runs `yarn lint` in the `lint-frontend` job.

**Warning baseline:** 198, mostly pre-existing `@typescript-eslint/no-explicit-any`
and `no-unused-vars`. Lower it (edit the `--max-warnings` number in
`package.json`) as warnings are cleaned up — never raise it silently.

**Known open errors (22, not fixed — owned by other in-flight work, do not
touch without coordinating):** `components/orders/OrderFormModal.tsx`,
`components/orders/StatusChangeDialog.tsx`, `components/repairs/IntakeChecklist.tsx`,
`pages/RepairsPage.tsx`, `pages/RepairDetailPage.tsx` (label/click/autofocus
errors), and one `no-useless-catch` in `pages/CustomerDetailPage.tsx`. `yarn
lint` will not exit 0 until these are fixed.

**Common escape hatch:** the hand-rolled `modal-overlay`/`modal-content`
backdrop-dismiss pattern (used before a shared `Modal` primitive exists) gets a
targeted `eslint-disable-next-line` with a one-line reason instead of forcing
DOM roles onto plain event-bubbling wrappers — see the comments in e.g.
`components/CustomerFormModal.tsx`.
