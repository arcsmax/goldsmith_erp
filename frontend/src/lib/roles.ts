// Frontend mirror of the backend's cross-cutting data-class permissions
// (SEC-01, SEC-09, GDPR-03, GDPR-04, GDPR-09 — see
// src/goldsmith_erp/api/role_projection.py and
// src/goldsmith_erp/core/permissions.py::Permission.FINANCIAL_VIEW /
// Permission.DESIGN_VIEW / Permission.VALUATION_EXPORT).
//
// CLAUDE.md "Data Privacy Rules":
// - Pricing, payment info, material costs -> ADMIN and GOLDSMITH only.
// - Custom jewelry designs, design descriptions -> GOLDSMITH or ADMIN only.
// - Insurance valuations -> exportable only by ADMIN.
//
// These helpers exist so every screen that renders financial data, design
// IP, or the valuation PDF export checks the SAME rule the backend enforces,
// instead of ad-hoc `role === 'ADMIN'` string comparisons scattered across
// pages. Use them to decide whether to call a gated endpoint at all (a
// VIEWER calling one 403s) and whether to render a price/design field that
// the backend may have stripped from an otherwise-visible resource.
import { UserRole } from '../types';

/**
 * Roles have been observed in both cases from the backend (see
 * AuthContext.hasRole's own normalisation) — never assume uppercase.
 */
function normalizeRole(role?: UserRole | string | null): string {
  return (role ?? '').toUpperCase();
}

/**
 * True when the caller may see prices, costs, revenue and stock value.
 * Mirrors `Permission.FINANCIAL_VIEW` (ADMIN + GOLDSMITH; VIEWER does not
 * hold it). Also covers the REPORTS_VIEW-gated analytics endpoints, which
 * share the identical ADMIN/GOLDSMITH-yes, VIEWER-no split.
 */
export function canViewFinancials(role?: UserRole | string | null): boolean {
  const normalized = normalizeRole(role);
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/**
 * True when the caller may see design descriptions, special instructions,
 * and order/repair photos. Mirrors `Permission.DESIGN_VIEW` (ADMIN +
 * GOLDSMITH; VIEWER does not hold it).
 */
export function canViewDesign(role?: UserRole | string | null): boolean {
  const normalized = normalizeRole(role);
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/**
 * True when the caller may download the valuation certificate PDF.
 * Mirrors `Permission.VALUATION_EXPORT` (ADMIN only, GDPR-09 — GOLDSMITH
 * keeps list/detail access but lost PDF export).
 */
export function canDownloadValuationPdf(role?: UserRole | string | null): boolean {
  return normalizeRole(role) === 'ADMIN';
}

/**
 * True when the caller may create orders. Mirrors `Permission.ORDER_CREATE`
 * (ADMIN + GOLDSMITH; VIEWER does not hold it). LV-07.
 */
export function canCreateOrders(role?: UserRole | string | null): boolean {
  const normalized = normalizeRole(role);
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/**
 * True when the caller may edit orders. Mirrors `Permission.ORDER_EDIT`
 * (ADMIN + GOLDSMITH).
 */
export function canEditOrders(role?: UserRole | string | null): boolean {
  const normalized = normalizeRole(role);
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/**
 * True when the caller may delete orders. Mirrors `Permission.ORDER_DELETE`
 * (ADMIN only; GOLDSMITH does not hold it).
 */
export function canDeleteOrders(role?: UserRole | string | null): boolean {
  return normalizeRole(role) === 'ADMIN';
}

/**
 * True when the caller may create a quote (Kostenvoranschlag). Mirrors
 * `Permission.QUOTE_CREATE` (ADMIN + GOLDSMITH; VIEWER does not hold it —
 * the /quotes route itself is gated the same way in App.tsx). LV2-04: the
 * order detail page's "Angebot erstellen" button navigated a VIEWER to
 * /quotes, which the route guard then silently bounced back to /dashboard.
 */
export function canCreateQuotes(role?: UserRole | string | null): boolean {
  const normalized = normalizeRole(role);
  return normalized === 'ADMIN' || normalized === 'GOLDSMITH';
}

/**
 * True when the caller may create, edit or delete materials. Mirrors
 * `Permission.MATERIAL_CREATE` / `MATERIAL_EDIT` / `MATERIAL_DELETE`
 * (ADMIN only; GOLDSMITH and VIEWER hold MATERIAL_VIEW).
 */
export function canManageMaterials(role?: UserRole | string | null): boolean {
  return normalizeRole(role) === 'ADMIN';
}

/** Short German hint shown where hiding a financial section would
 *  otherwise leave a confusing empty gap. */
export const FINANCIAL_HIDDEN_HINT = 'Keine Berechtigung für Finanzdaten';

/** Short German hint shown where hiding a design-IP section (photos,
 *  design descriptions) would otherwise leave a confusing empty gap. */
export const DESIGN_HIDDEN_HINT = 'Keine Berechtigung für Design-Daten';
