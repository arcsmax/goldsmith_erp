// Reparaturverwaltung — list view with status filter, search, and the
// counter intake (W2-12). `?neu=1` opens the intake, `&customer_id=` pre-
// selects the customer (link from the customer page's Verlauf).
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { repairsApi } from '../api/repairs';
import { RepairIntakeScreen } from '../components/repairs/RepairIntakeScreen';
import { useAuth } from '../contexts';
import { canCreateRepairs, canViewFinancials } from '../lib/roles';
import { logError } from '../lib/logError';
import type { RepairItemType, RepairJobListItem, RepairJobStatus } from '../types';
import { REPAIR_STATUS, statusLabelsFor } from '../design/status';
import { StatusBadge } from '../ui/StatusBadge';
import { formatEur, MONEY_CLASS } from '../lib/format';
import '../styles/repairs.css';

// ─── helpers ────────────────────────────────────────────────────────────────

// Labels come from the single status map (LV-05).
const STATUS_LABELS: Readonly<Record<RepairJobStatus, string>> =
  statusLabelsFor(REPAIR_STATUS);

const ITEM_TYPE_LABELS: Record<RepairItemType, string> = {
  ring: 'Ring',
  chain: 'Kette',
  bracelet: 'Armband',
  earring: 'Ohrringe',
  watch: 'Uhr',
  brooch: 'Brosche',
  other: 'Sonstiges',
};

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


const ALL_STATUSES: RepairJobStatus[] = [
  'received', 'diagnosed', 'quoted', 'approved',
  'in_repair', 'quality_check', 'ready', 'picked_up', 'cancelled',
];

const INTAKE_PARAM = 'neu';
const CUSTOMER_PARAM = 'customer_id';

// ─── Main Page ───────────────────────────────────────────────────────────────

export function RepairsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const showPrice = canViewFinancials(user?.role);
  const canCreate = canCreateRepairs(user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const [repairs, setRepairs] = useState<RepairJobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<RepairJobStatus | ''>('');
  const [searchTerm, setSearchTerm] = useState('');

  const isIntakeOpen = searchParams.get(INTAKE_PARAM) === '1';
  const intakeCustomerId = Number(searchParams.get(CUSTOMER_PARAM)) || undefined;

  const openIntake = () => setSearchParams({ [INTAKE_PARAM]: '1' });
  const closeIntake = () => setSearchParams({}, { replace: true });

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
      logError('RepairsPage.load', err);
      setError('Reparaturen konnten nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchTerm]);

  useEffect(() => {
    const timer = setTimeout(loadRepairs, searchTerm ? 300 : 0);
    return () => clearTimeout(timer);
  }, [loadRepairs, searchTerm]);

  // FE-17: after the intake, go straight to the new repair.
  const handleIntakeDone = (repairId: number) => navigate(`/repairs/${repairId}`);

  return (
    <div className="repairs-page">
      <div className="repairs-header">
        <h1>Reparaturen</h1>
        {canCreate && (
          <button type="button" className="btn-new-repair" onClick={openIntake}>
            Neue Reparatur
          </button>
        )}
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

      {error && (
        <div className="repairs-error" role="alert">
          {error}
          <button type="button" className="btn-secondary" onClick={loadRepairs}>
            Erneut versuchen
          </button>
        </div>
      )}

      {loading ? (
        <div className="repairs-loading" role="status">Wird geladen…</div>
      ) : repairs.length === 0 ? (
        <div className="repairs-empty">
          <h3>Keine Reparaturen gefunden</h3>
          <p>
            {statusFilter || searchTerm
              ? 'Passen Sie die Filter an oder suchen Sie nach einem anderen Begriff.'
              : 'Nehmen Sie die erste Reparatur an der Theke an.'}
          </p>
          {canCreate && (
            <button type="button" className="btn-primary" onClick={openIntake}>
              Neue Reparatur annehmen
            </button>
          )}
        </div>
      ) : (
        <div className="repairs-table-wrapper">
          <table className="repairs-table" aria-label="Reparaturen">
            <thead>
              <tr>
                <th>Nr.</th>
                <th>Tüte</th>
                <th>Kunde</th>
                <th>Gegenstand</th>
                <th>Status</th>
                <th>Zugesagt bis</th>
                {showPrice && <th>KVA</th>}
              </tr>
            </thead>
            <tbody>
              {repairs.map(r => (
                <tr key={r.id}>
                  <td className="repair-number-cell">
                    <Link to={`/repairs/${r.id}`} className="repair-row-link">
                      {r.repair_number}
                    </Link>
                  </td>
                  <td className="repair-bag-cell">{r.bag_number}</td>
                  <td>
                    {r.customer
                      ? `${r.customer.first_name} ${r.customer.last_name}`
                      : '—'}
                  </td>
                  <td className="repair-description-cell" title={r.item_description}>
                    <span>{ITEM_TYPE_LABELS[r.item_type]}</span>
                    {r.metal_type && <span className="repair-metal">{r.metal_type}</span>}
                  </td>
                  <td>
                    <StatusBadge kind="repair" status={r.status} />
                  </td>
                  <td
                    className={`repair-deadline-cell ${deadlineClass(r.estimated_completion_date)}`}
                  >
                    {formatDate(r.estimated_completion_date)}
                  </td>
                  {showPrice && <td className={MONEY_CLASS}>{formatEur(r.estimated_cost)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isIntakeOpen && (
        <RepairIntakeScreen
          onClose={closeIntake}
          onDone={handleIntakeDone}
          initialCustomerId={intakeCustomerId}
        />
      )}
    </div>
  );
}
