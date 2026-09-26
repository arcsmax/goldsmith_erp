// Übersicht tab of the order page (W2-08, DOM-17): status with its reason,
// the order facts and the customer card. W4-03: each block is a src/ui Card,
// the facts a description list, the deadline a DeadlineChip.
import type { ReactNode } from 'react';
import type { OrderType } from '../../types';
import { Card, DeadlineChip } from '../../ui';
import { canViewDesign, canViewFinancials } from '../../lib/roles';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { CustomerInfoCard } from './CustomerInfoCard';
import { GemstoneList } from './GemstoneList';
import { OrderStatusBadge } from './OrderStatusBadge';
import { LastScanLine } from '../scanner/LastScanLine';

/** Hold / cancel fields of OrderRead (W2-07) not yet in types.ts. */
export type OrderWithStatusFields = OrderType & {
  hold_reason?: string | null;
  resume_date?: string | null;
  cancel_reason?: string | null;
};

const DATE_TIME = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
const DATE_ONLY = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium' });

function formatDateTime(value: string): string {
  return DATE_TIME.format(new Date(value));
}

function formatDate(value: string): string {
  return DATE_ONLY.format(new Date(`${value}T00:00:00`));
}

interface OrderOverviewTabProps {
  order: OrderWithStatusFields;
  role?: string | null;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="order-fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function OrderOverviewTab({ order, role }: OrderOverviewTabProps) {
  const canDesign = canViewDesign(role);
  const canFinance = canViewFinancials(role);

  return (
    <div className="order-tab-body">
      <h2 className="ui-visually-hidden">Übersicht</h2>

      <Card title="Status" headingLevel={3}>
        <p className="order-overview-status">
          <OrderStatusBadge status={order.status} />
          {order.deadline && <DeadlineChip deadline={order.deadline} />}
        </p>
        <LastScanLine lastScan={order.last_scan} />
        {order.status === 'on_hold' && order.hold_reason && (
          <p className="order-overview-reason">Grund der Pause: {order.hold_reason}</p>
        )}
        {order.status === 'on_hold' && order.resume_date && (
          <p className="order-overview-reason">
            Weiter am <span className="tabular-nums">{formatDate(order.resume_date)}</span>
          </p>
        )}
        {order.status === 'cancelled' && order.cancel_reason && (
          <p className="order-overview-reason">Grund der Stornierung: {order.cancel_reason}</p>
        )}
      </Card>

      <Card title="Auftragsinformationen" headingLevel={3}>
        <dl className="order-facts">
          <Fact label="Auftragsnummer:">
            <span className="tabular-nums">#{order.id}</span>
          </Fact>
          <Fact label="Titel:">{order.title}</Fact>
          {/* DESIGN_VIEW (GDPR-04): `description` is stripped for a caller
              without it; omit the row rather than show an empty value. */}
          {canDesign && <Fact label="Beschreibung:">{order.description || '—'}</Fact>}
          {/* FINANCIAL_VIEW (SEC-01): `price` is stripped for a caller
              without it; omit the row rather than report "Nicht festgelegt". */}
          {canFinance && (
            <Fact label="Preis:">
              <span className={`tabular-nums ${MONEY_CLASS}`}>
                {order.price ? formatEur(order.price) : 'Nicht festgelegt'}
              </span>
            </Fact>
          )}
          {order.deadline && (
            <Fact label="Frist:">
              <span className="tabular-nums">{formatDateTime(order.deadline)}</span>
            </Fact>
          )}
          {order.current_location && <Fact label="Standort:">{order.current_location}</Fact>}
          <Fact label="Erstellt:">
            <span className="tabular-nums">{formatDateTime(order.created_at)}</span>
          </Fact>
          <Fact label="Aktualisiert:">
            <span className="tabular-nums">{formatDateTime(order.updated_at)}</span>
          </Fact>
        </dl>
      </Card>

      {/* W2-06 (DOM-04): stones; editing lives in the order form. */}
      <GemstoneList orderId={order.id} />

      <Card title="Kunde" headingLevel={3}>
        <CustomerInfoCard customerId={order.customer_id} />
      </Card>
    </div>
  );
}

export default OrderOverviewTab;
