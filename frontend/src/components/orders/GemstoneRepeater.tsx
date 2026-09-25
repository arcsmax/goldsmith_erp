// GemstoneRepeater (W2-06, DOM-04): the "Steine" section of an order.
//
// Editable (order form): one row per stone with Steinart, Anzahl, Karat,
// Farbe/Reinheit, Form, Fassungsart and Kundenstein; each row is saved on
// its own ("Stein speichern") because stones live in their own table.
// Read-only (Übersicht, VIEWER): one German line per stone. The backend
// already strips cost / design fields by role; `canViewCost` only decides
// whether the purchase-price input is rendered.
//
// W4-03: the saved stones come from TanStack Query (shared with
// GemstoneList); only unsaved edits and new rows are local state.
import { useId, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { gemstonesApi, type Gemstone, type GemstoneCreateInput } from '../../api/gemstones';
import { queryKeys } from '../../api/queryKeys';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import { Button, Card, EmptyState, Field, PageState, type FieldInputMode } from '../../ui';
import { GEMSTONES_EMPTY_TITLE, GemstoneLines, gemstonesQuery, gemstonesState } from './GemstoneList';
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

type StoneMutation =
  | { kind: 'save'; draft: Draft; payload: GemstoneCreateInput }
  | { kind: 'remove'; draft: Draft; stoneId: number };

export function GemstoneRepeater({ orderId, canEdit, canViewCost }: GemstoneRepeaterProps) {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const queryClient = useQueryClient();
  const query = useQuery(gemstonesQuery(orderId));
  const stones = query.data ?? [];
  // Local edits only: unsaved changes of saved stones (by key) and new rows.
  const [edits, setEdits] = useState<Readonly<Record<string, Draft>>>({});
  const [newDrafts, setNewDrafts] = useState<readonly Draft[]>([]);
  const drafts: Draft[] = [
    ...stones.map((stone) => edits[`stein-${stone.id}`] ?? toDraft(stone)),
    ...newDrafts,
  ];

  const dropLocal = (key: string) => {
    setEdits((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)));
    setNewDrafts((prev) => prev.filter((d) => d.key !== key));
  };

  const setStones = (update: (prev: Gemstone[]) => Gemstone[]) =>
    queryClient.setQueryData<Gemstone[]>(queryKeys.orders.gemstones(orderId), (prev) =>
      update(prev ?? []),
    );

  const mutation = useMutation({
    mutationFn: async (action: StoneMutation): Promise<Gemstone | null> => {
      if (action.kind === 'remove') {
        await gemstonesApi.remove(action.stoneId);
        return null;
      }
      return action.draft.id === undefined
        ? gemstonesApi.create(orderId, action.payload)
        : gemstonesApi.update(action.draft.id, action.payload);
    },
    onSuccess: (saved, action) => {
      dropLocal(action.draft.key);
      if (action.kind === 'remove') {
        setStones((prev) => prev.filter((s) => s.id !== action.stoneId));
        showToast('Stein entfernt', 'success');
      } else if (saved) {
        setStones((prev) => [...prev.filter((s) => s.id !== saved.id), saved]);
        showToast('Stein gespeichert', 'success');
      }
      // The order total and the Übersicht list depend on the stones.
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders.detail(orderId) });
    },
    onError: (err: unknown, action) => {
      const isRemove = action.kind === 'remove';
      logError(isRemove ? 'GemstoneRepeater.remove' : 'GemstoneRepeater.save', err);
      showToast(
        isRemove ? 'Stein konnte nicht entfernt werden.' : 'Stein konnte nicht gespeichert werden.',
        'error',
      );
    },
  });
  const busyKey = mutation.isPending ? (mutation.variables?.draft.key ?? null) : null;

  const updateDraft = (draft: Draft, patch: Partial<Draft>) => {
    const next = { ...draft, ...patch };
    if (draft.id === undefined) {
      setNewDrafts((prev) => prev.map((d) => (d.key === draft.key ? next : d)));
    } else {
      setEdits((prev) => ({ ...prev, [draft.key]: next }));
    }
  };

  const saveDraft = (draft: Draft) => {
    if (!draft.type.trim()) {
      showToast('Steinart fehlt. Bitte die Steinart eingeben.', 'error');
      return;
    }
    mutation.mutate({ kind: 'save', draft, payload: toPayload(draft, canViewCost) });
  };

  const removeDraft = async (draft: Draft) => {
    if (draft.id === undefined) {
      dropLocal(draft.key);
      return;
    }
    const confirmed = await showConfirm({
      title: 'Stein entfernen?',
      message: `„${draft.type}“ wird aus dem Auftrag entfernt.`,
      confirmLabel: 'Stein entfernen',
      variant: 'danger',
    });
    if (!confirmed) return;
    mutation.mutate({ kind: 'remove', draft, stoneId: draft.id });
  };

  const addStone = () => setNewDrafts((prev) => [...prev, emptyDraft()]);
  const addButton = (
    <Button variant="secondary" icon="plus" onClick={addStone}>
      Stein hinzufügen
    </Button>
  );

  const renderBody = () => {
    if (!canEdit) return <GemstoneLines stones={stones} />;
    if (drafts.length === 0) {
      return (
        <EmptyState icon="gem" title={GEMSTONES_EMPTY_TITLE} headingLevel={3} action={addButton} />
      );
    }
    return (
      <>
        {drafts.map((draft, index) => (
          <GemstoneRow
            key={draft.key}
            draft={draft}
            position={index + 1}
            canViewCost={canViewCost}
            isBusy={busyKey === draft.key}
            onChange={(patch) => updateDraft(draft, patch)}
            onSave={() => saveDraft(draft)}
            onRemove={() => void removeDraft(draft)}
          />
        ))}
        <div className="gemstone-row-actions">{addButton}</div>
      </>
    );
  };

  return (
    <Card title="Steine" headingLevel={3} className="gemstone-repeater">
      <PageState state={gemstonesState(query)} skeleton="list" skeletonCount={2}>
        {renderBody()}
      </PageState>
    </Card>
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
  const text = (
    name: keyof Draft,
    label: string,
    options: { placeholder?: string; inputMode?: FieldInputMode; unit?: string } = {},
  ) => (
    <Field label={label} name={`${name}-${position}`} inputMode={options.inputMode} suffix={options.unit}>
      <input
        id={`${id}-${name}`}
        aria-label={`${label}${suffix}`}
        type="text"
        placeholder={options.placeholder}
        value={draft[name] as string}
        onChange={(e) => onChange({ [name]: e.target.value } as Partial<Draft>)}
      />
    </Field>
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
        {text('type', 'Steinart', { placeholder: 'z. B. Diamant' })}
        {text('quantity', 'Anzahl', { inputMode: 'numeric' })}
        {text('carat', 'Karat je Stein', { inputMode: 'decimal', unit: 'ct' })}
      </div>
      <div className="form-row">
        {text('color', 'Farbe')}
        {text('quality', 'Reinheit')}
        {text('shape', 'Form', { placeholder: 'z. B. rund' })}
      </div>
      <div className="form-row">
        <Field label="Fassungsart" name={`setting-${position}`}>
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
        </Field>
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
        {canViewCost &&
          !draft.is_customer_stone &&
          text('cost', 'Einkaufspreis je Stein', { inputMode: 'decimal', unit: '€' })}
      </div>
      <div className="gemstone-row-actions">
        <Button variant="primary" loading={isBusy} onClick={onSave}>
          Stein speichern
        </Button>
        <Button variant="ghost" icon="trash" onClick={onRemove}>
          Stein entfernen
        </Button>
      </div>
    </fieldset>
  );
}

export default GemstoneRepeater;
