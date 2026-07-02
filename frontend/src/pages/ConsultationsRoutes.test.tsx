// Consultations route-matching test — Task 9 (V1.1 consultation frontend).
//
// App.tsx registers three /consultations routes: a static "" (list), a
// static "new" segment, and a dynamic ":id" segment. react-router v7
// ranks static path segments above dynamic ones during matching
// regardless of array order, so /consultations/new should always resolve
// to the wizard-new route and never be captured by :id — but that's a
// framework-matching guarantee worth pinning explicitly rather than
// trusting by inspection, per the Task 9 brief.
//
// This intentionally mirrors only the /consultations route shape from
// App.tsx (not the full app tree — MainLayout pulls in NotificationBell,
// GlobalSearch, ScanFab, etc., none of which are relevant to router
// matching behavior and would need extensive unrelated mocking to render).
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

function ConsultationsRoutesUnderTest() {
  return (
    <Routes>
      <Route path="consultations" element={<div>LIST</div>} />
      <Route path="consultations/new" element={<div>WIZARD_NEW</div>} />
      <Route path="consultations/:id" element={<div>WIZARD_ID</div>} />
    </Routes>
  );
}

describe('consultations route matching', () => {
  it('/consultations/new resolves to the wizard-new route, not :id', () => {
    render(
      <MemoryRouter initialEntries={['/consultations/new']}>
        <ConsultationsRoutesUnderTest />
      </MemoryRouter>
    );

    expect(screen.getByText('WIZARD_NEW')).toBeInTheDocument();
    expect(screen.queryByText('WIZARD_ID')).not.toBeInTheDocument();
  });

  it('/consultations/42 resolves to the dynamic :id route', () => {
    render(
      <MemoryRouter initialEntries={['/consultations/42']}>
        <ConsultationsRoutesUnderTest />
      </MemoryRouter>
    );

    expect(screen.getByText('WIZARD_ID')).toBeInTheDocument();
  });

  it('/consultations resolves to the list route', () => {
    render(
      <MemoryRouter initialEntries={['/consultations']}>
        <ConsultationsRoutesUnderTest />
      </MemoryRouter>
    );

    expect(screen.getByText('LIST')).toBeInTheDocument();
  });
});
