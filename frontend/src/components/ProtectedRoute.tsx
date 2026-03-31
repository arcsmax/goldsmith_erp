// Protected Route Component - Requires authentication and optional role check
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts';
import { UserRole } from '../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** When provided, the user must hold at least one of these roles. */
  requiredRoles?: UserRole[];
}

/**
 * ProtectedRoute Component
 * Wraps routes that require authentication.
 * When requiredRoles is provided, also checks that the current user
 * holds at least one of those roles. Unauthorized users are redirected
 * to /dashboard rather than logged out.
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredRoles,
}) => {
  const { isAuthenticated, isLoading, hasRole } = useAuth();

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh'
      }}>
        <p>Laden...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRoles && requiredRoles.length > 0 && !hasRole(requiredRoles)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};
