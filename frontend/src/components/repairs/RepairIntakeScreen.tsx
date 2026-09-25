// RepairIntakeScreen — Reparaturannahme at the counter in one screen
// (W2-12, FE-17, DOM-08). Tablet first: chips instead of typing wherever a
// common answer exists, 44px+ targets, camera input for photos.
//
// Step 1 "Annahme": customer (search or quick-create), piece, photos,
// condition, the customer's own words, first price indication, promised
// date. Step 2 "Annahmeschein": print the receipt for the customer to sign
// on paper, then open the new repair. A digital signature is not stored yet
// (RepairJob has no signature column; see the W2-12 report).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { customersApi } from '../../api/customers';
import { repairsApi } from '../../api/repairs';
import { useAuth, useConfirm, useToast } from '../../contexts';
import { canViewFinancials } from '../../lib/roles';
import { logError } from '../../lib/logError';
import type { RepairJob } from '../../types';
import { Icon } from '../../ui/Icon';
import { openAnnahmeschein } from './annahmeschein';
import { IntakeCustomerPicker, type PickedCustomer } from './IntakeCustomerPicker';
import {
  appendProblem,
  buildIntakePayload,
  CONDITION_OPTIONS,
  dateInDays,
  EMPTY_INTAKE,
  ITEM_TYPE_OPTIONS,
  METAL_OPTIONS,
  PROBLEM_OPTIONS,
  PROMISE_OPTIONS,
  toggle,
  validateIntake,
  type IntakeErrors,
  type IntakeForm,
} from './intakeOptions';

interface RepairIntakeScreenProps {
  onClose: () => void;
  onDone: (repairId: number) => void;
  /** Pre-select a customer (e.g. from the customer page). */
  initialCustomerId?: number;
}

interface ChipGroupProps {
  label: string;
  options: readonly string[];
  isActive: (option: string) => boolean;
  onPick: (option: string) => void;
}

const ChipGroup: React.FC<ChipGroupProps> = ({ label, options, isActive, onPick }) => (
  <div className="intake-chips" role="group" aria-label={label}>
    {options.map((option) => (
      <button
        key={option}
        type="button"
        className="intake-chip"
        aria-pressed={isActive(option)}
        onClick={() => onPick(option)}
      >
        {option}
      </button>
    ))}
  </div>
);

