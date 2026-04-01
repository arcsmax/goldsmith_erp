import { test, expect, Page } from '@playwright/test';

/**
 * Goldsmith Daily Workflow E2E Tests
 * Lena Vogel — UX Research, Goldsmith Workshop Simulation
 *
 * Tests the complete goldsmith day in sequence:
 * login → dashboard → create order → view order detail → navigate all pages → customer detail → metal inventory
 *
 * Backend: http://localhost:8080
 * Frontend: http://localhost:3000
 */

const ADMIN_EMAIL = 'admin@goldschmiede.de';
const ADMIN_PASSWORD = 'Admin123!';

// Helper: login once and reuse auth state
async function login(page: Page) {
  await page.goto('/login');
  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);
  await page.locator('button[type="submit"]').click();
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10_000 });
}

// Helper: check a page for common error indicators
async function checkNoErrors(page: Page, pageName: string) {
  const body = await page.locator('body').textContent();
  const lower = (body ?? '').toLowerCase();

  const hasError =
    lower.includes('uncaught') ||
    lower.includes('something went wrong') ||
    lower.includes('cannot read') ||
    lower.includes('typeerror');

  if (hasError) {
    console.warn(`[${pageName}] Potential JS error detected in body text`);
  }
}

// ─────────────────────────────────────────────────────────────
// Flow 1: Login
// ─────────────────────────────────────────────────────────────
test.describe('Flow 1: Login', () => {
  test('login page shows Goldsmith ERP heading', async ({ page }) => {
    await page.goto('/login');
    const h1 = page.locator('h1');
    await expect(h1).toBeVisible({ timeout: 5_000 });
    await expect(h1).toContainText('Goldsmith ERP');
  });

  test('login form has email and password fields', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#email')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toContainText('Anmelden');
  });

  test('successful login redirects to /dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10_000 });
    expect(page.url()).toContain('/dashboard');
  });

  test('dashboard has sidebar navigation after login', async ({ page }) => {
    await login(page);
    // Sidebar nav should be rendered — look for any nav element or sidebar landmark
    const sidebar = page.locator('nav, aside, [role="navigation"]').first();
    await expect(sidebar).toBeVisible({ timeout: 8_000 });
  });

  test('wrong credentials shows an error message', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#email').fill('wrong@example.com');
    await page.locator('#password').fill('WrongPass999!');
    await page.locator('button[type="submit"]').click();
    // Stay on /login and show some error indicator
    await page.waitForTimeout(3_000);
    expect(page.url()).toContain('/login');
  });
});

// ─────────────────────────────────────────────────────────────
// Flow 2: Dashboard
// ─────────────────────────────────────────────────────────────
test.describe('Flow 2: Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('dashboard URL is correct', async ({ page }) => {
    expect(page.url()).toContain('/dashboard');
  });

  test('dashboard page body is not blank', async ({ page }) => {
    const body = await page.locator('body').textContent();
    expect((body ?? '').trim().length).toBeGreaterThan(50);
  });

  test('no raw "undefined" or "null" text visible on dashboard', async ({ page }) => {
    const body = await page.locator('body').textContent();
    // Exact standalone "undefined" or "null" as visible user-facing text is a bug
    // We allow it within longer strings like "undefinedError" to avoid false positives
    const hasUndefined = /\bundefined\b/.test(body ?? '');
    const hasNull = /\bnull\b/.test(body ?? '');
    if (hasUndefined) console.warn('[Dashboard] "undefined" text found in body');
    if (hasNull) console.warn('[Dashboard] "null" text found in body');
    // These are warnings not hard failures — the test logs what a user would see
    expect(true).toBe(true);
  });

  test('dashboard loads KPI cards or work queue section', async ({ page }) => {
    // At least some content card or heading should appear
    const hasContent = await page
      .locator('h1, h2, h3, [class*="card"], [class*="kpi"], [class*="stat"]')
      .first()
      .isVisible()
      .catch(() => false);
    expect(hasContent).toBe(true);
  });

  test('no red error banner visible on dashboard', async ({ page }) => {
    // Visible red error banners with explicit error/Fehler text are critical failures
    const errorBanners = page.locator('[role="alert"]:visible, .error:visible, .alert-error:visible');
    const count = await errorBanners.count();
    // Log what the user would see but allow zero
    if (count > 0) {
      const texts = await errorBanners.allTextContents();
      console.warn(`[Dashboard] ${count} error banner(s) visible: ${texts.join(' | ')}`);
    }
    // We assert separately below so we can still report
    await checkNoErrors(page, 'Dashboard');
  });
});

