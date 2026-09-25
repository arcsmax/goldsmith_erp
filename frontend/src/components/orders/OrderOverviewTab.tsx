// Übersicht tab of the order page (W2-08, DOM-17): status with its reason,
// the order facts and the customer card.
import type { OrderType } from '../../types';
import { canViewDesign, canViewFinancials } from '../../lib/roles';
import { CustomerInfoCard } from './CustomerInfoCard';
import { OrderStatusBadge } from './OrderStatusBadge';

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

export function OrderOverviewTab({ order, role }: OrderOverviewTabProps) {
  const canDesign = canViewDesign(role);
  const canFinance = canViewFinancials(role);

  return (
    <div className="tab-panel">
      <h2>Übersicht</h2>

      <section className="details-section" aria-labelledby="order-overview-status">
        <h3 id="order-overview-status">Status</h3>
        <p className="order-overview-status">
          <OrderStatusBadge status={order.status} />
        </p>
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
      </section>

      <section className="details-section" aria-labelledby="order-overview-facts">
        <h3 id="order-overview-facts">Auftragsinformationen</h3>
        <div className="detail-grid">
          <div className="detail-item">
            <label>Auftragsnummer:</label>
            <span className="tabular-nums">#{order.id}</span>
          </div>
          <div className="detail-item">
            <label>Titel:</label>
            <span>{order.title}</span>
          </div>
          {/* DESIGN_VIEW (GDPR-04): `description` is stripped for a caller
              without it; omit the row rather than show an empty value. */}
          {canDesign && (
            <div className="detail-item">
              <label>Beschreibung:</label>
              <span>{order.description || '—'}</span>
            </div>
          )}
          {/* FINANCIAL_VIEW (SEC-01): `price` is stripped for a caller
              without it; omit the row rather than report "Nicht festgelegt". */}
          {canFinance && (
            <div className="detail-item">
              <label>Preis:</label>
              <span className="tabular-nums">
                {order.price ? `${order.price.toFixed(2)} €` : 'Nicht festgelegt'}
              </span>
            </div>
          )}
          {order.deadline && (
            <div className="detail-item">
              <label>Frist:</label>
              <span className="tabular-nums">{formatDateTime(order.deadline)}</span>
            </div>
          )}
          {order.current_location && (
            <div className="detail-item">
              <label>Standort:</label>
              <span>{order.current_location}</span>
            </div>
          )}
          <div className="detail-item">
            <label>Erstellt:</label>
            <span className="tabular-nums">{formatDateTime(order.created_at)}</span>
          </div>
          <div className="detail-item">
            <label>Aktualisiert:</label>
            <span className="tabular-nums">{formatDateTime(order.updated_at)}</span>
          </div>
        </div>
      </section>

      <section className="details-section" aria-labelledby="order-overview-customer">
        <h3 id="order-overview-customer">Kunde</h3>
        <CustomerInfoCard customerId={order.customer_id} />
      </section>
    </div>
  );
}

export default OrderOverviewTab;