const PhotoPreview: React.FC<{ file: File; index: number; onRemove: () => void }> = ({
  file,
  index,
  onRemove,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (typeof URL.createObjectURL !== 'function') return undefined;
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return (
    <li className="intake-photo">
      {url && <img src={url} alt={`Foto ${index + 1}`} />}
      <button type="button" className="btn-secondary" onClick={onRemove}>
        Foto {index + 1} entfernen
      </button>
    </li>
  );
};

async function uploadAll(repairId: number, photos: File[]): Promise<number> {
  let failed = 0;
  for (const photo of photos) {
    try {
      await repairsApi.uploadPhoto(repairId, photo, 'intake');
    } catch (err) {
      failed += 1;
      logError('RepairIntakeScreen.uploadPhoto', err);
    }
  }
  return failed;
}

const ReceiptStep: React.FC<{ repair: RepairJob; onDone: (id: number) => void }> = ({
  repair,
  onDone,
}) => {
  const { showToast } = useToast();
  const [isPrinting, setIsPrinting] = useState(false);
  const handlePrint = async () => {
    setIsPrinting(true);
    try {
      await openAnnahmeschein(repair.id);
    } catch (err) {
      logError('RepairIntakeScreen.annahmeschein', err);
      showToast('Annahmeschein konnte nicht geladen werden. Bitte erneut versuchen.', 'error');
    } finally {
      setIsPrinting(false);
    }
  };
  return (
    <div className="intake-receipt">
      <h3>Reparatur angenommen</h3>
      <p className="intake-receipt__numbers">
        {repair.repair_number} · Tüte {repair.bag_number}
      </p>
      <p>
        Annahmeschein drucken und von der Kundin oder dem Kunden unterschreiben lassen. Das
        Stück in Tüte {repair.bag_number} legen.
      </p>
      <div className="intake-actions">
        <button type="button" className="btn-secondary" onClick={handlePrint} disabled={isPrinting}>
          <Icon name="file-text" />
          {isPrinting ? 'Wird geladen…' : 'Annahmeschein drucken'}
        </button>
        <button type="button" className="btn-primary" onClick={() => onDone(repair.id)}>
          Zur Reparatur
        </button>
      </div>
    </div>
  );
};

function useInitialCustomer(
  initialCustomerId: number | undefined,
  select: (c: PickedCustomer) => void,
): void {
  const { showToast } = useToast();
  useEffect(() => {
    if (!initialCustomerId) return undefined;
    let cancelled = false;
    customersApi
      .getById(initialCustomerId)
      .then((c) => {
        if (!cancelled) select(c);
      })
      .catch((err) => {
        logError('RepairIntakeScreen.initialCustomer', err);
        if (!cancelled) showToast('Kundendaten konnten nicht geladen werden.', 'error');
      });
    return () => {
      cancelled = true;
    };
    // select is a state setter wrapper; re-running on its identity would refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCustomerId, showToast]);
}

export const RepairIntakeScreen: React.FC<RepairIntakeScreenProps> = ({
  onClose,
  onDone,
  initialCustomerId,
}) => {
  const { user } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const withPrice = canViewFinancials(user?.role);
  const [form, setForm] = useState<IntakeForm>(EMPTY_INTAKE);
  const [customer, setCustomer] = useState<PickedCustomer | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [errors, setErrors] = useState<IntakeErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [created, setCreated] = useState<RepairJob | null>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const priceRef = useRef<HTMLInputElement>(null);

  const update = <K extends keyof IntakeForm>(key: K, value: IntakeForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const selectCustomer = useCallback((c: PickedCustomer | null) => {
    setCustomer(c);
    setForm((prev) => ({ ...prev, customerId: c ? c.id : null }));
  }, []);
  useInitialCustomer(initialCustomerId, selectCustomer);

  const isDirty = created === null && (customer !== null || form !== EMPTY_INTAKE || photos.length > 0);

  const handleCancel = useCallback(async () => {
    if (isDirty) {
      const discard = await showConfirm({
        title: 'Annahme verwerfen?',
        message: 'Die eingegebenen Daten gehen verloren.',
        confirmLabel: 'Verwerfen',
        cancelLabel: 'Weiter erfassen',
        variant: 'danger',
      });
      if (!discard) return;
    }
    onClose();
  }, [isDirty, onClose, showConfirm]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleCancel]);

  const focusFirstError = (found: IntakeErrors) => {
    if (found.customer) document.getElementById('intake-customer-search')?.focus();
    else if (found.description) descriptionRef.current?.focus();
    else if (found.price) priceRef.current?.focus();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const found = validateIntake(form, withPrice);
    setErrors(found);
    if (Object.keys(found).length > 0) return focusFirstError(found);
    setIsSubmitting(true);
    try {
      const repair = await repairsApi.create(buildIntakePayload(form, withPrice));
      const failed = await uploadAll(repair.id, photos);
      if (failed > 0) {
        const noun = failed === 1 ? 'Foto konnte' : 'Fotos konnten';
        showToast(`${failed} ${noun} nicht hochgeladen werden. Bitte in der Reparatur erneut aufnehmen.`, 'error');
      }
      setCreated(repair);
    } catch (err) {
      logError('RepairIntakeScreen.create', err);
      showToast('Reparatur konnte nicht angelegt werden. Bitte erneut versuchen.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay repair-intake-overlay">
      <div className="modal-box repair-intake" role="dialog" aria-modal="true" aria-labelledby="repair-intake-title">
        <div className="modal-header">
          <h2 id="repair-intake-title">Neue Reparatur</h2>
          <button type="button" className="repair-intake__close" onClick={handleCancel} aria-label="Annahme schließen">
            <Icon name="circle-x" />
          </button>
        </div>
        {created ? (
          <div className="modal-body">
            <ReceiptStep repair={created} onDone={onDone} />
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <div className="modal-body repair-intake__body">
              <section className="intake-section" aria-labelledby="intake-customer-heading">
                <h3 id="intake-customer-heading">Kundin/Kunde</h3>
                <IntakeCustomerPicker
                  customer={customer}
                  onChange={selectCustomer}
                  error={errors.customer}
                  onSearchError={() => showToast('Kundensuche fehlgeschlagen. Bitte erneut versuchen.', 'error')}
                />
              </section>

              <section className="intake-section" aria-labelledby="intake-piece-heading">
                <h3 id="intake-piece-heading">Schmuckstück</h3>
                <div className="intake-chips" role="group" aria-label="Art des Stücks">
                  {ITEM_TYPE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className="intake-chip"
                      aria-pressed={form.itemType === opt.value}
                      onClick={() => update('itemType', opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <ChipGroup
                  label="Metall wählen"
                  options={METAL_OPTIONS}
                  isActive={(m) => form.metal === m}
                  onPick={(m) => update('metal', form.metal === m ? '' : m)}
                />
                <label className="intake-field">
                  <span>Metall</span>
                  <input value={form.metal} onChange={(e) => update('metal', e.target.value)} placeholder="z. B. 333 Gelbgold" />
                </label>
                <label className="intake-field">
                  <span>Beschreibung des Stücks (Pflichtfeld)</span>
                  <textarea
                    ref={descriptionRef}
                    rows={2}
                    value={form.description}
                    onChange={(e) => update('description', e.target.value)}
                    aria-invalid={Boolean(errors.description)}
                    aria-describedby={errors.description ? 'intake-description-error' : undefined}
                    placeholder="z. B. Ehering mit drei Brillanten"
                  />
                </label>
                {errors.description && (
                  <p className="intake-error" id="intake-description-error" role="alert">
                    {errors.description}
                  </p>
                )}
              </section>

              <section className="intake-section" aria-labelledby="intake-photo-heading">
                <h3 id="intake-photo-heading">Fotos und Zustand</h3>
                <label className="intake-camera btn-secondary" htmlFor="intake-photo-input">
                  <Icon name="camera" />
                  Foto aufnehmen
                </label>
                <input
                  id="intake-photo-input"
                  className="intake-camera__input"
                  type="file"
                  accept="image/*"
                  capture="environment"
                  multiple
                  onChange={(e) => {
                    const picked = Array.from(e.target.files ?? []);
                    setPhotos((prev) => [...prev, ...picked]);
                    e.target.value = '';
                  }}
                />
                {photos.length > 0 && (
                  <ul className="intake-photos">
                    {photos.map((file, i) => (
                      <PhotoPreview
                        key={`${file.name}-${i}`}
                        file={file}
                        index={i}
                        onRemove={() => setPhotos((prev) => prev.filter((_, j) => j !== i))}
                      />
                    ))}
                  </ul>
                )}
                <ChipGroup
                  label="Zustand bei Annahme"
                  options={CONDITION_OPTIONS}
                  isActive={(c) => form.conditions.includes(c)}
                  onPick={(c) => update('conditions', toggle(form.conditions, c))}
                />
              </section>

              <section className="intake-section" aria-labelledby="intake-problem-heading">
                <h3 id="intake-problem-heading">Anliegen der Kundin oder des Kunden</h3>
                <ChipGroup
                  label="Häufige Anliegen"
                  options={PROBLEM_OPTIONS}
                  isActive={(p) => form.problem.includes(p)}
                  onPick={(p) => update('problem', appendProblem(form.problem, p))}
                />
                <label className="intake-field">
                  <span>Kundenangabe</span>
                  <textarea rows={2} value={form.problem} onChange={(e) => update('problem', e.target.value)} />
                </label>
              </section>

              <section className="intake-section intake-section--split" aria-labelledby="intake-terms-heading">
                <h3 id="intake-terms-heading">Preis und Termin</h3>
                {withPrice && (
                  <label className="intake-field intake-field--money">
                    <span>Preisindikation in € (unverbindlich)</span>
                    <input
                      ref={priceRef}
                      inputMode="decimal"
                      value={form.price}
                      onChange={(e) => update('price', e.target.value)}
                      aria-invalid={Boolean(errors.price)}
                      aria-describedby={errors.price ? 'intake-price-error' : undefined}
                      placeholder="z. B. 45,00"
                    />
                  </label>
                )}
                {errors.price && (
                  <p className="intake-error" id="intake-price-error" role="alert">
                    {errors.price}
                  </p>
                )}
                <div className="intake-chips" role="group" aria-label="Termin wählen">
                  {PROMISE_OPTIONS.map((opt) => {
                    const value = dateInDays(opt.days);
                    return (
                      <button
                        key={opt.days}
                        type="button"
                        className="intake-chip"
                        aria-pressed={form.promisedDate === value}
                        onClick={() => update('promisedDate', value)}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                <label className="intake-field">
                  <span>Zugesagt bis</span>
                  <input type="date" value={form.promisedDate} onChange={(e) => update('promisedDate', e.target.value)} />
                </label>
              </section>
            </div>
            <div className="modal-footer repair-intake__footer">
              <button type="button" className="btn-secondary" onClick={handleCancel} disabled={isSubmitting}>
                Abbrechen
              </button>
              <button type="submit" className="btn-primary" disabled={isSubmitting}>
                {isSubmitting ? 'Wird angelegt…' : 'Reparatur annehmen'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default RepairIntakeScreen;
