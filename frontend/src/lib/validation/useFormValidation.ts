/**
 * useFormValidation – generic Zod-backed validation hook.
 *
 * Usage:
 *   const { validate, errors, clearErrors, clearError } = useFormValidation(LoginSchema);
 *
 *   const result = validate({ email, password });
 *   if (!result.success) {
 *     // result.errors is Record<string, string> with German messages
 *     return;
 *   }
 *   await login(result.data); // result.data is the typed, parsed value
 */

import { useState, useCallback } from 'react';
import type { ZodSchema, ZodError } from 'zod';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FieldErrors = Record<string, string>;

export type ValidationResult<T> =
  | { success: true; data: T; errors?: never }
  | { success: false; data?: never; errors: FieldErrors };

export interface UseFormValidation<T> {
  /** Validate a data object against the schema. Updates internal error state. */
  validate: (data: unknown) => ValidationResult<T>;
  /** Current field-level error map (field name → German error string). */
  errors: FieldErrors;
  /** Clear all field errors at once. */
  clearErrors: () => void;
  /** Clear the error for a single field. Useful on change handlers. */
  clearError: (field: string) => void;
}

// ---------------------------------------------------------------------------
// Zod error → German message mapping
// ---------------------------------------------------------------------------

/**
 * Translate a raw Zod issue message to a user-facing German string.
 * Zod v4 ships its own i18n support, but we keep this thin mapper so
 * messages stay consistent with the existing form error copy.
 */
function toGermanMessage(zodMessage: string): string {
  // Map common Zod v4 English messages to German equivalents.
  // The schemas already specify custom German messages for most rules;
  // this catches any remaining Zod default messages.
  const map: Record<string, string> = {
    'Required': 'Pflichtfeld',
    'Invalid type': 'Ungültiger Wert',
    'Expected string, received number': 'Muss ein Text sein',
    'Expected number, received string': 'Muss eine Zahl sein',
    'Expected number, received nan': 'Muss eine gültige Zahl sein',
    'String must contain at least 1 character(s)': 'Pflichtfeld',
    'Number must be greater than 0': 'Muss größer als 0 sein',
    'Number must be greater than or equal to 0': 'Darf nicht negativ sein',
    'Invalid email': 'Ungültige E-Mail-Adresse',
    'Invalid enum value': 'Ungültige Auswahl',
  };
  return map[zodMessage] ?? zodMessage;
}

/**
 * Flatten a ZodError into a flat Record<string, string> where the key is the
 * dot-joined path (e.g. "customer.email") and the value is the first message
 * for that path translated to German.
 */
function flattenZodErrors(error: ZodError): FieldErrors {
  const result: FieldErrors = {};
  for (const issue of error.issues) {
    const key = issue.path.join('.') || '_form';
    // Only keep the first error per field — avoid overwhelming the user
    if (!result[key]) {
      result[key] = toGermanMessage(issue.message);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useFormValidation<T>(schema: ZodSchema<T>): UseFormValidation<T> {
  const [errors, setErrors] = useState<FieldErrors>({});

  const validate = useCallback(
    (data: unknown): ValidationResult<T> => {
      const result = schema.safeParse(data);

      if (result.success) {
        setErrors({});
        return { success: true, data: result.data };
      }

      const fieldErrors = flattenZodErrors(result.error);
      setErrors(fieldErrors);
      return { success: false, errors: fieldErrors };
    },
    [schema]
  );

  const clearErrors = useCallback(() => {
    setErrors({});
  }, []);

  const clearError = useCallback((field: string) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  return { validate, errors, clearErrors, clearError };
}
