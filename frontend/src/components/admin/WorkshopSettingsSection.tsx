// Werkstatt-Stammdaten (W2-04, DOM-24): the seller data every Rechnung
// must carry under §14 Abs. 4 UStG (name, address, Steuernummer or
// USt-IdNr.), plus bank details, the Kleinunternehmer switch (§19 UStG),
// the default VAT rate and the invoice footer. ADMIN only (the page itself
// is ADMIN-gated; the backend enforces WORKSHOP_SETTINGS_MANAGE).
//
// Reuses the admin theme form classes (styles/admin-theme.css) so no new
// CSS or inline styles are introduced (UI rules, CLAUDE.md).
import React, { useEffect, useState } from 'react';
import {
  WorkshopSettings,
  WorkshopSettingsInput,
  getWorkshopSettings,
  updateWorkshopSettings,
} from '../../api/admin';
import { logError } from '../../lib/logError';

type TextField = Exclude<
  keyof WorkshopSettingsInput,
  'is_kleinunternehmer' | 'default_vat_rate'
>;

type Draft = Record<TextField, string> & {
  is_kleinunternehmer: boolean;
  default_vat_rate: string;
};

const TEXT_FIELDS: { key: TextField; label: string; hint?: string; type?: string; inputMode?: 'numeric' | 'tel' | 'email' }[] = [
  { key: 'name', label: 'Name der Werkstatt', hint: 'Erscheint als Rechnungssteller.' },
  { key: 'owner_name', label: 'Inhaberin oder Inhaber' },
  { key: 'street', label: 'Straße und Hausnummer' },
  { key: 'postal_code', label: 'PLZ', inputMode: 'numeric' },
  { key: 'city', label: 'Ort' },
  { key: 'country', label: 'Land' },
  { key: 'phone', label: 'Telefon', type: 'tel', inputMode: 'tel' },
  { key: 'email', label: 'E-Mail', type: 'email', inputMode: 'email' },
  { key: 'tax_number', label: 'Steuernummer', hint: 'Steuernummer oder USt-IdNr. ist Pflicht (§ 14 UStG).' },
  { key: 'vat_id', label: 'USt-IdNr.', hint: 'z. B. DE123456789' },
  { key: 'iban', label: 'IBAN' },
  { key: 'bic', label: 'BIC' },
  { key: 'bank_name', label: 'Bank' },
  { key: 'invoice_footer', label: 'Fußzeile der Rechnung', hint: 'z. B. Dank oder Zahlungsbedingungen.' },
];

const toDraft = (s: WorkshopSettings): Draft => ({
  name: s.name ?? '',
  owner_name: s.owner_name ?? '',
  street: s.street ?? '',
  postal_code: s.postal_code ?? '',
  city: s.city ?? '',
  country: s.country ?? '',
  phone: s.phone ?? '',
  email: s.email ?? '',
  tax_number: s.tax_number ?? '',
  vat_id: s.vat_id ?? '',
  iban: s.iban ?? '',
  bic: s.bic ?? '',
  bank_name: s.bank_name ?? '',
  invoice_footer: s.invoice_footer ?? '',
  is_kleinunternehmer: s.is_kleinunternehmer,
  default_vat_rate: String(s.default_vat_rate ?? 19),
});

const toPayload = (d: Draft): WorkshopSettingsInput => {
  const text = (value: string) => value.trim() || null;
  return {
    name: d.name.trim(),
    owner_name: text(d.owner_name),
    street: text(d.street),
    postal_code: text(d.postal_code),
    city: text(d.city),
    country: text(d.country),
    phone: text(d.phone),
    email: text(d.email),
    tax_number: text(d.tax_number),
    vat_id: text(d.vat_id),
    iban: text(d.iban),
    bic: text(d.bic),
    bank_name: text(d.bank_name),
    invoice_footer: text(d.invoice_footer),
    is_kleinunternehmer: d.is_kleinunternehmer,
    default_vat_rate: Number(d.default_vat_rate.replace(',', '.')),
  };
};

