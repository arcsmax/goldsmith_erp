// Order page icons (W2-08), now a thin wrapper over the shared set in
// src/ui/Icon.tsx (Wave 4 / LV-05). Kept so existing imports keep working;
// the status icons come from the single status map (src/design/status.ts).
import { ORDER_STATUS } from '../../design/status';
import type { OrderStatus } from '../../types';
import { Icon, type IconName } from '../../ui/Icon';

export type OrderIconName = IconName;

export const ORDER_STATUS_ICONS: Readonly<Record<OrderStatus, OrderIconName>> = Object.fromEntries(
  (Object.keys(ORDER_STATUS) as OrderStatus[]).map((status) => [status, ORDER_STATUS[status].icon]),
) as Record<OrderStatus, OrderIconName>;

interface OrderIconProps {
  name: OrderIconName;
  className?: string;
}

export function OrderIcon({ name, className }: OrderIconProps) {
  return <Icon name={name} className={className ? `order-icon ${className}` : 'order-icon'} />;
}
