// LV-01: at 390px the header user menu (Scanner, name, "Abmelden") pushed
// the page 58px wider than the viewport. jsdom has no layout, so this test
// pins the responsive structure instead: those items carry
// .header-desktop-only (hidden below 600px in layout.css) and the drawer
// holds an account block with the same actions. The screenshot loop at 390
// checks the pixels.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
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
// Stubs stand in for the real FABs (TimerWidget pulls in the timer API/
// context machinery; ScanFab pulls in the scanner context). The stubs still
// carry recognizable markers so tests below can assert both are mounted
// inside the same `.has-timer-fab` ancestor MainLayout renders (the class
// ScanFab.css's `.has-timer-fab .scan-fab` rule relies on to float ScanFab
// above the always-mounted TimerWidget FAB — see ScanFab.css).
vi.mock('../components/TimerWidget', () => ({
  default: () => <button type="button" data-testid="timer-fab-stub" className="timer-fab" />,
}));
vi.mock('../components/scanner', () => ({
  ScanFab: () => <button type="button" data-testid="scan-fab-stub" className="scan-fab" />,
  ScanOverlay: () => null,
}));
vi.mock('../components/HidBurstNudge', () => ({ HidBurstNudge: () => null }));
vi.mock('../components/NotificationBell', () => ({
  NotificationBell: () => <button type="button">Benachrichtigungen</button>,
}));
vi.mock('../components/HealthDot', () => ({ HealthDot: () => null }));
vi.mock('../components/GlobalSearch', () => ({ GlobalSearch: () => null }));

import { MainLayout } from './MainLayout';
import { navGroupsFor, tabBarItems, benchTabBarItems } from './navigation';
import { setBenchMode } from '../lib/benchMode';

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
    expect(within(nav).getByRole('link', { name: 'Werkstatt-Board' })).toHaveAttribute('href', '/werkstatt');
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

describe('MainLayout FAB stack (mobile overlap fix)', () => {
  // The scan FAB used to overlap the timer FAB on phones because ScanFab's
  // "stacked above timer" offset only applied while a timer was running —
  // but TimerWidget always occupies that slot (idle "Start" button included).
  // The fix: MainLayout's root carries `has-timer-fab` unconditionally
  // (TimerWidget is unconditionally mounted below), and ScanFab.css floats
  // `.scan-fab` above it via the `.has-timer-fab .scan-fab` descendant rule.
  it('marks the root has-timer-fab, with both FABs mounted inside it', () => {
    const { container } = renderLayout();
    const root = container.querySelector('.main-layout');
    expect(root).toHaveClass('has-timer-fab');
    expect(root).toContainElement(screen.getByTestId('timer-fab-stub'));
    expect(root).toContainElement(screen.getByTestId('scan-fab-stub'));
  });

  it('keeps has-timer-fab in bench mode too', () => {
    act(() => setBenchMode(true));
    const { container } = renderLayout();
    const root = container.querySelector('.main-layout');
    expect(root).toHaveClass('has-timer-fab');
    expect(root).toHaveClass('main-layout--bench');
    act(() => setBenchMode(false));
  });
});

describe('navigation config', () => {
  it('drops empty groups and swaps the fifth tab for roles without customers', () => {
    expect(navGroupsFor('VIEWER').map((group) => group.id)).not.toContain('buero');
    expect(tabBarItems('viewer')[4].to).toBe('/calendar');
    expect(tabBarItems('goldsmith')[4].to).toBe('/customers');
  });

  it('benchTabBarItems has exactly Scanner, Zeiterfassung, Aufträge, Heute', () => {
    expect(benchTabBarItems().map((item) => item.to)).toEqual([
      '/scanner',
      '/time-tracking',
      '/orders',
      '/dashboard',
    ]);
  });
});

describe('MainLayout Werkbank-Modus (5.5, W7 followup)', () => {
  afterEach(() => {
    act(() => setBenchMode(false));
  });

  it('hides the secondary navigation and footer, keeps the header', () => {
    act(() => setBenchMode(true));
    renderLayout();
    expect(screen.queryByRole('navigation', { name: 'Hauptnavigation' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('sidebar-account')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Navigation öffnen' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Alle Rechte vorbehalten/)).not.toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('shows only the four bench tab bar entries, in order', () => {
    act(() => setBenchMode(true));
    renderLayout();
    const bar = screen.getByRole('navigation', { name: 'Schnellzugriff' });
    const links = within(bar).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['Scan', 'Zeit', 'Aufträge', 'Heute']);
    expect(links[0]).toHaveAttribute('href', '/scanner');
  });

  it('offers a header toggle that switches bench mode on and off', () => {
    renderLayout();
    const toggle = screen.getByRole('button', { name: 'Werkbank-Modus einschalten' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(toggle);
    expect(
      screen.getByRole('button', { name: 'Werkbank-Modus ausschalten' }),
    ).toHaveAttribute('aria-pressed', 'true');
    // The drawer is gone now, but the toggle itself stays reachable.
    expect(screen.queryByRole('button', { name: 'Navigation öffnen' })).not.toBeInTheDocument();
  });

  it('keeps the five-entry tab bar and full navigation when bench mode is off', () => {
    renderLayout();
    expect(screen.getByRole('navigation', { name: 'Hauptnavigation' })).toBeInTheDocument();
    const bar = screen.getByRole('navigation', { name: 'Schnellzugriff' });
    expect(within(bar).getAllByRole('link')).toHaveLength(5);
  });
});
