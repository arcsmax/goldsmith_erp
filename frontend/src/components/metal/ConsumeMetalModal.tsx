// ConsumeMetalModal — record metal consumption against an order (W4-03).
// Supports FIFO, LIFO, AVERAGE and SPECIFIC costing methods; a preview call
// shows the cost breakdown before the user commits. Orders and batches load
// through useQuery (both legacy plain lists); preview and booking are
// mutations, and a booking invalidates the metal-inventory root.
import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { metalInventoryApi } from '../../api/metal-inventory';
import { ordersApi } from '../../api/orders';
import { queryKeys } from '../../api/queryKeys';
import type { MetalType, CostingMethod, OrderMaterialAllocation } from '../../types';
import { useMetalTypes } from '../../hooks/useMetalTypes';
import { getStatusLabel } from '../../design/status';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Field, Modal } from '../../ui';
import { formatPreciseWeight, formatWeight, METAL_TYPES, metalLabelWithPurity } from './metalLabels';

interface ConsumeMetalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const ORDER_LIMIT = 500;
const ACTIVE_ORDER_STATUSES: ReadonlySet<string> = new Set([
  'in_progress',
  'confirmed',
  'new',
  'draft',
  'waiting_for_fitting',
  'fitting_done',
  'ready_for_setting',
  'quality_check',
]);

const COSTING_METHODS: { value: CostingMethod; label: string; description: string }[] = [
  { value: 'fifo', label: 'FIFO', description: 'Älteste Charge zuerst' },
  { value: 'lifo', label: 'LIFO', description: 'Neueste Charge zuerst' },
  { value: 'average', label: 'Durchschnitt', description: 'Gewichteter Durchschnittspreis' },
  { value: 'specific', label: 'Spezifisch', description: 'Bestimmte Charge auswählen' },
];

const FALLBACK_OPTIONS = METAL_TYPES.map((value) => ({ value, label: metalLabelWithPurity(value) }));

interface ConsumeForm {
  orderId: number | '';
  metalType: MetalType | '';
  weightG: string;
  costingMethod: CostingMethod;
  specificPurchaseId: number | '';
  notes: string;
}

const EMPTY_FORM: ConsumeForm = {
  orderId: '',
  metalType: '',
  weightG: '',
  costingMethod: 'fifo',
  specificPurchaseId: '',
  notes: '',
};

function parseWeight(value: string): number {
  return parseFloat(value.replace(',', '.'));
}

function isComplete(form: ConsumeForm): boolean {
  const weight = parseWeight(form.weightG);
  if (!form.orderId || !form.metalType || !Number.isFinite(weight) || weight <= 0) return false;
  return form.costingMethod !== 'specific' || Boolean(form.specificPurchaseId);
}

function useConsumeData(isOpen: boolean, metalType: MetalType | '') {
  const orders = useQuery({
    queryKey: queryKeys.orders.legacyList(ORDER_LIMIT),
    queryFn: () => ordersApi.getAll({ limit: ORDER_LIMIT }),
    enabled: isOpen,
  });
  const batchParams = { metal_type: metalType || undefined, include_depleted: false };
  const batches = useQuery({
    queryKey: queryKeys.metalInventory.purchaseList(batchParams),
    queryFn: () =>
      metalInventoryApi.listPurchases({ metal_type: metalType as MetalType, include_depleted: false }),
    enabled: isOpen && Boolean(metalType),
  });
  return { orders, batches };
}

