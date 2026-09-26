// Erscheinungsbild (W4-03): workshop colours, name and logo with a live
// preview. The draft is applied to the page while editing (applyTheme) and
// saved to /theme. Defaults come from hooks/useTheme (the AA token values).
import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminKeys, themeQuery } from '../../api/adminQueries';
import { applyTheme, saveTheme, THEME_DEFAULTS, type ThemeSettings } from '../../hooks/useTheme';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, Field, PageState } from '../../ui';

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const HEX_DRAFT = /^[0-9a-fA-F]{0,6}$/;

type ColorKey = Exclude<keyof ThemeSettings, 'workshop_name' | 'logo_url'>;

const COLOR_FIELDS: { key: ColorKey; label: string; help: string }[] = [
  { key: 'primary_color', label: 'Hauptfarbe', help: 'Schaltflächen, Links, aktive Elemente' },
  { key: 'primary_dark', label: 'Hauptfarbe (dunkel)', help: 'Hover-Zustand der Hauptfarbe' },
  { key: 'header_gradient_start', label: 'Header-Verlauf Start', help: 'Linke Farbe des App-Headers' },
  { key: 'header_gradient_end', label: 'Header-Verlauf Ende', help: 'Rechte Farbe des App-Headers' },
  { key: 'accent_color', label: 'Akzentfarbe', help: 'Fokusringe, Markierungen, Badges' },
  { key: 'page_background', label: 'Seitenhintergrund', help: 'Hintergrundfarbe des Hauptbereichs' },
];

interface ColorFieldProps {
  id: string;
  label: string;
  help: string;
  value: string;
  onChange: (value: string) => void;
}

/** Swatch plus hex text; the text only accepts hex digits. */
const ColorField: React.FC<ColorFieldProps> = ({ id, label, help, value, onChange }) => (
  <div className="admin-color-field">
    <Field label={label} name={id} help={help}>
      <input
        id={id}
        type="text"
        className="admin-color-field__hex"
        value={value}
        maxLength={7}
        spellCheck={false}
        onChange={(e) => {
          const clean = e.target.value.trim().replace(/^#+/, '');
          if (HEX_DRAFT.test(clean)) onChange(`#${clean}`);
        }}
      />
    </Field>
    <input
      type="color"
      className="admin-color-field__swatch"
      value={HEX_COLOR.test(value) ? value : THEME_DEFAULTS.primary_color}
      onChange={(e) => onChange(e.target.value)}
      aria-label={`${label}: Farbe wählen`}
    />
  </div>
);

/** Live preview; the colours are runtime values, so they go in as CSS variables. */
const ThemePreview: React.FC<{ draft: ThemeSettings }> = ({ draft }) => (
  <div
    className="admin-theme-preview"
    aria-hidden="true"
    style={
      {
        '--preview-header-start': draft.header_gradient_start,
        '--preview-header-end': draft.header_gradient_end,
        '--preview-primary': draft.primary_color,
        '--preview-accent': draft.accent_color,
        '--preview-bg': draft.page_background,
      } as React.CSSProperties
    }
  >
    <div className="admin-theme-preview__header">
      {draft.logo_url && <img src={draft.logo_url} alt="" className="admin-theme-preview__logo" />}
      <span>{draft.workshop_name || 'Werkstatt'}</span>
    </div>
    <div className="admin-theme-preview__body">
      <span className="admin-theme-preview__primary">Speichern</span>
      <span className="admin-theme-preview__secondary">Abbrechen</span>
      <span className="admin-theme-preview__accent" />
    </div>
  </div>
);

export const ThemePanel: React.FC = () => {
  const queryClient = useQueryClient();
  const theme = useQuery(themeQuery());
  const [draft, setDraft] = useState<ThemeSettings>(THEME_DEFAULTS);

  useEffect(() => {
    if (theme.data) setDraft(theme.data);
  }, [theme.data]);

  const preview = (next: ThemeSettings) => {
    setDraft(next);
    applyTheme(next);
  };

  const save = useMutation({
    mutationFn: (settings: ThemeSettings) => saveTheme(settings),
    onSuccess: (saved) => queryClient.setQueryData(adminKeys.theme(), saved),
    onError: (err) => logError('ThemePanel.save', err),
  });

  return (
    <Card title="Erscheinungsbild" className="admin-panel">
      <PageState
        state={
          theme.isError
            ? {
                status: 'error',
                error: getErrorMessage(theme.error, 'Erscheinungsbild konnte nicht geladen werden.'),
                retry: () => void theme.refetch(),
              }
            : { status: theme.data ? 'ready' : 'loading' }
        }
        skeleton="detail"
      >
        <div className="admin-theme">
          <div className="admin-form">
            <div className="admin-form__grid">
              {COLOR_FIELDS.map(({ key, label, help }) => (
                <ColorField
                  key={key}
                  id={`theme-${key}`}
                  label={label}
                  help={help}
                  value={draft[key]}
                  onChange={(value) => preview({ ...draft, [key]: value })}
                />
              ))}
              <Field label="Name der Werkstatt" name="workshop_name" help="Wird im App-Header und auf Etiketten angezeigt.">
                <input
                  id="admin-workshop-name"
                  type="text"
                  maxLength={100}
                  value={draft.workshop_name}
                  onChange={(e) => preview({ ...draft, workshop_name: e.target.value })}
                />
              </Field>
              <Field
                label="Logo-URL (optional)"
                name="logo_url"
                help="Öffentlich erreichbare URL zu Ihrem Logo (JPG, PNG oder SVG, höchstens 64 px hoch empfohlen)."
              >
                <input
                  id="admin-logo-url"
                  type="url"
                  maxLength={512}
                  placeholder="https://meine-werkstatt.de/logo.png"
                  value={draft.logo_url ?? ''}
                  onChange={(e) => preview({ ...draft, logo_url: e.target.value || null })}
                />
              </Field>
            </div>
            <div className="admin-form__actions">
              <Button loading={save.isPending} onClick={() => save.mutate(draft)}>
                Erscheinungsbild speichern
              </Button>
              <Button variant="secondary" disabled={save.isPending} onClick={() => preview(THEME_DEFAULTS)}>
                Standardfarben wiederherstellen
              </Button>
              {save.isSuccess && (
                <span role="status" className="admin-status admin-status--ok">
                  Erscheinungsbild gespeichert
                </span>
              )}
              {save.isError && (
                <span role="status" className="admin-status admin-status--error">
                  {getErrorMessage(save.error, 'Erscheinungsbild konnte nicht gespeichert werden.')}
                </span>
              )}
            </div>
          </div>
          <ThemePreview draft={draft} />
        </div>
      </PageState>
    </Card>
  );
};

export default ThemePanel;
