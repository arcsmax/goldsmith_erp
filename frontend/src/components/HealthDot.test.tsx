// LV2-02: /health is served by the backend at root, outside /api/v1. Before
// the fix neither the Vite proxy nor nginx forwarded it, so the request fell
// through to the SPA's index.html — a 200 with an unrelated body — and
// data.status came back undefined, which the sidebar announced verbatim as
// "Systemstatus: undefined". These tests pin the defensive parsing: any
// response that isn't a known status string renders as "unbekannt" with the
// warning (amber) dot, never the raw value.
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const getHealth = vi.fn();

vi.mock('../contexts', () => ({
  useAuth: () => ({ hasRole: (roles: string[]) => roles.includes('ADMIN') }),
}));
vi.mock('../api/admin', () => ({ getHealth: () => getHealth() }));

import { HealthDot } from './HealthDot';

function renderHealthDot() {
  return render(
    <MemoryRouter>
      <HealthDot />
    </MemoryRouter>,
  );
}

describe('HealthDot', () => {
  it('shows the known status label and colour for a healthy response', async () => {
    getHealth.mockResolvedValue({ status: 'healthy' });
    renderHealthDot();

    const button = await screen.findByRole('button', { name: 'Systemstatus: OK' });
    expect(button.querySelector('.health-dot.healthy')).not.toBeNull();
  });

  it('shows "unbekannt" with the warning colour, never "undefined", when the body has no status', async () => {
    // Simulates the SPA-fallback body: a 200 response with no `status` field.
    getHealth.mockResolvedValue({});
    renderHealthDot();

    const button = await screen.findByRole('button', { name: 'Systemstatus: unbekannt' });
    expect(button.querySelector('.health-dot.degraded')).not.toBeNull();
    expect(button.querySelector('.health-dot.unhealthy')).toBeNull();
    expect(screen.queryByText(/undefined/)).toBeNull();
  });

  it('shows "unbekannt" with the warning colour when the fetch rejects', async () => {
    getHealth.mockRejectedValue(new Error('network error'));
    renderHealthDot();

    const button = await screen.findByRole('button', { name: 'Systemstatus: unbekannt' });
    expect(button.querySelector('.health-dot.degraded')).not.toBeNull();
  });
});
