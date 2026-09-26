// Order detail deep links (W2-01, FE-04 deep-link part).
//
// The scanner quick actions navigate to the order page with query params.
// This module turns those params into "open this tab" / "open the camera"
// so OrderDetailPage can honour them once and then drop them from the URL
// (a reload must not reopen the camera).
//
//   ?tab=<OrderTab>          open that tab
//   ?tab=fotos&capture=1     open Fotos and the camera (scanner "Foto")
//   ?action=take-photo       legacy form of the above
//   ?edit=status             open the Status tab
import type { OrderTab } from '../../contexts/OrderContext';

export const ORDER_TABS: readonly OrderTab[] = [
  'details',
  'kosten',
  'metall',
  'materials',
  'status',
  'history',
  'time-tracking',
  'comments',
  'scrap-gold',
  'soll-ist',
  'handoff',
  'arbeitszettel',
  'fotos',
  'kundeninfo',
];

/** Query keys this module consumes; everything else is left untouched. */
export const ORDER_DEEP_LINK_KEYS = ['tab', 'capture', 'action', 'edit'] as const;

export interface OrderDeepLink {
  tab: OrderTab | null;
  capture: boolean;
}

function isOrderTab(value: string | null): value is OrderTab {
  return value !== null && (ORDER_TABS as readonly string[]).includes(value);
}

/** Build the scanner "Foto" target for an order. */
export function orderPhotoCaptureLink(orderId: number): string {
  return `/orders/${orderId}?tab=fotos&capture=1`;
}

/** Parse the deep-link params; null when none of them are present. */
export function parseOrderDeepLink(params: URLSearchParams): OrderDeepLink | null {
  const hasAny = ORDER_DEEP_LINK_KEYS.some((key) => params.has(key));
  if (!hasAny) return null;

  const tabParam = params.get('tab');
  const action = params.get('action');
  const edit = params.get('edit');
  const isTakePhoto = action === 'take-photo';

  let tab: OrderTab | null = isOrderTab(tabParam) ? tabParam : null;
  if (tab === null && isTakePhoto) tab = 'fotos';
  if (tab === null && edit === 'status') tab = 'status';

  const capture = tab === 'fotos' && (params.get('capture') === '1' || isTakePhoto);
  return { tab, capture };
}

/** Copy of `params` without the deep-link keys. */
export function stripOrderDeepLink(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  ORDER_DEEP_LINK_KEYS.forEach((key) => next.delete(key));
  return next;
}
