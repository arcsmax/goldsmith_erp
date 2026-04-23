// Login Page Component
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts';
import { LoginSchema } from '../lib/validation/schemas';
import { useFormValidation } from '../lib/validation/useFormValidation';
import '../styles/auth.css';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const { validate, errors, clearError } = useFormValidation(LoginSchema);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const result = validate({ email, password });
    if (!result.success) {
      return;
    }

    setIsLoading(true);
    try {
      await login(result.data);
      navigate('/dashboard');
    } catch (err: any) {
      setSubmitError(
        err.response?.data?.detail || 'Login fehlgeschlagen. Bitte überprüfen Sie Ihre Eingaben.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-box">
        <h1>Goldsmith ERP</h1>
        <h2>Anmelden</h2>

        {submitError && <div className="error-message">{submitError}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="email">E-Mail</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                clearError('email');
              }}
              className={errors.email ? 'error' : ''}
              autoComplete="email"
              disabled={isLoading}
            />
            {errors.email && <span className="error-message">{errors.email}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="password">Passwort</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearError('password');
              }}
              className={errors.password ? 'error' : ''}
              autoComplete="current-password"
              disabled={isLoading}
            />
            {errors.password && <span className="error-message">{errors.password}</span>}
          </div>

          <button type="submit" disabled={isLoading} className="btn-primary">
            {isLoading ? 'Wird angemeldet...' : 'Anmelden'}
          </button>
        </form>

        {/* Public self-registration link removed (fix A3, 2026-04-23) —
            new accounts are created by an admin in the Benutzerverwaltung
            page. A dedicated "Request access" flow may replace this later. */}
      </div>
    </div>
  );
};
