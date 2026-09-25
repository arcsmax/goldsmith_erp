// User form dialog (admin only) on the src/ui Modal + Field primitives (W4-03).
//
// Never closes on backdrop click; a dirty form asks "Änderungen verwerfen?"
// before closing (Modal isDirty).
import React, { useEffect, useId, useState } from 'react';
import type { UserType, UserCreateInput, UserUpdateInput } from '../../types';
import { UserCreateSchema, UserUpdateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';
import { Button, Field, Modal } from '../../ui';
import '../../styles/users.css';

interface UserFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: UserCreateInput | UserUpdateInput) => Promise<void>;
  user?: UserType | null;
  isLoading?: boolean;
}

interface UserFormState {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

const EMPTY_FORM: UserFormState = { email: '', password: '', first_name: '', last_name: '' };

function formFromUser(user?: UserType | null): UserFormState {
  if (!user) return EMPTY_FORM;
  return {
    email: user.email,
    password: '',
    first_name: user.first_name || '',
    last_name: user.last_name || '',
  };
}

export const UserFormModal: React.FC<UserFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  user,
  isLoading = false,
}) => {
  const isEditing = Boolean(user);
  const formId = useId();
  const [formData, setFormData] = useState<UserFormState>(EMPTY_FORM);
  const [initialData, setInitialData] = useState<UserFormState>(EMPTY_FORM);

  const createValidation = useFormValidation(UserCreateSchema);
  const updateValidation = useFormValidation(UserUpdateSchema);
  const { validate, errors, clearErrors, clearError } = isEditing
    ? updateValidation
    : createValidation;

  // Populate the form when the dialog opens or the edited user changes.
  useEffect(() => {
    const next = formFromUser(user);
    setFormData(next);
    setInitialData(next);
    clearErrors();
  }, [user, isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const isDirty = (Object.keys(formData) as (keyof UserFormState)[]).some(
    (key) => formData[key] !== initialData[key],
  );

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

    const result = validate(payload as never);
    if (!result.success) {
      return;
    }

    const { password, ...rest } = result.data as UserCreateInput;
    const submitData: UserCreateInput | UserUpdateInput =
      isEditing && !password ? rest : { ...rest, password };

    await onSubmit(submitData);
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isLoading}>
        Abbrechen
      </Button>
      <Button type="submit" form={formId} loading={isLoading}>
        {isEditing ? 'Benutzer speichern' : 'Benutzer anlegen'}
      </Button>
    </>
  );

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={isEditing ? 'Benutzer bearbeiten' : 'Neuer Benutzer'}
      isDirty={isDirty && !isLoading}
      footer={footer}
    >
      <form id={formId} onSubmit={handleSubmit} noValidate>
        <Field label="E-Mail-Adresse" name="email" required inputMode="email" error={errors.email}>
          <input
            type="email"
            id="user-email"
            value={formData.email}
            onChange={handleChange}
            autoComplete="off"
          />
        </Field>

        <Field
          label="Passwort"
          name="password"
          required={!isEditing}
          help={isEditing ? 'Leer lassen, um das bisherige Passwort zu behalten.' : 'Mindestens 8 Zeichen.'}
          error={errors.password}
        >
          <input
            type="password"
            id="user-password"
            value={formData.password}
            onChange={handleChange}
            autoComplete="new-password"
          />
        </Field>

        <div className="user-form-row">
          <Field label="Vorname" name="first_name" error={errors.first_name}>
            <input type="text" id="user-first-name" value={formData.first_name} onChange={handleChange} />
          </Field>

          <Field label="Nachname" name="last_name" error={errors.last_name}>
            <input type="text" id="user-last-name" value={formData.last_name} onChange={handleChange} />
          </Field>
        </div>
      </form>
    </Modal>
  );
};