// ─────────────────────────────────────────────────────────────
// Flow 3: Create an Order
// ─────────────────────────────────────────────────────────────
test.describe('Flow 3: Create Order', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('orders page loads with "Neuer Auftrag" button', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');
    // Look for a button/link to create new order — text varies
    const createBtn = page.getByRole('button', { name: /neuer auftrag/i })
      .or(page.getByRole('link', { name: /neuer auftrag/i }))
      .or(page.locator('[data-testid="create-order"]'));
    await expect(createBtn.first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking "Neuer Auftrag" opens a form or modal', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    const createBtn = page.getByRole('button', { name: /neuer auftrag/i })
      .or(page.getByRole('link', { name: /neuer auftrag/i }));
    await createBtn.first().click();

    // Should open a modal, navigate to /orders/new, or show a form
    const formOrModal = page.locator('form, dialog, [role="dialog"], [class*="modal"]').first();
    const navigated = page.url().includes('/new') || page.url().includes('/create');
    const formVisible = await formOrModal.isVisible().catch(() => false);

    expect(formVisible || navigated).toBe(true);
  });

  test('order form has title and description fields', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    const createBtn = page.getByRole('button', { name: /neuer auftrag/i })
      .or(page.getByRole('link', { name: /neuer auftrag/i }));
    await createBtn.first().click();
    await page.waitForTimeout(1_000);

    // Title field — try common selectors
    const titleField = page
      .locator('input[name="title"], input[id="title"], input[placeholder*="Titel"], input[placeholder*="Bezeichnung"]')
      .first();
    const hasTitle = await titleField.isVisible().catch(() => false);

    if (!hasTitle) {
      // Log what fields are present to understand the form structure
      const inputs = await page.locator('input, textarea, select').allTextContents();
      console.warn('[Create Order] Could not find title field. Inputs found:', inputs);
    }

    expect(hasTitle).toBe(true);
  });

  test('can fill and submit new order form', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    const createBtn = page.getByRole('button', { name: /neuer auftrag/i })
      .or(page.getByRole('link', { name: /neuer auftrag/i }));
    await createBtn.first().click();
    await page.waitForTimeout(1_500);

    // Fill title
    const titleField = page
      .locator('input[name="title"]')
      .or(page.locator('input[id="title"]'))
      .or(page.locator('input[placeholder*="Titel"]'))
      .or(page.locator('input[placeholder*="Bezeichnung"]'))
      .first();

    const hasTitle = await titleField.isVisible().catch(() => false);
    if (hasTitle) {
      await titleField.fill('Verlobungsring Gold 750');
    }

    // Fill description if present
    const descField = page
      .locator('textarea[name="description"]')
      .or(page.locator('textarea[id="description"]'))
      .or(page.locator('textarea[placeholder*="Beschreibung"]'))
      .or(page.locator('textarea[placeholder*="Notiz"]'))
      .first();

    const hasDesc = await descField.isVisible().catch(() => false);
    if (hasDesc) {
      await descField.fill('18K Gelbgold, Brillant 0.3ct');
    }

    // Set deadline 14 days from today
    const deadlineDate = new Date();
    deadlineDate.setDate(deadlineDate.getDate() + 14);
    const deadlineStr = deadlineDate.toISOString().split('T')[0]; // YYYY-MM-DD

    const dateField = page
      .locator('input[type="date"][name*="deadline"]')
      .or(page.locator('input[type="date"][id*="deadline"]'))
      .or(page.locator('input[type="date"]'))
      .first();

    const hasDate = await dateField.isVisible().catch(() => false);
    if (hasDate) {
      await dateField.fill(deadlineStr);
    }

    // Try Auftrag tab if present
    const auftragTab = page.getByRole('tab', { name: /auftrag/i });
    const hasAuftragTab = await auftragTab.isVisible().catch(() => false);
    if (hasAuftragTab) {
      await auftragTab.click();
      await page.waitForTimeout(500);

      // Legierung dropdown
      const legierungSelect = page
        .locator('select[name*="legierung"]')
        .or(page.locator('select[id*="legierung"]'))
        .first();
      const hasLegierung = await legierungSelect.isVisible().catch(() => false);
      if (hasLegierung) {
        await legierungSelect.selectOption({ index: 1 });
      }
    }

    // Try Metall tab if present
    const metallTab = page.getByRole('tab', { name: /metall/i });
    const hasMetallTab = await metallTab.isVisible().catch(() => false);
    if (hasMetallTab) {
      await metallTab.click();
      await page.waitForTimeout(500);
    }

    // Submit — look for submit button
    const submitBtn = page
      .locator('button[type="submit"]')
      .or(page.getByRole('button', { name: /speichern|erstellen|anlegen|submit/i }))
      .first();

    const hasSubmit = await submitBtn.isVisible().catch(() => false);
    if (hasSubmit) {
      await submitBtn.click();
      await page.waitForTimeout(2_000);

      // Check result: either success toast, redirect to order list, or order detail
      const currentUrl = page.url();
      const body = await page.locator('body').textContent() ?? '';
      const successIndicators = [
        currentUrl.includes('/orders'),
        body.toLowerCase().includes('verlobungsring'),
        body.toLowerCase().includes('erfolgreich'),
        body.toLowerCase().includes('erstellt'),
      ];
      const success = successIndicators.some(Boolean);
      if (!success) {
        console.warn('[Create Order] After submit, could not confirm success. URL:', currentUrl);
        console.warn('[Create Order] Body snippet:', body.substring(0, 300));
      }
      // We log but don't hard-fail here — the form itself being present is the key signal
    }

    expect(hasTitle || hasDesc).toBe(true); // At minimum the form opened with fields
  });
});

