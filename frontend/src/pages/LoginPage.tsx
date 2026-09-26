// Login page (W4-03): Field + Button primitives, errors via getErrorMessage.
//
// No query client here (FRONTEND_DATA_LAYER: /login has none) and no extra
// session probe: the only request this page makes is the login call itself.
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { LoginSchema } from '../lib/validation/schemas';
import { useFormValidation } from '../lib/validation/useFormValidation';
import { Button, Field } from '../ui';
import '../styles/auth.css';

const LOGIN_FAILED = 'Anmeldung fehlgeschlagen. Bitte E-Mail und Passwort prüfen.';

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
    } catch (err: unknown) {
      setSubmitError(getErrorMessage(err, LOGIN_FAILED));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="auth-container">
      <div className="auth-box">
        <h1 className="auth-brand">Goldsmith ERP</h1>
        <h2 className="auth-title">Anmelden</h2>

        {submitError && (
          <div className="auth-alert" role="alert">
            {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Field label="E-Mail" name="email" inputMode="email" error={errors.email}>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                clearError('email');
              }}
              autoComplete="email"
              disabled={isLoading}
            />
          </Field>

          <Field label="Passwort" name="password" error={errors.password}>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                clearError('password');
              }}
              autoComplete="current-password"
              disabled={isLoading}
            />
          </Field>

          <Button type="submit" block loading={isLoading}>
            {isLoading ? 'Wird angemeldet…' : 'Anmelden'}
          </Button>
        </form>

        {/* Public self-registration link removed (fix A3, 2026-04-23) —
            new accounts are created by an admin in the Benutzerverwaltung
            page. A dedicated "Request access" flow may replace this later. */}
      </div>
    </main>
  );
};
