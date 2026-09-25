// Small inline icon set for the order page (W2-08).
//
// Stopgap until the shared icon set of Wave 4 exists. Shapes follow the
// Lucide names of UI-UX-PLAYBOOK 3.2 (MIT). Always decorative: the label
// next to the icon carries the meaning, so the SVG is aria-hidden.
import type { OrderStatus } from '../../types';

export type OrderIconName =
  | 'pencil'
  | 'sparkles'
  | 'clipboard-check'
  | 'hammer'
  | 'hourglass'
  | 'user-check'
  | 'gem'
  | 'scan-search'
  | 'circle-check'
  | 'package-check'
  | 'pause'
  | 'circle-x'
  | 'arrow-right'
  | 'chevron-down'
  | 'camera'
  | 'mail'
  | 'clock';

const PATHS: Readonly<Record<OrderIconName, readonly string[]>> = {
  pencil: ['M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z'],
  sparkles: ['M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z', 'M19 17v4', 'M17 19h4'],
  'clipboard-check': [
    'M9 4h6v3H9z',
    'M16 5h2a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2',
    'm9 14 2 2 4-4',
  ],
  hammer: ['m15 12-8.5 8.5a2.1 2.1 0 0 1-3-3L12 9', 'M17.6 15 22 10.6', 'm20 12-8-8 3-3 8 8Z'],
  hourglass: ['M5 22h14', 'M5 2h14', 'M17 22v-4.2a2 2 0 0 0-.6-1.4L12 12l-4.4 4.4a2 2 0 0 0-.6 1.4V22', 'M7 2v4.2a2 2 0 0 0 .6 1.4L12 12l4.4-4.4a2 2 0 0 0 .6-1.4V2'],
  'user-check': ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'm16 11 2 2 4-4'],
  gem: ['M6 3h12l4 6-10 13L2 9Z', 'M2 9h20', 'M12 22 8 9l4-6 4 6Z'],
  'scan-search': ['M3 7V5a2 2 0 0 1 2-2h2', 'M17 3h2a2 2 0 0 1 2 2v2', 'M21 17v2a2 2 0 0 1-2 2h-2', 'M7 21H5a2 2 0 0 1-2-2v-2', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'm16 16-1.9-1.9'],
  'circle-check': ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'm9 12 2 2 4-4'],
  'package-check': ['m16 16 2 2 4-4', 'M21 10V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l2-1.1', 'M3.3 7 12 12l8.7-5', 'M12 22V12'],
  pause: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M10 15V9', 'M14 15V9'],
  'circle-x': ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'm15 9-6 6', 'm9 9 6 6'],
  'arrow-right': ['M5 12h14', 'm12 5 7 7-7 7'],
  'chevron-down': ['m6 9 6 6 6-6'],
  camera: ['M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3Z', 'M12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z'],
  mail: ['M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z', 'm22 7-10 7L2 7'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 6v6l4 2'],
};

export const ORDER_STATUS_ICONS: Readonly<Record<OrderStatus, OrderIconName>> = {
  draft: 'pencil',
  new: 'sparkles',
  confirmed: 'clipboard-check',
  in_progress: 'hammer',
  waiting_for_fitting: 'hourglass',
  fitting_done: 'user-check',
  ready_for_setting: 'gem',
  quality_check: 'scan-search',
  completed: 'circle-check',
  delivered: 'package-check',
  on_hold: 'pause',
  cancelled: 'circle-x',
};

interface OrderIconProps {
  name: OrderIconName;
  className?: string;
}

export function OrderIcon({ name, className }: OrderIconProps) {
  return (
    <svg
      className={className ? `order-icon ${className}` : 'order-icon'}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
