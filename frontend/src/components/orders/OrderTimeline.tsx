// OrderTimeline — the Verlauf tab (W2-08, DOM-16).
//
// Renders GET /orders/{id}/timeline (status events, Kundeninfos, photos,
// time entries; already role-projected by the backend) as one vertical
// list, newest first. Each entry names its kind in text next to the icon,
// so nothing is conveyed by icon or colour alone.
//
// Data: useQuery(orderTimelineQuery) (W4-03). The key sits under the
// order's detail key, so a status change, an upload or an order_updates
// realtime hint refreshes it; no refresh prop.
import { useQuery } from '@tanstack/react-query';
import type { OrderTimelineItem, OrderTimelineKind } from '../../api/orders';
import { PageState, type PageStateValue } from '../../ui';
import { OrderIcon, type OrderIconName } from './OrderIcon';
import { orderTimelineQuery } from './orderQueries';

const KIND_META: Readonly<Record<OrderTimelineKind, { label: string; icon: OrderIconName }>> = {
  status: { label: 'Status', icon: 'arrow-right' },
  photo: { label: 'Foto', icon: 'camera' },
  customer_update: { label: 'Kundeninfo', icon: 'mail' },
  time_entry: { label: 'Zeit', icon: 'clock' },
};

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;
const JUST_NOW_SECONDS = 45;

const RELATIVE = new Intl.RelativeTimeFormat('de', { numeric: 'auto' });
const ABSOLUTE = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });

/** Backend timestamps are naive UTC (datetime.utcnow); treat them as UTC. */
export function parseBackendDate(value: string): Date {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

/** "gerade eben", "vor 5 Minuten", "gestern", "vor 2 Wochen" … */
export function formatRelativeGerman(date: Date, now: Date = new Date()): string {
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < JUST_NOW_SECONDS) return 'gerade eben';
  if (abs < HOUR) return RELATIVE.format(Math.round(seconds / MINUTE), 'minute');
  if (abs < DAY) return RELATIVE.format(Math.round(seconds / HOUR), 'hour');
  if (abs < WEEK) return RELATIVE.format(Math.round(seconds / DAY), 'day');
  if (abs < MONTH) return RELATIVE.format(Math.round(seconds / WEEK), 'week');
  if (abs < YEAR) return RELATIVE.format(Math.round(seconds / MONTH), 'month');
  return RELATIVE.format(Math.round(seconds / YEAR), 'year');
}

function sortNewestFirst(items: readonly OrderTimelineItem[]): OrderTimelineItem[] {
  return [...items].sort(
    (a, b) => parseBackendDate(b.at).getTime() - parseBackendDate(a.at).getTime()
  );
}

function detailLine(item: OrderTimelineItem): string | null {
  if (item.kind === 'status' && typeof item.data.reason === 'string' && item.data.reason) {
    return `Grund: ${item.data.reason}`;
  }
  if (item.kind === 'time_entry') {
    if (item.data.is_running === true) return 'läuft gerade';
    if (typeof item.data.duration_minutes === 'number') {
      return `${Math.round(item.data.duration_minutes)} Min.`;
    }
  }
  return null;
}

interface OrderTimelineProps {
  orderId: number;
  /** Injected in tests; defaults to the current time. */
  now?: Date;
}

function useTimeline(orderId: number) {
  return useQuery({
    ...orderTimelineQuery(orderId),
    select: (timeline) => sortNewestFirst(timeline.items),
  });
}

export function OrderTimeline({ orderId, now }: OrderTimelineProps) {
  const query = useTimeline(orderId);
  const items = query.data ?? [];
  const state: PageStateValue = query.isPending
    ? { status: 'loading' }
    : query.isError && !query.data
      ? {
          status: 'error',
          error: 'Verlauf konnte nicht geladen werden.',
          retry: () => void query.refetch(),
        }
      : items.length === 0
        ? { status: 'empty' }
        : { status: 'ready' };

  const reference = now ?? new Date();
  return (
    <PageState
      state={state}
      skeleton="list"
      skeletonCount={4}
      empty={{
        icon: 'clock',
        title: 'Noch kein Verlauf',
        body: 'Statuswechsel, Fotos, Kundeninfos und Zeiten erscheinen hier automatisch.',
        headingLevel: 3,
      }}
    >
      <ol className="order-timeline" aria-label="Auftragsverlauf">
        {items.map((item) => {
          const meta = KIND_META[item.kind] ?? { label: item.kind, icon: 'arrow-right' };
          const at = parseBackendDate(item.at);
          const detail = detailLine(item);
          return (
            <li key={item.id} className={`order-timeline-item kind-${item.kind}`} data-kind={item.kind}>
              <span className="order-timeline-marker">
                <OrderIcon name={meta.icon} />
              </span>
              <div className="order-timeline-body">
                <p className="order-timeline-head">
                  <span className="order-timeline-kind">{meta.label}</span>
                  <time dateTime={at.toISOString()} title={ABSOLUTE.format(at)}>
                    {formatRelativeGerman(at, reference)}
                  </time>
                </p>
                <p className="order-timeline-summary">{item.summary}</p>
                {detail && <p className="order-timeline-detail">{detail}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </PageState>
  );
}

export default OrderTimeline;
