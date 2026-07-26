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

// Public self-registration was removed on 2026-04-23 (fix A3): new users are
// created by admins via the authenticated /users page, so the login screen no
// longer renders a "Registrieren" link and there is no /register route. The
// former "link to register page", "Register page structure", and register
// navigation specs were deleted to match that behaviour (issue #8).

test.describe('Navigation from login page', () => {
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
