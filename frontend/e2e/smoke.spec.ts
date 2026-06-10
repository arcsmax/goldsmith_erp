import { test, expect } from '@playwright/test';

/**
 * Smoke Tests — verify the app loads and key structural elements are present.
 * These run without any backend; they only confirm the React shell renders.
 */

test.describe('App loads', () => {
  test('page has correct title', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveTitle('Goldsmith ERP');
  });

  test('root element renders', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#root')).toBeVisible();
  });
});

test.describe('Login page structure', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('shows Goldsmith ERP heading', async ({ page }) => {
    await expect(page.locator('h1')).toHaveText('Goldsmith ERP');
  });

  test('shows Anmelden sub-heading', async ({ page }) => {
    await expect(page.locator('h2')).toHaveText('Anmelden');
  });

  test('email input is present', async ({ page }) => {
    await expect(page.locator('#email')).toBeVisible();
    await expect(page.locator('label[for="email"]')).toContainText('E-Mail');
  });

  test('password input is present', async ({ page }) => {
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('label[for="password"]')).toContainText('Passwort');
  });

  test('submit button is present', async ({ page }) => {
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toHaveText('Anmelden');
  });
});

// Public /register route + page link were removed in fix A3 (2026-04-23) when
// self-registration became ADMIN-invitation-only via the authenticated /users
// page. The smoke specs for that flow (link presence, /register page
// structure, login↔register navigation) were not removed at the time and
// surfaced as 6 e2e failures the first time the e2e job actually ran (after
// PR #6's lint-decouple). Dropped here. RegisterPage.tsx + authApi.register
// stay on disk for the future admin-invitation UI, per App.tsx's note.

test.describe('Protected routes', () => {
  test('unauthenticated visit to / redirects to /login', async ({ page }) => {
    // Clear any lingering auth state
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    });

    await page.goto('/');
    // ProtectedRoute redirects unauthenticated users to /login
    await expect(page).toHaveURL(/\/login/);
  });

  test('unauthenticated visit to /dashboard redirects to /login', async ({ page }) => {
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
    });

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });
});