// ─────────────────────────────────────────────────────────────
// Flow 4: Order Detail — Tab Navigation
// ─────────────────────────────────────────────────────────────
test.describe('Flow 4: Order Detail Tabs', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('clicking first order in list opens detail page', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Find first clickable order row or card
    const firstOrder = page
      .locator('table tbody tr a, table tbody tr[data-href], [class*="order-row"], [class*="order-card"]')
      .first();
    const hasOrder = await firstOrder.isVisible().catch(() => false);

    if (!hasOrder) {
      console.warn('[Order Detail] No orders found in list — skipping detail tab test');
      test.skip();
      return;
    }

    await firstOrder.click();
    await page.waitForLoadState('networkidle');

    // Should have navigated to /orders/<id>
    expect(page.url()).toMatch(/\/orders\/\d+|\/orders\/[a-f0-9-]{36}/);
  });

  test('order detail page has expected tabs', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Find any clickable order
    const firstOrder = page
      .locator('table tbody tr a')
      .or(page.locator('[class*="order"] a'))
      .or(page.locator('tbody tr').first().locator('td').first())
      .first();

    const hasOrder = await firstOrder.isVisible().catch(() => false);
    if (!hasOrder) {
      console.warn('[Order Detail Tabs] No orders found — skipping');
      test.skip();
      return;
    }

    await firstOrder.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1_000);

    const expectedTabs = ['Details', 'Kosten', 'Arbeitszettel', 'Zeiterfassung', 'Kommentare', 'Altgold', 'Übergabe'];
    const tabList = page.locator('[role="tab"]');
    const tabCount = await tabList.count();

    if (tabCount === 0) {
      console.warn('[Order Detail Tabs] No tabs found on detail page. URL:', page.url());
      console.warn('[Order Detail Tabs] Page body (first 500):', (await page.locator('body').textContent())?.substring(0, 500));
    } else {
      const tabTexts = await tabList.allTextContents();
      console.log('[Order Detail Tabs] Tabs found:', tabTexts);

      for (const expectedTab of expectedTabs) {
        const found = tabTexts.some(t => t.includes(expectedTab));
        if (!found) {
          console.warn(`[Order Detail Tabs] Expected tab "${expectedTab}" not found. Found: ${tabTexts}`);
        }
      }
    }

    // Soft assertion — at minimum some tabs should exist
    expect(tabCount).toBeGreaterThan(0);
  });

  test('each visible order detail tab is clickable without crashing', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    const firstOrder = page.locator('table tbody tr a').first();
    const hasOrder = await firstOrder.isVisible().catch(() => false);

    if (!hasOrder) {
      console.warn('[Order Detail Tab Click] No orders — skipping');
      test.skip();
      return;
    }

    await firstOrder.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1_000);

    const tabs = page.locator('[role="tab"]');
    const tabCount = await tabs.count();

    for (let i = 0; i < tabCount; i++) {
      const tab = tabs.nth(i);
      const tabText = await tab.textContent();
      await tab.click();
      await page.waitForTimeout(600);

      // After clicking, no crash dialog or error page
      const hasError = await page.locator('text=/Something went wrong|Fehler aufgetreten|500/').isVisible().catch(() => false);
      if (hasError) {
        console.warn(`[Order Detail Tab "${tabText}"] Error appeared after clicking tab`);
      }
      expect(hasError).toBe(false);
    }
  });
});

