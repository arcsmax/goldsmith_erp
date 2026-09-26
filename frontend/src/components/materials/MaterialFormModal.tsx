// Material Form Modal — src/ui Modal + Field (W4-03).
import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { MaterialType, MaterialCreateInput, MaterialUpdateInput } from '../../types';
import { MaterialCreateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Field, Modal } from '../../ui';

/** Form payload: the API fields plus the chosen image, uploaded after save. */
export type MaterialFormSubmit = (MaterialCreateInput | MaterialUpdateInput) & { _imageFile?: File };

interface MaterialFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: MaterialFormSubmit) => Promise<void>;
  material?: MaterialType | null;
  isLoading?: boolean;
}

const FORM_ID = 'material-form';
const DEFAULT_MIN_STOCK = '10';

const UNIT_OPTIONS = [
  { value: 'Stück', label: 'Stück' },
  { value: 'g', label: 'Gramm (g)' },
  { value: 'kg', label: 'Kilogramm (kg)' },
  { value: 'ml', label: 'Milliliter (ml)' },
  { value: 'l', label: 'Liter (l)' },
  { value: 'cm', label: 'Zentimeter (cm)' },
  { value: 'm', label: 'Meter (m)' },
];

type FormState = {
  name: string;
  description: string;
  unit_price: string;
  stock: string;
  unit: string;
  supplier: string;
  webshop_url: string;
  min_stock: string;
};

function initialState(material?: MaterialType | null): FormState {
  if (!material) {
    return {
      name: '',
      description: '',
      unit_price: '',
      stock: '',
      unit: 'Stück',
      supplier: '',
      webshop_url: '',
      min_stock: DEFAULT_MIN_STOCK,
    };
  }
  return {
    name: material.name,
    description: material.description || '',
    unit_price: material.unit_price != null ? String(material.unit_price) : '',
    stock: String(material.stock),
    unit: material.unit,
    supplier: material.supplier || '',
    webshop_url: material.webshop_url || '',
    min_stock: String(material.min_stock ?? DEFAULT_MIN_STOCK),
  };
}

/** Accept "12,50" as well as "12.50". */
function parseDecimal(value: string): number {
  return parseFloat(value.replace(',', '.'));
}

export const MaterialFormModal: React.FC<MaterialFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  material,
  isLoading = false,
}) => {
  const [formData, setFormData] = useState<FormState>(() => initialState(material));
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const { validate, errors, clearError, clearErrors } = useFormValidation(MaterialCreateSchema);
  const firstInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setFormData(initialState(material));
    setImagePreview(material?.image_url || null);
    setImageFile(null);
    clearErrors();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens or the material changes
  }, [material, isOpen]);

  const isDirty = useMemo(() => {
    const start = initialState(material);
    return (
      imageFile !== null ||
      (Object.keys(start) as (keyof FormState)[]).some((key) => start[key] !== formData[key])
    );
  }, [formData, imageFile, material]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    clearError(name);
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setImageFile(file);
    if (file) setImagePreview(URL.createObjectURL(file));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = validate({
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      unit_price: parseDecimal(formData.unit_price),
      stock: parseDecimal(formData.stock),
      unit: formData.unit,
      supplier: formData.supplier.trim() || undefined,
      webshop_url: formData.webshop_url.trim() || undefined,
      min_stock: parseDecimal(formData.min_stock),
    });
    if (!result.success) {
      const firstInvalid = Object.keys(result.errors)[0];
      if (firstInvalid) document.getElementById(`material-${firstInvalid}`)?.focus();
      return;
    }
    await onSubmit({
      ...result.data,
      // image_url is set server-side after the upload POST; keep the
      // existing value when editing so saving does not clear it.
      image_url: imageFile ? undefined : (material?.image_url ?? undefined),
      _imageFile: imageFile ?? undefined,
    });
  };

  const unitPrice = parseDecimal(formData.unit_price);
  const stock = parseDecimal(formData.stock);
  const hasValue = Number.isFinite(unitPrice) && Number.isFinite(stock);

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={material ? 'Material bearbeiten' : 'Material anlegen'}
      isDirty={isDirty}
      initialFocusRef={firstInputRef}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button type="submit" form={FORM_ID} loading={isLoading}>
            {material ? 'Material speichern' : 'Material anlegen'}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="material-form" noValidate>
        <Field label="Name" name="name" required error={errors.name}>
          <input
            id="material-name"
            type="text"
            ref={firstInputRef}
            value={formData.name}
            onChange={handleChange}
            placeholder="z. B. Edelstein, Verschluss, Kette"
          />
        </Field>
        <Field label="Beschreibung" name="description">
          <textarea
            id="material-description"
            value={formData.description}
            onChange={handleChange}
            rows={3}
          />
        </Field>
        <Field
          label="Preis pro Einheit"
          name="unit_price"
          required
          inputMode="decimal"
          suffix="€"
          error={errors.unit_price}
        >
          <input
            id="material-unit_price"
            type="text"
            value={formData.unit_price}
            onChange={handleChange}
            placeholder="0,00"
          />
        </Field>
        <Field label="Bestand" name="stock" required inputMode="decimal" error={errors.stock}>
          <input
            id="material-stock"
            type="text"
            value={formData.stock}
            onChange={handleChange}
            placeholder="0"
          />
        </Field>
        <Field label="Einheit" name="unit" required error={errors.unit}>
          <select id="material-unit" value={formData.unit} onChange={handleChange}>
            {UNIT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Lieferant" name="supplier" error={errors.supplier}>
          <input
            id="material-supplier"
            type="text"
            value={formData.supplier}
            onChange={handleChange}
            placeholder="z. B. Hafner GmbH, Otto Feil"
          />
        </Field>
        <Field label="Webshop-URL" name="webshop_url" error={errors.webshop_url}>
          <input
            id="material-webshop_url"
            type="url"
            value={formData.webshop_url}
            onChange={handleChange}
            placeholder="https://lieferant.de/artikel/123"
          />
        </Field>
        <Field
          label="Mindestbestand"
          name="min_stock"
          inputMode="decimal"
          error={errors.min_stock}
        >
          <input
            id="material-min_stock"
            type="text"
            value={formData.min_stock}
            onChange={handleChange}
            placeholder="10"
          />
        </Field>
        <Field label="Bild" name="material_image" help="Erlaubte Formate: JPEG, PNG, WEBP (max. 10 MB)">
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleImageChange} />
        </Field>
        {imagePreview && (
          <img src={imagePreview} alt="Vorschau" className="materials-thumb materials-thumb--preview" />
        )}
        {hasValue && (
          <p className="material-form__value">
            Gesamtwert: <span className={MONEY_CLASS}>{formatEur(unitPrice * stock)}</span>
          </p>
        )}
      </form>
    </Modal>
  );
};
