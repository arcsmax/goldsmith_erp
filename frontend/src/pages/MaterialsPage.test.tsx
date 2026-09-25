// MaterialsPage — VIEWER role-projection regression (SEC-01/GDPR-03).
//
// GET /materials/ is "projected" for VIEWER — the request still succeeds,
// but `unit_price` and `stock_value` are stripped from every item (see
// tests/integration/test_viewer_role_projection.py::materials_list). Before
// this fix, `material.unit_price.toFixed(2)` crashed on the resulting
// `undefined` for the very first row. This test pins: no crash, "—" instead
// of a crash/"undefined", and the price/value columns disappear entirely;
// GOLDSMITH keeps seeing real prices.
import { describe, expect, it, vi, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import type { MaterialType } from '../types';
import { renderWithQuery } from '../test/queryWrapper';

// W4-03: the page reads GET /materials/?offset=… (Page envelope).
const mockPage = vi.fn();
vi.mock('../api/paged', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/paged')>();
  return {
    ...actual,
    pagedApi: { ...actual.pagedApi, materials: (...args: unknown[]) => mockPage(...args) },
  };
});

function pageOf(items: MaterialType[]) {
  return { items, total: items.length, limit: 25, offset: 0, next_offset: null };
}

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
  useAuth: () => mockUseAuth(),
}));

vi.mock('../components/materials/MaterialFormModal', () => ({
  MaterialFormModal: () => null,
}));

import { MaterialsPage } from './MaterialsPage';

// Mirrors the real (type-violating) wire payload a VIEWER receives —
// role_projection.py omits `unit_price` and `stock_value` entirely rather
// than sending null, so the field is well and truly `undefined` at runtime.
function makeViewerProjectedMaterial(): MaterialType {
  const material = {
    id: 1,
    name: 'Feingold 999',
    description: 'Granulat',
    stock: 42,
    unit: 'g',
  } as MaterialType;
  return material;
}

function makeFullMaterial(): MaterialType {
  return {
    id: 1,
    name: 'Feingold 999',
    description: 'Granulat',
    unit_price: 62.5,
    stock: 42,
    unit: 'g',
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('MaterialsPage — VIEWER role projection', () => {
  it('does not crash and shows no price/value columns when unit_price is absent', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER' } });
    mockPage.mockResolvedValue(pageOf([makeViewerProjectedMaterial()]));

    renderWithQuery(<MaterialsPage />);

    expect((await screen.findAllByText('Feingold 999')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Preis/Einheit')).not.toBeInTheDocument();
    expect(screen.queryByText('Wert')).not.toBeInTheDocument();
    // No leaked "undefined €" / "NaN €" anywhere in the row.
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    // Total-value summary line is omitted, not "Gesamtwert: NaN €".
    expect(screen.queryByText(/Gesamtwert/)).not.toBeInTheDocument();
  });

  it('shows the price/value columns and totals for GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockPage.mockResolvedValue(pageOf([makeFullMaterial()]));

    renderWithQuery(<MaterialsPage />);

    expect((await screen.findAllByText('Feingold 999')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Preis/Einheit').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Wert').length).toBeGreaterThan(0);
    expect(screen.getByText(/Gesamtwert/)).toBeInTheDocument();
  });

  it('offers create/edit/delete only to ADMIN (MATERIAL_CREATE/EDIT/DELETE)', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockPage.mockResolvedValue(pageOf([makeFullMaterial()]));
    const { unmount } = renderWithQuery(<MaterialsPage />);
    await screen.findAllByText('Feingold 999');
    expect(screen.queryByRole('button', { name: 'Material anlegen' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Feingold 999 löschen' })).not.toBeInTheDocument();
    unmount();

    mockUseAuth.mockReturnValue({ user: { role: 'ADMIN' } });
    renderWithQuery(<MaterialsPage />);
    await screen.findAllByText('Feingold 999');
    expect(screen.getByRole('button', { name: 'Material anlegen' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Feingold 999 löschen' }).length).toBeGreaterThan(0);
  });
});
