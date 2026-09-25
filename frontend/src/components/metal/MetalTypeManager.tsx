/**
 * MetalTypeManager — ADMIN-only dialog for custom metal types (W4-03).
 *
 * Lists all metal types (built-in ones read-only, custom ones editable and
 * deactivatable). "Metalltyp anlegen" opens an inline form. The list comes
 * from the shared useMetalTypes cache; saves are mutations that clear that
 * cache and refresh it.
 */
import React, { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { metalTypesApi } from '../../api/metal-types';
import type { MetalTypeOption, CustomMetalTypeCreate, CustomMetalTypeUpdate } from '../../types';
import { useMetalTypes, invalidateMetalTypesCache } from '../../hooks/useMetalTypes';
import { useConfirm, useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { Button, Field, Modal } from '../../ui';

interface MetalTypeManagerProps {
  isOpen: boolean;
  onClose: () => void;
}

interface FormState {
  code: string;
  display_name: string;
  fine_content_ratio: string;
  base_metal: string;
  color: string;
}

/** Data value for the colour picker (a native colour input needs a hex value). */
const DEFAULT_SWATCH = '#D4A843';
const HEX_COLOUR = /^#[0-9A-Fa-f]{6}$/;
const CODE_PATTERN = /^[a-z0-9_]+$/;
const CODE_MAX_LENGTH = 50;
const PER_MILLE = 1000;
const PERCENT = 100;

const EMPTY_FORM: FormState = {
  code: '',
  display_name: '',
  fine_content_ratio: '',
  base_metal: 'gold',
  color: '',
};

const BASE_METAL_LABELS: Record<string, string> = {
  gold: 'Gold',
  silver: 'Silber',
  platinum: 'Platin',
  palladium: 'Palladium',
};

const UMLAUT_MAP: Record<string, string> = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' };

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[äöüß]/g, (c) => UMLAUT_MAP[c] ?? c)
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, CODE_MAX_LENGTH);
}

function parseRatio(value: string): number {
  return parseFloat(value.replace(',', '.'));
}

function validate(form: FormState): Partial<FormState> {
  const errors: Partial<FormState> = {};
  if (!form.display_name.trim()) errors.display_name = 'Anzeigename fehlt.';
  if (!form.code.trim()) errors.code = 'Code fehlt.';
  else if (!CODE_PATTERN.test(form.code)) errors.code = 'Nur Kleinbuchstaben, Ziffern und _ erlaubt.';
  const ratio = parseRatio(form.fine_content_ratio);
  if (Number.isNaN(ratio) || ratio < 0 || ratio > 1) {
    errors.fine_content_ratio = 'Feingehalt muss zwischen 0,000 und 1,000 liegen.';
  }
  if (form.color && !HEX_COLOUR.test(form.color)) {
    errors.color = `Farbe muss ein Hex-Code sein (z. B. ${DEFAULT_SWATCH}).`;
  }
  return errors;
}

function formFromOption(option: MetalTypeOption): FormState {
  return {
    code: option.code,
    display_name: option.display_name,
    fine_content_ratio: String(option.fine_content_ratio),
    base_metal: option.base_metal,
    color: option.color ?? '',
  };
}

function formatFineness(ratio: number): string {
  return `${(ratio * PER_MILLE).toFixed(0)} ‰ (${(ratio * PERCENT).toFixed(1).replace('.', ',')} %)`;
}

interface TypeFormProps {
  editing: MetalTypeOption | null;
  isSaving: boolean;
  onCancel: () => void;
  onSave: (form: FormState) => void;
}

