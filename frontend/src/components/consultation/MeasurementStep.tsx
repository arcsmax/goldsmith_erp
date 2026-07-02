// MeasurementStep — Beratungs-Wizard step 5: Maße (wraps MeasurementPanel).
//
// MeasurementPanel takes `Pick<Customer, 'id' | 'ring_size' |
// 'chain_length_cm' | 'bracelet_length_cm'>` — see MeasurementPanel.tsx for
// why (it renders those legacy Customer fields alongside the dynamic
// measurement list). The wizard only carries `consultation.customer_id`, so
// this step is the thin fetch wrapper: load the customer once, then hand it
// to the shared panel — the same component CustomerDetailPage's
// Maßbibliothek tab uses.
import React, { useEffect, useState } from 'react';
import { customersApi } from '../../api/customers';
import { Customer } from '../../types';
import { logError } from '../../lib/logError';
import { MeasurementPanel } from '../measurements/MeasurementPanel';

export const MeasurementStep: React.FC<{ customerId: number }> = ({ customerId }) => {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        const data = await customersApi.getById(customerId);
        if (!cancelled) setCustomer(data);
      } catch (err) {
        logError('Kunde für Maßbibliothek laden fehlgeschlagen', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  if (isLoading) return <p>Lade Kundendaten...</p>;
  if (!customer) return <p>Kunde konnte nicht geladen werden.</p>;

  return <MeasurementPanel customer={customer} />;
};
