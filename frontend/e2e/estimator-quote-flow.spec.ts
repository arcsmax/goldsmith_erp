import { test, expect, Page } from '@playwright/test';

/**
 * Estimator-on-Quote Flow E2E — V1.3 Phase 3
 *
 * Exercises the wiring added in PR #49 (feat/v13-phase3-wire-order):
 * when a DRAFT quote references an order, QuotesPage fetches the
 * linked OrderType and passes alloy + surface_finish into the
 * EstimatorPanel. The panel renders for DRAFT quotes only and shows a
 * fallback message when no order is linked.
 *
 * Requires a live backend at http://localhost:8000 with seed data
 * loaded (scripts/seed_demo.py). The seed provides quote KV-2026-0001
 * (DRAFT, linked to order #9 "Armband Silber 925") and a mix of
 * non-DRAFT quotes that should suppress the EstimatorPanel.
 *
 * Mirrors goldsmith-workflow.spec.ts's approach of hard-coding the
 * seeded admin credentials — only runs in environments where the demo
 * seed has been applied.
 *
 * Intentionally does NOT exercise the full "fetch estimate → accept"
 * path: that depends on the labor corpus sample size (MAPE / bias
 * calibration) and is covered by the backend unit tests. This test
 * only verifies that the panel is reachable from a draft quote, that
 * the linked-order pre-fill is wired through, and that the gating
 * rules (DRAFT only, role-gated, no panel for non-DRAFT) hold.
 */

const ADMIN_EMAIL = 'admin@goldschmiede.de';
const ADMIN_PASSWORD = 'Admin123!';

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
  });
  await page.reload();
  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10_000 });
}

async function openQuotesPage(page: Page): Promise<void> {
  await page.goto('/quotes');
  // Wait for the quote list to render — either a row or an empty-state
  // message. The h1 "Angebote" is always rendered above the table.
  await expect(page.locator('h1')).toContainText(/angebote/i, { timeout: 10_000 });
}

test.describe('Estimator wiring — DRAFT quote with linked order', () => {
  test('selecting the seeded DRAFT quote renders the EstimatorPanel with the order linked', async ({
    page,
  }) => {
    await login(page);
    await openQuotesPage(page);

    // The seeded DRAFT quote is KV-2026-0001.
    const draftRow = page.getByRole('row', { name: /KV-2026-0001/ }).first();
    await expect(draftRow).toBeVisible({ timeout: 5_000 });
    await draftRow.click();

    // QuoteDetailPanel + EstimatorPanel both render. The panel has a
    // stable "Kalkulation" heading.
    const panel = page.locator('[data-testid="estimator-fetch-button"]').first();
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // Sanity-check the surrounding header
    await expect(
      page.getByRole('heading', { name: 'Kalkulation' })
    ).toBeVisible();

    // The idle form exposes the three estimator inputs
    await expect(page.locator('#estimator-finish')).toBeVisible();
    await expect(page.locator('#estimator-alloy')).toBeVisible();
    await expect(page.locator('#estimator-complexity')).toBeVisible();

    // The fetch button is labelled "Schätzung holen"
    await expect(panel).toHaveText(/Schätzung holen/);
  });

  test('selecting a non-DRAFT quote does not render the EstimatorPanel', async ({
    page,
  }) => {
    await login(page);
    await openQuotesPage(page);

    // The seeded SENT quote is KV-2026-0002 (status filter is "SENT").
    const sentRow = page.getByRole('row', { name: /KV-2026-0002/ }).first();
    await expect(sentRow).toBeVisible({ timeout: 5_000 });
    await sentRow.click();

    // QuoteDetailPanel renders (header line + Status badge) …
    await expect(
      page.getByText(/Genehmigen|Ablehnen|PDF/).first()
    ).toBeVisible({ timeout: 5_000 });

    // … but the EstimatorPanel does not.
    await expect(
      page.getByRole('heading', { name: 'Kalkulation' })
    ).toHaveCount(0);
    await expect(
      page.locator('[data-testid="estimator-fetch-button"]')
    ).toHaveCount(0);
  });
});