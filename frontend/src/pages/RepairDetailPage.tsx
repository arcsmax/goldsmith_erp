// Reparatur Detailansicht — status actions, photo tabs, diagnosis, history
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { repairsApi } from '../api/repairs';
import type {
  RepairCompleteInput,
  RepairDiagnoseInput,
  RepairJob,
  RepairJobStatus,
  RepairPhoto,
  RepairPhotoPhase,
} from '../types';
import { PhotoCompare } from '../components/PhotoCompare';
import type { PhotoItem } from '../components/PhotoCompare';
import '../styles/repairs.css';

// ─── helpers ────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<RepairJobStatus, string> = {
  received: 'Eingang',
  diagnosed: 'Diagnose',
  quoted: 'Angebot',
  approved: 'Genehmigt',
  in_repair: 'In Arbeit',
  quality_check: 'Qualitätskontrolle',
  ready: 'Fertig',
  picked_up: 'Abgeholt',
  cancelled: 'Storniert',
};

const PHASE_LABELS: Record<RepairPhotoPhase, string> = {
  intake: 'Eingang',
  during_repair: 'Während der Reparatur',
  completed: 'Fertiggestellt',
};

function StatusBadge({ status }: { status: RepairJobStatus }) {
  return <span className={`status-badge ${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatEur(amount: number | null | undefined): string {
  if (amount == null) return '—';
  return amount.toFixed(2) + ' EUR';
}

// ─── Status action buttons ───────────────────────────────────────────────────

interface ActionButtonsProps {
  repair: RepairJob;
  onAction: (action: string, extraData?: Record<string, unknown>) => void;
  busy: boolean;
}

function ActionButtons({ repair, onAction, busy }: ActionButtonsProps) {
  const { status } = repair;

  const actions: Array<{
    label: string;
    action: string;
    className: string;
    show: boolean;
  }> = [
    {
      label: 'Diagnose stellen',
      action: 'diagnose',
      className: 'btn btn-primary',
      show: status === 'received',
    },
    {
      label: 'Angebot bestätigen',
      action: 'approve',
      className: 'btn btn-success',
      show: status === 'quoted',
    },
    {
      label: 'Reparatur starten',
      action: 'start',
      className: 'btn btn-primary',
      show: status === 'approved',
    },
    {
      label: 'Zur QK einreichen',
      action: 'quality_check',
      className: 'btn btn-primary',
      show: status === 'in_repair',
    },
    {
      label: 'Fertigmelden',
      action: 'complete',
      className: 'btn btn-success',
      show: status === 'quality_check',
    },
    {
      label: 'Abholung bestätigen',
      action: 'pickup',
      className: 'btn btn-success',
      show: status === 'ready',
    },
    {
      label: 'Stornieren',
      action: 'cancel',
      className: 'btn btn-danger',
      show: !['picked_up', 'cancelled'].includes(status),
    },
  ];

  const visible = actions.filter(a => a.show);
  if (visible.length === 0) return null;

  return (
    <div className="repair-actions-strip">
      {visible.map(a => (
        <button
          key={a.action}
          className={a.className}
          disabled={busy}
          onClick={() => onAction(a.action)}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}

// ─── Diagnose Modal ──────────────────────────────────────────────────────────

interface DiagnoseModalProps {
  repairId: number;
  onClose: () => void;
  onDone: (repair: RepairJob) => void;
}

function DiagnoseModal({ repairId, onClose, onDone }: DiagnoseModalProps) {
  const [form, setForm] = useState<RepairDiagnoseInput>({
    diagnosis_notes: '',
    estimated_cost: 0,
    estimated_completion_date: undefined,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.diagnosis_notes.trim()) {
      setError('Bitte Befund eingeben.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: RepairDiagnoseInput = {
        ...form,
        estimated_completion_date: form.estimated_completion_date
          ? new Date(form.estimated_completion_date).toISOString()
          : undefined,
      };
      const updated = await repairsApi.diagnose(repairId, payload);
      onDone(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fehler beim Speichern.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box">
        <div className="modal-header">
          <h2>Diagnose stellen</h2>
          <button className="modal-close" onClick={onClose}>&#x2715;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="repairs-error">{error}</div>}
            <div className="form-group">
              <label className="form-label">
                Befundbeschreibung <span className="required">*</span>
              </label>
              <textarea
                className="form-textarea"
                rows={5}
                placeholder="Was wurde festgestellt? Welche Arbeiten sind erforderlich?"
                value={form.diagnosis_notes}
                onChange={e => setForm(prev => ({ ...prev, diagnosis_notes: e.target.value }))}
                required
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">
                  Kostenvoranschlag (EUR) <span className="required">*</span>
                </label>
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  className="form-input"
                  value={form.estimated_cost}
                  onChange={e => setForm(prev => ({ ...prev, estimated_cost: Number(e.target.value) }))}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Fertigstellung bis</label>
                <input
                  type="date"
                  className="form-input"
                  value={form.estimated_completion_date
                    ? form.estimated_completion_date.slice(0, 10)
                    : ''}
                  onChange={e => setForm(prev => ({
                    ...prev,
                    estimated_completion_date: e.target.value || undefined,
                  }))}
                />
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Abbrechen</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Wird gespeichert…' : 'Diagnose speichern'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Complete Modal ──────────────────────────────────────────────────────────

interface CompleteModalProps {
  repairId: number;
  estimatedCost: number | null | undefined;
  onClose: () => void;
  onDone: (repair: RepairJob) => void;
}

function CompleteModal({ repairId, estimatedCost, onClose, onDone }: CompleteModalProps) {
  const [actualCost, setActualCost] = useState<number>(estimatedCost ?? 0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const data: RepairCompleteInput = { actual_cost: actualCost };
      const updated = await repairsApi.complete(repairId, data);
      onDone(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fehler beim Speichern.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box">
        <div className="modal-header">
          <h2>Reparatur fertigmelden</h2>
          <button className="modal-close" onClick={onClose}>&#x2715;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="repairs-error">{error}</div>}
            <p style={{ marginTop: 0, fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>
              Die Reparatur wird auf <strong>Abholbereit</strong> gesetzt und alle
              Mitarbeiter werden benachrichtigt.
            </p>
            {estimatedCost != null && (
              <p style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
                Kostenvoranschlag: <strong>{estimatedCost.toFixed(2)} EUR</strong>
              </p>
            )}
            <div className="form-group">
              <label className="form-label">
                Tatsächliche Kosten (EUR) <span className="required">*</span>
              </label>
              <input
                type="number"
                min={0}
                step={0.01}
                className="form-input"
                value={actualCost}
                onChange={e => setActualCost(Number(e.target.value))}
                required
              />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Abbrechen</button>
            <button type="submit" className="btn btn-success" disabled={saving}>
              {saving ? 'Wird gespeichert…' : 'Fertigmelden'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Photo section ───────────────────────────────────────────────────────────

const PHASES: RepairPhotoPhase[] = ['intake', 'during_repair', 'completed'];

/** Map RepairPhoto to the generic PhotoItem shape expected by PhotoCompare. */
function toPhotoItem(p: RepairPhoto): PhotoItem {
  return { id: p.id, file_path: p.file_path, notes: p.notes, timestamp: p.timestamp };
}

function PhotosTab({
  repair,
  onPhotoAdded,
}: {
  repair: RepairJob;
  onPhotoAdded: (photo: RepairPhoto) => void;
}) {
  const [uploadingPhase, setUploadingPhase] = useState<RepairPhotoPhase | null>(null);
  const [error, setError] = useState<string | null>(null);

  const photosByPhase = (phase: RepairPhotoPhase) =>
    repair.photos.filter(p => p.phase === phase);

  const handleFileSelect = async (
    phase: RepairPhotoPhase,
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // In a real implementation this would upload to S3/storage.
    // For now we use a local blob URL as the file_path placeholder.
    const blobUrl = URL.createObjectURL(file);
    setUploadingPhase(phase);
    setError(null);
    try {
      const photo = await repairsApi.addPhoto(repair.id, {
        phase,
        file_path: blobUrl,
        notes: file.name,
      });
      onPhotoAdded(photo);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fehler beim Hochladen.');
    } finally {
      setUploadingPhase(null);
      e.target.value = '';
    }
  };

  const intakePhotos = photosByPhase('intake').map(toPhotoItem);
  const duringPhotos = photosByPhase('during_repair').map(toPhotoItem);
  const completedPhotos = photosByPhase('completed').map(toPhotoItem);

  return (
    <div className="repair-tab-panel">
      {error && <div className="repairs-error">{error}</div>}

      {/* Before / After comparison view */}
      <PhotoCompare
        beforePhotos={intakePhotos}
        duringPhotos={duringPhotos}
        afterPhotos={completedPhotos}
      />

      {/* Upload controls — one per phase, shown below the comparison */}
      <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-default)' }}>
        <p style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', marginTop: 0, marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
          Foto hinzufuegen
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {PHASES.map(phase => (
            <label
              key={phase}
              className="photo-upload-btn"
              style={{ flex: '1 1 140px', minWidth: 140, aspectRatio: 'unset', padding: '0.6rem 1rem', height: 'auto', minHeight: 44 }}
              title={`Foto hinzufuegen (${PHASE_LABELS[phase]})`}
            >
              <input
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={e => handleFileSelect(phase, e)}
                disabled={uploadingPhase !== null}
              />
              {uploadingPhase === phase ? (
                <span style={{ fontSize: '0.8rem' }}>Wird hochgeladen…</span>
              ) : (
                <>
                  <span style={{ fontSize: '1.1rem' }}>+</span>
                  <span style={{ fontSize: '0.82rem' }}>{PHASE_LABELS[phase]}</span>
                </>
              )}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── History tab ─────────────────────────────────────────────────────────────

const STATUS_ORDER: RepairJobStatus[] = [
  'received', 'diagnosed', 'quoted', 'approved',
  'in_repair', 'quality_check', 'ready', 'picked_up',
];

function HistoryTab({ repair }: { repair: RepairJob }) {
  const currentIdx = STATUS_ORDER.indexOf(repair.status);
  const isCancelled = repair.status === 'cancelled';

  const milestones: Array<{ label: string; date?: string | null; done: boolean }> = [
    { label: 'Eingang', date: repair.created_at, done: true },
    { label: 'Diagnose', date: repair.diagnosis_notes ? repair.updated_at : null, done: currentIdx >= 1 || repair.status === 'diagnosed' },
    { label: 'Angebot', date: null, done: currentIdx >= 2 },
    { label: 'Genehmigt', date: null, done: currentIdx >= 3 },
    { label: 'In Arbeit', date: null, done: currentIdx >= 4 },
    { label: 'Qualitätskontrolle', date: null, done: currentIdx >= 5 },
    { label: 'Fertig (Abholbereit)', date: repair.actual_completion_date, done: currentIdx >= 6 || repair.status === 'ready' },
    { label: 'Abgeholt', date: repair.picked_up_at, done: repair.status === 'picked_up' },
  ];

  return (
    <div className="repair-tab-panel">
      {isCancelled && (
        <div className="repairs-error" style={{ marginBottom: '1.5rem' }}>
          Dieser Reparaturauftrag wurde storniert.
        </div>
      )}
      <ul className="repair-history-list">
        {milestones.map((m, i) => (
          <li key={i} className="repair-history-item">
            <div
              className="repair-history-dot"
              style={{
                background: m.done
                  ? 'var(--color-brand-cta-500)'
                  : 'var(--color-border-default)',
              }}
            >
              {m.done ? '✓' : ''}
            </div>
            <div className="repair-history-content">
              <div
                className="repair-history-label"
                style={{ color: m.done ? 'var(--color-text-heading)' : 'var(--color-text-muted)' }}
              >
                {m.label}
              </div>
              {m.date && (
                <div className="repair-history-time">{formatDate(m.date)}</div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Diagnosis tab ────────────────────────────────────────────────────────────

function DiagnosisTab({ repair }: { repair: RepairJob }) {
  if (!repair.diagnosis_notes && repair.estimated_cost == null) {
    return (
      <div className="repair-tab-panel">
        <div className="repairs-empty" style={{ padding: '2rem' }}>
          <div className="repairs-empty-icon">&#128269;</div>
          <h3>Noch keine Diagnose</h3>
          <p>Verwenden Sie die Schaltfläche "Diagnose stellen" oben, um Befund und Kostenvoranschlag zu erfassen.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="repair-tab-panel">
      {repair.diagnosis_notes && (
        <div className="diagnosis-section">
          <h3>Befundbeschreibung</h3>
          <div className="diagnosis-notes-box">{repair.diagnosis_notes}</div>
        </div>
      )}

      <div className="cost-comparison">
        <div className="cost-card">
          <div className="cost-card-label">Kostenvoranschlag</div>
          <div className="cost-card-value">{formatEur(repair.estimated_cost)}</div>
        </div>
        <div className="cost-card">
          <div className="cost-card-label">Tatsächliche Kosten</div>
          <div className="cost-card-value">{formatEur(repair.actual_cost)}</div>
        </div>
      </div>
    </div>
  );
}

// ─── Details tab ──────────────────────────────────────────────────────────────

function DetailsTab({ repair }: { repair: RepairJob }) {
  const ITEM_TYPE_LABELS: Record<string, string> = {
    ring: 'Ring', chain: 'Kette', bracelet: 'Armband',
    earring: 'Ohrringe', watch: 'Uhr', brooch: 'Brosche', other: 'Sonstiges',
  };

  return (
    <div className="repair-tab-panel">
      <div className="repair-details-grid">
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Beschreibung</span>
          <span className="repair-detail-field-value">{repair.item_description}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Art</span>
          <span className="repair-detail-field-value">{ITEM_TYPE_LABELS[repair.item_type] ?? repair.item_type}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Metall</span>
          <span className="repair-detail-field-value">{repair.metal_type ?? '—'}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Versicherungswert</span>
          <span className="repair-detail-field-value">{formatEur(repair.estimated_value)}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Voraussichtliche Fertigstellung</span>
          <span className="repair-detail-field-value">{formatDateShort(repair.estimated_completion_date)}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Tatsächliche Fertigstellung</span>
          <span className="repair-detail-field-value">{formatDateShort(repair.actual_completion_date)}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Kunde benachrichtigt</span>
          <span className="repair-detail-field-value">{formatDate(repair.customer_notified_at)}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Abgeholt</span>
          <span className="repair-detail-field-value">{formatDate(repair.picked_up_at)}</span>
        </div>
        <div className="repair-detail-field">
          <span className="repair-detail-field-label">Angelegt</span>
          <span className="repair-detail-field-value">{formatDate(repair.created_at)}</span>
        </div>
      </div>

      {repair.customer && (
        <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-default)' }}>
          <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', fontWeight: 700, margin: '0 0 0.75rem' }}>
            Kundendaten
          </h3>
          <div className="repair-details-grid">
            <div className="repair-detail-field">
              <span className="repair-detail-field-label">Name</span>
              <span className="repair-detail-field-value highlight">
                {repair.customer.first_name} {repair.customer.last_name}
              </span>
            </div>
            <div className="repair-detail-field">
              <span className="repair-detail-field-label">E-Mail</span>
              <span className="repair-detail-field-value">{repair.customer.email}</span>
            </div>
            {repair.customer.phone && (
              <div className="repair-detail-field">
                <span className="repair-detail-field-label">Telefon</span>
                <span className="repair-detail-field-value">{repair.customer.phone}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Detail Page ─────────────────────────────────────────────────────────

type Tab = 'details' | 'fotos' | 'diagnose' | 'historie';

export function RepairDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const repairId = Number(id);

  const [repair, setRepair] = useState<RepairJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('details');
  const [busy, setBusy] = useState(false);
  const [activeModal, setActiveModal] = useState<string | null>(null);

  const loadRepair = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await repairsApi.getById(repairId);
      setRepair(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden.');
    } finally {
      setLoading(false);
    }
  }, [repairId]);

  useEffect(() => { loadRepair(); }, [loadRepair]);

  const handleAction = async (action: string) => {
    if (!repair) return;

    // Actions that need a modal
    if (action === 'diagnose') { setActiveModal('diagnose'); return; }
    if (action === 'complete') { setActiveModal('complete'); return; }

    setBusy(true);
    setError(null);
    try {
      let updated: RepairJob;
      switch (action) {
        case 'approve':
          updated = await repairsApi.approve(repair.id);
          break;
        case 'start':
          updated = await repairsApi.startRepair(repair.id);
          break;
        case 'quality_check':
          updated = await repairsApi.submitQualityCheck(repair.id);
          break;
        case 'pickup':
          updated = await repairsApi.pickup(repair.id);
          break;
        case 'cancel':
          if (!window.confirm('Reparaturauftrag wirklich stornieren?')) return;
          updated = await repairsApi.cancel(repair.id);
          break;
        default:
          return;
      }
      setRepair(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Aktion fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const handlePhotoAdded = (photo: RepairPhoto) => {
    setRepair(prev =>
      prev ? { ...prev, photos: [...prev.photos, photo] } : prev
    );
  };

  if (loading) return <div className="repairs-loading">Wird geladen…</div>;
  if (!repair) return (
    <div className="repair-detail-page">
      <div className="repairs-error">
        {error ?? 'Reparaturauftrag nicht gefunden.'}
      </div>
      <button className="btn btn-secondary" onClick={() => navigate('/repairs')}>
        Zurück zur Liste
      </button>
    </div>
  );

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'details', label: 'Details' },
    { id: 'fotos', label: `Fotos (${repair.photos.length})` },
    { id: 'diagnose', label: 'Diagnose' },
    { id: 'historie', label: 'Historie' },
  ];

  return (
    <div className="repair-detail-page">
      {/* Back link */}
      <button
        className="btn btn-secondary"
        style={{ marginBottom: '1rem', fontSize: '0.85rem' }}
        onClick={() => navigate('/repairs')}
      >
        ← Zur Liste
      </button>

      {/* Header */}
      <div className="repair-detail-header">
        <div className="repair-detail-title">
          <h1>{repair.repair_number}</h1>
          <StatusBadge status={repair.status} />
          <span className="repair-bag-number" title="Tütennummer">
            Tüte: {repair.bag_number}
          </span>
        </div>
      </div>

      {/* Meta strip */}
      <div className="repair-detail-meta">
        <div className="repair-meta-item">
          <span className="repair-meta-label">Kunde</span>
          <span className="repair-meta-value">
            {repair.customer
              ? `${repair.customer.first_name} ${repair.customer.last_name}`
              : 'Laufkunde'}
          </span>
        </div>
        <div className="repair-meta-item">
          <span className="repair-meta-label">Gegenstand</span>
          <span className="repair-meta-value">{repair.item_description}</span>
        </div>
        {repair.estimated_completion_date && (
          <div className="repair-meta-item">
            <span className="repair-meta-label">Deadline</span>
            <span className="repair-meta-value">
              {new Date(repair.estimated_completion_date).toLocaleDateString('de-DE')}
            </span>
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && <div className="repairs-error">{error}</div>}

      {/* Action buttons */}
      <ActionButtons repair={repair} onAction={handleAction} busy={busy} />

      {/* Tabs */}
      <div className="repair-tabs" role="tablist">
        {tabs.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            className={`repair-tab${activeTab === t.id ? ' active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      {activeTab === 'details' && <DetailsTab repair={repair} />}
      {activeTab === 'fotos' && (
        <PhotosTab repair={repair} onPhotoAdded={handlePhotoAdded} />
      )}
      {activeTab === 'diagnose' && <DiagnosisTab repair={repair} />}
      {activeTab === 'historie' && <HistoryTab repair={repair} />}

      {/* Modals */}
      {activeModal === 'diagnose' && (
        <DiagnoseModal
          repairId={repair.id}
          onClose={() => setActiveModal(null)}
          onDone={updated => { setRepair(updated); setActiveModal(null); }}
        />
      )}
      {activeModal === 'complete' && (
        <CompleteModal
          repairId={repair.id}
          estimatedCost={repair.estimated_cost}
          onClose={() => setActiveModal(null)}
          onDone={updated => { setRepair(updated); setActiveModal(null); }}
        />
      )}
    </div>
  );
}
