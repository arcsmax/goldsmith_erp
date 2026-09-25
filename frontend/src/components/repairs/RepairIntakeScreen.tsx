// RepairIntakeScreen — Reparaturannahme at the counter in one screen
// (W2-12, FE-17, DOM-08; W4-03 on react-hook-form + zod and the Modal
// primitive). Tablet first: chips instead of typing wherever a common answer
// exists, 44px+ targets, camera input for photos.
//
// Step 1 "Annahme": customer (search or quick-create), piece, photos,
// condition, the customer's own words, first price indication, promised
// date. Step 2 "Annahmeschein": print the receipt for the customer to sign
// on paper, then open the new repair. A digital signature is not stored yet
// (RepairJob has no signature column; see the W2-12 report).
//
// Dirty guard: while anything is entered, Escape, the close button and
// "Abbrechen" ask "Änderungen verwerfen?" (Modal isDirty); the backdrop never
// closes the form.
import React, { useEffect, useId, useState } from 'react';
import { useForm, type FieldErrors } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customersApi } from '../../api/customers';
import { queryKeys } from '../../api/queryKeys';
import { repairKeys } from '../../api/repairQueries';
import { repairsApi } from '../../api/repairs';
import { useAuth, useConfirm, useToast } from '../../contexts';
import { canViewFinancials } from '../../lib/roles';
import { logError } from '../../lib/logError';
import type { RepairJob } from '../../types';
import { Button, Field, Icon, Modal } from '../../ui';
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
  type IntakeForm,
} from './intakeOptions';
import { intakeSchema } from './repairSchemas';

interface RepairIntakeScreenProps {
  onClose: () => void;
  onDone: (repairId: number) => void;
  /** Pre-select a customer (e.g. from the customer page). */
  initialCustomerId?: number;
}

const CUSTOMER_INPUT_ID = 'intake-customer-search';

interface ChipGroupProps {
  label: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  isActive: (value: string) => boolean;
  onPick: (value: string) => void;
}

const ChipGroup: React.FC<ChipGroupProps> = ({ label, options, isActive, onPick }) => (
  <div className="intake-chips" role="group" aria-label={label}>
    {options.map((option) => (
      <button
        key={option.value}
        type="button"
        className="intake-chip"
        aria-pressed={isActive(option.value)}
        onClick={() => onPick(option.value)}
      >
        {option.label}
      </button>
    ))}
  </div>
);

const asOptions = (values: readonly string[]) => values.map((value) => ({ value, label: value }));

const PhotoPreview: React.FC<{ file: File; index: number; onRemove: () => void }> = ({
  file,
  index,
  onRemove,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  // Object URLs are a browser resource: create on mount, revoke on unmount.
  useEffect(() => {
    if (typeof URL.createObjectURL !== 'function') return undefined;
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return (
    <li className="intake-photo">
      {url && <img src={url} alt={`Foto ${index + 1}`} />}
      <Button variant="secondary" onClick={onRemove}>
        Foto {index + 1} entfernen
      </Button>
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

function usePrintAnnahmeschein(repairId: number | undefined) {
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => openAnnahmeschein(repairId as number),
    onError: (err) => {
      logError('RepairIntakeScreen.annahmeschein', err);
      showToast('Annahmeschein konnte nicht geladen werden. Bitte erneut versuchen.', 'error');
    },
  });
}

const ReceiptStep: React.FC<{ repair: RepairJob }> = ({ repair }) => (
  <div className="intake-receipt">
    <h3>Reparatur angenommen</h3>
    <p className="intake-receipt__numbers">
      {repair.repair_number} · Tüte {repair.bag_number}
    </p>
    <p>
      Annahmeschein drucken und von der Kundin oder dem Kunden unterschreiben lassen. Das Stück
      in Tüte {repair.bag_number} legen.
    </p>
  </div>
);

/** Customer preselected by the link (`?customer_id=`), loaded once. */
function useInitialCustomer(initialCustomerId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.customers.detail(initialCustomerId ?? 0),
    queryFn: () => customersApi.getById(initialCustomerId as number),
    enabled: Boolean(initialCustomerId),
  });
}

function useCreateIntake(withPrice: boolean, onCreated: (repair: RepairJob) => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: async ({ values, photos }: { values: IntakeForm; photos: File[] }) => {
      const repair = await repairsApi.create(buildIntakePayload(values, withPrice));
      return { repair, failed: await uploadAll(repair.id, photos) };
    },
    onSuccess: async ({ repair, failed }) => {
      if (failed > 0) {
        const noun = failed === 1 ? 'Foto konnte' : 'Fotos konnten';
        showToast(`${failed} ${noun} nicht hochgeladen werden. Bitte in der Reparatur erneut aufnehmen.`, 'error');
      }
      onCreated(repair);
      await queryClient.invalidateQueries({ queryKey: repairKeys.all });
    },
    onError: (err) => {
      logError('RepairIntakeScreen.create', err);
      showToast('Reparatur konnte nicht angelegt werden. Bitte erneut versuchen.', 'error');
    },
  });
}

