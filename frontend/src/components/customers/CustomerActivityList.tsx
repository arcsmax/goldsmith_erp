// CustomerActivityList — Kunde 360°, "Verlauf" tab (W2-12, DOM-38).
//
// One chronological list across orders, repairs, quotes, invoices and
// customer updates, from GET /customers/{id}/activity (server-side filtered
// by customer, paged, role-projected). Every row is one link to its detail:
// invoices open their order (no invoice detail page yet) and customer
// updates open the order or repair they belong to. Amounts only exist in the
// response for FINANCIAL_VIEW holders, so nothing is hidden here by role.
import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { customersApi, type CustomerActivityItem } from '../../api/customers';
import type { StatusKind } from '../../design/status';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { logError } from '../../lib/logError';
import { StatusBadge } from '../../ui/StatusBadge';

const PAGE_SIZE = 50;

type ActivityKind = CustomerActivityItem['kind'];

const KIND_LABELS: Readonly<Record<ActivityKind, string>> = {
  order: 'Auftrag',
  repair: 'Reparatur',
  quote: 'Kostenvoranschlag',
  invoice: 'Rechnung',
  customer_update: 'Kundeninfo',
};

const STATUS_KINDS: Readonly<Record<ActivityKind, StatusKind>> = {
  order: 'order',
  repair: 'repair',
  quote: 'quote',
  invoice: 'invoice',
  customer_update: 'customerUpdate',
};

/** Where a row leads. Invoices and updates open their parent. */
export function activityHref(item: CustomerActivityItem): string {
  switch (item.kind) {
    case 'order':
      return `/orders/${item.id}`;
    case 'repair':
      return `/repairs/${item.id}`;
    case 'quote':
      return `/quotes?quote_id=${item.id}`;
    case 'invoice':
      return item.order_id ? `/orders/${item.order_id}` : '/invoices';
    case 'customer_update':
      if (item.repair_job_id) return `/repairs/${item.repair_job_id}`;
      return item.order_id ? `/orders/${item.order_id}` : '/customers';
  }
}

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

const ActivityRow: React.FC<{ item: CustomerActivityItem }> = ({ item }) => (
  <li>
    <Link className="cactivity-row" to={activityHref(item)}>
      <span className="cactivity-row__kind">{KIND_LABELS[item.kind]}</span>
      <span className="cactivity-row__main">
        <span className="cactivity-row__title">{item.title}</span>
        {item.reference && <span className="cactivity-row__ref">{item.reference}</span>}
      </span>
      <time className="cactivity-row__date" dateTime={item.occurred_at}>
        {formatDay(item.occurred_at)}
      </time>
      <StatusBadge kind={STATUS_KINDS[item.kind]} status={item.status} />
      {item.amount != null && (
        <span className={`cactivity-row__amount ${MONEY_CLASS}`}>{formatEur(item.amount)}</span>
      )}
    </Link>
  </li>
);

interface CustomerActivityListProps {
  customerId: number;
}

export const CustomerActivityList: React.FC<CustomerActivityListProps> = ({ customerId }) => {
  const [items, setItems] = useState<CustomerActivityItem[]>([]);
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (offset: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const page = await customersApi.getActivity(customerId, { offset, limit: PAGE_SIZE });
        setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
        setTotal(page.total);
        setNextOffset(page.next_offset ?? null);
      } catch (err) {
        logError('CustomerActivityList.load', err);
        setError('Verlauf konnte nicht geladen werden.');
      } finally {
        setIsLoading(false);
      }
    },
    [customerId],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  if (error && items.length === 0) {
    return (
      <div className="cactivity-state" role="alert">
        <p>{error}</p>
        <button type="button" className="btn-secondary" onClick={() => load(0)}>
          Erneut versuchen
        </button>
      </div>
    );
  }

  if (isLoading && items.length === 0) {
    return (
      <p className="cactivity-state" role="status">
        Wird geladen…
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <div className="cactivity-state">
        <h3>Noch kein Verlauf</h3>
        <p>Aufträge, Reparaturen, Kostenvoranschläge und Rechnungen erscheinen hier.</p>
        <Link className="btn-primary" to={`/repairs?neu=1&customer_id=${customerId}`}>
          Neue Reparatur annehmen
        </Link>
      </div>
    );
  }

  return (
    <section className="cactivity" aria-labelledby="cactivity-heading">
      <div className="cdetail-panel__header">
        <h2 id="cactivity-heading">Verlauf</h2>
        <span className="cactivity-count">{total} Einträge</span>
      </div>
      <ol className="cactivity-list">
        {items.map((item) => (
          <ActivityRow key={`${item.kind}-${item.id}`} item={item} />
        ))}
      </ol>
      {error && (
        <p className="cactivity-error" role="alert">
          {error}
        </p>
      )}
      {nextOffset !== null && (
        <button
          type="button"
          className="btn-secondary cactivity-more"
          onClick={() => load(nextOffset)}
          disabled={isLoading}
        >
          {isLoading ? 'Wird geladen…' : 'Weitere laden'}
        </button>
      )}
    </section>
  );
};

export default CustomerActivityList;
