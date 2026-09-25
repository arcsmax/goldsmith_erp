// Werkstatt-Stammdaten (W2-04, DOM-24; W4-03): the seller data every
// Rechnung must carry under § 14 Abs. 4 UStG, plus bank details, the
// Kleinunternehmer switch (§ 19 UStG), the default VAT rate and the invoice
// footer. react-hook-form + zod on the Field primitive; data through
// TanStack Query. ADMIN only (route guard; backend WORKSHOP_SETTINGS_MANAGE).
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { updateWorkshopSettings } from '../../api/admin';
import { adminKeys, workshopSettingsQuery } from '../../api/adminQueries';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, Field, PageState } from '../../ui';
import {
  TEXT_FIELDS,
  toFormValues,
  toPayload,
  workshopSettingsSchema,
  type WorkshopSettingsValues,
} from './workshopSettingsForm';

const SAVE_FALLBACK = 'Stammdaten konnten nicht gespeichert werden.';

/** Prefer the backend's own validator text ("Ungültige IBAN") over field names. */
function saveErrorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d: { msg?: unknown }) => (typeof d?.msg === 'string' ? d.msg.replace(/^Value error, /, '') : ''))
      .filter(Boolean);
    if (messages.length > 0) return messages.join(' · ');
  }
  return getErrorMessage(err, SAVE_FALLBACK);
}

export const WorkshopSettingsPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const settings = useQuery(workshopSettingsQuery());
  const form = useForm<WorkshopSettingsValues>({ resolver: zodResolver(workshopSettingsSchema) });
  const { register, handleSubmit, reset, watch, formState } = form;
  const { errors } = formState;

  useEffect(() => {
    if (settings.data) reset(toFormValues(settings.data));
  }, [settings.data, reset]);

  const save = useMutation({
    mutationFn: (values: WorkshopSettingsValues) => updateWorkshopSettings(toPayload(values)),
    onSuccess: (saved) => {
      queryClient.setQueryData(adminKeys.workshopSettings(), saved);
    },
    onError: (err) => logError('WorkshopSettingsPanel.save', err),
  });

  const isKleinunternehmer = watch('is_kleinunternehmer');
  const missing = settings.data?.missing_fields ?? [];
  const isBusy = save.isPending;

  return (
    <Card title="Werkstatt-Stammdaten" className="admin-panel">
      <p className="admin-panel__intro">
        Diese Angaben stehen als Rechnungssteller auf jeder Rechnung (§ 14 Abs. 4 UStG).
        Bereits ausgestellte Rechnungen ändern sich nicht.
      </p>

      {missing.length > 0 && (
        <p className="admin-notice admin-notice--waiting" role="status">
          Für eine vollständige Rechnung fehlen noch: {missing.join(', ')}
        </p>
      )}

      <PageState
        state={
          settings.isError
            ? {
                status: 'error',
                error: getErrorMessage(settings.error, 'Stammdaten konnten nicht geladen werden.'),
                retry: () => void settings.refetch(),
              }
            : { status: settings.data ? 'ready' : 'loading' }
        }
        skeleton="detail"
      >
        <form
          className="admin-form"
          noValidate
          onSubmit={handleSubmit((values) => save.mutate(values))}
        >
          <div className="admin-form__grid">
            {TEXT_FIELDS.map(({ key, label, help, type, inputMode, required }) => (
              <Field
                key={key}
                label={label}
                name={key}
                help={help}
                required={required}
                inputMode={inputMode}
                error={errors[key]?.message}
              >
                <input id={`ws-${key}`} type={type ?? 'text'} disabled={isBusy} {...register(key)} />
              </Field>
            ))}
            <Field
              label="Umsatzsteuersatz (%)"
              name="default_vat_rate"
              help="Standard für neue Rechnungen."
              inputMode="decimal"
              suffix="%"
              error={errors.default_vat_rate?.message}
            >
              <input
                id="ws-default_vat_rate"
                type="text"
                disabled={isBusy || isKleinunternehmer}
                {...register('default_vat_rate')}
              />
            </Field>
            <div className="admin-form__check">
              <label htmlFor="ws-kleinunternehmer">
                <input
                  id="ws-kleinunternehmer"
                  type="checkbox"
                  disabled={isBusy}
                  {...register('is_kleinunternehmer')}
                />
                Kleinunternehmer (§ 19 UStG)
              </label>
              <p className="admin-panel__hint">
                Rechnungen ohne Umsatzsteuer, mit dem Hinweis nach § 19 UStG.
              </p>
            </div>
          </div>

          <div className="admin-form__actions">
            <Button type="submit" loading={isBusy}>
              Stammdaten speichern
            </Button>
            {save.isSuccess && !formState.isDirty && (
              <span role="status" className="admin-status admin-status--ok">
                Stammdaten gespeichert
              </span>
            )}
            {save.isError && (
              <span role="status" className="admin-status admin-status--error">
                {saveErrorText(save.error)}
              </span>
            )}
          </div>
        </form>
      </PageState>
    </Card>
  );
};

export default WorkshopSettingsPanel;
