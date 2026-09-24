// FE-09 / FE-11 / W1-14 — the service worker must never cache a response
// that can carry customer PII, financial data, design IP or insurance
// valuations (CLAUDE.md "Data Privacy Rules"). This is the single source of
// truth `vite.config.ts` consumes for `workbox.runtimeCaching`, so it is
// tested directly rather than by parsing the built `dist/sw.js`.
import { describe, expect, it } from 'vitest';
import { buildRuntimeCaching, resolveCachingRule } from './cachingRules';

describe('cachingRules', () => {
  const piiOrFinancialUrls = [
    'https://app.example/api/v1/customers',
    'https://app.example/api/v1/customers/42',
    'https://app.example/api/v1/orders',
    'https://app.example/api/v1/orders/17',
    'https://app.example/api/v1/invoices',
    'https://app.example/api/v1/invoices/9/pdf',
    'https://app.example/api/v1/materials',
    'https://app.example/api/v1/quotes',
    'https://app.example/api/v1/repairs',
    'https://app.example/api/v1/valuations',
    'https://app.example/api/v1/scrap-gold',
    'https://app.example/api/v1/time-tracking/running',
    'https://app.example/api/v1/users/me',
    'https://app.example/api/v1/auth/refresh',
  ];

  it.each(piiOrFinancialUrls)(
    'resolves %s to NetworkOnly (never cached)',
    (url) => {
      const rule = resolveCachingRule(url);
      expect(rule).toBeDefined();
      expect(rule?.handler).toBe('NetworkOnly');
    },
  );

  it('never emits an explicit runtime-caching rule for orders or materials', () => {
    // Regression guard for the built dist/sw.js check in the W1-14 hand-off
    // packet: no rule's urlPattern source may single out orders/materials
    // for caching — they must fall through to the generic NetworkOnly
    // /api/ rule like every other PII/financial endpoint.
    const rules = buildRuntimeCaching();
    const sources = rules
      .map((rule) => (rule.urlPattern instanceof RegExp ? rule.urlPattern.source : String(rule.urlPattern)))
      .join('|');
    expect(sources).not.toMatch(/orders/);
    expect(sources).not.toMatch(/materials/);
  });

  it('resolves activities to NetworkFirst, not CacheFirst (stale-activity fix)', () => {
    const rule = resolveCachingRule('https://app.example/api/v1/activities');
    expect(rule?.handler).toBe('NetworkFirst');
  });

  it('caches static build assets with CacheFirst', () => {
    const jsRule = resolveCachingRule('https://app.example/assets/index-abc123.js');
    const cssRule = resolveCachingRule('https://app.example/assets/index-abc123.css');
    const fontRule = resolveCachingRule('https://app.example/assets/roboto-abc123.woff2');

    for (const rule of [jsRule, cssRule, fontRule]) {
      expect(rule).toBeDefined();
      expect(rule?.handler).toBe('CacheFirst');
    }
  });

  it('orders the activities rule before the generic /api/ catch-all', () => {
    // First-match-wins (Workbox semantics): if the catch-all came first,
    // activities would never reach the NetworkFirst rule.
    const rules = buildRuntimeCaching();
    const activitiesIndex = rules.findIndex((r) => r.handler === 'NetworkFirst');
    const catchAllIndex = rules.findIndex(
      (r) => r.handler === 'NetworkOnly' && r.urlPattern instanceof RegExp && r.urlPattern.test('/api/v1/anything'),
    );
    expect(activitiesIndex).toBeGreaterThanOrEqual(0);
    expect(catchAllIndex).toBeGreaterThanOrEqual(0);
    expect(activitiesIndex).toBeLessThan(catchAllIndex);
  });
});
