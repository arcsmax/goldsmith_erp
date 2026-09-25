// Tabs, useTabParam and TabBar (UI-UX-PLAYBOOK 4.11; review 04 F item 5).
//
// Tabs: in-page WAI-ARIA tabs (role tablist/tab/tabpanel, roving tabindex,
// ArrowLeft/ArrowRight wrap, Home/End, automatic activation), 44px tall,
// horizontally scrollable on phones.
// useTabParam: keeps the selected tab in `?tab=` so reload and links work.
// TabBar: the app tab bar below 1024px, a labelled <nav> of links with
// aria-current="page" on the active item; `prominent` is the 56px scan slot.
import React, { useCallback, useId, useRef } from 'react';
import { NavLink, useSearchParams } from 'react-router-dom';

import { cx } from './devAssert';
import { Icon, type IconName } from './Icon';

export interface TabItem {
  id: string;
  label: string;
  panel?: React.ReactNode;
}

export interface TabsProps {
  /** Accessible name of the tablist ("Auftragsbereiche"). */
  label: string;
  tabs: TabItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Render panels from `tabs[].panel` (default true). Set false to render your own. */
  renderPanels?: boolean;
  className?: string;
}

export function tabDomIds(baseId: string, tabId: string): { tab: string; panel: string } {
  return { tab: `${baseId}-tab-${tabId}`, panel: `${baseId}-panel-${tabId}` };
}

export const Tabs: React.FC<TabsProps> = ({
  label,
  tabs,
  selectedId,
  onSelect,
  renderPanels = true,
  className,
}) => {
  const baseId = useId();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(
    0,
    tabs.findIndex((tab) => tab.id === selectedId),
  );
  const selected = tabs[selectedIndex];

  const moveTo = (index: number): void => {
    const count = tabs.length;
    const next = ((index % count) + count) % count;
    onSelect(tabs[next].id);
    tabRefs.current[next]?.focus();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number): void => {
    const keyMoves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in keyMoves)) return;
    event.preventDefault();
    moveTo(keyMoves[event.key]);
  };

  return (
    <div className={cx('ui-tabs', className)}>
      <div role="tablist" aria-label={label} className="ui-tabs__list">
        {tabs.map((tab, index) => {
          const ids = tabDomIds(baseId, tab.id);
          const isSelected = index === selectedIndex;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              type="button"
              role="tab"
              id={ids.tab}
              aria-selected={isSelected}
              aria-controls={ids.panel}
              tabIndex={isSelected ? 0 : -1}
              className={cx('ui-tabs__tab', isSelected && 'ui-tabs__tab--selected')}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {renderPanels && selected && (
        <div
          role="tabpanel"
          id={tabDomIds(baseId, selected.id).panel}
          aria-labelledby={tabDomIds(baseId, selected.id).tab}
          tabIndex={0}
          className="ui-tabs__panel"
        >
          {selected.panel}
        </div>
      )}
    </div>
  );
};

/**
 * Sync the selected tab with `?tab=`. Unknown or missing values fall back to
 * `defaultId`; other query params are kept; the default tab is written as a
 * clean URL (no `?tab=`). Uses `replace` so tab switches do not flood history.
 */
export function useTabParam<T extends string>(
  ids: readonly T[],
  defaultId: T,
  param = 'tab',
): [T, (id: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get(param);
  const current = raw !== null && (ids as readonly string[]).includes(raw) ? (raw as T) : defaultId;

  const setTab = useCallback(
    (id: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === defaultId) next.delete(param);
          else next.set(param, id);
          return next;
        },
        { replace: true },
      );
    },
    [defaultId, param, setSearchParams],
  );

  return [current, setTab];
}

export interface TabBarItem {
  to: string;
  label: string;
  icon: IconName;
  /** The centre scan slot, 56px. */
  prominent?: boolean;
}

export interface TabBarProps {
  label: string;
  items: TabBarItem[];
  className?: string;
}

export const TabBar: React.FC<TabBarProps> = ({ label, items, className }) => (
  <nav aria-label={label} className={cx('ui-tab-bar', className)}>
    <ul className="ui-tab-bar__list">
      {items.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            className={({ isActive }) =>
              cx(
                'ui-tab-bar__item',
                isActive && 'ui-tab-bar__item--active',
                item.prominent && 'ui-tab-bar__item--prominent',
              )
            }
          >
            <Icon name={item.icon} />
            <span className="ui-tab-bar__label">{item.label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  </nav>
);
