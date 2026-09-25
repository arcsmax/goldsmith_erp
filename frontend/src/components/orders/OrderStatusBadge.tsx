// Order status badge: kept as a named wrapper so the order page imports
// stay stable; renders the shared <StatusBadge kind="order"> (LV-05).
import type { OrderStatus } from '../../types';
import { StatusBadge } from '../../ui/StatusBadge';

interface OrderStatusBadgeProps {
  status: OrderStatus | string;
}

export function OrderStatusBadge({ status }: OrderStatusBadgeProps) {
  return <StatusBadge kind="order" status={status} />;
}
