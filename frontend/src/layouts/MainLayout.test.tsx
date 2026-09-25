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
const auth = { role: 'ADMIN' };

vi.mock('../contexts', () => ({
  useAuth: () => ({
    user: { first_name: 'Petra', email: 'petra@example.test', role: auth.role },
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
import { navGroupsFor, tabBarItems } from './navigation';

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

describe('MainLayout grouped navigation (W4-03)', () => {
  it('shows the playbook groups for ADMIN', () => {
    auth.role = 'ADMIN';
    renderLayout();
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    for (const heading of ['Aufträge', 'Werkstatt', 'Kunden', 'Angebote & Rechnungen', 'Material', 'Verwaltung']) {
      expect(within(nav).getByRole('heading', { name: heading })).toBeInTheDocument();
    }
    expect(within(nav).getByRole('link', { name: 'Heute' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'System' })).toHaveAttribute('href', '/admin/system');
  });

  it('hides financial, customer and admin entries from VIEWER', () => {
    auth.role = 'VIEWER';
    renderLayout();
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    for (const name of ['Kunden', 'Rechnungen', 'Angebote', 'Materialien', 'Benutzer', 'System']) {
      expect(within(nav).queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(within(nav).getByRole('link', { name: 'Aufträge' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Einstellungen' })).toBeInTheDocument();
    auth.role = 'ADMIN';
  });

  it('renders the tab bar with five entries and scan in the centre', () => {
    renderLayout();
    const bar = screen.getByRole('navigation', { name: 'Schnellzugriff' });
    const links = within(bar).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['Heute', 'Aufträge', 'Scan', 'Zeit', 'Kunden']);
    expect(links[2]).toHaveAttribute('href', '/scanner');
  });

  it('closes the drawer on Escape and returns focus to the menu button', () => {
    renderLayout();
    const menu = screen.getByRole('button', { name: 'Navigation öffnen' });
    fireEvent.click(menu);
    expect(menu).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveFocus();
  });
});

describe('navigation config', () => {
  it('drops empty groups and swaps the fifth tab for roles without customers', () => {
    expect(navGroupsFor('VIEWER').map((group) => group.id)).not.toContain('buero');
    expect(tabBarItems('viewer')[4].to).toBe('/calendar');
    expect(tabBarItems('goldsmith')[4].to).toBe('/customers');
  });
});