const MetalTypeForm: React.FC<TypeFormProps> = ({ editing, isSaving, onCancel, onSave }) => {
  const [form, setForm] = useState<FormState>(() => (editing ? formFromOption(editing) : EMPTY_FORM));
  const [errors, setErrors] = useState<Partial<FormState>>({});

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
      // Create mode: derive the code from the display name.
      ...(name === 'display_name' && !editing ? { code: slugify(value) } : {}),
    }));
    setErrors((prev) => ({ ...prev, [name]: undefined }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    const firstInvalid = Object.keys(found)[0];
    if (firstInvalid) {
      document.getElementById(`mt-${firstInvalid}`)?.focus();
      return;
    }
    onSave(form);
  };

  const ratio = parseRatio(form.fine_content_ratio);
  const ratioHelp = ratio >= 0 && ratio <= 1 ? `= ${formatFineness(ratio)}` : undefined;

  return (
    <form onSubmit={handleSubmit} className="metal-type-form" noValidate>
      <h3 className="metal-type-form__title">{editing ? 'Metalltyp bearbeiten' : 'Metalltyp anlegen'}</h3>
      <div className="metal-form metal-form--grid">
        <Field label="Anzeigename" name="display_name" required error={errors.display_name}>
          <input
            id="mt-display_name"
            type="text"
            value={form.display_name}
            onChange={handleChange}
            placeholder="z. B. Roségold 333"
          />
        </Field>
        <Field
          label="Code"
          name="code"
          required
          error={errors.code}
          help={editing ? 'Der Code lässt sich nicht ändern.' : 'Wird aus dem Anzeigenamen erzeugt.'}
        >
          <input
            id="mt-code"
            type="text"
            value={form.code}
            onChange={handleChange}
            placeholder="rose_gold_333"
            readOnly={Boolean(editing)}
          />
        </Field>
        <Field
          label="Feingehalt (0,000 bis 1,000)"
          name="fine_content_ratio"
          required
          inputMode="decimal"
          error={errors.fine_content_ratio}
          help={ratioHelp}
        >
          <input
            id="mt-fine_content_ratio"
            type="text"
            value={form.fine_content_ratio}
            onChange={handleChange}
            placeholder="0,333"
          />
        </Field>
        <Field label="Basismetall" name="base_metal" required>
          <select value={form.base_metal} onChange={handleChange}>
            {Object.entries(BASE_METAL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <div className="metal-type-form__colour">
          <Field label="Farbe" name="color" error={errors.color} help="Optional, als Hex-Code.">
            <input id="mt-color" type="text" value={form.color} onChange={handleChange} placeholder={DEFAULT_SWATCH} />
          </Field>
          <input
            type="color"
            aria-label="Farbe auswählen"
            className="metal-type-form__picker"
            value={form.color || DEFAULT_SWATCH}
            onChange={(e) => setForm((prev) => ({ ...prev, color: e.target.value }))}
          />
        </div>
      </div>
      <div className="metal-type-form__actions">
        <Button variant="secondary" onClick={onCancel} disabled={isSaving}>
          Abbrechen
        </Button>
        <Button type="submit" loading={isSaving}>
          {editing ? 'Metalltyp speichern' : 'Metalltyp anlegen'}
        </Button>
      </div>
    </form>
  );
};

const Swatch: React.FC<{ color: string }> = ({ color }) => (
  // Runtime value: the swatch shows the stored colour of the metal type.
  <span className="metal-swatch" style={{ background: color }} aria-hidden="true" />
);

function useTypeMutations(onSaved: () => void) {
  const { refresh } = useMetalTypes();
  const { showToast } = useToast();
  const afterChange = () => {
    invalidateMetalTypesCache();
    refresh();
  };

  const save = useMutation({
    mutationFn: async ({ editing, form }: { editing: MetalTypeOption | null; form: FormState }) => {
      const common = {
        display_name: form.display_name,
        fine_content_ratio: parseRatio(form.fine_content_ratio),
        base_metal: form.base_metal,
        color: form.color || null,
      };
      if (editing && editing.id != null) {
        await metalTypesApi.update(editing.id, common satisfies CustomMetalTypeUpdate);
        return 'Metalltyp gespeichert';
      }
      await metalTypesApi.create({ ...common, code: form.code } satisfies CustomMetalTypeCreate);
      return 'Metalltyp angelegt';
    },
    onSuccess: (message) => {
      afterChange();
      onSaved();
      showToast(message, 'success');
    },
    onError: (err) =>
      showToast(
        getErrorMessage(err, 'Metalltyp konnte nicht gespeichert werden. Bitte den Code auf Duplikate prüfen.'),
        'error',
      ),
  });

  const deactivate = useMutation({
    mutationFn: (id: number) => metalTypesApi.remove(id),
    onSuccess: () => {
      afterChange();
      showToast('Metalltyp deaktiviert', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Metalltyp konnte nicht deaktiviert werden.'), 'error'),
  });

  return { save, deactivate };
}

export const MetalTypeManager: React.FC<MetalTypeManagerProps> = ({ isOpen, onClose }) => {
  const { metalTypes, isLoading, error } = useMetalTypes();
  const { showConfirm } = useConfirm();
  const [editing, setEditing] = useState<MetalTypeOption | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);

  const closeForm = () => {
    setIsFormOpen(false);
    setEditing(null);
  };
  const { save, deactivate } = useTypeMutations(closeForm);

  useEffect(() => {
    if (isOpen) return;
    setIsFormOpen(false);
    setEditing(null);
  }, [isOpen]);

  const handleDeactivate = async (option: MetalTypeOption) => {
    if (option.id == null || option.is_builtin) return;
    const confirmed = await showConfirm({
      title: 'Metalltyp deaktivieren',
      message: `Möchten Sie den Metalltyp „${option.display_name}“ deaktivieren?`,
      confirmLabel: 'Deaktivieren',
      variant: 'danger',
    });
    if (confirmed) deactivate.mutate(option.id);
  };

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Metalltypen verwalten"
      size="lg"
      isDirty={isFormOpen}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Schließen
        </Button>
      }
    >
      {error && (
        <p className="metal-form__error" role="alert">
          {error}
        </p>
      )}
      {isFormOpen ? (
        <MetalTypeForm
          key={editing?.code ?? 'new'}
          editing={editing}
          isSaving={save.isPending}
          onCancel={closeForm}
          onSave={(form) => save.mutate({ editing, form })}
        />
      ) : (
        <div className="metal-type-toolbar">
          <Button icon="plus" onClick={() => setIsFormOpen(true)}>
            Metalltyp anlegen
          </Button>
        </div>
      )}

      {isLoading ? (
        <p role="status">Metalltypen werden geladen …</p>
      ) : (
        <div className="ui-table-scroll">
          <table className="ui-table">
            <caption className="ui-visually-hidden">Metalltypen</caption>
            <thead>
              <tr>
                <th>Anzeigename</th>
                <th>Code</th>
                <th>Basismetall</th>
                <th className="ui-align-end">Feingehalt</th>
                <th>Typ</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {metalTypes.map((option) => (
                <tr key={option.code} className={option.is_builtin ? 'metal-type-row--builtin' : undefined}>
                  <td>
                    <span className="metal-type-name">
                      {option.color && <Swatch color={option.color} />}
                      {option.display_name}
                    </span>
                  </td>
                  <td>
                    <code>{option.code}</code>
                  </td>
                  <td>{BASE_METAL_LABELS[option.base_metal] ?? option.base_metal}</td>
                  <td className="ui-align-end ui-num">{formatFineness(option.fine_content_ratio)}</td>
                  <td>{option.is_builtin ? 'Standard' : 'Benutzerdefiniert'}</td>
                  <td>
                    {option.is_builtin ? (
                      <span className="metal-muted">Schreibgeschützt</span>
                    ) : (
                      <span className="metal-actions">
                        <Button
                          variant="secondary"
                          icon="pencil"
                          aria-label={`${option.display_name} bearbeiten`}
                          onClick={() => {
                            setEditing(option);
                            setIsFormOpen(true);
                          }}
                        >
                          Bearbeiten
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => void handleDeactivate(option)}
                          disabled={deactivate.isPending}
                        >
                          Deaktivieren
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
};

