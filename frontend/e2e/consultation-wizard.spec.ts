import { test, expect } from '@playwright/test';

/**
 * Consultation Wizard E2E — Beratungs-Wizard (V1.1 consultation frontend,
 * Task 10).
 *
 * Requires a live backend at http://localhost:8000 with seed data loaded
 * (STANDARD_USERS / SAMPLE_CUSTOMERS — see
 * src/goldsmith_erp/db/seed_data.py). Mirrors auth.spec.ts's env-var gating:
 * without E2E_GOLDSMITH_EMAIL / E2E_GOLDSMITH_PASSWORD the test is skipped
 * rather than failing when no backend is reachable. Set both to the
 * goldschmied@goldschmiede.de account's credentials (SEED_GOLDSMITH_PASSWORD
 * at seed time, `dev-only-change-me` by default) to run locally.
 *
 * A single sequential test drives the whole walkthrough — logging in once,
 * per goldsmith-workflow.spec.ts's rationale (login is rate-limited to
 * 5/min). It deliberately stops at the summary step and never clicks
 * "Kostenvoranschlag erstellen" / "Auftrag anlegen": converting would create
 * a real order/quote and leave noise data behind (see Task 10 brief).
 *
 * Covers the previously-untested critical path flagged in review: the
 * draft-creation click in CustomerStep (search → select → "Beratung
 * starten" → POST /consultations → navigate to step 2).
 */

const GOLDSMITH_EMAIL = process.env.E2E_GOLDSMITH_EMAIL ?? '';
const GOLDSMITH_PASSWORD = process.env.E2E_GOLDSMITH_PASSWORD ?? '';
const hasCredentials = !!(GOLDSMITH_EMAIL && GOLDSMITH_PASSWORD);

// Tablet-first — 768x1024 portrait is the wizard's primary target viewport
// (see styles/consultations.css header comment). At this width the app's
// sidebar nav collapses to an off-canvas hamburger menu (layout.css, ≤768px).
test.use({ viewport: { width: 768, height: 1024 } });

test.describe('Consultation wizard — draft creation + step walkthrough', () => {
  test.skip(!hasCredentials, 'Set E2E_GOLDSMITH_EMAIL and E2E_GOLDSMITH_PASSWORD to run');

  test('goldsmith creates a draft consultation and walks it through to the summary', async ({
    page,
  }) => {
    // ============ LOGIN ============
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    });
    await page.reload();

    await page.locator('#email').fill(GOLDSMITH_EMAIL);
    await page.locator('#password').fill(GOLDSMITH_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.locator('.dashboard-container h1')).toHaveText('Dashboard');

    // ============ NAVIGATE TO BERATUNG ============
    // At 768px the sidebar is off-canvas until the hamburger opens it.
    await page.getByRole('button', { name: 'Navigation öffnen' }).click();
    const sidebar = page.locator('#main-sidebar');
    await expect(sidebar).toBeVisible();
    await sidebar.getByRole('link', { name: 'Beratung', exact: true }).click();
    await expect(page).toHaveURL(/\/consultations$/);
    await expect(page.locator('h1')).toHaveText('Beratungen');

    // ============ NEW CONSULTATION ============
    await page.getByRole('button', { name: '+ Neue Beratung', exact: true }).click();
    await expect(page).toHaveURL(/\/consultations\/new$/);
    await expect(page.locator('h2')).toHaveText('Kundin');

    // ============ STEP 1: CUSTOMER — search, select, create draft ============
    const search = page.getByRole('combobox', { name: 'Kundin suchen', exact: true });
    await search.fill('Sophie');
    const results = page.locator('.typeahead-results button');
    await expect(results.first()).toBeVisible({ timeout: 10_000 });
    await results.first().click();

    await expect(page.locator('.customer-confirm-card')).toBeVisible();

    // The untested critical path: CustomerStep.handleStartConsultation —
    // POST /consultations, then the wizard navigates to step 2 on success.
    await page.getByRole('button', { name: 'Beratung starten', exact: true }).click();
    await expect(page).toHaveURL(/\/consultations\/\d+\?step=2/, { timeout: 10_000 });

    // ============ STEP 2: ANLASS & BUDGET ============
    await expect(page.locator('h2')).toHaveText('Anlass & Budget');
    await page.getByRole('button', { name: 'Verlobung', exact: true }).click();
    await page.getByRole('button', { name: 'Weiter', exact: true }).click();

    // ============ STEP 3: DER WUNSCH ============
    await expect(page.locator('h2')).toHaveText('Der Wunsch');
    const wishText = `E2E-Testwunsch ${Date.now()}`;
    await page.getByRole('button', { name: 'Ring', exact: true }).click();
    await page.locator('#wishes').fill(wishText);
    await page.getByRole('button', { name: 'Weiter', exact: true }).click();

    // ============ STEP 4: STIL & NO-GOS (no fields needed) ============
    await expect(page.locator('h2')).toHaveText('Stil & No-Gos');
    await page.getByRole('button', { name: 'Weiter', exact: true }).click();

    // ============ STEP 5: MASSE (no fields needed) ============
    await expect(page.locator('h2')).toHaveText('Maße');
    await page.getByRole('button', { name: 'Weiter', exact: true }).click();

    // ============ STEP 6: SKIZZEN & FOTOS (no upload needed) ============
    await expect(page.locator('h2')).toHaveText('Skizzen & Fotos');
    await page.getByRole('button', { name: 'Weiter', exact: true }).click();

    // ============ STEP 7: ZUSAMMENFASSUNG ============
    await expect(page.locator('h2')).toHaveText('Zusammenfassung');
    const wishSection = page.locator('.summary-section', { hasText: 'Wunsch' });
    await expect(wishSection).toContainText(wishText);

    // No conversion click here — "Kostenvoranschlag erstellen" / "Auftrag
    // anlegen" would create real, non-reversible order/quote noise data.
  });
});
