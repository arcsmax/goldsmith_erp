// SummaryStep — Beratungs-Wizard step 7: Zusammenfassung + Konvertierung.
//
// Customer-presentable read-back (large type via .summary-section CSS — this
// screen is read out loud to the customer to re-confirm everything before
// converting). No-Gos are re-fetched here rather than reused from
// StyleNoGoStep's own state (a sibling step, unmounted by now) so the
// goldsmith can read them back to the customer one more time before
// conversion — design intent, not a caching shortcut.
//
// Terminal state: once converted, this step is read-only (banner + link to
// the created order/quote) — the action buttons below never apply again.
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import type { WizardStepProps } from '../../pages/ConsultationWizardPage';
import { consultationsApi, consultationPhotoThumbPath } from '../../api/consultations';
import { customersApi } from '../../api/customers';
import { Customer, NoGo } from '../../types';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import AuthenticatedImage from '../AuthenticatedImage';
import { OCCASION_LABELS, PIECE_TYPE_LABELS, PHOTO_KIND_LABELS, NO_GO_CATEGORY_LABELS } from './labels';

const budgetFormatter = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
});

/** Exported so the test suite derives the expected string from the same
 * formatter instead of hardcoding a locale-formatted literal. */
export const formatBudgetRange = (
  min?: number | null,
  max?: number | null
): string | null => {
  if (min == null && max == null) return null;
  if (min != null && max != null) {
    return `${budgetFormatter.format(min)} – ${budgetFormatter.format(max)}`;
  }
  return min != null
    ? `ab ${budgetFormatter.format(min)}`
    : `bis ${budgetFormatter.format(max as number)}`;
};

const formatDate = (iso?: string | null): string | null =>
  iso ? new Date(iso).toLocaleDateString('de-DE') : null;

/** Shape of the 409 detail body — see consultations.py convert_consultation. */
interface ConvertConflictDetail {
  message?: string;
  order_id?: number | null;
  quote_id?: number | null;
}

