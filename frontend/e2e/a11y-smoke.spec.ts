import { test, expect, type Page } from '@playwright/test';

/**
 * Accessibility smoke test (UI-UX-PLAYBOOK section 6 and 9, phase 1; W4-01).
 *
 * Runs axe-core on login, dashboard, orders and one order detail page and
 * fails on any "serious" or "critical" violation.
 *
 * STATUS: SKIPPED until `@axe-core/playwright` is added as a devDependency.
 * It is not installed today, and package.json was frozen for this change
 * (another branch is bumping dependencies). To enable:
 *   yarn add -D @axe-core/playwright
 * Nothing else in this file needs to change: the package is loaded at runtime
 * and every test skips cleanly while it is missing.
 *
 * The dashboard, orders and order detail checks also need a running backend
 * and E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD (same as auth.spec.ts); without
 * them those checks skip. The login check needs only the Vite dev server that
 * playwright.config.ts starts.
 */

const AXE_PACKAGE = '@axe-core/playwright';
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? '';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? '';
const hasCredentials = Boolean(ADMIN_EMAIL && ADMIN_PASSWORD);

interface AxeViolation {
  id: string;
  impact?: string | null;
  help: string;
  nodes: { target: unknown[] }[];
}
interface AxeBuilderLike {
  withTags(tags: string[]): AxeBuilderLike;
  analyze(): Promise<{ violations: AxeViolation[] }>;
}
type AxeBuilderCtor = new (options: { page: Page }) => AxeBuilderLike;

async function loadAxeBuilder(): Promise<AxeBuilderCtor | null> {
  try {
    // Variable specifier: resolved at runtime only, so neither tsc nor
    // Playwright's loader fails while the package is absent.
    const mod = (await import(/* @vite-ignore */ AXE_PACKAGE)) as { default: AxeBuilderCtor };
    return mod.default;
  } catch {
    return null;
  }
}

async function expectNoBlockingViolations(page: Page, AxeBuilder: AxeBuilderCtor, label: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const blocking = violations.filter((v) => BLOCKING_IMPACTS.has(v.impact ?? ''));
  const summary = blocking
    .map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.length}x, e.g. ${JSON.stringify(v.nodes[0]?.target)})`)
    .join('\n');
  expect(blocking, `${label}: serious/critical axe violations\n${summary}`).toEqual([]);
}

async function login(page: Page) {
  await page.goto('/login');
  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

let AxeBuilder: AxeBuilderCtor | null = null;

test.beforeAll(async () => {
  AxeBuilder = await loadAxeBuilder();
});

test.describe('a11y smoke (axe, serious + critical)', () => {
  test.beforeEach(() => {
    test.skip(AxeBuilder === null, `${AXE_PACKAGE} is not installed (yarn add -D ${AXE_PACKAGE})`);
  });

  test('login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#email')).toBeVisible();
    await expectNoBlockingViolations(page, AxeBuilder as AxeBuilderCtor, 'login');
  });

  test.describe('authenticated pages', () => {
    test.beforeEach(async ({ page }) => {
      test.skip(!hasCredentials, 'Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD and run the backend');
      await login(page);
    });

    test('dashboard', async ({ page }) => {
      await expectNoBlockingViolations(page, AxeBuilder as AxeBuilderCtor, 'dashboard');
    });

    test('orders list', async ({ page }) => {
      await page.goto('/orders');
      await page.waitForLoadState('networkidle');
      await expectNoBlockingViolations(page, AxeBuilder as AxeBuilderCtor, 'orders');
    });

    test('order detail', async ({ page }) => {
      await page.goto('/orders');
      await page.waitForLoadState('networkidle');
      // Rows are clickable <tr> today (DES-15); prefer a real link once it exists.
      const link = page.locator('a[href^="/orders/"]').first();
      const row = page.locator('.orders-table tbody tr').first();
      const target = (await link.count()) > 0 ? link : row;
      test.skip((await target.count()) === 0, 'No order in the database to open');
      await target.click();
      await expect(page).toHaveURL(/\/orders\/\d+/, { timeout: 10_000 });
      await page.waitForLoadState('networkidle');
      await expectNoBlockingViolations(page, AxeBuilder as AxeBuilderCtor, 'order detail');
    });
  });
});
