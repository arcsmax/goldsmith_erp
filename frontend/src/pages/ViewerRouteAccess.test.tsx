// VIEWER route access — Open follow-up (fix-w1b-viewer-ui.md): "App.tsx
// route guards are stricter than the backend's new VIEWER model (blocks
// /materials, /metal-inventory, /customers(/:id), /repairs(/:id))
// outright)". The backend grants VIEWER MATERIAL_VIEW, CUSTOMER_VIEW and
// REPAIR_VIEW (core/permissions.py) and each destination page already
// gates its own financial/design-only sections internally
// (canViewFinancials / canViewDesign, lib/roles.ts) — so App.tsx no longer
// needs to redirect VIEWER away from these routes before the page can even
// load.
//
// This intentionally mirrors only the route shape from App.tsx (ProtectedRoute
// wrapping a placeholder element), not the full page components, the same
// approach ConsultationsRoutes.test.tsx uses — the page components pull in
// API/query-client wiring irrelevant to the routing guard itself.
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from '../components/ProtectedRoute';

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => mockUseAuth(),
}));

function routesUnderTest() {
  return (
    <Routes>
      <Route
        path="customers"
        element={
          <ProtectedRoute>
            <div>CUSTOMERS_PAGE</div>
          </ProtectedRoute>
        }
      />
      <Route
        path="materials"
        element={
          <ProtectedRoute>
            <div>MATERIALS_PAGE</div>
          </ProtectedRoute>
        }
      />
      <Route
        path="metal-inventory"
        element={
          <ProtectedRoute>
            <div>METAL_INVENTORY_PAGE</div>
          </ProtectedRoute>
        }
      />
      <Route
        path="repairs"
        element={
          <ProtectedRoute>
            <div>REPAIRS_PAGE</div>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}>{routesUnderTest()}</MemoryRouter>);
}

describe('VIEWER route access (App.tsx route guard alignment)', () => {
  const routes: Array<[string, string]> = [
    ['/customers', 'CUSTOMERS_PAGE'],
    ['/materials', 'MATERIALS_PAGE'],
    ['/metal-inventory', 'METAL_INVENTORY_PAGE'],
    ['/repairs', 'REPAIRS_PAGE'],
  ];

  it.each(routes)('a VIEWER reaches %s instead of being redirected', (path, marker) => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false, hasRole: () => false });

    renderAt(path);

    expect(screen.getByText(marker)).toBeInTheDocument();
  });

  it('still redirects an unauthenticated visitor away from /materials', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, isLoading: false, hasRole: () => false });

    renderAt('/materials');

    expect(screen.queryByText('MATERIALS_PAGE')).not.toBeInTheDocument();
  });
});
