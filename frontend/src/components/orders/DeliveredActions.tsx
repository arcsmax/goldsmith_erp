// Next steps for a delivered order (W2-11, DOM-34/35): the Abholprotokoll
// PDF and a Wertgutachten (insurance valuation) created from the order.
// The valuation PDF export is ADMIN-only (W1-04, GDPR-09); a goldsmith can
// still create the certificate.
import { useEffect, useId, useState } from 'react';
import { downloadHandoverPdf, saveBlob } from '../../api/handover';
import { valuationsApi, type ValuationCertificate } from '../../api/valuations';
import { useToast } from '../../contexts';
import { canDownloadValuationPdf } from '../../lib/roles';
import { logError } from '../../lib/logError';

interface DeliveredActionsProps {
  orderId: number;
  price?: number | null;
  role?: string | null;
  userName?: string;
}

export function DeliveredActions({ orderId, price, role, userName }: DeliveredActionsProps) {
  const { showToast } = useToast();
  const id = useId();
  const canExport = canDownloadValuationPdf(role);
  const [existing, setExisting] = useState<ValuationCertificate | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [value, setValue] = useState(price ? String(price) : '');
  const [appraiser, setAppraiser] = useState(userName ?? '');
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    valuationsApi
      .list({ order_id: orderId, limit: 1 })
      .then((certs) => {
        if (isCurrent) setExisting(certs[0] ?? null);
      })
      .catch((err: unknown) => logError('DeliveredActions.listValuations', err));
    return () => {
      isCurrent = false;
    };
  }, [orderId]);

  const handleHandover = async () => {
    setIsBusy(true);
    try {
      saveBlob(await downloadHandoverPdf(orderId), `Abholprotokoll_${orderId}.pdf`);
    } catch (err: unknown) {
      logError('DeliveredActions.handover', err);
      showToast('Abholprotokoll konnte nicht erstellt werden.', 'error');
    } finally {
      setIsBusy(false);
    }
  };

  const downloadCertificate = async (cert: ValuationCertificate) => {
    try {
      await valuationsApi.downloadAndSavePdf(cert.id, cert.certificate_number);
    } catch (err: unknown) {
      logError('DeliveredActions.valuationPdf', err);
      showToast('Wertgutachten konnte nicht heruntergeladen werden.', 'error');
    }
  };

  const handleCreateValuation = async () => {
    const appraisedValue = Number(value.replace(',', '.'));
    if (!Number.isFinite(appraisedValue) || appraisedValue <= 0) {
      showToast('Gutachtenwert fehlt. Bitte einen Betrag in Euro eingeben.', 'error');
      return;
    }
    if (appraiser.trim().length < 2) {
      showToast('Gutachter fehlt. Bitte den Namen eingeben.', 'error');
      return;
    }
    setIsBusy(true);
    try {
      const cert = await valuationsApi.createFromOrder(orderId, {
        appraised_value: appraisedValue,
        goldsmith_name: appraiser.trim(),
      });
      setExisting(cert);
      setIsFormOpen(false);
      showToast(`Wertgutachten ${cert.certificate_number} erstellt`, 'success');
      if (canExport) await downloadCertificate(cert);
    } catch (err: unknown) {
      logError('DeliveredActions.createValuation', err);
      showToast('Wertgutachten konnte nicht erstellt werden.', 'error');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="delivered-actions">
      <button type="button" className="btn btn-secondary" onClick={() => void handleHandover()} disabled={isBusy}>
        Abholprotokoll herunterladen
      </button>
      {existing && canExport && (
        <button type="button" className="btn btn-secondary" onClick={() => void downloadCertificate(existing)}>
          {`Wertgutachten ${existing.certificate_number} herunterladen`}
        </button>
      )}
      {existing && !canExport && <p>Wertgutachten {existing.certificate_number} liegt vor (PDF nur für Administratoren).</p>}
      {!existing && !isFormOpen && (
        <button type="button" className="btn btn-secondary" onClick={() => setIsFormOpen(true)}>
          Wertgutachten erstellen
        </button>
      )}
      {!existing && isFormOpen && (
        <div className="delivered-actions-form">
          <div className="form-group">
            <label htmlFor={`${id}-value`}>Gutachtenwert (€)</label>
            <input
              id={`${id}-value`}
              type="text"
              inputMode="decimal"
              className="tabular-nums"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor={`${id}-appraiser`}>Gutachter</label>
            <input id={`${id}-appraiser`} type="text" value={appraiser} onChange={(e) => setAppraiser(e.target.value)} />
          </div>
          <button type="button" className="btn btn-primary" onClick={() => void handleCreateValuation()} disabled={isBusy}>
            Wertgutachten speichern
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setIsFormOpen(false)}>
            Abbrechen
          </button>
        </div>
      )}
    </div>
  );
}

export default DeliveredActions;