/** German message from a FastAPI error (string detail or 422 list). */
const errorText = (err: unknown): string => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const detail = (err as any)?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (typeof d?.msg === 'string' ? d.msg.replace(/^Value error, /, '') : ''))
      .filter(Boolean);
    if (messages.length > 0) return messages.join(' · ');
  }
  return 'Stammdaten konnten nicht gespeichert werden.';
};

export const WorkshopSettingsSection: React.FC = () => {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    getWorkshopSettings()
      .then((settings) => {
        setDraft(toDraft(settings));
        setMissing(settings.missing_fields);
      })
      .catch((err) => {
        logError('WorkshopSettingsSection.load', err);
        setMessage({ text: 'Stammdaten konnten nicht geladen werden.', ok: false });
      });
  }, []);

  const setField = (key: keyof Draft, value: string | boolean) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const handleSave = async () => {
    if (!draft) return;
    setIsSaving(true);
    setMessage(null);
    try {
      const saved = await updateWorkshopSettings(toPayload(draft));
      setDraft(toDraft(saved));
      setMissing(saved.missing_fields);
      setMessage({ text: 'Stammdaten gespeichert', ok: true });
    } catch (err) {
      logError('WorkshopSettingsSection.save', err);
      setMessage({ text: errorText(err), ok: false });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="admin-section">
      <h2>Werkstatt-Stammdaten</h2>
      <p className="theme-field-hint">
        Diese Angaben stehen als Rechnungssteller auf jeder Rechnung (§ 14 Abs. 4 UStG).
        Bereits ausgestellte Rechnungen ändern sich nicht.
      </p>

      {missing.length > 0 && (
        <div className="admin-error-banner" role="status">
          Für eine vollständige Rechnung fehlen noch: {missing.join(', ')}
        </div>
      )}

      {!draft ? (
        message ? null : <p className="theme-field-hint">Wird geladen…</p>
      ) : (
        <div className="theme-form-panel">
          <div className="theme-form-grid">
            {TEXT_FIELDS.map(({ key, label, hint, type, inputMode }) => (
              <div className="theme-field" key={key}>
                <label className="theme-field-label" htmlFor={`ws-${key}`}>
                  {label}
                </label>
                <input
                  id={`ws-${key}`}
                  className="theme-text-input"
                  type={type ?? 'text'}
                  inputMode={inputMode}
                  value={draft[key]}
                  onChange={(e) => setField(key, e.target.value)}
                  disabled={isSaving}
                />
                {hint && <span className="theme-field-hint">{hint}</span>}
              </div>
            ))}
            <div className="theme-field">
              <label className="theme-field-label" htmlFor="ws-default_vat_rate">
                Umsatzsteuersatz (%)
              </label>
              <input
                id="ws-default_vat_rate"
                className="theme-text-input"
                type="text"
                inputMode="decimal"
                value={draft.default_vat_rate}
                onChange={(e) => setField('default_vat_rate', e.target.value)}
                disabled={isSaving || draft.is_kleinunternehmer}
              />
              <span className="theme-field-hint">Standard für neue Rechnungen.</span>
            </div>
            <div className="theme-field">
              <label className="theme-field-label" htmlFor="ws-kleinunternehmer">
                <input
                  id="ws-kleinunternehmer"
                  type="checkbox"
                  checked={draft.is_kleinunternehmer}
                  onChange={(e) => setField('is_kleinunternehmer', e.target.checked)}
                  disabled={isSaving}
                />{' '}
                Kleinunternehmer (§ 19 UStG)
              </label>
              <span className="theme-field-hint">
                Rechnungen ohne Umsatzsteuer, mit dem Hinweis nach § 19 UStG.
              </span>
            </div>
          </div>

          <div className="theme-actions">
            <button
              type="button"
              className="theme-save-btn"
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? 'Wird gespeichert…' : 'Stammdaten speichern'}
            </button>
            {message && (
              <span
                role="status"
                className={`theme-status-msg ${message.ok ? 'theme-status-msg--ok' : 'theme-status-msg--err'}`}
              >
                {message.text}
              </span>
            )}
          </div>
        </div>
      )}

      {!draft && message && (
        <span role="status" className="theme-status-msg theme-status-msg--err">
          {message.text}
        </span>
      )}
    </div>
  );
};

export default WorkshopSettingsSection;
