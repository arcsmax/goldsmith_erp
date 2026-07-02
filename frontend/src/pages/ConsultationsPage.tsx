// ConsultationsPage — Beratungen (V1.1 consultation list, Task 9).
// Follows the page-container/page-header conventions established by
// CustomersPage; the status filter and card grid reuse the wizard's own
// chip/card visual language (styles/consultations.css) instead of the
// table layout other list pages use, since a Beratung reads as a small
// summary card rather than a row of tabular fields.
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { consultationsApi } from '../api/consultations';
import { ConsultationListItem, ConsultationStatus } from '../types';
import { OCCASION_LABELS, PIECE_TYPE_LABELS } from '../components/consultation/labels';
import { logError } from '../lib/logError';
import '../styles/pages.css';
import '../styles/consultations.css';

const STATUS_LABELS: Record<ConsultationStatus, string> = {
  draft: 'Entwurf',
  completed: 'Abgeschlossen',
  converted: 'Überführt',
  archived: 'Archiviert',
};

const STATUS_FILTERS: { label: string; value: ConsultationStatus | undefined }[] = [
  { label: 'Alle', value: undefined },
  { label: 'Entwurf', value: 'draft' },
  { label: 'Abgeschlossen', value: 'completed' },
  { label: 'Überführt', value: 'converted' },
  { label: 'Archiviert', value: 'archived' },
];

/** Card click target: drafts resume at the wizard step where editing left
 *  off (step 2, occasion/budget — step 1 is customer selection, already
 *  done for an existing draft); everything else opens the read-only
 *  summary step. */
function targetStepFor(status: ConsultationStatus): number {
  return status === 'draft' ? 2 : 7;
}

export const ConsultationsPage: React.FC = () => {
  const navigate = useNavigate();
  const [consultations, setConsultations] = useState<ConsultationListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ConsultationStatus | undefined>(undefined);

  const fetchConsultations = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await consultationsApi.getAll({ status: statusFilter });
      setConsultations(data);
    } catch (err) {
      logError('Beratungen laden fehlgeschlagen', err);
      setError('Fehler beim Laden der Beratungen');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchConsultations();
  }, [fetchConsultations]);

  const handleCardClick = (item: ConsultationListItem) => {
    navigate(`/consultations/${item.id}?step=${targetStepFor(item.status)}`);
  };

  if (isLoading && consultations.length === 0 && !error) {
    return <div className="page-loading">Lade Beratungen...</div>;
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Beratungen</h1>
        <button className="btn-primary" onClick={() => navigate('/consultations/new')}>
          + Neue Beratung
        </button>
      </header>

      <div
        className="chip-group consultation-status-filters"
        role="group"
        aria-label="Nach Status filtern"
      >
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            className={`chip${statusFilter === filter.value ? ' selected' : ''}`}
            aria-pressed={statusFilter === filter.value}
            onClick={() => setStatusFilter(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="page-error">
          {error}
          <button onClick={fetchConsultations} className="btn-primary">
            Erneut versuchen
          </button>
        </div>
      )}

      {!error && consultations.length === 0 ? (
        <div className="empty-state">
          <p>Keine Beratungen gefunden.</p>
          <p className="error-hint">Starten Sie eine neue Beratung, um loszulegen.</p>
        </div>
      ) : (
        !error && (
          <div className="consultation-list">
            {consultations.map((item) => (
              <button
                key={item.id}
                type="button"
                className="consultation-list-card"
                onClick={() => handleCardClick(item)}
              >
                <div className="consultation-list-card-header">
                  <span className={`consultation-status-badge status-${item.status}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                  <span className="consultation-list-card-date">
                    {format(new Date(item.created_at), 'dd.MM.yyyy')}
                  </span>
                </div>
                <h3 className="consultation-list-card-title">{OCCASION_LABELS[item.occasion]}</h3>
                <p className="consultation-list-card-meta">
                  {item.piece_type ? PIECE_TYPE_LABELS[item.piece_type] : 'Kein Schmuckstück-Typ'}
                </p>
                {item.follow_up_at && (
                  <p className="consultation-list-card-followup">
                    Wiedervorlage: {format(new Date(item.follow_up_at), 'dd.MM.yyyy')}
                  </p>
                )}
              </button>
            ))}
          </div>
        )
      )}
    </div>
  );
};
