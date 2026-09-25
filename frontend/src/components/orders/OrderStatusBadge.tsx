// Order status badge: icon + German label on the global status tones
// (styles/status-tones.css). Stopgap for <StatusBadge kind="order"> of
// Wave 4; keeps the existing `.status-badge.status-<value>` classes.
import type { OrderStatus } from '../../types';
import { OrderIcon, ORDER_STATUS_ICONS } from './OrderIcon';
import { isKnownStatus, statusLabel } from './orderStatus';

interface OrderStatusBadgeProps {
  status: OrderStatus | string;
}

export function OrderStatusBadge({ status }: OrderStatusBadgeProps) {
  const known = isKnownStatus(status);
  if (!known) {
    // A new backend status must be noticed, not silently mislabelled.
    console.warn('OrderStatusBadge: unknown order status', { status });
  }
  return (
    <span className={`status-badge status-${known ? status : 'unknown'}`}>
      {known && <OrderIcon name={ORDER_STATUS_ICONS[status]} />}
      {statusLabel(status)}
    </span>
  );
}
