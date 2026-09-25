// Tab state of the order page (W4-03): `?tab=` is the source of truth
// (useTabParam), the OrderContext keeps remembering the last tab per order
// (dashboard lanes set it before they navigate here), and the scanner /
// dashboard deep links (W2-01, FE-04: legacy `?tab=kosten`, `capture=1`,
// `action=take-photo`, `edit=status`) are translated once into the page
// tab, the section to scroll to, the camera and the status menu.
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useOrders } from '../../contexts';
import { useTabParam } from '../../ui';
import { parseOrderDeepLink, stripOrderDeepLink } from './orderDeepLink';
import {
  PAGE_TAB_ORDER,
  PAGE_TAB_STORAGE,
  resolveOrderTab,
  type OrderPageTab,
  type WorkSection,
} from './orderPageTabs';

const DEFAULT_TAB: OrderPageTab = 'uebersicht';

interface OrderPageTabOptions {
  orderId: number;
  /** DESIGN_VIEW: without it the Fotos tab does not exist. */
  canDesign: boolean;
  canChangeStatus: boolean;
  /** Deep links wait for the order, so the camera opens on a real page. */
  isOrderLoaded: boolean;
}

export interface OrderPageTabState {
  tabs: readonly OrderPageTab[];
  activeTab: OrderPageTab;
  selectTab: (tab: OrderPageTab) => void;
  focusSection: WorkSection | null;
  clearFocusSection: () => void;
  /** Open Arbeit and scroll to one of its sections ("Kosten"). */
  openWorkSection: (section: WorkSection) => void;
  autoCapture: boolean;
  clearAutoCapture: () => void;
  isStatusMenuOpen: boolean;
  setStatusMenuOpen: (isOpen: boolean) => void;
}

export function useOrderPageTab({
  orderId,
  canDesign,
  canChangeStatus,
  isOrderLoaded,
}: OrderPageTabOptions): OrderPageTabState {
  const { getOrderTab, setOrderTab } = useOrders();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabs = PAGE_TAB_ORDER.filter((tab) => tab !== 'fotos' || canDesign);
  const remembered = resolveOrderTab(getOrderTab(orderId)).tab;
  const fallback = tabs.includes(remembered) ? remembered : DEFAULT_TAB;
  const [tabParam, setTabParam] = useTabParam(tabs, fallback);
  const [focusSection, setFocusSection] = useState<WorkSection | null>(null);
  const [autoCapture, setAutoCapture] = useState(false);
  const [isStatusMenuOpen, setStatusMenuOpen] = useState(false);

  const selectTab = useCallback(
    (tab: OrderPageTab) => {
      setOrderTab(orderId, PAGE_TAB_STORAGE[tab]);
      setTabParam(tab);
    },
    // setOrderTab is recreated by the context on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orderId, setTabParam]
  );

  // Deep links: honoured once the order is loaded, then rewritten to the
  // plain `?tab=<page tab>` so a reload does not reopen the camera.
  useEffect(() => {
    if (!isOrderLoaded) return;
    const link = parseOrderDeepLink(searchParams);
    if (link === null) return;
    const raw = searchParams.get('tab');
    const isPageTab = raw !== null && (tabs as readonly string[]).includes(raw);
    const target = link.tab ? resolveOrderTab(link.tab) : null;
    const isAllowed = target !== null && (target.tab !== 'fotos' || canDesign);

    const next = stripOrderDeepLink(searchParams);
    if (isAllowed && target.tab !== DEFAULT_TAB) next.set('tab', target.tab);
    else if (!isAllowed && isPageTab && raw) next.set('tab', raw);
    // Already the plain page-tab URL (also ends the loop after our rewrite).
    if (next.toString() === searchParams.toString()) return;

    if (isAllowed) {
      setOrderTab(orderId, PAGE_TAB_STORAGE[target.tab]);
      setFocusSection(target.section);
    }
    if (link.tab === 'status' && canChangeStatus) setStatusMenuOpen(true);
    if (link.capture && canDesign) setAutoCapture(true);
    setSearchParams(next, { replace: true });
    // setOrderTab is recreated by the context on every render; the effect
    // reacts to a loaded order and new params only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOrderLoaded, searchParams, canDesign, canChangeStatus, orderId]);

  return {
    tabs,
    activeTab: tabParam,
    selectTab,
    focusSection,
    clearFocusSection: useCallback(() => setFocusSection(null), []),
    openWorkSection: (section: WorkSection) => {
      selectTab('arbeit');
      setFocusSection(section);
    },
    autoCapture,
    clearAutoCapture: useCallback(() => setAutoCapture(false), []),
    isStatusMenuOpen,
    setStatusMenuOpen,
  };
}
