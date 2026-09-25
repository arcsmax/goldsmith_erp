// Completeness of the single status map against the backend enums (LV-05).
// enums.json is generated from the OpenAPI schema, so a backend status that
// the map does not know (or a stale one the backend dropped) fails here.
import { describe, expect, it } from 'vitest';
import enums from '../api/generated/enums.json';
import {
  STATUS_MAP,
  getHandoffTypeLabel,
  getStatusLabel,
  getStatusMeta,
  type StatusKind,
} from './status';
import { ICON_PATHS } from '../ui/Icon';

const ENUM_FOR_KIND: Readonly<Record<Exclude<StatusKind, 'scrapGold'>, string>> = {
  order: 'OrderStatusEnum',
  repair: 'RepairJobStatus',
  quote: 'QuoteStatus',
  invoice: 'InvoiceStatus',
  consultation: 'ConsultationStatus',
  costChange: 'CostChangeStatus',
  handoff: 'HandoffStatusEnum',
  hallmark: 'HallmarkStatus',
  customerUpdate: 'CustomerUpdateStatus',
};

const enumValues = enums as unknown as Record<string, string[]>;
const ASCII_UMLAUT = /(ae|oe|ue)/i;

describe('design/status map', () => {
  it.each(Object.entries(ENUM_FOR_KIND))(
    '%s covers exactly the backend enum values',
    (kind, enumName) => {
      const expected = [...(enumValues[enumName] ?? [])].sort();
      expect(expected.length).toBeGreaterThan(0);
      expect(Object.keys(STATUS_MAP[kind as StatusKind]).sort()).toEqual(expected);
    },
  );

  it('covers the scrap gold statuses of the backend ScrapGoldStatus enum', () => {
    expect(Object.keys(STATUS_MAP.scrapGold).sort()).toEqual(
      ['calculated', 'credited', 'received', 'signed'],
    );
  });

  it('gives every status a German label, a known icon and a tone', () => {
    for (const table of Object.values(STATUS_MAP)) {
      for (const [value, meta] of Object.entries(table)) {
        expect(meta.label, value).not.toBe('');
        expect(meta.label, value).not.toMatch(/^[A-Z_]+$/);
        expect(meta.label.toLowerCase(), value).not.toMatch(ASCII_UMLAUT);
        expect(Object.keys(ICON_PATHS), value).toContain(meta.icon);
      }
    }
  });

  it('uses the playbook labels where pages disagreed', () => {
    expect(getStatusLabel('order', 'confirmed')).toBe('Bestätigt');
    expect(getStatusLabel('order', 'draft')).toBe('Entwurf');
    expect(getStatusLabel('repair', 'ready')).toBe('Abholbereit');
    expect(getStatusLabel('repair', 'quoted')).toBe('Angebot offen');
    expect(getStatusLabel('quote', 'converted')).toBe('In Auftrag umgewandelt');
  });

  it('falls back to lower case for upper-case wire values', () => {
    expect(getStatusMeta('handoff', 'PENDING')?.label).toBe('Offen');
  });

  it('returns the raw value for unknown statuses', () => {
    expect(getStatusMeta('order', 'teleported')).toBeUndefined();
    expect(getStatusLabel('order', 'teleported')).toBe('teleported');
  });

  it('labels every handoff type of the backend enum (LV-08)', () => {
    for (const value of enumValues.HandoffTypeEnum) {
      expect(getHandoffTypeLabel(value)).not.toBe(value);
    }
    expect(getHandoffTypeLabel('request_review')).toBe('Prüfung anfordern');
  });
});
