// The order page's five tabs (W2-08, DOM-17).
//
// Before: up to 14 tabs (Details, Kosten, Metall, Materialien, Status,
// Historie, Zeiterfassung, Notizen, Altgold, Fotos, Übergabe, Kundeninfo,
// Arbeitszettel, Soll/Ist). After: Übersicht, Arbeit, Fotos, Kunde, Verlauf.
//
// The remembered tab lives in OrderContext as an `OrderTab` value (the
// context and the scanner / dashboard deep links still speak the old
// names), so each page tab is stored as one canonical OrderTab and every
// old value maps onto the tab that now holds its content, plus the
// section to scroll to inside it.
import type { OrderTab } from '../../contexts/OrderContext';

export type OrderPageTab = 'uebersicht' | 'arbeit' | 'fotos' | 'kunde' | 'verlauf';

export type WorkSection =
  | 'zeit'
  | 'material'
  | 'metall'
  | 'arbeitszettel'
  | 'kosten'
  | 'soll-ist'
  | 'altgold'
  | 'uebergabe';

export const PAGE_TAB_LABELS: Readonly<Record<OrderPageTab, string>> = {
  uebersicht: 'Übersicht',
  arbeit: 'Arbeit',
  fotos: 'Fotos',
  kunde: 'Kunde',
  verlauf: 'Verlauf',
};

export const PAGE_TAB_ORDER: readonly OrderPageTab[] = [
  'uebersicht',
  'arbeit',
  'fotos',
  'kunde',
  'verlauf',
];

/** The OrderTab value each page tab is remembered as. */
export const PAGE_TAB_STORAGE: Readonly<Record<OrderPageTab, OrderTab>> = {
  uebersicht: 'details',
  arbeit: 'time-tracking',
  fotos: 'fotos',
  kunde: 'kundeninfo',
  verlauf: 'history',
};

interface TabTarget {
  tab: OrderPageTab;
  section: WorkSection | null;
}

const LEGACY_TARGETS: Readonly<Record<OrderTab, TabTarget>> = {
  details: { tab: 'uebersicht', section: null },
  status: { tab: 'uebersicht', section: null },
  'time-tracking': { tab: 'arbeit', section: null },
  materials: { tab: 'arbeit', section: 'material' },
  metall: { tab: 'arbeit', section: 'metall' },
  arbeitszettel: { tab: 'arbeit', section: 'arbeitszettel' },
  kosten: { tab: 'arbeit', section: 'kosten' },
  'soll-ist': { tab: 'arbeit', section: 'soll-ist' },
  'scrap-gold': { tab: 'arbeit', section: 'altgold' },
  handoff: { tab: 'arbeit', section: 'uebergabe' },
  fotos: { tab: 'fotos', section: null },
  kundeninfo: { tab: 'kunde', section: null },
  comments: { tab: 'kunde', section: null },
  history: { tab: 'verlauf', section: null },
};

export function resolveOrderTab(stored: OrderTab): TabTarget {
  return LEGACY_TARGETS[stored] ?? { tab: 'uebersicht', section: null };
}

export function workSectionId(section: WorkSection): string {
  return `order-work-${section}`;
}
