// Metal Purchase Form Modal — src/ui Modal + Field (W4-03).
// Create sends the full purchase; edit sends metadata only (the backend's
// PATCH does not accept weight, price or metal type, so those fields are
// read-only when editing).
import React, { useEffect, useMemo, useState } from 'react';
import type {
  MetalPurchaseListItem,
  MetalPurchaseCreateInput,
  MetalPurchaseUpdateInput,
  MetalType,
} from '../../types';
import { useMetalTypes } from '../../hooks/useMetalTypes';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Field, Modal } from '../../ui';
import { METAL_TYPES, metalLabelWithPurity } from './metalLabels';

interface MetalPurchaseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: MetalPurchaseCreateInput | MetalPurchaseUpdateInput) => Promise<void>;
  purchase?: MetalPurchaseListItem | null;
  isLoading?: boolean;
}

interface FormData {
  date_purchased: string;
  metal_type: MetalType | '';
  weight_g: string;
  price_total: string;
  supplier: string;
  invoice_number: string;
  notes: string;
  lot_number: string;
}

type FormErrors = Partial<Record<'metal_type' | 'weight_g' | 'price_total', string>>;

const FORM_ID = 'metal-purchase-form';
const LOT_SUFFIX_LENGTH = 4;
const BASE_METAL_LABELS: Record<string, string> = {
  gold: 'Gold',
  silver: 'Silber',
  platinum: 'Platin',
  palladium: 'Palladium',
};

type OptionGroup = { category: string; options: Array<{ value: string; label: string }> };

/** Static options while the metal-types API is loading. */
const FALLBACK_GROUPS: OptionGroup[] = [
  { category: 'Metalle', options: METAL_TYPES.map((value) => ({ value, label: metalLabelWithPurity(value) })) },
];

function today(): string {
  return new Date().toISOString().split('T')[0];
}

function emptyForm(): FormData {
  return {
    date_purchased: today(),
    metal_type: '',
    weight_g: '',
    price_total: '',
    supplier: '',
    invoice_number: '',
    notes: '',
    lot_number: '',
  };
}

function formFromPurchase(purchase: MetalPurchaseListItem): FormData {
  return {
    date_purchased: purchase.date_purchased
      ? new Date(purchase.date_purchased).toISOString().split('T')[0]
      : today(),
    metal_type: purchase.metal_type,
    weight_g: String(purchase.weight_g),
    // The list endpoint has no price_total; show price_per_gram * weight.
    price_total: (purchase.price_per_gram * purchase.weight_g).toFixed(2),
    supplier: purchase.supplier || '',
    invoice_number: '',
    notes: '',
    lot_number: '',
  };
}

function generateLotNumber(metalType: string, date: string): string {
  const d = new Date(date);
  const yymmdd = [d.getFullYear() % 100, d.getMonth() + 1, d.getDate()]
    .map((n) => String(n).padStart(2, '0'))
    .join('');
  const suffix = Math.random().toString(36).substring(2, 2 + LOT_SUFFIX_LENGTH).toUpperCase();
  return `${metalType.toUpperCase().replace(/_/g, '-')}-${yymmdd}-${suffix}`;
}

function parseDecimal(value: string): number {
  return parseFloat(value.replace(',', '.'));
}

function validate(form: FormData): FormErrors {
  const errors: FormErrors = {};
  if (!form.metal_type) errors.metal_type = 'Metalltyp fehlt. Bitte einen Metalltyp auswählen.';
  if (!(parseDecimal(form.weight_g) > 0)) errors.weight_g = 'Gewicht fehlt. Bitte in Gramm eingeben (größer als 0).';
  if (!(parseDecimal(form.price_total) > 0)) errors.price_total = 'Gesamtpreis fehlt. Bitte in Euro eingeben (größer als 0).';
  return errors;
}

function useGroupedOptions(): { groups: OptionGroup[]; isLoading: boolean } {
  const { groupedMetalTypes, isLoading } = useMetalTypes();
  const dynamic = Object.entries(groupedMetalTypes).map(([baseMetal, options]) => ({
    category: BASE_METAL_LABELS[baseMetal] ?? baseMetal,
    options: options.map((o) => ({ value: o.code, label: o.display_name })),
  }));
  return { groups: isLoading || dynamic.length === 0 ? FALLBACK_GROUPS : dynamic, isLoading };
}

