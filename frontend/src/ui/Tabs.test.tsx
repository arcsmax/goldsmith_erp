import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { TabBar, Tabs, useTabParam, type TabItem } from './Tabs';

const TABS: TabItem[] = [
  { id: 'overview', label: 'Übersicht', panel: <p>Übersicht-Inhalt</p> },
  { id: 'photos', label: 'Fotos', panel: <p>Fotos-Inhalt</p> },
  { id: 'time', label: 'Zeit', panel: <p>Zeit-Inhalt</p> },
];

function Controlled() {
  const [selected, setSelected] = useState('overview');
  return <Tabs label="Auftragsbereiche" tabs={TABS} selectedId={selected} onSelect={setSelected} />;
}

describe('Tabs', () => {
  it('renders the WAI-ARIA tabs pattern', () => {
    render(<Controlled />);
    const tablist = screen.getByRole('tablist', { name: 'Auftragsbereiche' });
    expect(tablist).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('tabindex', '0');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
    expect(tabs[1]).toHaveAttribute('tabindex', '-1');
    const panel = screen.getByRole('tabpanel', { name: 'Übersicht' });
    expect(panel).toHaveTextContent('Übersicht-Inhalt');
    expect(tabs[0]).toHaveAttribute('aria-controls', panel.id);
  });

  it('moves with arrow keys, Home and End, wrapping around', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const tabs = screen.getAllByRole('tab');
    tabs[0].focus();
    await user.keyboard('{ArrowRight}');
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Fotos-Inhalt');
    await user.keyboard('{ArrowRight}{ArrowRight}');
    expect(tabs[0]).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(tabs[2]).toHaveFocus();
    await user.keyboard('{Home}');
    expect(tabs[0]).toHaveFocus();
    await user.keyboard('{End}');
    expect(tabs[2]).toHaveFocus();
  });

  it('selects on click', async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    await user.click(screen.getByRole('tab', { name: 'Zeit' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Zeit-Inhalt');
  });
});

function UrlTabs() {
  const [tab, setTab] = useTabParam(['overview', 'photos', 'time'], 'overview');
  const location = useLocation();
  return (
    <>
      <Tabs label="Bereiche" tabs={TABS} selectedId={tab} onSelect={setTab} />
      <output data-testid="search">{location.search}</output>
    </>
  );
}

describe('useTabParam', () => {
  it('reads ?tab= and falls back to the default for unknown ids', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/orders/1?tab=photos']}>
        <UrlTabs />
      </MemoryRouter>,
    );
    expect(screen.getByRole('tab', { name: 'Fotos' })).toHaveAttribute('aria-selected', 'true');
    unmount();
    render(
      <MemoryRouter initialEntries={['/orders/1?tab=bogus']}>
        <UrlTabs />
      </MemoryRouter>,
    );
    expect(screen.getByRole('tab', { name: 'Übersicht' })).toHaveAttribute('aria-selected', 'true');
  });

  it('writes the selected tab to the URL, keeping other params', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/orders/1?filter=open']}>
        <UrlTabs />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('tab', { name: 'Zeit' }));
    expect(screen.getByTestId('search')).toHaveTextContent('filter=open');
    expect(screen.getByTestId('search')).toHaveTextContent('tab=time');
  });
});

describe('TabBar', () => {
  it('is a labelled nav with aria-current on the active item', () => {
    render(
      <MemoryRouter initialEntries={['/orders']}>
        <TabBar
          label="Hauptnavigation"
          items={[
            { to: '/dashboard', label: 'Heute', icon: 'home' },
            { to: '/orders', label: 'Aufträge', icon: 'clipboard' },
            { to: '/scanner', label: 'Scan', icon: 'scan', prominent: true },
          ]}
        />
      </MemoryRouter>,
    );
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Aufträge' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Heute' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Scan' })).toHaveClass('ui-tab-bar__item--prominent');
  });
});
