// Order form (W3-06): react-hook-form + zod on the Modal, Tabs and Field
// primitives. The sections live in ./form/*; the business rules stay in
// lib/validation/schemas.ts (see form/orderFormSchema.ts). Escape and the close
// button ask "Änderungen verwerfen?" once the form is dirty; the backdrop
// never closes it. On an invalid submit the tab with the first error opens
// and its field takes the focus.
import React, { useEffect, useRef, useState } from 'react';
import { FormProvider, useForm, useWatch, type FieldErrors, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { OrderCreateInput, OrderType, OrderUpdateInput } from '../../types';
import { customersApi } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Modal, Tabs } from '../../ui';
import { NoGoWarning } from '../consultation/NoGoWarning';
import { gemstonesQuery, gemstonesState } from './GemstoneList';
import { findAlloyChoice, alloyChoiceKey } from './orderIntakeOptions';
import { BasicSection } from './form/BasicSection';
import { IntakeSection, pflichtfelderOf } from './form/IntakeSection';
import { MetalSection } from './form/MetalSection';
import { PricingSection } from './form/PricingSection';
import { applyGemstonePlan, isEmptyPlan, planGemstoneSync } from './form/gemstoneSync';
import { SURFACE_FINISH_OPTIONS, firstInvalidField, tabOfField, type OrderFormTab } from './form/orderFormOptions';
import {
  orderFormSchema,
  toFormValues,
  toGemstoneRow,
  toOrderPayload,
  type OrderFormValues,
} from './form/orderFormSchema';
import '../../styles/orders.css';

const FORM_ID = 'order-form';
/** Customer picker: 100 is ample for the dropdown. */
const CUSTOMER_PICKER_PARAMS = { skip: 0, limit: 100 };
/** The form is offered to ADMIN and GOLDSMITH only (canCreateOrders / canEditOrders). */
const CAN_VIEW_COST = true;

interface OrderFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: OrderCreateInput | OrderUpdateInput) => Promise<void>;
  order?: OrderType | null;
  isLoading?: boolean;
}

export const OrderFormModal: React.FC<OrderFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  order,
  isLoading = false,
}) => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<OrderFormTab>('basic');
  const [saveError, setSaveError] = useState<string | null>(null);
  const titleRef = useRef<HTMLElement | null>(null);
  const isEdit = Boolean(order);

  const customers = useQuery({
    queryKey: queryKeys.customers.list(CUSTOMER_PICKER_PARAMS),
    queryFn: () => customersApi.getAll(CUSTOMER_PICKER_PARAMS),
    enabled: isOpen,
  });
  const gemstones = useQuery({ ...gemstonesQuery(order?.id ?? 0), enabled: isOpen && isEdit });

  const form = useForm<OrderFormValues>({
    defaultValues: toFormValues(order),
    resolver: zodResolver(orderFormSchema) as unknown as Resolver<OrderFormValues>,
  });
  const { control, handleSubmit, reset, setFocus, formState } = form;

  useEffect(() => {
    if (!isOpen) return;
    reset(toFormValues(order));
    setActiveTab('basic');
    setSaveError(null);
  }, [order, isOpen, reset]);

  // Saved stones arrive after the order; they become the array's baseline.
  // keepDirtyValues keeps anything the user already typed.
  useEffect(() => {
    if (!isOpen || !gemstones.data) return;
    reset({ ...toFormValues(order), gemstones: gemstones.data.map(toGemstoneRow) }, { keepDirtyValues: true });
  }, [gemstones.data, isOpen, order, reset]);

  const values = useWatch({ control }) as OrderFormValues;
  const pflichtfelder = pflichtfelderOf(values);
  const filledCount = pflichtfelder.filter((f) => f.filled).length;

  // No-Go candidates (Task 9): the human-readable alloy and finish labels plus
  // the description; raw codes would never match a no-go like "Weißgold".
  const noGoCandidates = [
    findAlloyChoice(alloyChoiceKey(values.metal_type, values.alloy))?.label,
    SURFACE_FINISH_OPTIONS.find((o) => o.value === values.surface_finish)?.label,
    values.description,
  ].filter((v): v is string => Boolean(v && v.trim()));

  const onInvalid = (errors: FieldErrors<OrderFormValues>) => {
    const field = firstInvalidField(Object.keys(errors));
    if (!field) return;
    setActiveTab(tabOfField(field));
    if (field !== 'gemstones') window.setTimeout(() => setFocus(field), 0);
  };

  const submit = handleSubmit(async (formValues) => {
    setSaveError(null);
    if (order) {
      const plan = planGemstoneSync(gemstones.data ?? [], formValues.gemstones, CAN_VIEW_COST);
      if (!isEmptyPlan(plan)) {
        try {
          await applyGemstonePlan(order.id, plan);
        } catch (err) {
          logError('OrderFormModal.gemstones', err);
          setSaveError(getErrorMessage(err, 'Steine konnten nicht gespeichert werden. Bitte erneut speichern.'));
          return;
        } finally {
          await queryClient.invalidateQueries({ queryKey: queryKeys.orders.detail(order.id) });
        }
      }
    }
    await onSubmit(toOrderPayload(formValues, isEdit));
  }, onInvalid);

  const isBusy = isLoading || formState.isSubmitting;
  const auftragLabel = `Auftrag (${filledCount}/${pflichtfelder.length})`;
  const tabs = [
    {
      id: 'basic',
      label: 'Basisinformationen',
      panel: <BasicSection customers={customers.data ?? []} isLoadingCustomers={customers.isPending} />,
    },
    {
      id: 'auftrag',
      label: auftragLabel,
      panel: (
        <IntakeSection
          pflichtfelder={pflichtfelder}
          isEdit={isEdit}
          canViewCost={CAN_VIEW_COST}
          gemstonesState={gemstonesState(gemstones)}
        />
      ),
    },
    { id: 'metal', label: 'Metall', panel: <MetalSection /> },
    { id: 'pricing', label: 'Preisgestaltung', panel: <PricingSection /> },
  ];

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={order ? 'Auftrag bearbeiten' : 'Neuer Auftrag'}
      size="lg"
      isDirty={formState.isDirty}
      initialFocusRef={titleRef}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isBusy}>
            Abbrechen
          </Button>
          <Button type="submit" form={FORM_ID} loading={isBusy}>
            {order ? 'Auftrag speichern' : 'Auftrag anlegen'}
          </Button>
        </>
      }
    >
      <FormProvider {...form}>
        <form
          id={FORM_ID}
          className="order-form"
          noValidate
          onSubmit={(event) => void submit(event)}
          ref={(el) => {
            titleRef.current = el?.querySelector<HTMLElement>('#title') ?? null;
          }}
        >
          <Tabs
            label="Auftragsbereiche"
            tabs={tabs}
            selectedId={activeTab}
            onSelect={(id) => setActiveTab(id as OrderFormTab)}
          />
          {saveError && (
            <p className="ui-field__error" role="alert">
              {saveError}
            </p>
          )}
          <NoGoWarning customerId={Number(values.customer_id) || null} candidates={noGoCandidates} />
        </form>
      </FormProvider>
    </Modal>
  );
};