const PreviewTable: React.FC<{ preview: OrderMaterialAllocation }> = ({ preview }) => (
  <section className="consume-preview" aria-label="Kostenvorschau">
    <h3 className="consume-preview__title">Kostenvorschau</h3>
    <table className="ui-table">
      <thead>
        <tr>
          <th>Charge</th>
          <th className="ui-align-end">Gewicht</th>
          <th className="ui-align-end">Preis/g</th>
          <th className="ui-align-end">Kosten</th>
        </tr>
      </thead>
      <tbody>
        {preview.allocations.map((alloc) => (
          <tr key={alloc.metal_purchase_id}>
            <td>#{alloc.metal_purchase_id}</td>
            <td className="ui-align-end ui-num">{formatPreciseWeight(alloc.weight_allocated_g)}</td>
            <td className={`ui-align-end ${MONEY_CLASS}`}>{formatEur(alloc.price_per_gram)}</td>
            <td className={`ui-align-end ${MONEY_CLASS}`}>{formatEur(alloc.cost)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" colSpan={2}>
            Gesamt ({preview.costing_method.toUpperCase()})
          </th>
          <td className="ui-align-end ui-num">{formatPreciseWeight(preview.required_weight_g)}</td>
          <td className={`ui-align-end ${MONEY_CLASS}`}>
            <strong>{formatEur(preview.total_cost)}</strong>
          </td>
        </tr>
      </tfoot>
    </table>
  </section>
);

export const ConsumeMetalModal: React.FC<ConsumeMetalModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const queryClient = useQueryClient();
  const { metalTypes: allMetalTypes, isLoading: isLoadingMetalTypes } = useMetalTypes();
  const [form, setForm] = useState<ConsumeForm>(EMPTY_FORM);
  const { orders, batches } = useConsumeData(isOpen, form.metalType);

  const preview = useMutation({
    mutationFn: (f: ConsumeForm) =>
      metalInventoryApi.previewAllocation({
        metal_type: f.metalType as MetalType,
        required_weight_g: parseWeight(f.weightG),
        costing_method: f.costingMethod,
        specific_purchase_id:
          f.costingMethod === 'specific' && f.specificPurchaseId ? Number(f.specificPurchaseId) : undefined,
      }),
  });

  const book = useMutation({
    mutationFn: (f: ConsumeForm) =>
      metalInventoryApi.consumeMaterial(
        {
          order_id: Number(f.orderId),
          weight_used_g: parseWeight(f.weightG),
          costing_method: f.costingMethod,
          metal_purchase_id:
            f.costingMethod === 'specific' && f.specificPurchaseId ? Number(f.specificPurchaseId) : undefined,
          notes: f.notes.trim() || undefined,
        },
        f.metalType as MetalType,
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.metalInventory.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]);
      onSuccess();
      onClose();
    },
  });

  // A fresh form every time the dialog opens.
  useEffect(() => {
    if (!isOpen) return;
    setForm(EMPTY_FORM);
    preview.reset();
    book.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only on open
  }, [isOpen]);

  const update = (patch: Partial<ConsumeForm>) => {
    setForm((prev) => ({ ...prev, ...patch }));
    preview.reset();
  };

  const complete = isComplete(form);
  const isDirty = form !== EMPTY_FORM;
  const activeOrders = (orders.data ?? []).filter((o) => ACTIVE_ORDER_STATUSES.has(o.status));
  const metalOptions =
    isLoadingMetalTypes || allMetalTypes.length === 0
      ? FALLBACK_OPTIONS
      : allMetalTypes.map((o) => ({ value: o.code, label: o.display_name }));
  const availableBatches = batches.data ?? [];
  const previewData = preview.data ? { ...preview.data, order_id: Number(form.orderId) } : null;

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Verbrauch erfassen"
      size="lg"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={book.isPending}>
            Abbrechen
          </Button>
          <Button
            variant="secondary"
            onClick={() => preview.mutate(form)}
            disabled={!complete || book.isPending}
            loading={preview.isPending}
          >
            Vorschau anzeigen
          </Button>
          <Button onClick={() => book.mutate(form)} disabled={!complete} loading={book.isPending}>
            Verbrauch buchen
          </Button>
        </>
      }
    >
      <div className="metal-form">
        <Field
          label="Auftrag"
          name="consume-order"
          required
          help={orders.isError ? 'Aufträge konnten nicht geladen werden.' : undefined}
        >
          <select
            value={form.orderId}
            onChange={(e) => update({ orderId: e.target.value ? Number(e.target.value) : '' })}
            disabled={orders.isPending || book.isPending}
          >
            <option value="">{orders.isPending ? 'Aufträge werden geladen …' : 'Auftrag auswählen'}</option>
            {activeOrders.map((o) => (
              <option key={o.id} value={o.id}>
                #{o.id} – {o.title} ({getStatusLabel('order', o.status)})
              </option>
            ))}
          </select>
        </Field>

        <Field label="Metalltyp" name="consume-metal-type" required>
          <select
            value={form.metalType}
            onChange={(e) =>
              update({ metalType: e.target.value as MetalType | '', specificPurchaseId: '' })
            }
            disabled={book.isPending || isLoadingMetalTypes}
          >
            <option value="">Metalltyp auswählen</option>
            {metalOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Gewicht" name="consume-weight" required inputMode="decimal" suffix="g">
          <input
            type="text"
            value={form.weightG}
            onChange={(e) => update({ weightG: e.target.value })}
            placeholder="z. B. 4,2"
            disabled={book.isPending}
          />
        </Field>

        <fieldset className="costing-methods">
          <legend className="ui-field__label">Bewertungsmethode</legend>
          {COSTING_METHODS.map((m) => (
            <label
              key={m.value}
              className={`costing-method${form.costingMethod === m.value ? ' costing-method--selected' : ''}`}
            >
              <input
                type="radio"
                name="costing-method"
                value={m.value}
                checked={form.costingMethod === m.value}
                onChange={() => update({ costingMethod: m.value })}
                disabled={book.isPending}
              />
              <span className="costing-method__label">{m.label}</span>
              <span className="costing-method__desc">{m.description}</span>
            </label>
          ))}
        </fieldset>

        {form.costingMethod === 'specific' && (
          <Field
            label="Charge"
            name="consume-batch"
            required
            help={
              !form.metalType
                ? 'Bitte zuerst den Metalltyp auswählen.'
                : batches.isSuccess && availableBatches.length === 0
                  ? 'Keine aktiven Chargen für diesen Metalltyp.'
                  : undefined
            }
          >
            <select
              value={form.specificPurchaseId}
              onChange={(e) => update({ specificPurchaseId: e.target.value ? Number(e.target.value) : '' })}
              disabled={!form.metalType || batches.isFetching || book.isPending}
            >
              <option value="">{batches.isFetching ? 'Chargen werden geladen …' : 'Charge auswählen'}</option>
              {availableBatches.map((b) => (
                <option key={b.id} value={b.id}>
                  #{b.id} – {b.supplier ?? 'Unbekannt'} – {formatWeight(b.remaining_weight_g)} verbleibend
                  zu {formatEur(b.price_per_gram)}/g
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label="Notiz" name="consume-notes">
          <textarea
            rows={2}
            value={form.notes}
            onChange={(e) => update({ notes: e.target.value })}
            placeholder="z. B. Ringfertigung – Kundenwunsch Rotgold"
            disabled={book.isPending}
          />
        </Field>

        {preview.isError && (
          <p className="metal-form__error" role="alert">
            {getErrorMessage(preview.error, 'Vorschau konnte nicht geladen werden.')}
          </p>
        )}
        {previewData && <PreviewTable preview={previewData} />}
        {book.isError && (
          <p className="metal-form__error" role="alert">
            {getErrorMessage(book.error, 'Verbrauch konnte nicht gespeichert werden.')}
          </p>
        )}
      </div>
    </Modal>
  );
};
