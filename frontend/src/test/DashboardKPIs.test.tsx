// DashboardKPIs click-navigation tests.
//
// Scope:
//   * Each KPI card that advertises "Klicken Sie auf die KPI-Karten für
//     weitere Details" must actually wire navigation on click.
//   * Cards must be keyboard accessible — Enter and Space activate the
//     same handler as a mouse click (role="button", tabIndex=0).
//   * Regression guard for the previously-orphaned "Umsatz (Monat)" card
//     which had no onClick at all.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Hoisted navigate mock so the react-router-dom factory below can refer to it.
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

// Stub the API surface used by DashboardKPIs so no network calls fire.
vi.mock('../api', () => ({
  ordersApi: {
    getAll: vi.fn(async () => []),
  },
  metalInventoryApi: {
    getStatistics: vi.fn(async () => ({ total_value: 1234 })),
  },
  timeTrackingApi: {
    getSummary: vi.fn(async () => ({ total_hours: 7.5 })),
  },
}));

import { DashboardKPIs } from '../components/dashboard/DashboardKPIs';
import { MemoryRouter } from 'react-router-dom';

function renderKPIs(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <DashboardKPIs />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.navigate.mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('DashboardKPIs — KPI card click navigation', () => {
  it('navigates to /orders when the "Aktive Aufträge" card is clicked', async () => {
    renderKPIs();
    // Wait for loading skeletons to disappear.
    const card = await screen.findByRole('button', { name: /Aktive Aufträge/i });
    await userEvent.click(card);
    expect(mocks.navigate).toHaveBeenCalledWith('/orders');
  });

  it('navigates to /orders?status=in_progress when the "In Produktion" card is clicked', async () => {
    renderKPIs();
    const card = await screen.findByRole('button', { name: /In Produktion/i });
    await userEvent.click(card);
    expect(mocks.navigate).toHaveBeenCalledWith('/orders?status=in_progress');
  });

  it('navigates to /metal-inventory when the "Inventarwert" card is clicked', async () => {
    renderKPIs();
    const card = await screen.findByRole('button', { name: /Inventarwert/i });
    await userEvent.click(card);
    expect(mocks.navigate).toHaveBeenCalledWith('/metal-inventory');
  });

  it('navigates to /time-tracking when the "Stunden (Woche)" card is clicked', async () => {
    renderKPIs();
    const card = await screen.findByRole('button', { name: /Stunden \(Woche\)/i });
    await userEvent.click(card);
    expect(mocks.navigate).toHaveBeenCalledWith('/time-tracking');
  });

  it('navigates to /orders?status=completed when the "Umsatz (Monat)" card is clicked (regression)', async () => {
    renderKPIs();
    // Previously this card rendered without onClick, so role=button was
    // absent. The fix wires it to the completed-orders view.
    const card = await screen.findByRole('button', { name: /Umsatz \(Monat\)/i });
    await userEvent.click(card);
    expect(mocks.navigate).toHaveBeenCalledWith('/orders?status=completed');
  });

  it('activates click handler on Enter keypress (keyboard a11y)', async () => {
    renderKPIs();
    const card = await screen.findByRole('button', { name: /Aktive Aufträge/i });
    card.focus();
    await userEvent.keyboard('{Enter}');
    expect(mocks.navigate).toHaveBeenCalledWith('/orders');
  });

  it('activates click handler on Space keypress (keyboard a11y)', async () => {
    renderKPIs();
    const card = await screen.findByRole('button', { name: /Aktive Aufträge/i });
    card.focus();
    await userEvent.keyboard(' ');
    expect(mocks.navigate).toHaveBeenCalledWith('/orders');
  });
});
