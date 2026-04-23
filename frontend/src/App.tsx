// Main App Component with Routing
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, OrderProvider, ScannerProvider, TimeTrackingProvider, ToastProvider } from './contexts';
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
const CustomerPortalPage = lazy(() => import('./pages/CustomerPortalPage').then(m => ({ default: m.CustomerPortalPage })));
const UserSettingsPage = lazy(() => import('./pages/UserSettingsPage').then(m => ({ default: m.UserSettingsPage })));

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

const App: React.FC = () => {
  // Apply admin-configurable theme settings as CSS variables on first paint
  useTheme();

  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <ScannerProvider>
            <TimeTrackingProvider>
              <OrderProvider>
                <ErrorBoundary variant="app">
                <Suspense fallback={<PageLoader />}>
                <Routes>
                  {/* Public Routes */}
                  <Route path="/login" element={<LoginPage />} />
                  {/* /register route removed (fix A3, 2026-04-23).
                      Public self-registration is no longer supported; admins
                      create users via the authenticated /users page. Any
                      hard-coded /register link now falls through to the
                      catch-all → /dashboard → /login (unauthenticated). */}
                  {/* Customer self-service portal — no login required */}
                  <Route path="/portal" element={<CustomerPortalPage />} />

                  {/* Protected Routes */}
                  <Route
                    path="/"
                    element={
                      <ProtectedRoute>
                        <MainLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="dashboard" element={<DashboardPage />} />

                    {/* Kunden — ADMIN und GOLDSMITH */}
                    <Route
                      path="customers"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <CustomersPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="customers/:id"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <CustomerDetailPage />
                        </ProtectedRoute>
                      }
                    />

                    {/* Materialien — ADMIN und GOLDSMITH */}
                    <Route
                      path="materials"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <MaterialsPage />
                        </ProtectedRoute>
                      }
                    />

                    {/* Metallinventar — ADMIN und GOLDSMITH */}
                    <Route
                      path="metal-inventory"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <MetalInventoryPage />
                        </ProtectedRoute>
                      }
                    />

                    <Route path="orders" element={<OrdersPage />} />
                    <Route path="orders/:orderId" element={<OrderDetailPage />} />

                    {/* Reparaturen — ADMIN und GOLDSMITH */}
                    <Route
                      path="repairs"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <RepairsPage />
                        </ProtectedRoute>
                      }
                    />
                    <Route
                      path="repairs/:id"
                      element={
                        <ProtectedRoute requiredRoles={['ADMIN', 'GOLDSMITH']}>
                          <RepairDetailPage />
                        </ProtectedRoute>
                      }
                    />

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
                </Suspense>
                </ErrorBoundary>
              </OrderProvider>
            </TimeTrackingProvider>
          </ScannerProvider>
        </AuthProvider>
        {/* Toast notifications and confirm dialogs rendered above all app content */}
        <ToastContainer />
        <ConfirmDialog />
      </ToastProvider>
    </BrowserRouter>
  );
};

export default App;