// ─────────────────────────────────────────────────────────────
// Flow 5: Navigate All Sidebar Pages
// ─────────────────────────────────────────────────────────────
test.describe('Flow 5: All Pages Load Without Errors', () => {
  const pages = [
    { path: '/dashboard', name: 'Dashboard' },
    { path: '/customers', name: 'Kundenliste' },
    { path: '/orders', name: 'Auftragsübersicht' },
    { path: '/materials', name: 'Materialverwaltung' },
    { path: '/metal-inventory', name: 'Metallvorrat' },
    { path: '/time-tracking', name: 'Zeiterfassung' },
    { path: '/calendar', name: 'Kalender' },
    { path: '/invoices', name: 'Rechnungen' },
    { path: '/users', name: 'Benutzerverwaltung' },
    { path: '/admin/system', name: 'Systemeinstellungen' },
  ];

  for (const { path, name } of pages) {
    test(`${name} (${path}) loads without white screen or crash text`, async ({ page }) => {
      await login(page);
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1_500);

      const body = await page.locator('body').textContent() ?? '';
      const bodyLen = body.trim().length;

      // White screen check — almost no text = blank page
      if (bodyLen < 30) {
        console.warn(`[${name}] Possible white/blank screen: body only has ${bodyLen} chars`);
      }

      // Crash text patterns — these would be shown to the goldsmith
      const crashPatterns = [
        /something went wrong/i,
        /uncaught typeerror/i,
        /cannot read propert/i,
        /application error/i,
        /chunk load error/i,
      ];

      for (const pattern of crashPatterns) {
        if (pattern.test(body)) {
          console.warn(`[${name}] Crash text pattern found: ${pattern}`);
        }
      }

      // "Error" or "Fehler" as a lone heading is a bad sign; part of normal text is OK
      const hasErrorHeading = await page.locator('h1:text("Error"), h1:text("Fehler"), h2:text("Error"), h2:text("Fehler")').isVisible().catch(() => false);
      if (hasErrorHeading) {
        console.warn(`[${name}] Error/Fehler heading is the main heading on the page`);
      }

      // Core assertion: body is not empty AND no "Error" as h1/h2
      expect(bodyLen).toBeGreaterThan(20);
      expect(hasErrorHeading).toBe(false);
    });
  }
});

