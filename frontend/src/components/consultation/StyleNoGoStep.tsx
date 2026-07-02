// StyleNoGoStep — Beratungs-Wizard step 4: No-Gos (customer-level, permanent
// blocklist) and Stilprofil (metal tones / finishes / stones / style words).
//
// Unlike the consultation-field steps (2, 3), this step has no pendingPatch:
// no-gos and the style profile live on the customer, not the consultation,
// and every add/delete/chip change hits its own endpoint immediately. A
// crash mid-wizard loses nothing here — the shared Weiter button never
// touches this data.
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import type { WizardStepProps } from '../../pages/ConsultationWizardPage';
import { customersApi } from '../../api/customers';
import { NoGo, NoGoCategory, NoGoCreateInput, StyleProfile } from '../../types';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
// Moved to labels.ts (kills the bundle coupling — see that file's header);
// re-exported here for backwards compatibility.
export { NO_GO_CATEGORY_LABELS } from './labels';
import { NO_GO_CATEGORY_LABELS } from './labels';

const NO_GO_CATEGORY_KEYS = Object.keys(NO_GO_CATEGORY_LABELS) as NoGoCategory[];

/** One-tap allergy shortcuts — the most common workshop allergens. */
const QUICK_ALLERGENS = ['Nickel', 'Kupfer', 'Silber'];

// Mirrors the backend's StyleProfile validation (consultation.py:
// `_StyleProfileItem = Annotated[str, StringConstraints(max_length=100)]`,
// each list `Field(None, max_length=50)`) — capping here means a runaway
// chip entry never reaches the API and triggers a 422.
const MAX_STYLE_ITEMS = 50;
const MAX_STYLE_ITEM_LENGTH = 100;

type StyleListField = keyof StyleProfile;

const STYLE_FIELDS: { field: StyleListField; label: string; placeholder: string }[] = [
  { field: 'metal_tones', label: 'Metallfarben', placeholder: 'z. B. Gelbgold, Enter zum Hinzufügen' },
  { field: 'finishes', label: 'Oberflächen', placeholder: 'z. B. matt, Enter zum Hinzufügen' },
  { field: 'stone_preferences', label: 'Steine', placeholder: 'z. B. Diamant, Enter zum Hinzufügen' },
  { field: 'style_words', label: 'Stil-Worte', placeholder: 'z. B. schlicht, Enter zum Hinzufügen' },
];

const EMPTY_STYLE_PROFILE: StyleProfile = {
  metal_tones: [],
  finishes: [],
  stone_preferences: [],
  style_words: [],
};

