// "Basisinformationen" tab of the order form (W3-06).
import React, { useEffect } from 'react';
import { useFormContext } from 'react-hook-form';
import type { CustomerListItem } from '../../../types';
import { Field } from '../../../ui';
import { LocationPicker } from '../../LocationPicker';
import { ORDER_TYPE_OPTIONS } from '../orderIntakeOptions';
import { STATUS_OPTIONS } from './orderFormOptions';
import type { OrderFormValues } from './orderFormSchema';

interface BasicSectionProps {
  customers: readonly CustomerListItem[];
  isLoadingCustomers: boolean;
}

const customerLabel = (c: CustomerListItem): string =>
  `${c.first_name} ${c.last_name}${c.company_name ? ` (${c.company_name})` : ''}`;

export const BasicSection: React.FC<BasicSectionProps> = ({ customers, isLoadingCustomers }) => {
  const { register, formState, getValues, setValue, watch } = useFormContext<OrderFormValues>();
  const locationId = watch('location_id');
  const currentLocation = watch('current_location');
  const { errors } = formState;

  // The saved customer's <option> arrives with the list; re-apply the value
  // so the select shows it (without marking the form dirty).
  useEffect(() => {
    if (customers.length > 0) setValue('customer_id', getValues('customer_id'));
  }, [customers, getValues, setValue]);

  return (
    <div className="tab-content-form">
      <Field label="Bezeichnung" name="title" required error={errors.title?.message}>
        <input id="title" type="text" placeholder="z. B. Goldring mit Diamant" {...register('title')} />
      </Field>

      <Field label="Beschreibung" name="description" required error={errors.description?.message}>
        <textarea
          id="description"
          rows={4}
          placeholder="Detaillierte Beschreibung des Auftrags"
          {...register('description')}
        />
      </Field>

      <Field label="Kunde" name="customer_id" required error={errors.customer_id?.message}>
        <select id="customer_id" disabled={isLoadingCustomers} {...register('customer_id')}>
          <option value="">{isLoadingCustomers ? 'Wird geladen…' : 'Kunde auswählen'}</option>
          {customers.map((customer) => (
            <option key={customer.id} value={customer.id}>
              {customerLabel(customer)}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Schmuckart" name="order_type">
        <select id="order_type" {...register('order_type')}>
          <option value="">Schmuckart auswählen</option>
          {ORDER_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

      <div className="form-row">
        <Field label="Abgabetermin" name="deadline" required error={errors.deadline?.message}>
          <input id="deadline" type="date" {...register('deadline')} />
        </Field>
        <Field label="Status" name="status">
          <select id="status" {...register('status')}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <LocationPicker
        id="current_location"
        label="Aktueller Standort"
        value={locationId ? Number.parseInt(locationId, 10) : null}
        currentName={currentLocation}
        error={errors.current_location?.message}
        onChange={(location) => {
          const opts = { shouldDirty: true };
          setValue('location_id', location ? String(location.id) : '', opts);
          setValue('current_location', location?.name ?? '', opts);
        }}
      />
    </div>
  );
};
