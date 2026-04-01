// User Form Modal Component (Admin only)
import React, { useState, useEffect } from 'react';
import { UserType, UserCreateInput, UserUpdateInput } from '../../types';
import { UserCreateSchema, UserUpdateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';

interface UserFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: UserCreateInput | UserUpdateInput) => Promise<void>;
  user?: UserType | null;
  isLoading?: boolean;
}

export const UserFormModal: React.FC<UserFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  user,
  isLoading = false,
}) => {
  const isEditing = Boolean(user);

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    first_name: '',
    last_name: '',
  });

  const createValidation = useFormValidation(UserCreateSchema);
  const updateValidation = useFormValidation(UserUpdateSchema);
  const { validate, errors, clearErrors, clearError } = isEditing
    ? updateValidation
    : createValidation;

  // Populate form when editing an existing user
  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email,
        password: '',
        first_name: user.first_name || '',
        last_name: user.last_name || '',
      });
    } else {
      setFormData({
        email: '',
        password: '',
        first_name: '',
        last_name: '',
      });
    }
    clearErrors();
  }, [user, isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    clearError(name);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload: Record<string, string | undefined> = {
      email: formData.email.trim(),
      first_name: formData.first_name.trim() || undefined,
      last_name: formData.last_name.trim() || undefined,
    };

    if (!isEditing) {
      payload.password = formData.password;
    } else if (formData.password.trim()) {
      // Only include password on update if the admin actually typed one
      payload.password = formData.password.trim();
    }

    const result = validate(payload as any);
    if (!result.success) {
      return;
    }

    // Remove empty optional password from update payload
    const submitData: UserCreateInput | UserUpdateInput = { ...result.data };
    if (isEditing && !(submitData as UserUpdateInput).password) {
      delete (submitData as UserUpdateInput).password;
    }

    await onSubmit(submitData);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEditing ? 'Benutzer bearbeiten' : 'Neuer Benutzer'}</h2>
          <button className="modal-close" onClick={onClose} type="button">
            x
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-body">
            <div className="form-group">
              <label htmlFor="user-email">
                E-Mail-Adresse <span className="required">*</span>
              </label>
              <input
                type="email"
                id="user-email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                className={errors.email ? 'error' : ''}
                placeholder="benutzer@beispiel.de"
                autoComplete="off"
              />
              {errors.email && <span className="error-message">{errors.email}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="user-password">
                Passwort{' '}
                {isEditing ? (
                  <span style={{ color: '#666', fontWeight: 'normal', fontSize: '0.85rem' }}>
                    (leer lassen um beizubehalten)
                  </span>
                ) : (
                  <span className="required">*</span>
                )}
              </label>
              <input
                type="password"
                id="user-password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                className={errors.password ? 'error' : ''}
                placeholder={isEditing ? 'Neues Passwort eingeben...' : 'Mindestens 8 Zeichen'}
                autoComplete="new-password"
              />
              {errors.password && <span className="error-message">{errors.password}</span>}
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="user-first-name">Vorname</label>
                <input
                  type="text"
                  id="user-first-name"
                  name="first_name"
                  value={formData.first_name}
                  onChange={handleChange}
                  className={errors.first_name ? 'error' : ''}
                  placeholder="Vorname"
                />
                {errors.first_name && (
                  <span className="error-message">{errors.first_name}</span>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="user-last-name">Nachname</label>
                <input
                  type="text"
                  id="user-last-name"
                  name="last_name"
                  value={formData.last_name}
                  onChange={handleChange}
                  className={errors.last_name ? 'error' : ''}
                  placeholder="Nachname"
                />
                {errors.last_name && (
                  <span className="error-message">{errors.last_name}</span>
                )}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary"
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? 'Speichern...' : isEditing ? 'Aktualisieren' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
