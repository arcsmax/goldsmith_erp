// Main App Component with Routing
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, OrderProvider, ScannerProvider, TimeTrackingProvider, ToastProvider } from './contexts';
import { WebSocketProvider } from './contexts/WebSocketProvider';
import { AppQueryProvider } from './lib/queryProvider';
import { RealtimeInvalidation } from './lib/realtimeInvalidation';
import { ProtectedRoute } from './components/ProtectedRoute';
import { MainLayout } from './layouts/MainLayout';
import { ToastContainer } from './components/Toast';
import { ConfirmDialog } from './components/ConfirmDialog';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useTheme } from './hooks/useTheme';

// Lazy load pages for code splitting and better performance
// Note: Pages use named exports, so we need to destructure them
const LoginPage = lazy(() => import('./pages/LoginPage').then(m => ({ default: m.LoginPage })));
// Public self-registration route removed (fix A3, 2026-04-23).
// /users/register is now ADMIN-invitation-only; new users are created
// via the admin UsersPage. The dormant RegisterPage.tsx + authApi.register
// remain on disk for possible reuse by a future admin-invitation UI.
const DashboardPage = lazy(() => import('./pages/DashboardPage').then(m => ({ default: m.DashboardPage })));
const CustomersPage = lazy(() => import('./pages/CustomersPage').then(m => ({ default: m.CustomersPage })));
const MaterialsPage = lazy(() => import('./pages/MaterialsPage').then(m => ({ default: m.MaterialsPage })));
const MetalInventoryPage = lazy(() => import('./pages/MetalInventoryPage').then(m => ({ default: m.MetalInventoryPage })));
const OrdersPage = lazy(() => import('./pages/OrdersPage').then(m => ({ default: m.OrdersPage })));
const OrderDetailPage = lazy(() => import('./pages/OrderDetailPage').then(m => ({ default: m.OrderDetailPage })));
const TimeTrackingPage = lazy(() => import('./pages/TimeTrackingPage').then(m => ({ default: m.TimeTrackingPage })));
const UsersPage = lazy(() => import('./pages/UsersPage').then(m => ({ default: m.UsersPage })));
const ScannerPage = lazy(() => import('./pages/ScannerPage').then(m => ({ default: m.ScannerPage })));
const CalendarPage = lazy(() => import('./pages/CalendarPage').then(m => ({ default: m.CalendarPage })));
const InvoicesPage = lazy(() => import('./pages/InvoicesPage').then(m => ({ default: m.InvoicesPage })));
const QuotesPage = lazy(() => import('./pages/QuotesPage').then(m => ({ default: m.QuotesPage })));
const AdminSystemPage = lazy(() => import('./pages/AdminSystemPage').then(m => ({ default: m.AdminSystemPage })));
const ScanAdoptionDashboard = lazy(() => import('./pages/admin/ScanAdoptionDashboard').then(m => ({ default: m.ScanAdoptionDashboard })));
const CustomerDetailPage = lazy(() => import('./pages/CustomerDetailPage').then(m => ({ default: m.CustomerDetailPage })));
const RepairsPage = lazy(() => import('./pages/RepairsPage').then(m => ({ default: m.RepairsPage })));
const RepairDetailPage = lazy(() => import('./pages/RepairDetailPage').then(m => ({ default: m.RepairDetailPage })));
const WorkshopBoardPage = lazy(() => import('./pages/WorkshopBoardPage').then(m => ({ default: m.WorkshopBoardPage })));
const CustomerPortalPage = lazy(() => import('./pages/CustomerPortalPage').then(m => ({ default: m.CustomerPortalPage })));
const UserSettingsPage = lazy(() => import('./pages/UserSettingsPage').then(m => ({ default: m.UserSettingsPage })));
const ConsultationWizardPage = lazy(() =>
  import('./pages/ConsultationWizardPage').then((m) => ({ default: m.ConsultationWizardPage }))
);
const ConsultationsPage = lazy(() =>
  import('./pages/ConsultationsPage').then((m) => ({ default: m.ConsultationsPage }))
);
// W4-02: /dev/ui primitives gallery, development builds only. The ternary on
// import.meta.env.DEV lets Vite drop the chunk from production builds.
const UiDemoPage = import.meta.env.DEV
  ? lazy(() => import('./pages/dev/UiDemoPage').then((m) => ({ default: m.UiDemoPage })))
  : null;

// Loading fallback component
const PageLoader: React.FC = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '60vh',
    fontSize: '1.2rem',
    color: '#666'
  }}>
    <div>Laden...</div>
  </div>
);

/**
 * Staff shell — everything that needs a session. AuthProvider wraps both
 * /login and the protected tree (LoginPage and ProtectedRoute's session
 * probe both need useAuth; that probe's 401s are expected and stay silent).
 * The rest of the per-user providers (Query, WebSocket, Scanner, TimeTracking,
 * Order) mount ONLY inside ProtectedRoute, wrapping MainLayout — never for
 * /login or /portal (LV-21). That keeps /users/me + /refresh as the only
 * requests an unauthenticated visitor ever triggers; the WS connect and the
 * timer/activity loaders wait for a real session.
 */
