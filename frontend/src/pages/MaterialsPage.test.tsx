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
import { render, screen } from '@testing-library/react';
import type { MaterialType } from '../types';

const mockGetAll = vi.fn();
vi.mock('../api', () => ({
  materialsApi: {
    getAll: (...args: unknown[]) => mockGetAll(...args),
  },
}));

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
    mockGetAll.mockResolvedValue([makeViewerProjectedMaterial()]);

    render(<MaterialsPage />);

    expect(await screen.findByText('Feingold 999')).toBeInTheDocument();
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
    mockGetAll.mockResolvedValue([makeFullMaterial()]);

    render(<MaterialsPage />);

    expect(await screen.findByText('Feingold 999')).toBeInTheDocument();
    expect(screen.getByText('Preis/Einheit')).toBeInTheDocument();
    expect(screen.getByText('Wert')).toBeInTheDocument();
    expect(screen.getByText(/Gesamtwert/)).toBeInTheDocument();
  });
});
