// roles.ts — frontend mirror of the backend's FINANCIAL_VIEW / DESIGN_VIEW /
// VALUATION_EXPORT data-class permissions (SEC-01, SEC-09, GDPR-03, GDPR-04,
// GDPR-09). Pins the exact ADMIN/GOLDSMITH/VIEWER split so a future role
// change can't silently drift from the backend.
import { describe, expect, it } from 'vitest';
import {
  canCreateOrders,
  canDeleteOrders,
  canEditOrders,
  canDownloadValuationPdf,
  canViewDesign,
  canViewFinancials,
  DESIGN_HIDDEN_HINT,
  FINANCIAL_HIDDEN_HINT,
} from './roles';

describe('canViewFinancials', () => {
  it('returns true for ADMIN', () => {
    expect(canViewFinancials('ADMIN')).toBe(true);
  });

  it('returns true for GOLDSMITH', () => {
    expect(canViewFinancials('GOLDSMITH')).toBe(true);
  });

  it('returns false for VIEWER', () => {
    expect(canViewFinancials('VIEWER')).toBe(false);
  });

  it('is case-insensitive, mirroring backend responses observed in both cases', () => {
    expect(canViewFinancials('goldsmith')).toBe(true);
    expect(canViewFinancials('viewer')).toBe(false);
  });

  it('returns false when role is missing', () => {
    expect(canViewFinancials(undefined)).toBe(false);
    expect(canViewFinancials(null)).toBe(false);
    expect(canViewFinancials('')).toBe(false);
  });
});

describe('canViewDesign', () => {
  it('returns true for ADMIN and GOLDSMITH', () => {
    expect(canViewDesign('ADMIN')).toBe(true);
    expect(canViewDesign('GOLDSMITH')).toBe(true);
  });

  it('returns false for VIEWER', () => {
    expect(canViewDesign('VIEWER')).toBe(false);
  });

  it('returns false when role is missing', () => {
    expect(canViewDesign(undefined)).toBe(false);
  });
});

describe('canDownloadValuationPdf', () => {
  it('returns true for ADMIN only (GDPR-09 — GOLDSMITH lost PDF export)', () => {
    expect(canDownloadValuationPdf('ADMIN')).toBe(true);
    expect(canDownloadValuationPdf('GOLDSMITH')).toBe(false);
    expect(canDownloadValuationPdf('VIEWER')).toBe(false);
  });

  it('is case-insensitive', () => {
    expect(canDownloadValuationPdf('admin')).toBe(true);
  });

  it('returns false when role is missing', () => {
    expect(canDownloadValuationPdf(undefined)).toBe(false);
  });
});

describe('hidden-section hint text', () => {
  it('provides distinct German hints for financial vs. design gaps', () => {
    expect(FINANCIAL_HIDDEN_HINT).toBe('Keine Berechtigung für Finanzdaten');
    expect(DESIGN_HIDDEN_HINT).toBe('Keine Berechtigung für Design-Daten');
    expect(FINANCIAL_HIDDEN_HINT).not.toBe(DESIGN_HIDDEN_HINT);
  });
});

// LV-07: mirrors Permission.ORDER_CREATE / ORDER_EDIT (ADMIN + GOLDSMITH)
// and ORDER_DELETE (ADMIN only) in core/permissions.py.
describe('order write permissions', () => {
  it.each([
    ['ADMIN', true, true, true],
    ['GOLDSMITH', true, true, false],
    ['VIEWER', false, false, false],
    ['admin', true, true, true],
    [null, false, false, false],
  ] as const)('%s: create=%s edit=%s delete=%s', (role, create, edit, remove) => {
    expect(canCreateOrders(role)).toBe(create);
    expect(canEditOrders(role)).toBe(edit);
    expect(canDeleteOrders(role)).toBe(remove);
  });
});
