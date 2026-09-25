// Register page (W4-03): Field + Button primitives, errors via getErrorMessage.
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { Button, Field } from '../ui';
import '../styles/auth.css';

const MIN_PASSWORD_LENGTH = 6;
const REGISTER_FAILED = 'Registrierung fehlgeschlagen. Bitte erneut versuchen.';

export const RegisterPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwörter stimmen nicht überein. Bitte beide Felder gleich ausfüllen.');
      return;
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Passwort ist zu kurz. Bitte mindestens ${MIN_PASSWORD_LENGTH} Zeichen eingeben.`);
      return;
    }

    setIsLoading(true);
    try {
      await register({
        email,
        password,
        first_name: firstName,
        last_name: lastName,
      });
      navigate('/dashboard');
    } catch (err: unknown) {
      setError(getErrorMessage(err, REGISTER_FAILED));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="auth-container">
      <div className="auth-box">
        <h1 className="auth-brand">Goldsmith ERP</h1>
        <h2 className="auth-title">Registrieren</h2>

        {error && (
          <div className="auth-alert" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <Field label="E-Mail" name="email" inputMode="email" required>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={isLoading}
            />
          </Field>

          <div className="auth-form-row">
            <Field label="Vorname" name="firstName">
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name"
                disabled={isLoading}
              />
            </Field>

            <Field label="Nachname" name="lastName">
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
                disabled={isLoading}
              />
            </Field>
          </div>

          <Field
            label="Passwort"
            name="password"
            required
            help={`Mindestens ${MIN_PASSWORD_LENGTH} Zeichen.`}
          >
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              disabled={isLoading}
              minLength={MIN_PASSWORD_LENGTH}
            />
          </Field>

          <Field label="Passwort bestätigen" name="confirmPassword" required>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              disabled={isLoading}
              minLength={MIN_PASSWORD_LENGTH}
            />
          </Field>

          <Button type="submit" block loading={isLoading}>
            {isLoading ? 'Wird registriert…' : 'Registrieren'}
          </Button>
        </form>

        <p className="auth-link">
          Bereits registriert? <Link to="/login">Anmelden</Link>
        </p>
      </div>
    </main>
  );
};
