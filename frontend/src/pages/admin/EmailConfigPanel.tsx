// E-Mail-Konfiguration (W4-03): SMTP settings and a test mail, on the Field
// primitive with react-hook-form + zod and TanStack Query.
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { sendTestEmail, updateEmailConfig, type EmailConfig } from '../../api/admin';
import { adminKeys, emailConfigQuery } from '../../api/adminQueries';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, Field, PageState } from '../../ui';

const DEFAULT_PORT = 587;
const MAX_PORT = 65535;

const optionalEmail = z
  .string()
  .trim()
  .refine((v) => v === '' || z.email().safeParse(v).success, {
    message: 'E-Mail-Adresse ist ungültig. Bitte im Format name@beispiel.de eingeben.',
  });

const emailConfigSchema = z.object({
  smtp_host: z.string().trim(),
  smtp_port: z
    .number({ message: 'Port fehlt. Bitte eine Zahl eingeben, meist 587.' })
    .int('Port bitte als ganze Zahl eingeben.')
    .min(1, `Port muss zwischen 1 und ${MAX_PORT} liegen.`)
    .max(MAX_PORT, `Port muss zwischen 1 und ${MAX_PORT} liegen.`),
  smtp_user: z.string().trim(),
  smtp_password: z.string(),
  smtp_from: optionalEmail,
  email_notifications_enabled: z.boolean(),
});

type EmailConfigValues = z.infer<typeof emailConfigSchema>;

const toValues = (c: EmailConfig): EmailConfigValues => ({
  smtp_host: c.smtp_host ?? '',
  smtp_port: c.smtp_port ?? DEFAULT_PORT,
  smtp_user: c.smtp_user ?? '',
  smtp_password: '',
  smtp_from: c.smtp_from ?? '',
  email_notifications_enabled: c.email_notifications_enabled,
});

const TestMail: React.FC = () => {
  const [recipient, setRecipient] = useState('');
  const test = useMutation({
    mutationFn: (to: string) => sendTestEmail(to),
    onError: (err) => logError('EmailConfigPanel.test', err),
  });
  const trimmed = recipient.trim();
  return (
    <div className="admin-form__inline">
      <Field label="Test-Empfänger" name="test_recipient" inputMode="email">
        <input
          type="email"
          placeholder="name@beispiel.de"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
      </Field>
      <Button
        variant="secondary"
        icon="send"
        loading={test.isPending}
        disabled={!trimmed}
        onClick={() => test.mutate(trimmed)}
      >
        Test-E-Mail senden
      </Button>
      {test.data && (
        <p role="status" className={`admin-status admin-status--${test.data.success ? 'ok' : 'error'}`}>
          {test.data.message}
        </p>
      )}
      {test.isError && (
        <p role="status" className="admin-status admin-status--error">
          {getErrorMessage(test.error, 'Test-E-Mail konnte nicht gesendet werden.')}
        </p>
      )}
    </div>
  );
};

export const EmailConfigPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const config = useQuery(emailConfigQuery());
  const { register, handleSubmit, reset, formState } = useForm<EmailConfigValues>({
    resolver: zodResolver(emailConfigSchema),
  });
  const { errors } = formState;

  useEffect(() => {
    if (config.data) reset(toValues(config.data));
  }, [config.data, reset]);

  const save = useMutation({
    mutationFn: ({ smtp_password, ...rest }: EmailConfigValues) =>
      updateEmailConfig({ ...rest, smtp_password: smtp_password || undefined }),
    onSuccess: (saved) => queryClient.setQueryData(adminKeys.emailConfig(), saved),
    onError: (err) => logError('EmailConfigPanel.save', err),
  });

  const passwordSet = config.data?.password_configured ?? false;

  return (
    <Card title="E-Mail-Konfiguration" className="admin-panel">
      <PageState
        state={
          config.isError
            ? {
                status: 'error',
                error: getErrorMessage(config.error, 'E-Mail-Konfiguration konnte nicht geladen werden.'),
                retry: () => void config.refetch(),
              }
            : { status: config.data ? 'ready' : 'loading' }
        }
        skeleton="detail"
      >
        <form className="admin-form" noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
          <div className="admin-form__grid">
            <Field label="SMTP-Server" name="smtp_host" error={errors.smtp_host?.message}>
              <input type="text" placeholder="z. B. smtp.beispiel.de" {...register('smtp_host')} />
            </Field>
            <Field label="SMTP-Port" name="smtp_port" inputMode="numeric" error={errors.smtp_port?.message}>
              <input type="number" min={1} max={MAX_PORT} {...register('smtp_port', { valueAsNumber: true })} />
            </Field>
            <Field label="SMTP-Benutzer" name="smtp_user" error={errors.smtp_user?.message}>
              <input type="text" autoComplete="off" {...register('smtp_user')} />
            </Field>
            <Field
              label="SMTP-Passwort"
              name="smtp_password"
              help={passwordSet ? 'Gesetzt. Zum Ändern neu eingeben.' : undefined}
            >
              <input type="password" autoComplete="new-password" {...register('smtp_password')} />
            </Field>
            <Field label="Absender-Adresse" name="smtp_from" inputMode="email" error={errors.smtp_from?.message}>
              <input type="email" placeholder="werkstatt@beispiel.de" {...register('smtp_from')} />
            </Field>
            <div className="admin-form__check">
              <label htmlFor="email-notifications">
                <input id="email-notifications" type="checkbox" {...register('email_notifications_enabled')} />
                Kunden-E-Mails aktivieren
              </label>
              <p className="admin-panel__hint">
                Sendet automatisch E-Mails bei Auftragsbestätigung, Abholbereitschaft und Anproben.
              </p>
            </div>
          </div>
          <div className="admin-form__actions">
            <Button type="submit" loading={save.isPending}>
              Einstellungen speichern
            </Button>
            {save.isSuccess && !formState.isDirty && (
              <span role="status" className="admin-status admin-status--ok">
                Einstellungen gespeichert
              </span>
            )}
            {save.isError && (
              <span role="status" className="admin-status admin-status--error">
                {getErrorMessage(save.error, 'Einstellungen konnten nicht gespeichert werden.')}
              </span>
            )}
          </div>
        </form>
        <TestMail />
      </PageState>
    </Card>
  );
};

export default EmailConfigPanel;
