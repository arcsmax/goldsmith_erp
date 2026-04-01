import { test, expect, Page } from '@playwright/test';

const BASE = 'http://localhost:3000';
const EMAIL = 'admin@goldschmiede.de';
const PASSWORD = 'Admin123!';

// Use a SINGLE test with sequential steps to avoid rate limiting on login (5/min)
test('Full goldsmith workflow — single session', async ({ page }) => {
  // ============ LOGIN ============
  await page.goto(BASE);
  await expect(page.locator('h1')).toContainText('Goldsmith ERP');
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  console.log('✅ Login successful');

  // ============ DASHBOARD ============
  await page.waitForTimeout(3000);
  const dashText = await page.textContent('body');
  expect(dashText!.length).toBeGreaterThan(50);
  console.log(`✅ Dashboard loaded (${dashText!.length} chars)`);

  // Check sidebar has links
  const navLinks = await page.locator('.nav-link').count();
  expect(navLinks).toBeGreaterThanOrEqual(4);
  console.log(`✅ Sidebar has ${navLinks} nav links`);

  // ============ NAVIGATE ALL PAGES ============
  const pages = [
    '/orders',
    '/customers',
    '/materials',
    '/metal-inventory',
    '/time-tracking',
    '/calendar',
    '/invoices',
    '/users',
    '/admin/system',
  ];

  for (const path of pages) {
    await page.goto(`${BASE}${path}`);
    await page.waitForTimeout(2000);
    const bodyLen = (await page.textContent('body'))!.length;
    const hasContent = bodyLen > 100;

    // Check for crash indicators
    const pageText = await page.textContent('body') || '';
    const hasCrash = pageText.includes('Cannot read properties') ||
                     pageText.includes('is not a function') ||
                     pageText.includes('Unexpected token');

    if (hasCrash) {
      console.log(`❌ ${path} — CRASHED: JS error visible on page`);
    } else if (!hasContent) {
      console.log(`⚠️ ${path} — blank or very short (${bodyLen} chars)`);
    } else {
      console.log(`✅ ${path} — loaded (${bodyLen} chars)`);
    }
  }

  // ============ ORDERS PAGE ============
  await page.goto(`${BASE}/orders`);
  await page.waitForTimeout(2000);

  // Wait for page content to fully render
  await page.waitForTimeout(3000);
  // Check for "Neuer Auftrag" button
  const newOrderBtn = page.locator('button', { hasText: 'Neuer Auftrag' });
  const hasNewBtn = await newOrderBtn.count() > 0;
  console.log(hasNewBtn ? '✅ "Neuer Auftrag" button found' : '❌ "Neuer Auftrag" button MISSING');

  if (hasNewBtn) {
    await newOrderBtn.click();
    await page.waitForTimeout(1000);

    // Check modal opened
    const modalVisible = await page.locator('.modal-overlay, .modal-content, .modal').count() > 0;
    console.log(modalVisible ? '✅ Order form modal opened' : '❌ Order form modal did NOT open');

    // Close modal if open
    const closeBtn = page.locator('.modal-close, button[aria-label*="schließen"]');
    if (await closeBtn.count() > 0) await closeBtn.first().click();
  }

  // ============ METAL INVENTORY ============
  await page.goto(`${BASE}/metal-inventory`);
  await page.waitForTimeout(3000);

  const metalText = await page.textContent('body') || '';
  const hasFehler = metalText.includes('Fehler');
  console.log(hasFehler ? '⚠️ Metal inventory has "Fehler" text' : '✅ Metal inventory no errors');

  // Check for summary cards or table
  const hasCards = await page.locator('.metal-summary-cards, .summary-card').count() > 0;
  const hasTable = await page.locator('table, .metal-inventory-table').count() > 0;
  console.log(`Metal inventory: cards=${hasCards}, table=${hasTable}`);

  // ============ CUSTOMER DETAIL ============
  await page.goto(`${BASE}/customers`);
  await page.waitForTimeout(2000);

  const customerRows = await page.locator('tbody tr').count();
  console.log(`Customers page: ${customerRows} rows`);

  if (customerRows > 0) {
    await page.locator('tbody tr').first().click();
    await page.waitForTimeout(2000);

    const isDetailPage = page.url().includes('/customers/');
    console.log(isDetailPage ? '✅ Customer detail page loaded' : '⚠️ Customer click did not navigate');

    if (isDetailPage) {
      // Check for tabs
      const tabs = await page.locator('button').filter({ hasText: /Stammdaten|Maßbibliothek|Auftragshistorie|Rechnungen/ }).count();
      console.log(`Customer detail has ${tabs} tab buttons`);
    }
  }

  // ============ CALENDAR ============
  await page.goto(`${BASE}/calendar`);
  await page.waitForTimeout(2000);

  const calendarGrid = await page.locator('.calendar-grid, .calendar-body, table').count();
  console.log(calendarGrid > 0 ? '✅ Calendar grid rendered' : '❌ Calendar grid MISSING');

  // ============ VISIBLE ERRORS CHECK ============
  // Go back to dashboard and check for any visible error banners
  await page.goto(`${BASE}/dashboard`);
  await page.waitForTimeout(3000);

  const errorBanners = await page.locator('.error-message, .error-banner, [class*="error"]').count();
  const fehlerText = (await page.textContent('body') || '').match(/Fehler/g);
  console.log(`Dashboard: ${errorBanners} error elements, ${fehlerText?.length || 0} "Fehler" occurrences`);

  console.log('\n🏁 Full workflow test complete');
});