/** Move focus to the first invalid field, in screen order. */
function focusFirstError(errors: FieldErrors<IntakeForm>, focus: (name: 'description' | 'price') => void) {
  if (errors.customerId) document.getElementById(CUSTOMER_INPUT_ID)?.focus();
  else if (errors.description) focus('description');
  else if (errors.price) focus('price');
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
  const formId = useId();
  const [picked, setPicked] = useState<PickedCustomer | null | undefined>(undefined);
  const [photos, setPhotos] = useState<File[]>([]);
  const [created, setCreated] = useState<RepairJob | null>(null);

  const form = useForm<IntakeForm>({
    defaultValues: EMPTY_INTAKE,
    resolver: zodResolver(intakeSchema(withPrice)),
    shouldFocusError: false,
  });
  const { register, handleSubmit, setValue, setFocus, watch, formState } = form;
  const { errors, isDirty, isSubmitted } = formState;
  const values = watch();

  const initialCustomer = useInitialCustomer(initialCustomerId);
  const customer: PickedCustomer | null =
    picked !== undefined ? picked : (initialCustomer.data ?? null);
  // The preselected customer fills the form once it arrives (not a user edit).
  const initialId = initialCustomer.data?.id;
  useEffect(() => {
    if (initialId !== undefined) setValue('customerId', initialId);
  }, [initialId, setValue]);

  const create = useCreateIntake(withPrice, setCreated);
  const print = usePrintAnnahmeschein(created?.id);

  const change = <K extends keyof IntakeForm>(key: K, value: IntakeForm[K]) =>
    setValue(key, value as never, { shouldDirty: true, shouldValidate: isSubmitted });

  const selectCustomer = (c: PickedCustomer | null) => {
    setPicked(c);
    change('customerId', c ? c.id : null);
  };

  const hasInput = isDirty || photos.length > 0 || Boolean(picked);
  // Escape and the close button ask inside the Modal (isDirty); the footer
  // "Abbrechen" asks through the same confirm the rest of the app uses.
  const handleCancel = async () => {
    if (hasInput) {
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
  };
  const onValid = (data: IntakeForm) => create.mutate({ values: data, photos });

  const footer = created ? (
    <>
      <Button variant="secondary" icon="file-text" onClick={() => print.mutate()} loading={print.isPending}>
        Annahmeschein drucken
      </Button>
      <Button onClick={() => onDone(created.id)}>Zur Reparatur</Button>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={() => void handleCancel()} disabled={create.isPending}>
        Abbrechen
      </Button>
      <Button type="submit" form={formId} loading={create.isPending}>
        Reparatur annehmen
      </Button>
    </>
  );

  return (
    <Modal
      open
      title="Neue Reparatur"
      size="lg"
      onClose={onClose}
      isDirty={created === null && hasInput}
      footer={footer}
      className="repair-intake"
    >
      {created ? (
        <ReceiptStep repair={created} />
      ) : (
        <form
          id={formId}
          onSubmit={handleSubmit(onValid, (found) => focusFirstError(found, setFocus))}
          noValidate
        >
          <section className="intake-section" aria-labelledby={`${formId}-customer`}>
            <h3 id={`${formId}-customer`}>Kundin/Kunde</h3>
            {initialCustomer.isError && (
              <p className="ui-field__error" role="alert">
                <Icon name="alert-triangle" />
                <span>Kundendaten konnten nicht geladen werden. Bitte die Kundin oder den Kunden suchen.</span>
              </p>
            )}
            <IntakeCustomerPicker
              customer={customer}
              onChange={selectCustomer}
              error={errors.customerId?.message}
              onSearchError={() => showToast('Kundensuche fehlgeschlagen. Bitte erneut versuchen.', 'error')}
            />
          </section>

          <section className="intake-section" aria-labelledby={`${formId}-piece`}>
            <h3 id={`${formId}-piece`}>Schmuckstück</h3>
            <ChipGroup
              label="Art des Stücks"
              options={ITEM_TYPE_OPTIONS}
              isActive={(type) => values.itemType === type}
              onPick={(type) => change('itemType', type as IntakeForm['itemType'])}
            />
            <ChipGroup
              label="Metall wählen"
              options={asOptions(METAL_OPTIONS)}
              isActive={(metal) => values.metal === metal}
              onPick={(metal) => change('metal', values.metal === metal ? '' : metal)}
            />
            <Field label="Metall" name="metal" error={errors.metal?.message}>
              <input {...register('metal')} placeholder="z. B. 333 Gelbgold" />
            </Field>
            <Field label="Beschreibung des Stücks" name="description" required error={errors.description?.message}>
              <textarea rows={2} {...register('description')} placeholder="z. B. Ehering mit drei Brillanten" />
            </Field>
          </section>

          <section className="intake-section" aria-labelledby={`${formId}-photos`}>
            <h3 id={`${formId}-photos`}>Fotos und Zustand</h3>
            <label className="ui-button ui-button--secondary intake-camera" htmlFor={`${formId}-photo-input`}>
              <Icon name="camera" />
              Foto aufnehmen
            </label>
            <input
              id={`${formId}-photo-input`}
              className="intake-camera__input"
              type="file"
              accept="image/*"
              capture="environment"
              multiple
              onChange={(e) => {
                const added = Array.from(e.target.files ?? []);
                setPhotos((prev) => [...prev, ...added]);
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
              options={asOptions(CONDITION_OPTIONS)}
              isActive={(c) => values.conditions.includes(c)}
              onPick={(c) => change('conditions', toggle(values.conditions, c))}
            />
            {errors.conditions?.message && (
              <p className="ui-field__error" role="alert">
                <Icon name="alert-triangle" />
                <span>{errors.conditions.message}</span>
              </p>
            )}
          </section>

          <section className="intake-section" aria-labelledby={`${formId}-problem`}>
            <h3 id={`${formId}-problem`}>Anliegen der Kundin oder des Kunden</h3>
            <ChipGroup
              label="Häufige Anliegen"
              options={asOptions(PROBLEM_OPTIONS)}
              isActive={(p) => values.problem.includes(p)}
              onPick={(p) => change('problem', appendProblem(values.problem, p))}
            />
            <Field label="Kundenangabe" name="problem" error={errors.problem?.message}>
              <textarea rows={2} {...register('problem')} />
            </Field>
          </section>

          <section className="intake-section intake-section--split" aria-labelledby={`${formId}-terms`}>
            <h3 id={`${formId}-terms`}>Preis und Termin</h3>
            {withPrice && (
              <Field
                label="Preisindikation (unverbindlich)"
                name="price"
                inputMode="decimal"
                suffix="€"
                error={errors.price?.message}
              >
                <input {...register('price')} placeholder="z. B. 45,00" />
              </Field>
            )}
            <ChipGroup
              label="Termin wählen"
              options={PROMISE_OPTIONS.map((opt) => ({ value: dateInDays(opt.days), label: opt.label }))}
              isActive={(date) => values.promisedDate === date}
              onPick={(date) => change('promisedDate', date)}
            />
            <Field label="Zugesagt bis" name="promisedDate">
              <input type="date" {...register('promisedDate')} />
            </Field>
          </section>
        </form>
      )}
    </Modal>
  );
};

export default RepairIntakeScreen;
