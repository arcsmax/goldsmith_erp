// LV-01: at 390px the header user menu (Scanner, name, "Abmelden") pushed
// the page 58px wider than the viewport. jsdom has no layout, so this test
// pins the responsive structure instead: those items carry
// .header-desktop-only (hidden below 600px in layout.css) and the drawer
// holds an account block with the same actions. The screenshot loop at 390
// checks the pixels.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const logout = vi.fn();

vi.mock('../contexts', () => ({
  useAuth: () => ({
    user: { first_name: 'Petra', email: 'petra@example.test', role: 'ADMIN' },
    logout,
    hasRole: () => true,
  }),
  useTimeTracking: () => ({
    runningEntry: null,
    stopTracking: vi.fn(),
    refreshRunningEntry: vi.fn(),
  }),
}));
vi.mock('../components/TimerWidget', () => ({ default: () => null }));
vi.mock('../components/scanner', () => ({ ScanFab: () => null, ScanOverlay: () => null }));
vi.mock('../components/HidBurstNudge', () => ({ HidBurstNudge: () => null }));
vi.mock('../components/NotificationBell', () => ({
  NotificationBell: () => <button type="button">Benachrichtigungen</button>,
}));
vi.mock('../components/HealthDot', () => ({ HealthDot: () => null }));
vi.mock('../components/GlobalSearch', () => ({ GlobalSearch: () => null }));

import { MainLayout } from './MainLayout';

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <MainLayout />
    </MemoryRouter>,
  );
}

describe('MainLayout responsive header (LV-01)', () => {
  it('marks Scanner, user name and Abmelden in the header as desktop-only', () => {
    renderLayout();
    const header = screen.getByRole('banner');
    const scanner = within(header).getByRole('link', { name: /Scanner/ });
    const logoutButton = within(header).getByRole('button', { name: 'Abmelden' });
    const name = within(header).getByText('Petra');

    for (const el of [scanner, logoutButton, name]) {
      expect(el).toHaveClass('header-desktop-only');
    }
  });

  it('keeps the bell and the hamburger visible in the header', () => {
    renderLayout();
    const header = screen.getByRole('banner');
    expect(
      within(header).getByRole('button', { name: 'Benachrichtigungen' }),
    ).not.toHaveClass('header-desktop-only');
    expect(
      within(header).getByRole('button', { name: 'Navigation öffnen' }),
    ).not.toHaveClass('header-desktop-only');
  });

  it('offers name, Scanner and Abmelden in the drawer account block', () => {
    renderLayout();
    const account = screen.getByTestId('sidebar-account');
    expect(within(account).getByText('Petra')).toBeInTheDocument();
    expect(within(account).getByRole('link', { name: /Scanner/ })).toHaveAttribute(
      'href',
      '/scanner',
    );
    fireEvent.click(within(account).getByRole('button', { name: 'Abmelden' }));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
