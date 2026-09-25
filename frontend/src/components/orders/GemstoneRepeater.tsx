// GemstoneRepeater (W2-06, DOM-04): the "Steine" section of an order.
//
// Editable (order form): one row per stone with Steinart, Anzahl, Karat,
// Farbe/Reinheit, Form, Fassungsart and Kundenstein; each row is saved on
// its own ("Stein speichern") because stones live in their own table.
// Read-only (Übersicht, VIEWER): one German line per stone. The backend
// already strips cost / design fields by role; `canViewCost` only decides
// whether the purchase-price input is rendered.
import { useCallback, useEffect, useId, useState } from 'react';
import { gemstonesApi, type Gemstone, type GemstoneCreateInput } from '../../api/gemstones';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import { GemstoneLines } from './GemstoneList';
import { SETTING_TYPE_OPTIONS } from './orderIntakeOptions';

interface GemstoneRepeaterProps {
  orderId: number;
  canEdit: boolean;
  canViewCost: boolean;
}

interface Draft {
  key: string;
  id?: number;
  type: string;
  quantity: string;
  carat: string;
  color: string;
  quality: string;
  shape: string;
  setting_type: string;
  is_customer_stone: boolean;
  cost: string;
}

let draftCounter = 0;
const nextKey = (): string => `neu-${(draftCounter += 1)}`;

function toDraft(stone: Gemstone): Draft {
  return {
    key: `stein-${stone.id}`,
    id: stone.id,
    type: stone.type,
    quantity: String(stone.quantity ?? 1),
    carat: stone.carat != null ? String(stone.carat).replace('.', ',') : '',
    color: stone.color ?? '',
    quality: stone.quality ?? '',
    shape: stone.shape ?? '',
    setting_type: stone.setting_type ?? '',
    is_customer_stone: Boolean(stone.is_customer_stone),
    cost: stone.cost != null ? String(stone.cost).replace('.', ',') : '',
  };
}

const emptyDraft = (): Draft => ({
  key: nextKey(),
  type: '',
  quantity: '1',
  carat: '',
  color: '',
  quality: '',
  shape: '',
  setting_type: '',
  is_customer_stone: false,
  cost: '',
});

