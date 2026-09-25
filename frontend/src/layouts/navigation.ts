// Grouped navigation for the staff app (UI-UX-PLAYBOOK 4.11, W4-03).
//
// One source for the desktop sidebar and the phone drawer (NAV_GROUPS) and
// for the app tab bar below 1024px (tabBarItems). Every entry carries the
// role rule the route guard in App.tsx enforces, so a VIEWER never sees a
// link that would bounce them back to the dashboard.
import type { IconName } from '../ui/Icon';
import type { TabBarItem } from '../ui/Tabs';
import type { UserRole } from '../types';
import { canAdministerSystem, canViewFinancials } from '../lib/roles';

type RoleRule = (role?: UserRole | string | null) => boolean;

export interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
  /** Omitted = every authenticated role. */
  allow?: RoleRule;
}

export interface NavGroup {
  id: string;
  /** Group heading; omitted for single-link groups ("Heute"). */
  label?: string;
  entries: NavEntry[];
}

/** ADMIN + GOLDSMITH: customers, repairs, consultations, materials, money. */
const staffOnly: RoleRule = canViewFinancials;

export const NAV_GROUPS: NavGroup[] = [
  { id: 'heute', entries: [{ to: '/dashboard', label: 'Heute', icon: 'home' }] },
  {
    id: 'auftraege',
    label: 'Aufträge',
    entries: [
      { to: '/orders', label: 'Aufträge', icon: 'clipboard' },
      { to: '/repairs', label: 'Reparaturen', icon: 'wrench', allow: staffOnly },
      { to: '/calendar', label: 'Kalender', icon: 'clock' },
    ],
  },
  {
    id: 'werkstatt',
    label: 'Werkstatt',
    entries: [
      { to: '/scanner', label: 'Scanner', icon: 'scan' },
      { to: '/time-tracking', label: 'Zeiterfassung', icon: 'hourglass' },
    ],
  },
  {
    id: 'kunden',
    label: 'Kunden',
    entries: [
      { to: '/customers', label: 'Kunden', icon: 'user-check', allow: staffOnly },
      { to: '/consultations', label: 'Beratung', icon: 'sparkles', allow: staffOnly },
    ],
  },
  {
    id: 'buero',
    label: 'Angebote & Rechnungen',
    entries: [
      { to: '/quotes', label: 'Angebote', icon: 'calculator', allow: staffOnly },
      { to: '/invoices', label: 'Rechnungen', icon: 'receipt', allow: staffOnly },
    ],
  },
  {
    id: 'material',
    label: 'Material',
    entries: [
      { to: '/materials', label: 'Materialien', icon: 'gem', allow: staffOnly },
      { to: '/metal-inventory', label: 'Metallinventar', icon: 'archive', allow: staffOnly },
    ],
  },
  {
    id: 'verwaltung',
    label: 'Verwaltung',
    entries: [
      { to: '/users', label: 'Benutzer', icon: 'user-check', allow: canAdministerSystem },
      { to: '/admin/system', label: 'System', icon: 'stamp', allow: canAdministerSystem },
      { to: '/settings', label: 'Einstellungen', icon: 'pen-line' },
    ],
  },
];

function isVisible(entry: NavEntry, role?: UserRole | string | null): boolean {
  return entry.allow ? entry.allow(role) : true;
}

/** The groups a role may see; empty groups are dropped. */
export function navGroupsFor(role?: UserRole | string | null): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    entries: group.entries.filter((entry) => isVisible(entry, role)),
  })).filter((group) => group.entries.length > 0);
}

/** Five most-used entries for the phone/tablet tab bar; scan in the centre. */
export function tabBarItems(role?: UserRole | string | null): TabBarItem[] {
  const fifth: TabBarItem = staffOnly(role)
    ? { to: '/customers', label: 'Kunden', icon: 'user-check' }
    : { to: '/calendar', label: 'Kalender', icon: 'clock' };
  return [
    { to: '/dashboard', label: 'Heute', icon: 'home' },
    { to: '/orders', label: 'Aufträge', icon: 'clipboard' },
    { to: '/scanner', label: 'Scan', icon: 'scan', prominent: true },
    { to: '/time-tracking', label: 'Zeit', icon: 'hourglass' },
    fifth,
  ];
}