const StaffApp: React.FC = () => (
  <AuthProvider>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* /register route removed (fix A3, 2026-04-23).
          Public self-registration is no longer supported; admins
          create users via the authenticated /users page. Any
          hard-coded /register link now falls through to the
          catch-all → /dashboard → /login (unauthenticated). */}

      {/* Protected Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            {/* W3-03: one QueryClient per session; unmounting on logout drops the cache. */}
            <AppQueryProvider>
              {/* W2-13: the one live-update socket; authenticated shell only, never /login or /portal. */}
              <WebSocketProvider>
                <RealtimeInvalidation />
                <ScannerProvider>
                  <TimeTrackingProvider>
                    <OrderProvider>
                      <MainLayout />
                    </OrderProvider>
                  </TimeTrackingProvider>
                </ScannerProvider>
              </WebSocketProvider>
            </AppQueryProvider>
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />

        {/* Kunden — any authenticated role. VIEWER holds CUSTOMER_VIEW
            (core/permissions.py) and gets a role-projected read (no design
            IP — CustomerDetailPage's own canViewDesign gate handles that);
            the route no longer redirects VIEWER away before it can load. */}
        <Route
          path="customers"
          element={
            <ProtectedRoute>
              <CustomersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="customers/:id"
          element={
            <ProtectedRoute>
              <CustomerDetailPage />
            </ProtectedRoute>
          }
        />

        {/* Beratung — ADMIN und GOLDSMITH */}
        <Route
          path="consultations"
          element={
            <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
              <ConsultationsPage />
            </ProtectedRoute>
          }
        />
        {/* Static "new" segment must be registered alongside the
            dynamic ":id" segment below — react-router v7 ranks
            static path segments above dynamic ones during
            matching regardless of array order, so /consultations/new
            always resolves here and never against :id. Pinned by
            pages/ConsultationsRoutes.test.tsx. */}
        <Route
          path="consultations/new"
          element={
            <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
              <ConsultationWizardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="consultations/:id"
          element={
            <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
              <ConsultationWizardPage />
            </ProtectedRoute>
          }
        />

        {/* Materialien — any authenticated role. VIEWER holds
            MATERIAL_VIEW; MaterialsPage's own canViewFinancials gate hides
            unit prices and stock value (SEC-01). */}
        <Route
          path="materials"
          element={
            <ProtectedRoute>
              <MaterialsPage />
            </ProtectedRoute>
          }
        />

        {/* Metallinventar — any authenticated role. VIEWER holds
            MATERIAL_VIEW for the list itself, but every metal-inventory
            endpoint this page calls is FINANCIAL_VIEW-gated, so
            MetalInventoryPage's own guard shows an empty state for VIEWER
            instead of 403ing on load. */}
        <Route
          path="metal-inventory"
          element={
            <ProtectedRoute>
              <MetalInventoryPage />
            </ProtectedRoute>
          }
        />

        <Route path="orders" element={<OrdersPage />} />
        <Route path="orders/:orderId" element={<OrderDetailPage />} />

        {/* Reparaturen — any authenticated role. VIEWER holds REPAIR_VIEW
            (e.g. front desk); RepairsPage's own canViewFinancials gate
            hides pricing. */}
        <Route
          path="repairs"
          element={
            <ProtectedRoute>
              <RepairsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="repairs/:id"
          element={
            <ProtectedRoute>
              <RepairDetailPage />
            </ProtectedRoute>
          }
        />

        {/* Werkstatt-Board über Aufträge und Reparaturen (W6, jobs spine) */}
        <Route path="werkstatt" element={<WorkshopBoardPage />} />
        <Route path="time-tracking" element={<TimeTrackingPage />} />

        {/* Benutzerverwaltung — nur ADMIN */}
        <Route
          path="users"
          element={
            <ProtectedRoute requiredRoles={['ADMIN']}>
              <UsersPage />
            </ProtectedRoute>
          }
        />

        <Route path="scanner" element={<ScannerPage />} />
        <Route path="settings" element={<UserSettingsPage />} />
        <Route path="calendar" element={<CalendarPage />} />

        {/* Rechnungen — ADMIN und GOLDSMITH */}
        <Route
          path="invoices"
          element={
            <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
              <InvoicesPage />
            </ProtectedRoute>
          }
        />

        {/* Angebote (Kostenvoranschlag) — ADMIN und GOLDSMITH */}
        <Route
          path="quotes"
          element={
            <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
              <QuotesPage />
            </ProtectedRoute>
          }
        />

        {/* Systemübersicht — nur ADMIN */}
        <Route
          path="admin/system"
          element={
            <ProtectedRoute requiredRoles={['ADMIN']}>
              <AdminSystemPage />
            </ProtectedRoute>
          }
        />

        {/* V1.1 Scan-Adoption Dashboard — nur ADMIN (Slice 13) */}
        <Route
          path="admin/scan-gate"
          element={
            <ProtectedRoute requiredRoles={['ADMIN']}>
              <ScanAdoptionDashboard />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Catch all - redirect to dashboard */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  </AuthProvider>
);

/**
 * Top-level route split: public customer routes first (no auth providers),
 * everything else falls through to the staff shell. Exported for routing
 * tests (App.portal.test.tsx) so they can use a MemoryRouter.
 */
export const AppRoutes: React.FC = () => (
  <ErrorBoundary variant="app">
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* Customer self-service portal — public, no login, no auth providers (FE-01) */}
        <Route path="/portal" element={<CustomerPortalPage />} />
        {UiDemoPage && <Route path="/dev/ui" element={<UiDemoPage />} />}
        <Route path="*" element={<StaffApp />} />
      </Routes>
    </Suspense>
  </ErrorBoundary>
);

const App: React.FC = () => {
  // Apply admin-configurable theme settings as CSS variables on first paint
  useTheme();

  return (
    <BrowserRouter>
      <ToastProvider>
        <AppRoutes />
        {/* Toast notifications and confirm dialogs rendered above all app content */}
        <ToastContainer />
        <ConfirmDialog />
      </ToastProvider>
    </BrowserRouter>
  );
};

export default App;
