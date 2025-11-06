/**
 * Main App Component with Routing
 */
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';

// Components
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';

// Placeholder pages (will be implemented later)
const OrdersPage = () => <div style={{ padding: '20px' }}><h1>Aufträge</h1><p>Coming soon...</p></div>;
const MaterialsPage = () => <div style={{ padding: '20px' }}><h1>Material</h1><p>Coming soon...</p></div>;
const CustomersPage = () => <div style={{ padding: '20px' }}><h1>Kunden</h1><p>Coming soon...</p></div>;

function App() {
  const initializeAuth = useAuthStore((state) => state.initializeAuth);

  // Initialize auth on app load
  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />

        {/* Protected Routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="materials" element={<MaterialsPage />} />
          <Route path="customers" element={<CustomersPage />} />
        </Route>

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;