export const MetalPurchaseFormModal: React.FC<MetalPurchaseFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  purchase,
  isLoading = false,
}) => {
  const isEditMode = Boolean(purchase);
  const { groups, isLoading: isLoadingTypes } = useGroupedOptions();
  const [formData, setFormData] = useState<FormData>(emptyForm);
  const [initial, setInitial] = useState<FormData>(emptyForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [autoLot, setAutoLot] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    const start = purchase ? formFromPurchase(purchase) : emptyForm();
    setFormData(start);
    setInitial(start);
    setAutoLot(!purchase);
    setErrors({});
  }, [isOpen, purchase]);

  const isDirty = useMemo(
    () => (Object.keys(initial) as (keyof FormData)[]).some((key) => initial[key] !== formData[key]),
    [formData, initial],
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setErrors((prev) => ({ ...prev, [name]: undefined }));
    setFormData((prev) => {
      const next = { ...prev, [name]: value };
      const regenerate = autoLot && (name === 'metal_type' || name === 'date_purchased');
      return regenerate && next.metal_type && next.date_purchased
        ? { ...next, lot_number: generateLotNumber(next.metal_type, next.date_purchased) }
        : next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const found = isEditMode ? {} : validate(formData);
    setErrors(found);
    const firstInvalid = Object.keys(found)[0];
    if (firstInvalid) {
      document.getElementById(`metal-purchase-${firstInvalid}`)?.focus();
      return;
    }
    const metadata: MetalPurchaseUpdateInput = {
      supplier: formData.supplier || undefined,
      invoice_number: formData.invoice_number || undefined,
      notes: formData.notes || undefined,
      lot_number: formData.lot_number || undefined,
    };
    if (isEditMode) {
      await onSubmit(metadata);
      return;
    }
    await onSubmit({
      ...metadata,
      date_purchased: formData.date_purchased,
      metal_type: formData.metal_type as MetalType,
      weight_g: parseDecimal(formData.weight_g),
      price_total: parseDecimal(formData.price_total),
    } satisfies MetalPurchaseCreateInput);
  };

  const weight = parseDecimal(formData.weight_g);
  const price = parseDecimal(formData.price_total);
  const pricePerGram = weight > 0 && price > 0 ? price / weight : null;

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={isEditMode ? 'Metalleinkauf bearbeiten' : 'Metalleinkauf anlegen'}
      size="lg"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button type="submit" form={FORM_ID} loading={isLoading}>
            {isEditMode ? 'Einkauf speichern' : 'Einkauf anlegen'}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="metal-form metal-form--grid" noValidate>
        <Field label="Kaufdatum" name="date_purchased" required>
          <input type="date" value={formData.date_purchased} onChange={handleChange} disabled={isEditMode} />
        </Field>

        <Field label="Metalltyp" name="metal_type" required error={errors.metal_type}>
          <select
            id="metal-purchase-metal_type"
            value={formData.metal_type}
            onChange={handleChange}
            disabled={isLoadingTypes || isEditMode}
          >
            <option value="">Metalltyp auswählen</option>
            {groups.map(({ category, options }) => (
              <optgroup key={category} label={category}>
                {options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>

        <Field label="Gewicht" name="weight_g" required inputMode="decimal" suffix="g" error={errors.weight_g}>
          <input
            id="metal-purchase-weight_g"
            type="text"
            value={formData.weight_g}
            onChange={handleChange}
            placeholder="100,00"
            disabled={isEditMode}
          />
        </Field>

        <Field
          label="Gesamtpreis"
          name="price_total"
          required
          inputMode="decimal"
          suffix="€"
          error={errors.price_total}
        >
          <input
            id="metal-purchase-price_total"
            type="text"
            value={formData.price_total}
            onChange={handleChange}
            placeholder="5000,00"
            disabled={isEditMode}
          />
        </Field>

        {pricePerGram !== null && (
          <p className="metal-form__calculated">
            Preis pro Gramm: <span className={MONEY_CLASS}>{formatEur(pricePerGram)}</span>
          </p>
        )}

        <Field label="Lieferant" name="supplier">
          <input type="text" value={formData.supplier} onChange={handleChange} placeholder="Edelmetall GmbH" />
        </Field>

        <Field label="Rechnungsnummer" name="invoice_number">
          <input type="text" value={formData.invoice_number} onChange={handleChange} placeholder="RE-2025-12345" />
        </Field>

        <div className="metal-form__lot">
          <Field label="Chargennummer" name="lot_number">
            <input
              type="text"
              value={formData.lot_number}
              onChange={handleChange}
              disabled={autoLot && !isEditMode}
              placeholder="GOLD-24K-250115-A3F2"
            />
          </Field>
          {!isEditMode && (
            <label className="metal-form__check">
              <input type="checkbox" checked={autoLot} onChange={(e) => setAutoLot(e.target.checked)} />
              Automatisch erzeugen
            </label>
          )}
        </div>

        <Field label="Notizen" name="notes" className="metal-form__full">
          <textarea value={formData.notes} onChange={handleChange} rows={3} placeholder="Zusätzliche Informationen …" />
        </Field>
      </form>
    </Modal>
  );
};
