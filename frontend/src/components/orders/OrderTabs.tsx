// In-page tab bar of the order page (W2-08, DOM-17; playbook 4.11):
// WAI-ARIA tabs with automatic activation, arrow / Home / End keys, and
// one shared tabpanel that the page fills.
import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { PAGE_TAB_LABELS, type OrderPageTab } from './orderPageTabs';

export const ORDER_TABPANEL_ID = 'order-tabpanel';

export function orderTabId(tab: OrderPageTab): string {
  return `order-tab-${tab}`;
}

interface OrderTabsProps {
  tabs: readonly OrderPageTab[];
  active: OrderPageTab;
  onChange: (tab: OrderPageTab) => void;
  /** Optional per-tab label override, e.g. "Fotos (3)". */
  labels?: Partial<Record<OrderPageTab, string>>;
}

export function OrderTabs({ tabs, active, onChange, labels = {} }: OrderTabsProps) {
  const listRef = useRef<HTMLDivElement>(null);

  const focusTab = (tab: OrderPageTab) => {
    onChange(tab);
    listRef.current?.querySelector<HTMLButtonElement>(`#${orderTabId(tab)}`)?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.indexOf(active);
    const targets: Record<string, number> = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in targets)) return;
    event.preventDefault();
    focusTab(tabs[targets[event.key]]);
  };

  return (
    <div
      ref={listRef}
      className="order-tabs"
      role="tablist"
      aria-label="Auftragsbereiche"
      onKeyDown={handleKeyDown}
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <button
            key={tab}
            id={orderTabId(tab)}
            type="button"
            role="tab"
            className={`tab ${isActive ? 'active' : ''}`}
            aria-selected={isActive}
            aria-controls={ORDER_TABPANEL_ID}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab)}
          >
            {labels[tab] ?? PAGE_TAB_LABELS[tab]}
          </button>
        );
      })}
    </div>
  );
}

interface OrderTabPanelProps {
  active: OrderPageTab;
  children: ReactNode;
}

export function OrderTabPanel({ active, children }: OrderTabPanelProps) {
  return (
    <div
      id={ORDER_TABPANEL_ID}
      className="tab-content"
      role="tabpanel"
      aria-labelledby={orderTabId(active)}
      tabIndex={0}
    >
      {children}
    </div>
  );
}
