// Icon — the shared inline SVG icon set for src/ui (UI-UX-PLAYBOOK 4, 6).
//
// A small, dependency-free stand-in until an SVG icon package is adopted
// (playbook section 9, phase 2; adding a package is out of this item's scope).
// Shapes follow the Lucide 24px grid, stroke-based, `currentColor`, so they
// inherit text colour and never carry colour on their own. Icons are always
// decorative (`aria-hidden`); the accessible name comes from visible text or
// an IconButton `label`.
import React from 'react';

const PATHS = {
  close: ['M18 6 6 18', 'M6 6l12 12'],
  plus: ['M12 5v14', 'M5 12h14'],
  'arrow-left': ['M19 12H5', 'M12 19l-7-7 7-7'],
  'chevron-up': ['M18 15l-6-6-6 6'],
  'chevron-down': ['M6 9l6 6 6-6'],
  'chevrons-up-down': ['M7 15l5 5 5-5', 'M7 9l5-5 5 5'],
  'alert-triangle': [
    'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    'M12 9v4',
    'M12 17h.01',
  ],
  inbox: [
    'M22 12h-6l-2 3h-4l-2-3H2',
    'M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z',
  ],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'M21 21l-4.3-4.3'],
  refresh: ['M3 12a9 9 0 0 1 15-6.7L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-15 6.7L3 16', 'M8 16H3v5'],
  pencil: ['M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z'],
  trash: ['M3 6h18', 'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6', 'M10 11v6', 'M14 11v6', 'M9 6V4h6v2'],
  more: ['M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z', 'M19 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z', 'M5 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z'],
  check: ['M20 6 9 17l-5-5'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 6v6l4 2'],
  home: ['M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z'],
  clipboard: [
    'M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z',
    'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2',
  ],
  scan: ['M3 7V5a2 2 0 0 1 2-2h2', 'M17 3h2a2 2 0 0 1 2 2v2', 'M21 17v2a2 2 0 0 1-2 2h-2', 'M7 21H5a2 2 0 0 1-2-2v-2', 'M7 12h10'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
} as const;

export type IconName = keyof typeof PATHS;

export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export interface IconProps {
  name: IconName;
  className?: string;
}

export const Icon: React.FC<IconProps> = ({ name, className }) => (
  <svg
    className={className ? `ui-icon ${className}` : 'ui-icon'}
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
