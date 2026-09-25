// OrderTimeline — the Verlauf tab (W2-08, DOM-16).
//
// Renders GET /orders/{id}/timeline (status events, Kundeninfos, photos,
// time entries; already role-projected by the backend) as one vertical
// list, newest first. Each entry names its kind in text next to the icon,
// so nothing is conveyed by icon or colour alone.
import { useCallback, useEffect, useState } from 'react';
import { ordersApi } from '../../api';
import type { OrderTimelineItem, OrderTimelineKind } from '../../api/orders';
import { logError } from '../../lib/logError';
import { OrderIcon, type OrderIconName } from './OrderIcon';

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

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; items: OrderTimelineItem[] };

interface OrderTimelineProps {
  orderId: number;
  /** Bump to reload (status change, realtime hint). */
  refreshKey?: number;
  /** Injected in tests; defaults to the current time. */
  now?: Date;
}

export function OrderTimeline({ orderId, refreshKey = 0, now }: OrderTimelineProps) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let isCancelled = false;
    // Keep what is on screen during a background reload.
    setState((prev) => (prev.status === 'ready' ? prev : { status: 'loading' }));
    ordersApi
      .getTimeline(orderId)
      .then((timeline) => {
        if (!isCancelled) setState({ status: 'ready', items: sortNewestFirst(timeline.items) });
      })
      .catch((err: unknown) => {
        logError(`OrderTimeline.load order=${orderId}`, err);
        if (!isCancelled) setState({ status: 'error' });
      });
    return () => {
      isCancelled = true;
    };
  }, [orderId, refreshKey, attempt]);

  if (state.status === 'loading') {
    return (
      <p className="order-timeline-state" role="status">
        Wird geladen…
      </p>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="order-timeline-state">
        <p>Verlauf konnte nicht geladen werden.</p>
        <button type="button" className="btn-secondary" onClick={retry}>
          Erneut versuchen
        </button>
      </div>
    );
  }

  if (state.items.length === 0) {
    return (
      <div className="order-timeline-state">
        <p className="order-timeline-empty-title">Noch kein Verlauf</p>
        <p>Statuswechsel, Fotos, Kundeninfos und Zeiten erscheinen hier automatisch.</p>
      </div>
    );
  }

  const reference = now ?? new Date();
  return (
    <ol className="order-timeline" aria-label="Auftragsverlauf">
      {state.items.map((item) => {
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
  );
}

export default OrderTimeline;
