# A6 — `CustomerPortalPage` raw fetch leaks cookies

**Item:** A6 · **Severity:** P0 · **Effort:** S · **Owner:** FE + SEC
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by report 02

## Context

`frontend/src/pages/CustomerPortalPage.tsx:191-198` uses raw `fetch('/api/v1/portal/lookup', ...)`. The default `credentials` for same-origin `fetch` is `'same-origin'`, meaning the browser **sends cookies** with the request. If a logged-in employee (admin/goldsmith) visits `/portal/*` (e.g. to test the customer flow), their authenticated session cookie travels with what should be a fully-unauthenticated public-portal lookup. The backend portal endpoint doesn't read the cookie today, but the leak is still there on the wire, logged by any proxy, and any future backend change that opportunistically inspects cookies becomes a cross-privilege bridge.

Confirmed current state (2026-04-23):
```tsx
const response = await fetch('/api/v1/portal/lookup', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    reference_number: referenceNumber.trim(),
    email: email.trim(),
  }),
});
```

No `credentials:` option set → browser default = `same-origin` → cookies sent.

## Goal

The portal lookup never sends any authentication cookie. Preferably it flows through `apiClient` with `withCredentials: false` so we also get consistent timeout, logging, error shape, and interceptor behaviour.

## Files

- **Modify** `frontend/src/pages/CustomerPortalPage.tsx` — lines 191–ish.
- **Modify or confirm** `frontend/src/api/client.ts` — already has the shared client; if it's not trivial to override `withCredentials` per request, use a one-shot `axios.create({ withCredentials: false })` instance for public endpoints, OR set `credentials: 'omit'` on the native fetch (simplest).
- **Create or extend** `frontend/src/pages/CustomerPortalPage.test.tsx` — Vitest unit test verifying the request never sends credentials.

## Acceptance criteria

- [ ] Unit test asserts `fetch` (or axios) is called with `credentials: 'omit'` (or `withCredentials: false` if using axios) when the user submits the lookup form.
- [ ] Manual DevTools check: in a logged-in session, submitting the public portal form → Network tab shows the request with **no Cookie header** (or with Cookie but `credentials:'omit'` strips it — the former is strictly correct).
- [ ] Other request flows on the page (if any) still use `apiClient` or cookies as appropriate.
- [ ] No regression: `yarn test` green, `yarn build` green.

## Test design (TDD)

```tsx
// frontend/src/pages/CustomerPortalPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CustomerPortalPage from './CustomerPortalPage';

describe('CustomerPortalPage — public portal lookup', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'abc', expires_in: 3600 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
  });

  it('submits lookup without credentials', async () => {
    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/auftragsnummer/i), {
      target: { value: 'ORD-123' },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'a@b.de' },
    });
    fireEvent.click(screen.getByRole('button', { name: /anzeigen|suchen|lookup/i }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.credentials).toBe('omit');
    expect(init?.method?.toUpperCase()).toBe('POST');
  });
});
```

## Implementation sketch

Simplest approach — keep the native `fetch`, add `credentials: 'omit'`:

```tsx
const response = await fetch('/api/v1/portal/lookup', {
  method: 'POST',
  credentials: 'omit',  // NEW — never send cookies on public endpoint
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    reference_number: referenceNumber.trim(),
    email: email.trim(),
  }),
});
```

If the project prefers flowing through `apiClient`, check whether axios supports per-request override of `withCredentials`:

```tsx
// axios does allow per-request override
await apiClient.post('/portal/lookup', {
  reference_number: referenceNumber.trim(),
  email: email.trim(),
}, { withCredentials: false });
```

The latter is cleaner (consistent interceptors) but may route through error handlers that assume authenticated context. Start with `credentials: 'omit'` on native fetch; if that works and tests pass, ship that.

## Parallel-safety

Owns `frontend/src/pages/CustomerPortalPage.tsx` and a new test file. No other Wave-1 item touches this page. (A5 touches `App.tsx` / `MainLayout.tsx` — disjoint.)

## Commit message

```
fix(portal): stop leaking auth cookie on public /portal/lookup

Fix item A6 — the public portal's raw fetch used the browser's
default `credentials: 'same-origin'`, sending any authenticated
session cookie on a lookup request that should be fully
unauthenticated. Explicit `credentials: 'omit'` closes the leak.

Ref: docs/fix-plan/2026-04-23/A6-portal-fetch.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Any OTHER raw `fetch(` calls in `CustomerPortalPage.tsx`? `grep -n "fetch(" frontend/src/pages/CustomerPortalPage.tsx` — if more exist (e.g. for loading linked order details post-token), they also need `credentials: 'omit'` unless they MUST be authenticated.
- Is there a separate /portal/* route path that also does lookups? The review only flagged `CustomerPortalPage.tsx`; if there's a sibling page under `/portal/`, audit those too before closing the item.
