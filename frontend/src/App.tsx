/**
 * Main App Component with Routing
 */
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import MaterialList from './pages/materials/MaterialList';
import MaterialForm from './pages/materials/MaterialForm';
import MaterialDetail from './pages/materials/MaterialDetail';
import CustomerList from './pages/customers/CustomerList';
import CustomerDetail from './pages/customers/CustomerDetail';

// Components
import ProtectedRoute from './components/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';

// Placeholder pages (will be implemented later)
const OrdersPage = () => <div style={{ padding: '20px' }}><h1>Aufträge</h1><p>Coming soon...</p></div>;
const CustomerFormPage = () => <div style={{ padding: '20px' }}><h1>Kunden-Formular</h1><p>Coming soon...</p></div>;
const CustomerConsentPage = () => <div style={{ padding: '20px' }}><h1>Einwilligungen verwalten</h1><p>Coming soon...</p></div>;

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

          {/* Material Management Routes */}
          <Route path="materials" element={<MaterialList />} />
          <Route path="materials/new" element={<MaterialForm />} />
          <Route path="materials/:id" element={<MaterialDetail />} />
          <Route path="materials/:id/edit" element={<MaterialForm />} />

          {/* Customer Management Routes */}
          <Route path="customers" element={<CustomerList />} />
          <Route path="customers/new" element={<CustomerFormPage />} />
          <Route path="customers/:id" element={<CustomerDetail />} />
          <Route path="customers/:id/edit" element={<CustomerFormPage />} />
          <Route path="customers/:id/consent" element={<CustomerConsentPage />} />
        </Route>

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;