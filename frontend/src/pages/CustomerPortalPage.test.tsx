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

const LOOKUP_URL = '/api/v1/portal/lookup';
const CONTACT_URL = '/api/v1/portal/workshop-contact';

/** The page also fetches the public workshop-contact endpoint on mount
 * (W7 hygiene: real name/phone/email instead of a hardcoded placeholder).
 * Find the lookup-specific call among the mock's calls instead of assuming
 * index 0 — the contact fetch races it. */
function lookupCall(fetchSpy: ReturnType<typeof vi.spyOn>) {
  const call = fetchSpy.mock.calls.find(([url]: [RequestInfo | URL, RequestInit | undefined]) => url === LOOKUP_URL);
  if (!call) throw new Error('lookup fetch was never called');
  return call as [string, RequestInit | undefined];
}

describe('CustomerPortalPage — public portal lookup', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === CONTACT_URL) {
        return new Response(
          JSON.stringify({ name: 'Goldschmiede Musterstadt', phone: null, email: null }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(
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
      );
    });
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

    await waitFor(() => expect(fetchSpy.mock.calls.some(([u]: [RequestInfo | URL, RequestInit | undefined]) => u === LOOKUP_URL)).toBe(true));

    const [url, init] = lookupCall(fetchSpy);
    expect(url).toBe(LOOKUP_URL);
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

    await waitFor(() => expect(fetchSpy.mock.calls.some(([u]: [RequestInfo | URL, RequestInit | undefined]) => u === LOOKUP_URL)).toBe(true));
    const [, init] = lookupCall(fetchSpy);
    expect(init?.body).toBeDefined();
    const payload = JSON.parse(init!.body as string);
    expect(payload).toEqual({
      reference_number: 'ORD-999',
      email: 'user@example.de',
    });
  });

  it('shows the customer-facing status label and steps, never the staff label', async () => {
    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Auftragsnummer oder Reparaturnummer/i), {
      target: { value: 'ORD-123' },
    });
    fireEvent.change(screen.getByLabelText(/E-Mail-Adresse/i), {
      target: { value: 'customer@example.de' },
    });
    fireEvent.click(screen.getByRole('button', { name: /status prüfen/i }));

    expect(await screen.findByRole('heading', { name: 'Ehering' })).toBeInTheDocument();
    expect(screen.getByText('In Arbeit')).toBeInTheDocument();
    expect(screen.queryByText('In Bearbeitung')).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
    expect(screen.getByText('B').closest('li')).toHaveAttribute('aria-current', 'step');
  });

  it('reads a disabled or unknown lookup (404) as "not found" in plain language', async () => {
    // Override just the lookup response; the contact fetch keeps its
    // beforeEach behavior (200, harmless placeholder contact).
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === CONTACT_URL) {
        return new Response(
          JSON.stringify({ name: 'Goldschmiede Musterstadt', phone: null, email: null }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });
    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Auftragsnummer oder Reparaturnummer/i), {
      target: { value: 'X-1' },
    });
    fireEvent.change(screen.getByLabelText(/E-Mail-Adresse/i), {
      target: { value: 'customer@example.de' },
    });
    fireEvent.click(screen.getByRole('button', { name: /status prüfen/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('keinen Auftrag');
  });
});

describe('CustomerPortalPage — workshop contact (W7 hygiene)', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('shows the real workshop name and contact instead of the old hardcoded placeholder', async () => {
    fetchSpy = vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === CONTACT_URL) {
        return new Response(
          JSON.stringify({
            name: 'Goldschmiede Musterstadt',
            phone: '+49 30 1234567',
            email: 'kontakt@goldschmiede-musterstadt.de',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      throw new Error('unexpected fetch in this test');
    });

    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Goldschmiede Musterstadt')).toBeInTheDocument();
    const emailLink = screen.getByRole('link', { name: 'kontakt@goldschmiede-musterstadt.de' });
    expect(emailLink).toHaveAttribute('href', 'mailto:kontakt@goldschmiede-musterstadt.de');
    const phoneLink = screen.getByRole('link', { name: '+49 30 1234567' });
    expect(phoneLink).toHaveAttribute('href', 'tel:+49301234567');
    // The old fake placeholders must be gone.
    expect(screen.queryByText('info@goldschmiede.de')).not.toBeInTheDocument();
    expect(screen.queryByText('+49 0 000 000')).not.toBeInTheDocument();
  });

  it('falls back to a generic footer message when the contact fetch fails', async () => {
    fetchSpy = vi.spyOn(global, 'fetch').mockRejectedValue(new Error('network down'));

    render(
      <MemoryRouter initialEntries={['/portal']}>
        <CustomerPortalPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Fragen? Wenden Sie sich an Ihre Werkstatt.')).toBeInTheDocument();
    expect(screen.getByText('Goldschmiede')).toBeInTheDocument();
  });
});
