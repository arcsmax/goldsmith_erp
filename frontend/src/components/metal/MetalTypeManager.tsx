/**
 * MetalTypeManager — ADMIN-only section for managing custom metal types.
 *
 * Renders a table of all metal types (built-in shown as read-only, custom
 * types editable/deactivatable).  A "Neuer Metalltyp" button opens a form
 * for creating or editing entries.
 *
 * Props:
 *   isOpen   — controls visibility (rendered by MetalInventoryPage)
 *   onClose  — callback to hide the manager
 */
import React, { useState, useEffect } from 'react';
import { metalTypesApi } from '../../api';
import {
  MetalTypeOption,
  CustomMetalTypeCreate,
  CustomMetalTypeUpdate,
} from '../../types';
import { useMetalTypes, invalidateMetalTypesCache } from '../../hooks/useMetalTypes';

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

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[äöüß]/g, (c) =>
      ({ ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' }[c] ?? c)
    )
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 50);
}

export const MetalTypeManager: React.FC<MetalTypeManagerProps> = ({ isOpen, onClose }) => {
  const { metalTypes, isLoading, error, refresh } = useMetalTypes();

  const [editingType, setEditingType] = useState<MetalTypeOption | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formData, setFormData] = useState<FormState>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Partial<FormState>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Reset on open/close
  useEffect(() => {
    if (!isOpen) {
      setIsFormOpen(false);
      setEditingType(null);
      setApiError(null);
      setSuccessMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // ---------------------------------------------------------------------------
  // Form helpers
  // ---------------------------------------------------------------------------

  const openCreate = () => {
    setEditingType(null);
    setFormData(EMPTY_FORM);
    setFormErrors({});
    setApiError(null);
    setIsFormOpen(true);
  };

  const openEdit = (option: MetalTypeOption) => {
    setEditingType(option);
    setFormData({
      code: option.code,
      display_name: option.display_name,
      fine_content_ratio: String(option.fine_content_ratio),
      base_metal: option.base_metal,
      color: option.color ?? '',
    });
    setFormErrors({});
    setApiError(null);
    setIsFormOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setEditingType(null);
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => {
      const next = { ...prev, [name]: value };
      // Auto-generate code from display_name in create mode
      if (name === 'display_name' && !editingType) {
        next.code = slugify(value);
      }
      return next;
    });
    if (formErrors[name as keyof FormState]) {
      setFormErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const validate = (): boolean => {
    const errors: Partial<FormState> = {};
    if (!formData.display_name.trim()) errors.display_name = 'Anzeigename ist erforderlich';
    if (!formData.code.trim()) {
      errors.code = 'Code ist erforderlich';
    } else if (!/^[a-z0-9_]+$/.test(formData.code)) {
      errors.code = 'Nur Kleinbuchstaben, Ziffern und _ erlaubt';
    }
    const ratio = parseFloat(formData.fine_content_ratio);
    if (isNaN(ratio) || ratio < 0 || ratio > 1) {
      errors.fine_content_ratio = 'Feingehalt muss zwischen 0.000 und 1.000 liegen';
    }
    if (formData.color && !/^#[0-9A-Fa-f]{6}$/.test(formData.color)) {
      errors.color = 'Farbe muss ein gültiger Hex-Code sein (z.B. #D4A843)';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSaving(true);
    setApiError(null);

    try {
      if (editingType && editingType.id != null) {
        // Update existing custom type
        const update: CustomMetalTypeUpdate = {
          display_name: formData.display_name,
          fine_content_ratio: parseFloat(formData.fine_content_ratio),
          base_metal: formData.base_metal,
          color: formData.color || null,
        };
        await metalTypesApi.update(editingType.id, update);
        setSuccessMsg(`Metalltyp "${formData.display_name}" wurde aktualisiert.`);
      } else {
        // Create new custom type
        const create: CustomMetalTypeCreate = {
          code: formData.code,
          display_name: formData.display_name,
          fine_content_ratio: parseFloat(formData.fine_content_ratio),
          base_metal: formData.base_metal,
          color: formData.color || null,
        };
        await metalTypesApi.create(create);
        setSuccessMsg(`Metalltyp "${formData.display_name}" wurde erstellt.`);
      }

      invalidateMetalTypesCache();
      refresh();
      closeForm();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Speichern fehlgeschlagen. Bitte prüfen Sie den Code auf Duplikate.';
      setApiError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeactivate = async (option: MetalTypeOption) => {
    if (option.id == null || option.is_builtin) return;
    if (!window.confirm(`Metalltyp "${option.display_name}" deaktivieren?`)) return;

    setApiError(null);
    try {
      await metalTypesApi.remove(option.id);
      invalidateMetalTypesCache();
      refresh();
      setSuccessMsg(`Metalltyp "${option.display_name}" wurde deaktiviert.`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Deaktivierung fehlgeschlagen.';
      setApiError(msg);
    }
  };

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  const finePercent = parseFloat(formData.fine_content_ratio);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content metal-type-manager-modal"
        style={{ maxWidth: '900px', width: '95vw' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <h2>Metalltypen verwalten</h2>
          <button className="modal-close" onClick={onClose} aria-label="Schliessen">
            x
          </button>
        </div>

        <div style={{ padding: '1rem 1.5rem' }}>
          {/* Feedback messages */}
          {successMsg && (
            <div
              style={{
                background: 'var(--color-success, #e8f5e9)',
                color: 'var(--color-success-text, #2e7d32)',
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                marginBottom: '1rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span>{successMsg}</span>
              <button
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}
                onClick={() => setSuccessMsg(null)}
              >
                x
              </button>
            </div>
          )}
          {apiError && (
            <div
              style={{
                background: 'var(--color-error-bg, #ffebee)',
                color: 'var(--color-error, #c62828)',
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                marginBottom: '1rem',
              }}
            >
              {apiError}
            </div>
          )}
          {error && (
            <div style={{ color: 'var(--color-error, #c62828)', marginBottom: '1rem' }}>
              {error}
            </div>
          )}

          {/* Toolbar */}
          {!isFormOpen && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
              <button className="btn-primary" onClick={openCreate}>
                + Neuer Metalltyp
              </button>
            </div>
          )}

          {/* Create / Edit form */}
          {isFormOpen && (
            <form
              onSubmit={handleSubmit}
              style={{
                background: 'var(--color-surface-secondary, #f8f9fa)',
                padding: '1.25rem',
                borderRadius: '8px',
                marginBottom: '1.5rem',
                border: '1px solid var(--color-border, #dee2e6)',
              }}
            >
              <h3 style={{ margin: '0 0 1rem' }}>
                {editingType ? 'Metalltyp bearbeiten' : 'Neuer Metalltyp'}
              </h3>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '1rem',
                }}
              >
                {/* Display Name */}
                <div className="form-group">
                  <label htmlFor="mt_display_name">
                    Anzeigename <span className="required">*</span>
                  </label>
                  <input
                    id="mt_display_name"
                    name="display_name"
                    type="text"
                    value={formData.display_name}
                    onChange={handleChange}
                    placeholder="z.B. Roségold 333"
                    className={formErrors.display_name ? 'error' : ''}
                  />
                  {formErrors.display_name && (
                    <span className="error-text">{formErrors.display_name}</span>
                  )}
                </div>

                {/* Code */}
                <div className="form-group">
                  <label htmlFor="mt_code">
                    Code <span className="required">*</span>
                    {!editingType && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--color-muted, #666)', marginLeft: '0.5rem' }}>
                        (wird automatisch generiert)
                      </span>
                    )}
                  </label>
                  <input
                    id="mt_code"
                    name="code"
                    type="text"
                    value={formData.code}
                    onChange={handleChange}
                    placeholder="rose_gold_333"
                    readOnly={!!editingType}
                    className={formErrors.code ? 'error' : ''}
                    style={editingType ? { opacity: 0.6, cursor: 'not-allowed' } : {}}
                  />
                  {formErrors.code && (
                    <span className="error-text">{formErrors.code}</span>
                  )}
                </div>

                {/* Feingehalt */}
                <div className="form-group">
                  <label htmlFor="mt_fine">
                    Feingehalt (0.000 – 1.000) <span className="required">*</span>
                  </label>
                  <input
                    id="mt_fine"
                    name="fine_content_ratio"
                    type="number"
                    step="0.001"
                    min="0"
                    max="1"
                    value={formData.fine_content_ratio}
                    onChange={handleChange}
                    placeholder="0.333"
                    className={formErrors.fine_content_ratio ? 'error' : ''}
                  />
                  {!isNaN(finePercent) && finePercent >= 0 && finePercent <= 1 && (
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-muted, #666)' }}>
                      = {(finePercent * 1000).toFixed(0)}‰ = {(finePercent * 100).toFixed(1)} %
                    </span>
                  )}
                  {formErrors.fine_content_ratio && (
                    <span className="error-text">{formErrors.fine_content_ratio}</span>
                  )}
                </div>

                {/* Basismetall */}
                <div className="form-group">
                  <label htmlFor="mt_base_metal">
                    Basismetall <span className="required">*</span>
                  </label>
                  <select
                    id="mt_base_metal"
                    name="base_metal"
                    value={formData.base_metal}
                    onChange={handleChange}
                  >
                    {Object.entries(BASE_METAL_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Color */}
                <div className="form-group">
                  <label htmlFor="mt_color">Farbe (optional)</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input
                      id="mt_color"
                      name="color"
                      type="color"
                      value={formData.color || '#D4A843'}
                      onChange={(e) =>
                        handleChange({
                          ...e,
                          target: { ...e.target, name: 'color', value: e.target.value },
                        } as React.ChangeEvent<HTMLInputElement>)
                      }
                      style={{ width: '48px', height: '36px', padding: '2px', cursor: 'pointer' }}
                    />
                    <input
                      name="color"
                      type="text"
                      value={formData.color}
                      onChange={handleChange}
                      placeholder="#D4A843"
                      style={{ flex: 1 }}
                      className={formErrors.color ? 'error' : ''}
                    />
                  </div>
                  {formErrors.color && (
                    <span className="error-text">{formErrors.color}</span>
                  )}
                </div>
              </div>

              <div className="modal-actions" style={{ marginTop: '1rem' }}>
                <button type="button" className="btn-secondary" onClick={closeForm} disabled={isSaving}>
                  Abbrechen
                </button>
                <button type="submit" className="btn-primary" disabled={isSaving}>
                  {isSaving ? 'Wird gespeichert...' : editingType ? 'Speichern' : 'Erstellen'}
                </button>
              </div>
            </form>
          )}

          {/* Table */}
          {isLoading ? (
            <p>Lade Metalltypen...</p>
          ) : (
            <table className="metal-inventory-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Anzeigename</th>
                  <th>Code</th>
                  <th>Basismetall</th>
                  <th>Feingehalt</th>
                  <th>Farbe</th>
                  <th>Typ</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {metalTypes.map((option) => (
                  <tr
                    key={option.code}
                    style={option.is_builtin ? { opacity: 0.65 } : {}}
                  >
                    <td>
                      {option.color && (
                        <span
                          style={{
                            display: 'inline-block',
                            width: '12px',
                            height: '12px',
                            borderRadius: '50%',
                            background: option.color,
                            border: '1px solid rgba(0,0,0,0.2)',
                            marginRight: '6px',
                            verticalAlign: 'middle',
                          }}
                        />
                      )}
                      {option.display_name}
                    </td>
                    <td>
                      <code style={{ fontSize: '0.8rem' }}>{option.code}</code>
                    </td>
                    <td>{BASE_METAL_LABELS[option.base_metal] ?? option.base_metal}</td>
                    <td>
                      {(option.fine_content_ratio * 1000).toFixed(0)}‰
                      <span style={{ color: 'var(--color-muted, #888)', marginLeft: '4px', fontSize: '0.8rem' }}>
                        ({(option.fine_content_ratio * 100).toFixed(1)} %)
                      </span>
                    </td>
                    <td>
                      {option.color ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span
                            style={{
                              display: 'inline-block',
                              width: '20px',
                              height: '20px',
                              borderRadius: '4px',
                              background: option.color,
                              border: '1px solid rgba(0,0,0,0.2)',
                            }}
                          />
                          <code style={{ fontSize: '0.75rem' }}>{option.color}</code>
                        </span>
                      ) : (
                        <span style={{ color: 'var(--color-muted, #aaa)' }}>—</span>
                      )}
                    </td>
                    <td>
                      {option.is_builtin ? (
                        <span
                          style={{
                            fontSize: '0.75rem',
                            background: 'var(--color-primary-light, #e3f2fd)',
                            color: 'var(--color-primary, #1565c0)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          Standard
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: '0.75rem',
                            background: 'var(--color-success-light, #e8f5e9)',
                            color: 'var(--color-success-dark, #2e7d32)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          Benutzerdefiniert
                        </span>
                      )}
                    </td>
                    <td>
                      {option.is_builtin ? (
                        <span style={{ color: 'var(--color-muted, #aaa)', fontSize: '0.8rem' }}>
                          schreibgeschutzt
                        </span>
                      ) : (
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button
                            className="btn-secondary"
                            style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                            onClick={() => openEdit(option)}
                          >
                            Bearbeiten
                          </button>
                          <button
                            style={{
                              padding: '4px 10px',
                              fontSize: '0.8rem',
                              background: 'var(--color-error, #dc3545)',
                              color: '#fff',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                            }}
                            onClick={() => handleDeactivate(option)}
                          >
                            Deaktivieren
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};