function parseDecimal(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function toPayload(draft: Draft, canViewCost: boolean): GemstoneCreateInput {
  const payload: GemstoneCreateInput = {
    type: draft.type.trim(),
    quantity: Math.max(1, parseInt(draft.quantity, 10) || 1),
    carat: parseDecimal(draft.carat),
    color: draft.color.trim() || null,
    quality: draft.quality.trim() || null,
    shape: draft.shape.trim() || null,
    setting_type: (draft.setting_type || null) as GemstoneCreateInput['setting_type'],
    is_customer_stone: draft.is_customer_stone,
  };
  if (canViewCost && !draft.is_customer_stone) {
    return { ...payload, cost: parseDecimal(draft.cost) ?? 0 };
  }
  return payload;
}

export function GemstoneRepeater({ orderId, canEdit, canViewCost }: GemstoneRepeaterProps) {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const headingId = useId();
  const [stones, setStones] = useState<Gemstone[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setIsLoading(true);
      setLoadError(null);
      const data = await gemstonesApi.list(orderId);
      setStones(data);
      setDrafts(data.map(toDraft));
    } catch (err: unknown) {
      logError('GemstoneRepeater.load', err);
      setLoadError('Steine konnten nicht geladen werden.');
    } finally {
      setIsLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = (key: string, patch: Partial<Draft>) => {
    setDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  };

  const saveDraft = async (draft: Draft) => {
    if (!draft.type.trim()) {
      showToast('Steinart fehlt. Bitte die Steinart eingeben.', 'error');
      return;
    }
    setBusyKey(draft.key);
    try {
      const payload = toPayload(draft, canViewCost);
      const saved =
        draft.id === undefined
          ? await gemstonesApi.create(orderId, payload)
          : await gemstonesApi.update(draft.id, payload);
      setStones((prev) => [...prev.filter((s) => s.id !== saved.id), saved]);
      setDrafts((prev) => prev.map((d) => (d.key === draft.key ? toDraft(saved) : d)));
      showToast('Stein gespeichert', 'success');
    } catch (err: unknown) {
      logError('GemstoneRepeater.save', err);
      showToast('Stein konnte nicht gespeichert werden.', 'error');
    } finally {
      setBusyKey(null);
    }
  };

  const removeDraft = async (draft: Draft) => {
    if (draft.id === undefined) {
      setDrafts((prev) => prev.filter((d) => d.key !== draft.key));
      return;
    }
    const confirmed = await showConfirm({
      title: 'Stein entfernen?',
      message: `„${draft.type}“ wird aus dem Auftrag entfernt.`,
      confirmLabel: 'Stein entfernen',
      variant: 'danger',
    });
    if (!confirmed) return;
    const stoneId = draft.id;
    setBusyKey(draft.key);
    try {
      await gemstonesApi.remove(stoneId);
      setStones((prev) => prev.filter((s) => s.id !== stoneId));
      setDrafts((prev) => prev.filter((d) => d.key !== draft.key));
      showToast('Stein entfernt', 'success');
    } catch (err: unknown) {
      logError('GemstoneRepeater.remove', err);
      showToast('Stein konnte nicht entfernt werden.', 'error');
    } finally {
      setBusyKey(null);
    }
  };

  const addButton = canEdit && (
    <button
      type="button"
      className="btn-secondary"
      onClick={() => setDrafts((prev) => [...prev, emptyDraft()])}
    >
      Stein hinzufügen
    </button>
  );

  const body = (() => {
    if (isLoading) return <p role="status">Steine werden geladen…</p>;
    if (loadError) {
      return (
        <p role="alert">
          {loadError}{' '}
          <button type="button" className="btn-secondary" onClick={() => void load()}>
            Erneut laden
          </button>
        </p>
      );
    }
    if (!canEdit) return <GemstoneLines stones={stones} />;
    if (drafts.length === 0) return <p>Noch keine Steine erfasst.</p>;
    return drafts.map((draft, index) => (
      <GemstoneRow
        key={draft.key}
        draft={draft}
        position={index + 1}
        canViewCost={canViewCost}
        isBusy={busyKey === draft.key}
        onChange={(patch) => updateDraft(draft.key, patch)}
        onSave={() => void saveDraft(draft)}
        onRemove={() => void removeDraft(draft)}
      />
    ));
  })();

  return (
    <section className="details-section gemstone-repeater" aria-labelledby={headingId}>
      <h3 id={headingId}>Steine</h3>
      {body}
      {addButton}
    </section>
  );
}

interface GemstoneRowProps {
  draft: Draft;
  position: number;
  canViewCost: boolean;
  isBusy: boolean;
  onChange: (patch: Partial<Draft>) => void;
  onSave: () => void;
  onRemove: () => void;
}

function GemstoneRow({ draft, position, canViewCost, isBusy, onChange, onSave, onRemove }: GemstoneRowProps) {
  const id = useId();
  const suffix = ` (Stein ${position})`;
  const text = (name: keyof Draft, label: string, extra: Record<string, string> = {}) => (
    <div className="form-group">
      <label htmlFor={`${id}-${name}`}>
        {label}
      </label>
      <input
        id={`${id}-${name}`}
        aria-label={`${label}${suffix}`}
        type="text"
        value={draft[name] as string}
        onChange={(e) => onChange({ [name]: e.target.value } as Partial<Draft>)}
        {...extra}
      />
    </div>
  );

  return (
    <fieldset
      className="gemstone-row"
      disabled={isBusy}
      onKeyDown={(e) => {
        // Enter in a stone field must not submit the surrounding order form.
        if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') e.preventDefault();
      }}
    >
      <legend>Stein {position}</legend>
      <div className="form-row">
        {text('type', 'Steinart', { placeholder: 'z.B. Diamant' })}
        {text('quantity', 'Anzahl', { inputMode: 'numeric' })}
        {text('carat', 'Karat je Stein', { inputMode: 'decimal' })}
      </div>
      <div className="form-row">
        {text('color', 'Farbe')}
        {text('quality', 'Reinheit')}
        {text('shape', 'Form', { placeholder: 'z.B. rund' })}
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor={`${id}-setting`}>Fassungsart</label>
          <select
            id={`${id}-setting`}
            aria-label={`Fassungsart${suffix}`}
            value={draft.setting_type}
            onChange={(e) => onChange({ setting_type: e.target.value })}
          >
            <option value="">— keine Angabe —</option>
            {SETTING_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group form-group--checkbox">
          <label className="checkbox-label">
            <input
              type="checkbox"
              aria-label={`Kundenstein${suffix}`}
              checked={draft.is_customer_stone}
              onChange={(e) =>
                onChange({ is_customer_stone: e.target.checked, cost: e.target.checked ? '' : draft.cost })
              }
            />
            <span>Kundenstein</span>
          </label>
        </div>
        {canViewCost && !draft.is_customer_stone && text('cost', 'Einkaufspreis je Stein (€)', { inputMode: 'decimal' })}
      </div>
      <div className="gemstone-row-actions">
        <button type="button" className="btn-primary" onClick={onSave}>
          Stein speichern
        </button>
        <button type="button" className="btn-secondary" onClick={onRemove}>
          Stein entfernen
        </button>
      </div>
    </fieldset>
  );
}

export default GemstoneRepeater;