export const StyleNoGoStep: React.FC<WizardStepProps> = ({ consultation }) => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const customerId = consultation.customer_id;

  const [noGos, setNoGos] = useState<NoGo[]>([]);
  const [styleProfile, setStyleProfile] = useState<StyleProfile>(EMPTY_STYLE_PROFILE);
  const [isLoading, setIsLoading] = useState(true);

  // No-Go add form
  const [category, setCategory] = useState<NoGoCategory>('metal');
  const [value, setValue] = useState('');
  const [note, setNote] = useState('');
  const [isAddingNoGo, setIsAddingNoGo] = useState(false);
  const [addingQuickAllergen, setAddingQuickAllergen] = useState<string | null>(null);
  const [deletingNoGoId, setDeletingNoGoId] = useState<number | null>(null);

  // Stilprofil chip inputs — one draft value per field.
  const [styleInputs, setStyleInputs] = useState<Record<StyleListField, string>>({
    metal_tones: '',
    finishes: '',
    stone_preferences: '',
    style_words: '',
  });
  const [savingStyleField, setSavingStyleField] = useState<StyleListField | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        const [loadedNoGos, loadedProfile] = await Promise.all([
          customersApi.getNoGos(customerId),
          customersApi.getStyleProfile(customerId),
        ]);
        if (cancelled) return;
        setNoGos(loadedNoGos);
        setStyleProfile(loadedProfile);
      } catch (err) {
        logError('No-Gos/Stilprofil laden fehlgeschlagen', err);
        if (!cancelled) showToast('Stilprofil konnte nicht geladen werden', 'error');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [customerId, showToast]);

  /** Shared by the add-form submit and the quick-allergy chips. */
  const createNoGo = async (input: NoGoCreateInput): Promise<boolean> => {
    try {
      const created = await customersApi.addNoGo(customerId, input);
      setNoGos((prev) => [...prev, created]);
      return true;
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        showToast('Dieses No-Go existiert bereits', 'error');
        return false;
      }
      // NEVER log the raw error: err.config.data carries the request body
      // (allergy no-go values) and FastAPI 422s echo the input in the response.
      logError('No-Go anlegen fehlgeschlagen', err);
      showToast('No-Go konnte nicht angelegt werden', 'error');
      return false;
    }
  };

  const handleAddNoGo = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedValue = value.trim();
    if (!trimmedValue) return;
    setIsAddingNoGo(true);
    const ok = await createNoGo({
      category,
      value: trimmedValue,
      note: note.trim() || undefined,
    });
    setIsAddingNoGo(false);
    if (ok) {
      setValue('');
      setNote('');
    }
  };

  const handleQuickAllergen = async (allergen: string) => {
    setAddingQuickAllergen(allergen);
    await createNoGo({ category: 'allergy', value: allergen });
    setAddingQuickAllergen(null);
  };

  const handleDeleteNoGo = async (noGo: NoGo) => {
    const confirmed = await showConfirm({
      title: 'No-Go löschen',
      message: 'No-Go wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (!confirmed) return;
    setDeletingNoGoId(noGo.id);
    try {
      await customersApi.deleteNoGo(customerId, noGo.id);
      setNoGos((prev) => prev.filter((n) => n.id !== noGo.id));
    } catch (err) {
      logError('No-Go löschen fehlgeschlagen', err);
      showToast('No-Go konnte nicht gelöscht werden', 'error');
    } finally {
      setDeletingNoGoId(null);
    }
  };

  /** PATCHes only the changed list; server merges and is treated as truth. */
  const patchStyleField = async (field: StyleListField, nextList: string[]) => {
    setSavingStyleField(field);
    try {
      const updated = await customersApi.updateStyleProfile(customerId, { [field]: nextList });
      setStyleProfile(updated);
    } catch (err) {
      logError('Stilprofil speichern fehlgeschlagen', err);
      showToast('Stilprofil konnte nicht gespeichert werden', 'error');
    } finally {
      setSavingStyleField(null);
    }
  };

  const handleStyleInputKeyDown = (
    field: StyleListField,
    e: React.KeyboardEvent<HTMLInputElement>
  ) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const trimmed = styleInputs[field].trim();
    setStyleInputs((prev) => ({ ...prev, [field]: '' }));
    if (!trimmed || styleProfile[field].includes(trimmed)) return;
    // Client-side caps mirroring the backend (see MAX_STYLE_ITEMS/
    // MAX_STYLE_ITEM_LENGTH above) — reject BEFORE the PATCH instead of
    // letting a 422 surface as a generic save-failure toast.
    if (trimmed.length > MAX_STYLE_ITEM_LENGTH) {
      showToast(`Eintrag darf maximal ${MAX_STYLE_ITEM_LENGTH} Zeichen haben`, 'error');
      return;
    }
    if (styleProfile[field].length >= MAX_STYLE_ITEMS) {
      showToast(`Maximal ${MAX_STYLE_ITEMS} Einträge pro Liste`, 'error');
      return;
    }
    patchStyleField(field, [...styleProfile[field], trimmed]);
  };

  const handleRemoveStyleValue = (field: StyleListField, valueToRemove: string) => {
    patchStyleField(
      field,
      styleProfile[field].filter((entry) => entry !== valueToRemove)
    );
  };

  if (isLoading) {
    return <p>Lade No-Gos und Stilprofil...</p>;
  }

  return (
    <div className="style-no-go-step">
      <section>
        <h3>No-Gos — bitte unbedingt beachten</h3>

        {noGos.length > 0 && (
          <div className="no-go-list">
            {noGos.map((noGo) => (
              <div className="no-go-item" key={noGo.id}>
                <span>
                  <strong>{NO_GO_CATEGORY_LABELS[noGo.category]}:</strong> {noGo.value}
                  {noGo.note && <span className="field-hint"> — {noGo.note}</span>}
                </span>
                <button
                  type="button"
                  className="btn-danger"
                  onClick={() => handleDeleteNoGo(noGo)}
                  disabled={deletingNoGoId === noGo.id}
                  aria-label={`${noGo.value} löschen`}
                >
                  {deletingNoGoId === noGo.id ? '...' : 'Löschen'}
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="wizard-field">
          <label>Schnellauswahl Allergien</label>
          <div className="chip-group" role="group" aria-label="Schnellauswahl Allergien">
            {QUICK_ALLERGENS.map((allergen) => (
              <button
                key={allergen}
                type="button"
                className="chip"
                onClick={() => handleQuickAllergen(allergen)}
                disabled={addingQuickAllergen === allergen}
              >
                {addingQuickAllergen === allergen ? '...' : allergen}
              </button>
            ))}
          </div>
        </div>

        <form className="wizard-field-row" onSubmit={handleAddNoGo}>
          <div className="wizard-field">
            <label htmlFor="no_go_category">Kategorie</label>
            <select
              id="no_go_category"
              value={category}
              onChange={(e) => setCategory(e.target.value as NoGoCategory)}
              disabled={isAddingNoGo}
            >
              {NO_GO_CATEGORY_KEYS.map((key) => (
                <option key={key} value={key}>
                  {NO_GO_CATEGORY_LABELS[key]}
                </option>
              ))}
            </select>
          </div>
          <div className="wizard-field">
            <label htmlFor="no_go_value">Wert</label>
            <input
              id="no_go_value"
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="z. B. Nickel"
              disabled={isAddingNoGo}
            />
          </div>
          <div className="wizard-field">
            <label htmlFor="no_go_note">Notiz (optional)</label>
            <input
              id="no_go_note"
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={isAddingNoGo}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={isAddingNoGo || !value.trim()}>
            {isAddingNoGo ? 'Speichert...' : 'Hinzufügen'}
          </button>
        </form>
      </section>

      <section>
        <h3>Stilprofil</h3>
        {STYLE_FIELDS.map(({ field, label, placeholder }) => (
          <div className="wizard-field" key={field}>
            <label htmlFor={`style_${field}`}>{label}</label>
            {styleProfile[field].length > 0 && (
              <div className="chip-group">
                {styleProfile[field].map((entry) => (
                  <button
                    key={entry}
                    type="button"
                    className="chip selected chip-removable"
                    onClick={() => handleRemoveStyleValue(field, entry)}
                    disabled={savingStyleField === field}
                    aria-label={`${entry} entfernen`}
                  >
                    {entry}
                  </button>
                ))}
              </div>
            )}
            <input
              id={`style_${field}`}
              type="text"
              value={styleInputs[field]}
              onChange={(e) => setStyleInputs((prev) => ({ ...prev, [field]: e.target.value }))}
              onKeyDown={(e) => handleStyleInputKeyDown(field, e)}
              placeholder={placeholder}
              disabled={savingStyleField === field}
            />
          </div>
        ))}
      </section>
    </div>
  );
};
