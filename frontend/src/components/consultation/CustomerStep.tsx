// CustomerStep — Beratungs-Wizard step 1: find or quick-create the customer,
// then create the consultation draft.
//
// Two render paths:
//   - existingCustomerId set (resumed draft): fetch + show a read-only card,
//     no further action here — the shared wizard footer drives navigation.
//   - no existingCustomerId (fresh /consultations/new): typeahead search +
//     quick-create, then "Beratung starten" creates the draft and hands it
//     to the wizard shell via onDraftCreated.
import React, { useEffect, useState } from 'react';
import { customersApi } from '../../api/customers';
import { consultationsApi } from '../../api/consultations';
import {
  Consultation,
  Customer,
  CustomerCreateInput,
  CustomerListItem,
  CustomerUpdateInput,
} from '../../types';
import { useToast } from '../../contexts';
import { CustomerTypeahead } from './CustomerTypeahead';
import { CustomerFormModal } from '../CustomerFormModal';

interface CustomerStepProps {
  onDraftCreated: (consultation: Consultation) => void;
  existingCustomerId?: number;
}

type SelectedCustomer = CustomerListItem | Customer;

/** CustomerListItem has no ring_size; Customer does. Undefined = unknown source. */
const ringSizeOf = (customer: SelectedCustomer): number | null | undefined =>
  'ring_size' in customer ? customer.ring_size : undefined;

const CustomerCard: React.FC<{ customer: SelectedCustomer; readOnly?: boolean }> = ({
  customer,
  readOnly,
}) => {
  const ringSize = ringSizeOf(customer);
  return (
    <div className="customer-confirm-card">
      <p className="customer-confirm-name">
        {customer.first_name} {customer.last_name}
      </p>
      <p className="customer-confirm-email">{customer.email}</p>
      {ringSize != null && <p className="customer-confirm-ring">Ringgröße: {ringSize}</p>}
      {readOnly && <p className="customer-confirm-hint">Kundin dieser Beratung</p>}
    </div>
  );
};

export const CustomerStep: React.FC<CustomerStepProps> = ({
  onDraftCreated,
  existingCustomerId,
}) => {
  const { showToast } = useToast();
  const [selectedCustomer, setSelectedCustomer] = useState<SelectedCustomer | null>(null);
  const [isLoadingExisting, setIsLoadingExisting] = useState(Boolean(existingCustomerId));
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [isCreatingCustomer, setIsCreatingCustomer] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!existingCustomerId) return;
    let cancelled = false;
    (async () => {
      try {
        setIsLoadingExisting(true);
        const customer = await customersApi.getById(existingCustomerId);
        if (!cancelled) setSelectedCustomer(customer);
      } catch (err) {
        console.error('Kundendaten laden fehlgeschlagen', err);
        if (!cancelled) showToast('Kundendaten konnten nicht geladen werden', 'error');
      } finally {
        if (!cancelled) setIsLoadingExisting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [existingCustomerId, showToast]);

  const handleTypeaheadSelect = (customer: CustomerListItem) => setSelectedCustomer(customer);

  const handleStartConsultation = async () => {
    if (!selectedCustomer) return;
    try {
      setIsCreatingDraft(true);
      const created = await consultationsApi.create({ customer_id: selectedCustomer.id });
      onDraftCreated(created);
    } catch (err) {
      console.error('Beratung anlegen fehlgeschlagen', err);
      showToast('Beratung konnte nicht gestartet werden — bitte erneut versuchen', 'error');
    } finally {
      setIsCreatingDraft(false);
    }
  };

  const handleCreateCustomer = async (data: CustomerCreateInput | CustomerUpdateInput) => {
    try {
      setIsCreatingCustomer(true);
      const created = await customersApi.create(data as CustomerCreateInput);
      setSelectedCustomer(created);
      setIsModalOpen(false);
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || 'Fehler beim Erstellen der Kundin');
    } finally {
      setIsCreatingCustomer(false);
    }
  };

  if (existingCustomerId) {
    if (isLoadingExisting) return <p className="page-loading">Lade Kundendaten...</p>;
    if (!selectedCustomer) return <p className="page-error">Kundin konnte nicht geladen werden</p>;
    return <CustomerCard customer={selectedCustomer} readOnly />;
  }

  return (
    <div className="customer-step">
      {!selectedCustomer && (
        <>
          <CustomerTypeahead onSelect={handleTypeaheadSelect} autoFocus />
          <button
            type="button"
            className="btn-secondary customer-step-quick-create"
            onClick={() => setIsModalOpen(true)}
          >
            + Neue Kundin
          </button>
        </>
      )}

      {selectedCustomer && (
        <>
          <CustomerCard customer={selectedCustomer} />
          <div className="customer-step-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSelectedCustomer(null)}
              disabled={isCreatingDraft}
            >
              Andere Kundin wählen
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleStartConsultation}
              disabled={isCreatingDraft}
            >
              {isCreatingDraft ? 'Wird gestartet...' : 'Beratung starten'}
            </button>
          </div>
        </>
      )}

      <CustomerFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleCreateCustomer}
        isLoading={isCreatingCustomer}
      />
    </div>
  );
};
