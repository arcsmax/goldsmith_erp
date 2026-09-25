// Generated API types (FE-12, W3-02): the enum unions that types.ts now
// re-exports must match the value sets the backend publishes in OpenAPI.
//
// `enums.json` is written by scripts/gen-api-types.mjs from the same
// OpenAPI document as schema.d.ts, so it is the runtime witness of the
// backend's enums. Each expected list below is also checked at compile time
// against the exported type (both directions), so if the backend adds,
// removes or renames a value, either tsc or this test fails.
import { describe, expect, it } from 'vitest';
import enums from './generated/enums.json';
import type {
  CalendarEventType,
  InvoiceStatus,
  NotificationSeverity,
  OrderStatus,
  QuoteStatus,
  RepairJobStatus,
  UserRole,
} from '../types';

/** Compile-time proof that `List` names every member of `T` and nothing else. */
type Exhaustive<T extends string, List extends readonly T[]> =
  [T] extends [List[number]] ? List : never;

function values<T extends string>() {
  return <const List extends readonly T[]>(list: Exhaustive<T, List>): List => list;
}

const USER_ROLES = values<UserRole>()(['admin', 'goldsmith', 'viewer']);
const ORDER_STATUSES = values<OrderStatus>()([
  'draft',
  'confirmed',
  'in_progress',
  'waiting_for_fitting',
  'fitting_done',
  'ready_for_setting',
  'quality_check',
  'completed',
  'delivered',
  'on_hold',
  'cancelled',
  'new',
]);
const NOTIFICATION_SEVERITIES = values<NotificationSeverity>()(['info', 'warning', 'urgent']);
const CALENDAR_EVENT_TYPES = values<CalendarEventType>()([
  'order_deadline',
  'workshop_task',
  'appointment',
  'reminder',
]);
const INVOICE_STATUSES = values<InvoiceStatus>()(['draft', 'sent', 'paid', 'overdue', 'cancelled']);
const QUOTE_STATUSES = values<QuoteStatus>()([
  'draft',
  'sent',
  'approved',
  'rejected',
  'expired',
  'converted',
]);
const REPAIR_STATUSES = values<RepairJobStatus>()([
  'received',
  'diagnosed',
  'quoted',
  'approved',
  'in_repair',
  'quality_check',
  'ready',
  'picked_up',
  'cancelled',
]);

const sorted = (list: readonly string[]): string[] => [...list].sort();

describe('generated API enums match the backend OpenAPI schema', () => {
  it.each([
    ['UserRole', USER_ROLES],
    ['OrderStatusEnum', ORDER_STATUSES],
    ['NotificationSeverityEnum', NOTIFICATION_SEVERITIES],
    ['CalendarEventType', CALENDAR_EVENT_TYPES],
    ['InvoiceStatus', INVOICE_STATUSES],
    ['QuoteStatus', QUOTE_STATUSES],
    ['RepairJobStatus', REPAIR_STATUSES],
  ] as const)('%s', (schemaName, expected) => {
    const published = (enums as Record<string, readonly string[]>)[schemaName];
    expect(published).toBeDefined();
    expect(sorted(published)).toEqual(sorted(expected));
  });

  it('publishes roles lowercase with no phantom USER role (FE-12)', () => {
    expect(enums.UserRole).not.toContain('USER');
    for (const role of enums.UserRole) {
      expect(role).toBe(role.toLowerCase());
    }
  });
});