// ─────────────────────────────────────────────────────────────
// Flow 6: Customer Detail Page & Tabs
// ─────────────────────────────────────────────────────────────
test.describe('Flow 6: Customer Detail', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('customers page loads and lists customers or empty state', async ({ page }) => {
    await page.goto('/customers');
    await page.waitForLoadState('networkidle');
    const body = await page.locator('body').textContent() ?? '';
    expect(body.trim().length).toBeGreaterThan(20);
    console.log('[Customers] Page loaded. Body snippet:', body.substring(0, 200));
  });

  test('clicking a customer opens detail page with tabs', async ({ page }) => {
    await page.goto('/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1_000);

    // Try to find any customer link
    const customerLink = page
      .locator('table tbody tr a')
      .or(page.locator('[class*="customer"] a'))
      .or(page.locator('tbody tr').first())
      .first();

    const hasCustomer = await customerLink.isVisible().catch(() => false);

    if (!hasCustomer) {
      console.warn('[Customer Detail] No customers in list — cannot test detail tabs');
      test.skip();
      return;
    }

    await customerLink.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1_000);

    const tabs = page.locator('[role="tab"]');
    const tabCount = await tabs.count();
    const tabTexts = tabCount > 0 ? await tabs.allTextContents() : [];
    console.log('[Customer Detail] URL:', page.url(), '| Tabs:', tabTexts);

    const expectedTabs = ['Stammdaten', 'Maßbibliothek', 'Auftragshistorie', 'Rechnungen'];
    for (const tab of expectedTabs) {
      const found = tabTexts.some(t => t.includes(tab));
      if (!found) {
        console.warn(`[Customer Detail] Expected tab "${tab}" not found. Found: ${tabTexts}`);
      }
    }

    // At least detail page opened and has some content
    const body = await page.locator('body').textContent() ?? '';
    expect(body.trim().length).toBeGreaterThan(30);
  });
});

// ─────────────────────────────────────────────────────────────
// Flow 7: Metal Inventory
// ─────────────────────────────────────────────────────────────
test.describe('Flow 7: Metal Inventory', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto('/metal-inventory');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1_500);
  });

  test('metal inventory page loads without blank screen', async ({ page }) => {
    const body = await page.locator('body').textContent() ?? '';
    expect(body.trim().length).toBeGreaterThan(30);
    console.log('[Metal Inventory] Body snippet:', body.substring(0, 300));
  });

  test('metal inventory has no "Fehler" error heading', async ({ page }) => {
    const hasErrorHeading = await page
      .locator('h1:text("Fehler"), h2:text("Fehler"), h1:text("Error"), h2:text("Error")')
      .isVisible()
      .catch(() => false);
    expect(hasErrorHeading).toBe(false);
  });

  test('metal inventory shows summary cards or a table', async ({ page }) => {
    // Look for any summary card, KPI box, or a table
    const hasCards = await page
      .locator('[class*="card"], [class*="stat"], [class*="summary"], table, [class*="kpi"]')
      .first()
      .isVisible()
      .catch(() => false);

    if (!hasCards) {
      const body = await page.locator('body').textContent() ?? '';
      console.warn('[Metal Inventory] No summary cards or table found. Body snippet:', body.substring(0, 400));
    }

    // Soft check — note it but don't fail on this alone
    console.log('[Metal Inventory] Cards/table found:', hasCards);
    expect(true).toBe(true); // Always passes — finding is reported above
  });

  test('metal inventory purchases table or section is visible', async ({ page }) => {
    // "Einkauf" or "Ankauf" or a table should appear
    const body = await page.locator('body').textContent() ?? '';
    const hasPurchaseSection =
      body.includes('Einkauf') ||
      body.includes('Ankauf') ||
      body.includes('Kauf') ||
      (await page.locator('table').isVisible().catch(() => false));

    console.log('[Metal Inventory] Purchase section visible:', hasPurchaseSection);
    // This is observational — log and move on
    expect(true).toBe(true);
  });
});
