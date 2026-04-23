# A5 — Top-level + MainLayout `ErrorBoundary`

**Item:** A5 · **Severity:** P0 · **Effort:** S · **Owner:** FE
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by report 02

## Context

The frontend has **no `ErrorBoundary` anywhere** (confirmed 2026-04-23 via `grep -rn "ErrorBoundary\|componentDidCatch\|getDerivedStateFromError" frontend/src`). A single render crash in any lazy-loaded page — or e.g. `QuickActionModalV2.buildEntityDisplay` on a malformed resolve response — unmounts the entire `<Suspense>` and shows a blank screen. In the workshop, a goldsmith won't know to hard-reload; they'll think the device is broken.

React's error boundary is the only mechanism to recover from render errors. Needs to be a class component (hooks can't catch).

## Goal

Two levels of boundary:
1. **Top-level** in `App.tsx` — wraps the whole `<Suspense>` + router. Catches app-level render disasters; fallback UI lets the user reload the app.
2. **Inner** in `MainLayout.tsx` — wraps `<Outlet />`. A single page crash only kills that page; the timer widget, scan FAB, nav, and notification bell stay alive.

Fallback UX: error digest (dev only) + "Neu laden" button + "Zur Startseite" button. Matches the project's German copy.

## Files

- **Create** `frontend/src/components/ErrorBoundary.tsx` — class component.
- **Create** `frontend/src/components/ErrorBoundary.test.tsx` — Vitest unit test.
- **Modify** `frontend/src/App.tsx` — wrap the root `<Suspense>` in `<ErrorBoundary variant="app">`.
- **Modify** `frontend/src/layouts/MainLayout.tsx` — wrap the `<Outlet />` in `<ErrorBoundary variant="page">`.

## Acceptance criteria

- [ ] Unit test: a child that throws on render → boundary renders fallback with a retry button; clicking "Neu laden" re-renders (error cleared).
- [ ] Unit test: a child that throws → `console.error` is called (not swallowed) so the error is observable in dev.
- [ ] Manual smoke: add `throw new Error('BOUNDARY_TEST')` in `DashboardPage` temporarily, `yarn dev`, navigate to `/`. Expect MainLayout to remain (nav + timer visible), page content replaced by fallback. Revert the test throw.
- [ ] Manual smoke: put the throw in `App.tsx` (pre-router level). Expect the app-level boundary to render.
- [ ] No regression: `yarn test` (Vitest) stays green.
- [ ] No regression: `yarn build` still succeeds.
- [ ] No emoji in the fallback UI unless explicitly added (per project rule).

## Test design (TDD)

Write this test first:

```tsx
// frontend/src/components/ErrorBoundary.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

function Boom({ msg = 'kaboom' }: { msg?: string }): JSX.Element {
  throw new Error(msg);
}

describe('ErrorBoundary', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    // React logs errors to console.error in dev — suppress + assert
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders children when no error', () => {
    render(
      <ErrorBoundary variant="page">
        <div>hello</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('renders fallback when child throws', () => {
    render(
      <ErrorBoundary variant="page">
        <Boom />
      </ErrorBoundary>
    );
    // German copy; adapt to whatever the implementation uses
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /neu laden/i })).toBeInTheDocument();
  });

  it('clears error when retry is clicked', () => {
    const { rerender } = render(
      <ErrorBoundary variant="page">
        <Boom />
      </ErrorBoundary>
    );
    fireEvent.click(screen.getByRole('button', { name: /neu laden/i }));
    // After retry, boundary state resets; re-render with non-throwing child
    rerender(
      <ErrorBoundary variant="page">
        <div>recovered</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('recovered')).toBeInTheDocument();
  });

  it('calls console.error (visible in dev)', () => {
    render(
      <ErrorBoundary variant="page">
        <Boom msg="visible-error" />
      </ErrorBoundary>
    );
    expect(consoleErrorSpy).toHaveBeenCalled();
  });
});
```

## Implementation sketch

```tsx
// frontend/src/components/ErrorBoundary.tsx
import { Component, type ReactNode, type ErrorInfo } from 'react';

export type ErrorBoundaryVariant = 'app' | 'page';

interface Props {
  variant: ErrorBoundaryVariant;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught', error, info);
    // V1.2 hook: send to Sentry once integrated (see FIX-PLAN.md#1.8c).
  }

  handleRetry = (): void => {
    this.setState({ error: null });
  };

  handleHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    if (this.state.error) {
      const isApp = this.props.variant === 'app';
      return (
        <div role="alert" className="error-boundary" data-variant={this.props.variant}>
          <h1>Etwas ist schiefgelaufen.</h1>
          <p>
            {isApp
              ? 'Die Anwendung konnte nicht geladen werden. Bitte neu laden.'
              : 'Diese Seite hat einen Fehler. Du kannst es erneut versuchen oder zur Startseite zurückkehren.'}
          </p>
          {import.meta.env.DEV && (
            <pre className="error-boundary__details">
              {this.state.error.message}
            </pre>
          )}
          <div className="error-boundary__actions">
            <button type="button" onClick={this.handleRetry}>Neu laden</button>
            {!isApp && (
              <button type="button" onClick={this.handleHome}>Zur Startseite</button>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
```

### Wiring

`App.tsx` — wrap root Suspense (read current file to find exact spot):
```tsx
<ErrorBoundary variant="app">
  <Suspense fallback={<LoadingScreen />}>
    <RouterProvider router={router} />
  </Suspense>
</ErrorBoundary>
```

`MainLayout.tsx` — wrap the Outlet:
```tsx
<ErrorBoundary variant="page">
  <Outlet />
</ErrorBoundary>
```

## Parallel-safety

Owns `frontend/src/components/ErrorBoundary.tsx` (new), `.test.tsx` (new), `App.tsx`, `layouts/MainLayout.tsx`. No other Wave-1 item touches these files.

## Commit message

```
feat(frontend): add ErrorBoundary at app + page level

Fix item A5 — without a boundary, a single render crash unmounted
Suspense and showed a blank screen. Two boundaries: app-level (wraps
Suspense/router) and page-level (wraps Outlet) so a page crash doesn't
kill the shell (timer, FAB, nav stay alive).

Ref: docs/fix-plan/2026-04-23/A5-error-boundary.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- **Styling**: is there a shared stylesheet location for this? Inline styles are fine for a first pass; if the project uses CSS modules elsewhere, match that. Keep the fallback accessible (role="alert", focusable buttons, no emoji).
- **Dev-only stack trace**: `import.meta.env.DEV` is Vite-standard; confirm the build env exposes this (should be default).
- **When Sentry lands (FIX-PLAN.md §1.8c)**: leave a `// V1.2 hook` comment in `componentDidCatch` pointing at where the `Sentry.captureException(error, { contexts: { react: info } })` call will go.