export const SummaryStep: React.FC<WizardStepProps> = ({
  consultation,
  onPatch,
  refresh,
}) => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [isUnconverting, setIsUnconverting] = useState(false);

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [isLoadingCustomer, setIsLoadingCustomer] = useState(true);
  const [noGos, setNoGos] = useState<NoGo[]>([]);
  const [followUpDate, setFollowUpDate] = useState('');
  const [convertingTarget, setConvertingTarget] = useState<'quote' | 'order' | null>(null);
  const [isSavingFollowUp, setIsSavingFollowUp] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoadingCustomer(true);
        const data = await customersApi.getById(consultation.customer_id);
        if (!cancelled) setCustomer(data);
      } catch (err) {
        logError('Kundin laden fehlgeschlagen', err);
        if (!cancelled) showToast('Kundin konnte nicht geladen werden', 'error');
      } finally {
        if (!cancelled) setIsLoadingCustomer(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [consultation.customer_id, showToast]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await customersApi.getNoGos(consultation.customer_id);
        if (!cancelled) setNoGos(data);
      } catch (err) {
        logError('No-Gos laden fehlgeschlagen', err);
        if (!cancelled) showToast('No-Gos konnten nicht geladen werden', 'error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [consultation.customer_id, showToast]);

  const customerName = customer
    ? `${customer.first_name} ${customer.last_name}`
    : isLoadingCustomer
      ? 'Lädt…'
      : `Kundin #${consultation.customer_id}`;

  /** 409 "already converted": order_id wins when both are present — an order
   * is the more concrete downstream artifact than a quote. */
  const navigateToExisting = (detail: ConvertConflictDetail | undefined) => {
    if (detail?.order_id) {
      navigate(`/orders/${detail.order_id}`);
    } else {
      navigate('/quotes');
    }
  };

  const handleConvert = async (target: 'quote' | 'order') => {
    const confirmed = await showConfirm({
      title: target === 'quote' ? 'Kostenvoranschlag erstellen' : 'Auftrag anlegen',
      message:
        target === 'quote'
          ? 'Aus der Beratung wird ein Kostenvoranschlag als Entwurf erstellt — '
            + 'mit einer Budget-Schätzung, die Sie anschließend anpassen können. '
            + 'Fortfahren?'
          : 'Beratung in einen Auftrag überführen?',
      confirmLabel: target === 'quote' ? 'Kostenvoranschlag erstellen' : 'Auftrag anlegen',
    });
    if (!confirmed) return;

    setConvertingTarget(target);
    try {
      const updated = await consultationsApi.convert(consultation.id, target);
      showToast(
        target === 'quote' ? 'Kostenvoranschlag erstellt' : 'Auftrag angelegt',
        'success'
      );
      // Null-guard both ids before building a route — there is no
      // `/quotes/:id` detail route (the quote branch always lands on the
      // generic list), but the order branch interpolates an id and must
      // never navigate to `/orders/undefined` if the backend response is
      // ever missing it.
      if (target === 'quote') {
        navigate('/quotes');
      } else {
        navigate(updated.converted_order_id ? `/orders/${updated.converted_order_id}` : '/orders');
      }
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        showToast('Bereits konvertiert', 'error');
        navigateToExisting(err.response.data?.detail as ConvertConflictDetail | undefined);
        return;
      }
      // NEVER log the raw error: the consultation's design-IP wish text can
      // ride along in err.config.data / echoed 4xx bodies (see logError).
      logError('Beratung konvertieren fehlgeschlagen', err);
      showToast('Konvertierung fehlgeschlagen', 'error');
    } finally {
      setConvertingTarget(null);
    }
  };

  const handleUnconvert = async () => {
    const confirmed = await showConfirm({
      title: 'Überführung rückgängig machen',
      message:
        'Der Kostenvoranschlag-Entwurf wird gelöscht und die Beratung '
        + 'zurückgesetzt. Fortfahren?',
      confirmLabel: 'Rückgängig machen',
      variant: 'danger',
    });
    if (!confirmed) return;
    setIsUnconverting(true);
    try {
      await consultationsApi.unconvert(consultation.id);
      showToast('Überführung rückgängig gemacht', 'success');
      await refresh();
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        showToast('Nur Entwürfe können zurückgesetzt werden', 'error');
      } else {
        logError('Überführung rückgängig machen fehlgeschlagen', err);
        showToast('Rückgängig machen fehlgeschlagen', 'error');
      }
    } finally {
      setIsUnconverting(false);
    }
  };

  const handleSaveFollowUp = async () => {
    if (!followUpDate) return;
    setIsSavingFollowUp(true);
    // onPatch (ConsultationWizardPage) already logs + toasts on failure —
    // this step only needs to react to the success/failure boolean.
    //
    // followUpDate is a date-ONLY string ('YYYY-MM-DD'); `new Date(dateOnly)`
    // parses that per the ISO-8601 spec as UTC MIDNIGHT, not local midnight.
    // In any negative-UTC-offset timezone that instant, read back locally,
    // falls on the PREVIOUS calendar day — the goldsmith picks "10.07." and
    // the stored follow-up silently becomes "09.07.". Appending a local
    // noon time-of-day instead makes the string parse as LOCAL time (a
    // date-TIME string with no offset is local per spec); noon is far
    // enough from both UTC day boundaries that the intended calendar date
    // survives the round trip for any real-world timezone.
    const ok = await onPatch({
      follow_up_at: new Date(`${followUpDate}T12:00:00`).toISOString(),
      status: 'completed',
    });
    setIsSavingFollowUp(false);
    if (!ok) return;
    showToast('Wiedervorlage gespeichert', 'success');
    navigate('/consultations');
  };

  const handleArchive = async () => {
    const confirmed = await showConfirm({
      title: 'Archivieren',
      message: 'Beratung wirklich archivieren?',
      confirmLabel: 'Archivieren',
      variant: 'danger',
    });
    if (!confirmed) return;
    setIsArchiving(true);
    const ok = await onPatch({ status: 'archived' });
    setIsArchiving(false);
    if (!ok) return;
    navigate('/consultations');
  };

  if (consultation.status === 'converted') {
    const hasOrder = Boolean(consultation.converted_order_id);
    const target = hasOrder ? `/orders/${consultation.converted_order_id}` : '/quotes';
    return (
      <div className="summary-step">
        <div className="summary-section">
          <h3>Status</h3>
          <p>Diese Beratung wurde bereits überführt.</p>
          <div className="summary-actions">
            <button type="button" className="btn-secondary" onClick={() => navigate(target)}>
              {hasOrder ? 'Zum Auftrag' : 'Zum Kostenvoranschlag'}
            </button>
            {!hasOrder && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleUnconvert}
                disabled={isUnconverting}
              >
                {isUnconverting ? 'Wird zurückgesetzt…' : 'Überführung rückgängig machen'}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const budgetLabel = formatBudgetRange(consultation.budget_min, consultation.budget_max);
  const occasionDateLabel = formatDate(consultation.occasion_date);
  const materials = (consultation.materials_discussed ?? [])
    .map((entry) => entry.metal)
    .filter((metal): metal is string => Boolean(metal));

  return (
    <div className="summary-step">
      <div className="summary-section">
        <h3>Kundin</h3>
        <p>{customerName}</p>
      </div>

      <div className="summary-section">
        <h3>Anlass</h3>
        <p>
          {OCCASION_LABELS[consultation.occasion]}
          {occasionDateLabel ? ` — ${occasionDateLabel}` : ''}
        </p>
      </div>

      {budgetLabel && (
        <div className="summary-section">
          <h3>Budget</h3>
          <p>{budgetLabel}</p>
        </div>
      )}

      {consultation.piece_type && (
        <div className="summary-section">
          <h3>Schmuckstück</h3>
          <p>{PIECE_TYPE_LABELS[consultation.piece_type]}</p>
        </div>
      )}

      {consultation.wishes && (
        <div className="summary-section">
          <h3>Wunsch</h3>
          <p>{consultation.wishes}</p>
        </div>
      )}

      {materials.length > 0 && (
        <div className="summary-section">
          <h3>Materialien</h3>
          <div className="chip-group">
            {materials.map((metal) => (
              <span className="chip selected" key={metal}>
                {metal}
              </span>
            ))}
          </div>
        </div>
      )}

      {consultation.source_material && (
        <div className="summary-section">
          <h3>Mitgebrachtes Material</h3>
          <p>{consultation.source_material}</p>
        </div>
      )}

      <div className="summary-section">
        <h3>No-Gos ({noGos.length})</h3>
        {noGos.length > 0 ? (
          <ul>
            {noGos.map((noGo) => (
              <li key={noGo.id}>
                {NO_GO_CATEGORY_LABELS[noGo.category]}: {noGo.value}
              </li>
            ))}
          </ul>
        ) : (
          <p>Keine No-Gos hinterlegt</p>
        )}
      </div>

      {consultation.photos.length > 0 && (
        <div className="summary-section">
          <h3>Skizzen & Fotos</h3>
          <div className="consultation-photo-grid">
            {consultation.photos.map((photo) => (
              <div className="consultation-photo-card" key={photo.id}>
                <AuthenticatedImage
                  src={consultationPhotoThumbPath(photo.id)}
                  alt={PHOTO_KIND_LABELS[photo.kind]}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {consultation.follow_up_at && (
        <div className="summary-section">
          <h3>Vereinbarte Wiedervorlage</h3>
          <p>{formatDate(consultation.follow_up_at)}</p>
        </div>
      )}

      <div className="summary-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={() => handleConvert('quote')}
          disabled={convertingTarget !== null}
        >
          {convertingTarget === 'quote' ? 'Wird erstellt...' : 'Kostenvoranschlag erstellen'}
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => handleConvert('order')}
          disabled={convertingTarget !== null}
        >
          {convertingTarget === 'order' ? 'Wird angelegt...' : 'Auftrag anlegen'}
        </button>
      </div>

      <div className="summary-section wizard-field">
        <label htmlFor="follow_up_date">Neue Wiedervorlage</label>
        <input
          id="follow_up_date"
          type="date"
          value={followUpDate}
          onChange={(e) => setFollowUpDate(e.target.value)}
        />
        <div className="summary-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleSaveFollowUp}
            disabled={!followUpDate || isSavingFollowUp}
          >
            {isSavingFollowUp ? 'Speichert...' : 'Speichern & abschließen'}
          </button>
        </div>
      </div>

      <div className="summary-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={handleArchive}
          disabled={isArchiving}
        >
          {isArchiving ? 'Archiviert...' : 'Archivieren'}
        </button>
      </div>
    </div>
  );
};
