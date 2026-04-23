// CustomerPortalPage tests — fix item A6.
//
// The public portal is served under /portal and MUST never send an
// authenticated session cookie on its lookup request. The browser default
// for same-origin `fetch` is `credentials: 'same-origin'`, so any admin /
// goldsmith session cookie in the browser would be transmitted to the
// public endpoint. This test pins the mitigation: the request MUST use
// `credentials: 'omit'`.
//
// Ref: docs/fix-plan/2026-04-23/A6-portal-fetch.md

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import CustomerPortalPage from './CustomerPortalPage';

describe('CustomerPortalPage — public portal lookup', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          reference_number: 'ORD-123',
          record_type: 'order',
          status_key: 'in_progress',
          status_label: 'In Arbeit',
          item_title: 'Ehering',
          current_step: 2,
          total_steps: 5,
          step_label: 'Goldschmiedearbeit',
          pipeline_labels: ['A', 'B', 'C', 'D', 'E'],
          estimated_completion: null,
          is_complete: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      )
    );
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('submits lookup with credentials: "omit" to avoid leaking auth cookies', async () => {
    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );

    fireEvent.change(
      screen.getByLabelText(/Auftragsnummer oder Reparaturnummer/i),
      { target: { value: 'ORD-123' } }
    );
    fireEvent.change(screen.getByLabelText(/E-Mail-Adresse/i), {
      target: { value: 'customer@example.de' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: /status prüfen/i })
    );

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [
      string,
      RequestInit | undefined,
    ];
    expect(url).toBe('/api/v1/portal/lookup');
    expect(init?.method?.toUpperCase()).toBe('POST');
    // The load-bearing assertion for A6:
    expect(init?.credentials).toBe('omit');
  });

  it('sends the trimmed reference number and email in the JSON body', async () => {
    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );

    fireEvent.change(
      screen.getByLabelText(/Auftragsnummer oder Reparaturnummer/i),
      { target: { value: '  ORD-999  ' } }
    );
    fireEvent.change(screen.getByLabelText(/E-Mail-Adresse/i), {
      target: { value: '  user@example.de  ' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: /status prüfen/i })
    );

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const [, init] = fetchSpy.mock.calls[0] as [
      string,
      RequestInit | undefined,
    ];
    expect(init?.body).toBeDefined();
    const payload = JSON.parse(init!.body as string);
    expect(payload).toEqual({
      reference_number: 'ORD-999',
      email: 'user@example.de',
    });
  });
});
