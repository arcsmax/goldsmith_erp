// Next steps for a delivered order (W2-11, DOM-34/35): the Abholprotokoll
// PDF and a Wertgutachten (insurance valuation) created from the order.
// The valuation PDF export is ADMIN-only (W1-04, GDPR-09); a goldsmith can
// still create the certificate. Data on TanStack Query (W4-03).
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { downloadHandoverPdf, saveBlob } from '../../api/handover';
import { queryKeys } from '../../api/queryKeys';
import { valuationsApi, type ValuationCertificate } from '../../api/valuations';
import { useToast } from '../../contexts';
import { canDownloadValuationPdf } from '../../lib/roles';
import { logError } from '../../lib/logError';
import { Button, Field } from '../../ui';

interface DeliveredActionsProps {
  orderId: number;
  price?: number | null;
  role?: string | null;
  userName?: string;
}

const MIN_APPRAISER_LENGTH = 2;

/** The order's latest valuation certificate; nested under the order detail key. */
const valuationKey = queryKeys.orders.valuation;

function useExistingValuation(orderId: number) {
  return useQuery({
    queryKey: valuationKey(orderId),
    queryFn: async (): Promise<ValuationCertificate | null> => {
      try {
        const certs = await valuationsApi.list({ order_id: orderId, limit: 1 });
        return certs[0] ?? null;
      } catch (err: unknown) {
        logError('DeliveredActions.listValuations', err);
        throw err;
      }
    },
  });
}

function parseAppraisedValue(value: string): number | null {
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function DeliveredActions({ orderId, price, role, userName }: DeliveredActionsProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const canExport = canDownloadValuationPdf(role);
  const existing = useExistingValuation(orderId).data ?? null;
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [value, setValue] = useState(price ? String(price) : '');
  const [appraiser, setAppraiser] = useState(userName ?? '');

  const handover = useMutation({
    mutationFn: () => downloadHandoverPdf(orderId),
    onSuccess: (blob) => saveBlob(blob, `Abholprotokoll_${orderId}.pdf`),
    onError: (err) => {
      logError('DeliveredActions.handover', err);
      showToast('Abholprotokoll konnte nicht erstellt werden.', 'error');
    },
  });

  const downloadCertificate = useMutation({
    mutationFn: (cert: ValuationCertificate) =>
      valuationsApi.downloadAndSavePdf(cert.id, cert.certificate_number),
    onError: (err) => {
      logError('DeliveredActions.valuationPdf', err);
      showToast('Wertgutachten konnte nicht heruntergeladen werden.', 'error');
    },
  });

  const createValuation = useMutation({
    mutationFn: (input: { appraised_value: number; goldsmith_name: string }) =>
      valuationsApi.createFromOrder(orderId, input),
    onSuccess: (cert) => {
      queryClient.setQueryData(valuationKey(orderId), cert);
      setIsFormOpen(false);
      showToast(`Wertgutachten ${cert.certificate_number} erstellt`, 'success');
      if (canExport) downloadCertificate.mutate(cert);
    },
    onError: (err) => {
      logError('DeliveredActions.createValuation', err);
      showToast('Wertgutachten konnte nicht erstellt werden.', 'error');
    },
  });

  const handleCreateValuation = () => {
    const appraisedValue = parseAppraisedValue(value);
    if (appraisedValue === null) {
      showToast('Gutachtenwert fehlt. Bitte einen Betrag in Euro eingeben.', 'error');
      return;
    }
    if (appraiser.trim().length < MIN_APPRAISER_LENGTH) {
      showToast('Gutachter fehlt. Bitte den Namen eingeben.', 'error');
      return;
    }
    createValuation.mutate({ appraised_value: appraisedValue, goldsmith_name: appraiser.trim() });
  };

  const isBusy = handover.isPending || createValuation.isPending;

  return (
    <div className="delivered-actions">
      <Button variant="secondary" icon="file-text" loading={handover.isPending} disabled={isBusy} onClick={() => handover.mutate()}>
        Abholprotokoll herunterladen
      </Button>
      {existing && canExport && (
        <Button
          variant="secondary"
          icon="file-text"
          loading={downloadCertificate.isPending}
          onClick={() => downloadCertificate.mutate(existing)}
        >
          {`Wertgutachten ${existing.certificate_number} herunterladen`}
        </Button>
      )}
      {existing && !canExport && (
        <p>Wertgutachten {existing.certificate_number} liegt vor (PDF nur für Administratoren).</p>
      )}
      {!existing && !isFormOpen && (
        <Button variant="secondary" onClick={() => setIsFormOpen(true)}>
          Wertgutachten erstellen
        </Button>
      )}
      {!existing && isFormOpen && (
        <div className="delivered-actions-form">
          <Field label="Gutachtenwert (€)" name="appraised_value" inputMode="decimal">
            <input
              type="text"
              className="tabular-nums"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </Field>
          <Field label="Gutachter" name="goldsmith_name">
            <input type="text" value={appraiser} onChange={(e) => setAppraiser(e.target.value)} />
          </Field>
          <Button loading={createValuation.isPending} disabled={isBusy} onClick={handleCreateValuation}>
            Wertgutachten speichern
          </Button>
          <Button variant="secondary" onClick={() => setIsFormOpen(false)}>
            Abbrechen
          </Button>
        </div>
      )}
    </div>
  );
}

export default DeliveredActions;
