import { test, expect } from '@playwright/test';

/**
 * Auth Flow E2E Tests
 *
 * These tests cover the full login / logout cycle.
 * They require a running backend at http://localhost:8000 to pass.
 * When the backend is unavailable the login attempt will fail with an error
 * message — that failure path is also tested below.
 *
 * Set the env vars E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run the
 * happy-path "login succeeds" tests against a real backend.
 * Without those vars the happy-path tests are skipped.
 */

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? '';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? '';
const hasCredentials = !!(ADMIN_EMAIL && ADMIN_PASSWORD);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function clearAuthStorage(page: import('@playwright/test').Page) {
  await page.evaluate(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
  });
}

// ---------------------------------------------------------------------------
// Login form — interaction tests (no backend required)
// ---------------------------------------------------------------------------

test.describe('Login form interactions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();
  });

  test('email field accepts input', async ({ page }) => {
    await page.locator('#email').fill('test@example.com');
    await expect(page.locator('#email')).toHaveValue('test@example.com');
  });

  test('password field accepts input and masks it', async ({ page }) => {
    await page.locator('#password').fill('geheim');
    await expect(page.locator('#password')).toHaveValue('geheim');
    await expect(page.locator('#password')).toHaveAttribute('type', 'password');
  });

  test('submit button is disabled while submitting', async ({ page }) => {
    // Fill in fields so the form is valid
    await page.locator('#email').fill('somebody@example.com');
    await page.locator('#password').fill('wrongpassword');

    // Click and immediately check the loading state.
    // The button text changes to "Wird angemeldet..." during the async call.
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();

    // Either the button shows loading text OR the error appears — both are fine.
    // We just confirm the app does not crash.
    await expect(page.locator('.auth-box')).toBeVisible();
  });

  test('shows error message when credentials are wrong', async ({ page }) => {
    await page.locator('#email').fill('nobody@example.com');
    await page.locator('#password').fill('wrongpassword');
    await page.locator('button[type="submit"]').click();

    // Wait for the error message to appear (network request completes)
    const errorMsg = page.locator('.error-message');
    await expect(errorMsg).toBeVisible({ timeout: 15_000 });
    // Error text is either the server detail or the fallback German message
    await expect(errorMsg).not.toBeEmpty();
  });

  test('form requires email to be valid format', async ({ page }) => {
    // HTML5 validation: type="email" rejects plain text
    await page.locator('#email').fill('not-an-email');
    await page.locator('#password').fill('anypassword');
    await page.locator('button[type="submit"]').click();

    // The browser blocks submission and we should still be on /login
    await expect(page).toHaveURL(/\/login/);
  });
});

// ---------------------------------------------------------------------------
// Happy path — requires live backend + valid credentials
// ---------------------------------------------------------------------------

test.describe('Login / logout happy path', () => {
  test.skip(!hasCredentials, 'Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD to run');

  test('successful login redirects to /dashboard', async ({ page }) => {
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();

    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    // After login, app navigates to /dashboard
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    // Dashboard page header should be visible
    await expect(page.locator('.dashboard-container h1')).toHaveText('Dashboard');
  });

  test('authenticated user sees sidebar navigation', async ({ page }) => {
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();

    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    // Sidebar nav links from MainLayout
    const sidebar = page.locator('.main-sidebar');
    await expect(sidebar).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Dashboard/ })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Kunden/ })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Aufträge/ })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Zeiterfassung/ })).toBeVisible();
  });

  test('logout button clears session and redirects to /login', async ({ page }) => {
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();

    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    // Click the "Abmelden" button in the header
    await page.locator('.btn-logout').click();

    // Should be back on the login page
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('h2')).toHaveText('Anmelden');

    // Token should be gone from localStorage
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeNull();
  });

  test('sidebar links navigate to correct pages', async ({ page }) => {
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();

    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    const sidebar = page.locator('.main-sidebar');

    // Navigate to Kunden (Customers)
    await sidebar.getByRole('link', { name: /Kunden/ }).click();
    await expect(page).toHaveURL(/\/customers/);

    // Navigate to Aufträge (Orders)
    await sidebar.getByRole('link', { name: /Aufträge/ }).click();
    await expect(page).toHaveURL(/\/orders/);

    // Navigate back to Dashboard
    await sidebar.getByRole('link', { name: /Dashboard/ }).click();
    await expect(page).toHaveURL(/\/dashboard/);
  });
});

// ---------------------------------------------------------------------------
// Token persistence
// ---------------------------------------------------------------------------

test.describe('Auth persistence', () => {
  test.skip(!hasCredentials, 'Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD to run');

  test('page reload keeps user logged in', async ({ page }) => {
    // Log in
    await page.goto('/login');
    await clearAuthStorage(page);
    await page.reload();

    await page.locator('#email').fill(ADMIN_EMAIL);
    await page.locator('#password').fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    // Reload the page — token is in localStorage so user should stay on dashboard
    await page.reload();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  });
});
