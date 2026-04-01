// Reparaturverwaltung — list view with status filter, search, and intake modal
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { repairsApi } from '../api/repairs';
import type {
  Customer,
  RepairItemType,
  RepairJobCreateInput,
  RepairJobListItem,
  RepairJobStatus,
} from '../types';
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

const ITEM_TYPE_LABELS: Record<RepairItemType, string> = {
  ring: 'Ring',
  chain: 'Kette',
  bracelet: 'Armband',
  earring: 'Ohrringe',
  watch: 'Uhr',
  brooch: 'Brosche',
  other: 'Sonstiges',
};

function StatusBadge({ status }: { status: RepairJobStatus }) {
  return (
    <span className={`status-badge ${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function deadlineClass(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const days = (new Date(dateStr).getTime() - Date.now()) / 86_400_000;
  if (days < 0) return 'overdue';
  if (days < 3) return 'soon';
  return '';
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

// ─── New Repair Modal ────────────────────────────────────────────────────────

interface NewRepairModalProps {
  onClose: () => void;
  onCreated: (repair: RepairJobListItem) => void;
}

const ITEM_TYPES: RepairItemType[] = [
  'ring', 'chain', 'bracelet', 'earring', 'watch', 'brooch', 'other',
];

function NewRepairModal({ onClose, onCreated }: NewRepairModalProps) {
  const [form, setForm] = useState<RepairJobCreateInput>({
    customer_id: undefined,
    item_description: '',
    item_type: 'ring',
    metal_type: '',
    estimated_value: undefined,
    estimated_completion_date: undefined,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm(prev => ({
      ...prev,
      [name]:
        name === 'customer_id' || name === 'estimated_value'
          ? value === '' ? undefined : Number(value)
          : value || (name === 'metal_type' ? '' : undefined),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.item_description.trim()) {
      setError('Bitte Beschreibung eingeben.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: RepairJobCreateInput = {
        ...form,
        metal_type: form.metal_type || undefined,
        estimated_completion_date: form.estimated_completion_date
          ? new Date(form.estimated_completion_date).toISOString()
          : undefined,
      };
      const created = await repairsApi.create(payload);
      // Cast full RepairJob to list item shape for the table
      onCreated(created as unknown as RepairJobListItem);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Fehler beim Speichern.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-header">
          <h2 id="modal-title">Neue Reparatur</h2>
          <button className="modal-close" onClick={onClose} aria-label="Schließen">&#x2715;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="repairs-error">{error}</div>}

            <div className="form-group">
              <label className="form-label" htmlFor="item_description">
                Beschreibung <span className="required">*</span>
              </label>
              <textarea
                id="item_description"
                name="item_description"
                className="form-textarea"
                placeholder="z.B. Ehering Gelbgold 585, Stein lose — Neufassung erforderlich"
                value={form.item_description}
                onChange={handleChange}
                required
                rows={3}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="item_type">
                  Art <span className="required">*</span>
                </label>
                <select
                  id="item_type"
                  name="item_type"
                  className="form-select"
                  value={form.item_type}
                  onChange={handleChange}
                >
                  {ITEM_TYPES.map(t => (
                    <option key={t} value={t}>{ITEM_TYPE_LABELS[t]}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="metal_type">Metall</label>
                <input
                  id="metal_type"
                  name="metal_type"
                  className="form-input"
                  placeholder="z.B. 585 Gelbgold"
                  value={form.metal_type ?? ''}
                  onChange={handleChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="customer_id">Kunden-ID</label>
                <input
                  id="customer_id"
                  name="customer_id"
                  type="number"
                  min={1}
                  className="form-input"
                  placeholder="Optional"
                  value={form.customer_id ?? ''}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="estimated_value">
                  Versicherungswert (EUR)
                </label>
                <input
                  id="estimated_value"
                  name="estimated_value"
                  type="number"
                  min={0}
                  step={0.01}
                  className="form-input"
                  placeholder="Optional"
                  value={form.estimated_value ?? ''}
                  onChange={handleChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="estimated_completion_date">
                Voraussichtliche Fertigstellung
              </label>
              <input
                id="estimated_completion_date"
                name="estimated_completion_date"
                type="date"
                className="form-input"
                value={
                  form.estimated_completion_date
                    ? form.estimated_completion_date.slice(0, 10)
                    : ''
                }
                onChange={handleChange}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Abbrechen
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Wird gespeichert…' : 'Reparatur anlegen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function RepairsPage() {
  const navigate = useNavigate();
  const [repairs, setRepairs] = useState<RepairJobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<RepairJobStatus | ''>('');
  const [searchTerm, setSearchTerm] = useState('');
  const [showModal, setShowModal] = useState(false);

  const loadRepairs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        status?: RepairJobStatus;
        search?: string;
        limit: number;
      } = { limit: 200 };
      if (statusFilter) params.status = statusFilter;
      if (searchTerm.trim()) params.search = searchTerm.trim();
      const data = await repairsApi.getAll(params);
      setRepairs(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchTerm]);

  useEffect(() => {
    const timer = setTimeout(loadRepairs, searchTerm ? 300 : 0);
    return () => clearTimeout(timer);
  }, [loadRepairs, searchTerm]);

  const handleCreated = (repair: RepairJobListItem) => {
    setRepairs(prev => [repair, ...prev]);
    setShowModal(false);
  };

  const handleRowClick = (id: number) => {
    navigate(`/repairs/${id}`);
  };

  const ALL_STATUSES: RepairJobStatus[] = [
    'received', 'diagnosed', 'quoted', 'approved',
    'in_repair', 'quality_check', 'ready', 'picked_up', 'cancelled',
  ];

  return (
    <div className="repairs-page">
      <div className="repairs-header">
        <h1>Reparaturen</h1>
        <button className="btn-new-repair" onClick={() => setShowModal(true)}>
          + Neue Reparatur
        </button>
      </div>

      <div className="repairs-toolbar">
        <input
          type="search"
          className="repairs-search"
          placeholder="Suche nach Nr., Tüte oder Beschreibung…"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          aria-label="Reparaturen suchen"
        />
        <select
          className="repairs-filter-select"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as RepairJobStatus | '')}
          aria-label="Nach Status filtern"
        >
          <option value="">Alle Status</option>
          {ALL_STATUSES.map(s => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
      </div>

      {error && <div className="repairs-error">{error}</div>}

      {loading ? (
        <div className="repairs-loading">Laden…</div>
      ) : repairs.length === 0 ? (
        <div className="repairs-empty">
          <div className="repairs-empty-icon">&#128295;</div>
          <h3>Keine Reparaturen gefunden</h3>
          <p>
            {statusFilter || searchTerm
              ? 'Passen Sie die Filter an oder suchen Sie nach einem anderen Begriff.'
              : 'Legen Sie den ersten Reparaturauftrag über die Schaltfläche oben an.'}
          </p>
        </div>
      ) : (
        <div className="repairs-table-wrapper">
          <table className="repairs-table">
            <thead>
              <tr>
                <th>Nr.</th>
                <th>Tüte</th>
                <th>Kunde</th>
                <th>Gegenstand</th>
                <th>Status</th>
                <th>Deadline</th>
                <th>KVA</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {repairs.map(r => (
                <tr key={r.id} onClick={() => handleRowClick(r.id)}>
                  <td className="repair-number-cell">{r.repair_number}</td>
                  <td className="repair-bag-cell">{r.bag_number}</td>
                  <td>
                    {r.customer
                      ? `${r.customer.first_name} ${r.customer.last_name}`
                      : '—'}
                  </td>
                  <td className="repair-description-cell" title={r.item_description}>
                    <span>{ITEM_TYPE_LABELS[r.item_type]}</span>
                    {r.metal_type && (
                      <span style={{ color: 'var(--color-text-muted)', marginLeft: '0.3rem', fontSize: '0.8rem' }}>
                        {r.metal_type}
                      </span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td
                    className={`repair-deadline-cell ${deadlineClass(r.estimated_completion_date)}`}
                  >
                    {formatDate(r.estimated_completion_date)}
                  </td>
                  <td>
                    {r.estimated_cost != null
                      ? `${r.estimated_cost.toFixed(2)} EUR`
                      : '—'}
                  </td>
                  <td>
                    <div className="repair-actions" onClick={e => e.stopPropagation()}>
                      <button
                        className="btn-repair-action"
                        onClick={() => handleRowClick(r.id)}
                        title="Details anzeigen"
                      >
                        Details
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <NewRepairModal
          onClose={() => setShowModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
