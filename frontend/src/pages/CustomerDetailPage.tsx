// CustomerDetailPage — Kunden 360° Detailansicht
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { customersApi, ordersApi } from '../api';
import { measurementsApi } from '../api/measurements';
import { photosApi } from '../api/photos';
import AuthenticatedImage from '../components/AuthenticatedImage';
import { CustomerFormModal } from '../components/CustomerFormModal';
import { Customer, CustomerMeasurement, CustomerCreateInput, CustomerUpdateInput, OrderType } from '../types';
import '../styles/customer-detail.css';

type CustomerDetailTab = 'stammdaten' | 'masse' | 'auftraege' | 'rechnungen';

// ============================================================
// Helpers
// ============================================================

const getStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    new: 'Neu',
    draft: 'Entwurf',
    confirmed: 'Bestätigt',
    in_progress: 'In Bearbeitung',
    waiting_for_fitting: 'Wartet auf Anprobe',
    fitting_done: 'Anprobe fertig',
    ready_for_setting: 'Bereit zum Fassen',
    quality_check: 'Qualitätsprüfung',
    completed: 'Fertig',
    delivered: 'Ausgeliefert',
  };
  return labels[status] || status;
};

const formatDate = (dateStr?: string | null): string => {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('de-DE');
};

// ============================================================
// Sub-components
// ============================================================

const StammdatenTab: React.FC<{ customer: Customer; onEdit: () => void }> = ({ customer, onEdit }) => (
  <div className="cdetail-panel tab-panel">
    <div className="cdetail-panel__header">
      <h2>Stammdaten</h2>
      <button className="btn-primary" onClick={onEdit}>
        Bearbeiten
      </button>
    </div>

    <div className="cdetail-info-grid">
      {/* Personal */}
      <section className="cdetail-section">
        <h3 className="cdetail-section__title">Persönliche Daten</h3>
        <dl className="cdetail-dl">
          <dt>Vorname</dt>
          <dd>{customer.first_name}</dd>
          <dt>Nachname</dt>
          <dd>{customer.last_name}</dd>
          {customer.company_name && (
            <>
              <dt>Firma</dt>
              <dd>{customer.company_name}</dd>
            </>
          )}
          {customer.birthday && (
            <>
              <dt>Geburtstag</dt>
              <dd>{formatDate(customer.birthday)}</dd>
            </>
          )}
          <dt>Kundenseit</dt>
          <dd>{formatDate(customer.created_at)}</dd>
          <dt>Status</dt>
          <dd>
            <span className={`cdetail-status-badge ${customer.is_active ? 'active' : 'inactive'}`}>
              {customer.is_active ? 'Aktiv' : 'Inaktiv'}
            </span>
          </dd>
        </dl>
      </section>

      {/* Contact */}
      <section className="cdetail-section">
        <h3 className="cdetail-section__title">Kontakt</h3>
        <dl className="cdetail-dl">
          <dt>E-Mail</dt>
          <dd>
            {customer.email ? (
              <a href={`mailto:${customer.email}`} className="cdetail-link">
                {customer.email}
              </a>
            ) : '—'}
          </dd>
          <dt>Telefon</dt>
          <dd>
            {customer.phone ? (
              <a href={`tel:${customer.phone}`} className="cdetail-link">
                {customer.phone}
              </a>
            ) : '—'}
          </dd>
          <dt>Mobil</dt>
          <dd>
            {customer.mobile ? (
              <a href={`tel:${customer.mobile}`} className="cdetail-link">
                {customer.mobile}
              </a>
            ) : '—'}
          </dd>
        </dl>
      </section>

      {/* Address */}
      <section className="cdetail-section">
        <h3 className="cdetail-section__title">Adresse</h3>
        <dl className="cdetail-dl">
          <dt>Straße</dt>
          <dd>{customer.street || '—'}</dd>
          <dt>PLZ / Stadt</dt>
          <dd>
            {customer.postal_code || customer.city
              ? `${customer.postal_code || ''} ${customer.city || ''}`.trim()
              : '—'}
          </dd>
          <dt>Land</dt>
          <dd>{customer.country || '—'}</dd>
        </dl>
      </section>

      {/* Preferences */}
      <section className="cdetail-section">
        <h3 className="cdetail-section__title">Präferenzen & Allergien</h3>
        <dl className="cdetail-dl">
          <dt>Allergien</dt>
          <dd>{customer.allergies || '—'}</dd>
          {customer.preferences && Object.keys(customer.preferences).length > 0 && (
            <>
              {Object.entries(customer.preferences).map(([key, value]) => (
                <React.Fragment key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </React.Fragment>
              ))}
            </>
          )}
        </dl>
        {customer.tags.length > 0 && (
          <div className="cdetail-tags">
            {customer.tags.map((tag) => (
              <span key={tag} className="cdetail-tag">{tag}</span>
            ))}
          </div>
        )}
      </section>

      {/* Notes */}
      {customer.notes && (
        <section className="cdetail-section cdetail-section--full">
          <h3 className="cdetail-section__title">Notizen</h3>
          <p className="cdetail-notes">{customer.notes}</p>
        </section>
      )}
    </div>
  </div>
);

// ============================================================

const HAND_OPTIONS = ['Links', 'Rechts'];
const FINGER_OPTIONS = [
  'Daumen', 'Zeigefinger', 'Mittelfinger', 'Ringfinger', 'Kleiner Finger',
];

// Values must exactly match the backend MeasurementType enum values.
const MEASUREMENT_TYPES = [
  { value: 'ring_size', label: 'Ringgröße (mm)' },
  { value: 'chain_length', label: 'Kettenlänge (cm)' },
  { value: 'wrist_circumference', label: 'Handgelenkumfang (cm)' },
  { value: 'finger_circumference', label: 'Fingerumfang (mm)' },
  { value: 'neck_circumference', label: 'Halsumfang (cm)' },
  { value: 'ankle_circumference', label: 'Knöchelumfang (cm)' },
];

const MasseTab: React.FC<{ customer: Customer }> = ({ customer }) => {
  const [measurements, setMeasurements] = useState<CustomerMeasurement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    type: 'ring_size',
    value: '',
    hand: 'Links',
    finger: 'Ringfinger',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadMeasurements = useCallback(async () => {
    try {
      setIsLoading(true);
      const resp = await measurementsApi.getForCustomer(customer.id);
      setMeasurements(resp.data || []);
    } catch {
      // Backend may not have this endpoint yet — fall back to legacy fields
      setMeasurements([]);
    } finally {
      setIsLoading(false);
    }
  }, [customer.id]);

  useEffect(() => {
    loadMeasurements();
  }, [loadMeasurements]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSubmitting(true);
      await measurementsApi.add(customer.id, formData);
      setShowForm(false);
      setFormData({ type: 'ring_size', value: '', hand: 'Links', finger: 'Ringfinger' });
      await loadMeasurements();
    } catch {
      // Ignore if endpoint not yet implemented
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (measurementId: number) => {
    try {
      setDeletingId(measurementId);
      await measurementsApi.remove(measurementId);
      await loadMeasurements();
    } catch {
      // Ignore if endpoint not yet implemented
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="cdetail-panel tab-panel">
      <div className="cdetail-panel__header">
        <h2>Maßbibliothek</h2>
        <button
          className="btn-primary cdetail-btn-add"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? 'Abbrechen' : '+ Maß hinzufügen'}
        </button>
      </div>

      {/* Legacy fields from Customer record */}
      <div className="cdetail-legacy-masse">
        <h3 className="cdetail-section__title">Gespeicherte Maße</h3>
        <div className="cdetail-masse-cards">
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#128141;</span>
            <span className="cdetail-mass-label">Ringgröße</span>
            <span className="cdetail-mass-value">
              {customer.ring_size != null ? `${customer.ring_size} mm` : '—'}
            </span>
          </div>
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#128278;</span>
            <span className="cdetail-mass-label">Kettenlänge</span>
            <span className="cdetail-mass-value">
              {customer.chain_length_cm != null ? `${customer.chain_length_cm} cm` : '—'}
            </span>
          </div>
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#8987;</span>
            <span className="cdetail-mass-label">Armbandlänge</span>
            <span className="cdetail-mass-value">
              {customer.bracelet_length_cm != null ? `${customer.bracelet_length_cm} cm` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Add measurement form */}
      {showForm && (
        <form className="cdetail-masse-form" onSubmit={handleAdd}>
          <div className="form-group">
            <label>Maßart</label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            >
              {MEASUREMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Wert</label>
            <input
              type="number"
              step="0.1"
              value={formData.value}
              onChange={(e) => setFormData({ ...formData, value: e.target.value })}
              placeholder="z. B. 53.4"
              required
            />
          </div>
          {(formData.type === 'ring_size' || formData.type === 'finger_circumference') && (
            <>
              <div className="form-group">
                <label>Hand</label>
                <select
                  value={formData.hand}
                  onChange={(e) => setFormData({ ...formData, hand: e.target.value })}
                >
                  {HAND_OPTIONS.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Finger</label>
                <select
                  value={formData.finger}
                  onChange={(e) => setFormData({ ...formData, finger: e.target.value })}
                >
                  {FINGER_OPTIONS.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </div>
            </>
          )}
          <div className="cdetail-masse-form__actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting || !formData.value}
            >
              {isSubmitting ? 'Speichern...' : 'Maß speichern'}
            </button>
          </div>
        </form>
      )}

      {/* Dynamic measurements list */}
      {isLoading ? (
        <div className="cdetail-loading">Lade Maße...</div>
      ) : measurements.length > 0 ? (
        <div className="cdetail-masse-list">
          <h3 className="cdetail-section__title">Weitere Maße</h3>
          {measurements.map((m) => (
            <div key={m.id} className="cdetail-mass-card cdetail-mass-card--dynamic">
              <span className="cdetail-mass-label">
                {MEASUREMENT_TYPES.find((t) => t.value === m.measurement_type)?.label || m.measurement_type}
                {m.hand && m.finger && (
                  <span className="cdetail-mass-sublabel"> · {m.hand}, {m.finger}</span>
                )}
              </span>
              <span className="cdetail-mass-value">{m.value} {m.unit}</span>
              <button
                className="cdetail-mass-delete"
                aria-label="Maß löschen"
                disabled={deletingId === m.id}
                onClick={() => handleDelete(m.id)}
              >
                {deletingId === m.id ? '...' : 'Löschen'}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

// ============================================================

// Maps order.id -> first photo URL path (or null if no photos)
type PhotoMap = Record<number, string | null>;

const AuftraegeTab: React.FC<{ customerId: number }> = ({ customerId }) => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [photoMap, setPhotoMap] = useState<PhotoMap>({});

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        // Use server-side customer_id filter to avoid loading all orders client-side
        const customerOrders = await ordersApi.getAll({ customer_id: customerId, limit: 50 });
        // Sort: newest first (backend already orders by created_at desc, but enforce here too)
        customerOrders.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setOrders(customerOrders);

        // Fetch first photo for each order lazily (fire-and-forget per order)
        customerOrders.forEach(async (order) => {
          try {
            const resp = await photosApi.getForOrder(order.id);
            const photos: any[] = Array.isArray(resp.data)
              ? resp.data
              : (resp.data as any)?.items ?? [];
            const firstPhoto = photos[0] ?? null;
            // Prefer a pre-built file URL; fall back to constructed path
            const photoSrc: string | null = firstPhoto
              ? (firstPhoto.file_url ?? `/orders/${order.id}/photos/${firstPhoto.id}/file`)
              : null;
            setPhotoMap((prev) => ({ ...prev, [order.id]: photoSrc }));
          } catch {
            // Backend may not implement this endpoint yet — show placeholder
            setPhotoMap((prev) => ({ ...prev, [order.id]: null }));
          }
        });
      } catch {
        setError('Fehler beim Laden der Auftragshistorie');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [customerId]);

  if (isLoading) return <div className="cdetail-loading">Lade Aufträge...</div>;
  if (error) return <div className="cdetail-error">{error}</div>;

  return (
    <div className="cdetail-panel tab-panel">
      <div className="cdetail-panel__header">
        <h2>Auftragshistorie ({orders.length})</h2>
      </div>
      {orders.length === 0 ? (
        <div className="cdetail-empty">
          <p>Noch keine Aufträge für diesen Kunden vorhanden.</p>
        </div>
      ) : (
        <div className="cdetail-timeline">
          {orders.map((order) => {
            const photoSrc = photoMap[order.id];
            return (
              <div
                key={order.id}
                className="cdetail-timeline-card"
                onClick={() => navigate(`/orders/${order.id}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && navigate(`/orders/${order.id}`)}
              >
                <div className="cdetail-timeline-marker" />
                {/* Thumbnail — shown once photo map entry resolves */}
                {order.id in photoMap ? (
                  photoSrc ? (
                    <AuthenticatedImage
                      src={photoSrc}
                      alt={`Foto für Auftrag #${order.id}`}
                    />
                  ) : (
                    <div
                      className="cdetail-timeline-thumb-placeholder"
                      aria-label="Kein Foto vorhanden"
                      role="img"
                    >
                      &#128247;
                    </div>
                  )
                ) : null}
                <div className="cdetail-timeline-content">
                  <div className="cdetail-timeline-header">
                    <span className="cdetail-timeline-id">#{order.id}</span>
                    <span className={`status-badge status-${order.status}`}>
                      {getStatusLabel(order.status)}
                    </span>
                  </div>
                  <h4 className="cdetail-timeline-title">{order.title}</h4>
                  <div className="cdetail-timeline-meta">
                    <span>Erstellt: {formatDate(order.created_at)}</span>
                    {order.deadline && (
                      <span>Deadline: {formatDate(order.deadline)}</span>
                    )}
                    {order.price != null && (
                      <span className="cdetail-timeline-price">
                        {order.price.toFixed(2)} €
                      </span>
                    )}
                  </div>
                </div>
                <span className="cdetail-timeline-arrow">›</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ============================================================

const RechnungenTab: React.FC<{ customerId: number }> = ({ customerId }) => {
  const [invoices, setInvoices] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const handleDownloadPdf = async (invoiceId: number, invoiceNumber: string) => {
    try {
      setDownloadingId(invoiceId);
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/v1/invoices/${invoiceId}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Rechnung_${invoiceNumber || invoiceId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Silently ignore — backend PDF endpoint may not be implemented yet
    } finally {
      setDownloadingId(null);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        // Import lazily to avoid circular imports
        const { invoicesApi } = await import('../api/invoices');
        const data = await invoicesApi.getAll({ limit: 200 });
        const items = Array.isArray(data) ? data : (data as any).items || [];
        const customerInvoices = items.filter(
          (inv: any) => inv.customer_id === customerId
        );
        setInvoices(customerInvoices);
      } catch {
        setError('Fehler beim Laden der Rechnungen');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [customerId]);

  if (isLoading) return <div className="cdetail-loading">Lade Rechnungen...</div>;
  if (error) return <div className="cdetail-error">{error}</div>;

  return (
    <div className="cdetail-panel tab-panel">
      <div className="cdetail-panel__header">
        <h2>Rechnungen ({invoices.length})</h2>
      </div>
      {invoices.length === 0 ? (
        <div className="cdetail-empty">
          <p>Noch keine Rechnungen für diesen Kunden vorhanden.</p>
        </div>
      ) : (
        <div className="cdetail-invoices-list">
          {invoices.map((inv) => (
            <div key={inv.id} className="cdetail-invoice-card">
              <div className="cdetail-invoice-number">{inv.invoice_number || `#${inv.id}`}</div>
              <div className="cdetail-invoice-meta">
                <span>{formatDate(inv.issue_date || inv.created_at)}</span>
                {inv.due_date && <span>Fällig: {formatDate(inv.due_date)}</span>}
              </div>
              <span className={`invoice-status-badge status-${inv.status || 'DRAFT'}`}>
                {inv.status || 'ENTWURF'}
              </span>
              {inv.total_amount != null && (
                <span className="cdetail-invoice-amount">
                  {Number(inv.total_amount).toFixed(2)} €
                </span>
              )}
              <button
                className="btn-pdf-download"
                aria-label={`Rechnung ${inv.invoice_number || inv.id} als PDF herunterladen`}
                disabled={downloadingId === inv.id}
                onClick={() => handleDownloadPdf(inv.id, inv.invoice_number || String(inv.id))}
              >
                {downloadingId === inv.id ? '...' : 'PDF'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ============================================================
// Main Page Component
// ============================================================

export const CustomerDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<CustomerDetailTab>('stammdaten');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const loadCustomer = useCallback(async (customerId: number) => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await customersApi.getById(customerId);
      setCustomer(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Kunden');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!id) {
      navigate('/customers');
      return;
    }
    loadCustomer(parseInt(id));
  }, [id, navigate, loadCustomer]);

  const handleEditSubmit = useCallback(async (data: CustomerCreateInput | CustomerUpdateInput) => {
    if (!customer) return;
    try {
      setIsSaving(true);
      await customersApi.update(customer.id, data as CustomerUpdateInput);
      setIsEditModalOpen(false);
      await loadCustomer(customer.id);
    } catch (err: any) {
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, [customer, loadCustomer]);

  if (isLoading) {
    return <div className="page-loading">Lade Kunde...</div>;
  }

  if (error || !customer) {
    return (
      <div className="page-error">
        <p>{error || 'Kunde nicht gefunden'}</p>
        <button onClick={() => navigate('/customers')} className="btn-primary">
          Zurück zu Kunden
        </button>
      </div>
    );
  }

  const customerId = parseInt(id!);

  return (
    <div className="cdetail-container">
      {/* Breadcrumb */}
      <nav className="cdetail-breadcrumb" aria-label="Breadcrumb">
        <button
          className="cdetail-breadcrumb__link"
          onClick={() => navigate('/customers')}
        >
          Kunden
        </button>
        <span className="cdetail-breadcrumb__sep">›</span>
        <span className="cdetail-breadcrumb__current">
          {customer.first_name} {customer.last_name}
        </span>
      </nav>

      {/* Header */}
      <header className="cdetail-header">
        <div className="cdetail-header__left">
          <button
            className="btn-back"
            onClick={() => navigate('/customers')}
          >
            {/* left arrow */}
            &larr; Zurück
          </button>
          <div className="cdetail-identity">
            <div className="cdetail-avatar">
              {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
            </div>
            <div>
              <h1 className="cdetail-name">
                {customer.first_name} {customer.last_name}
              </h1>
              {customer.company_name && (
                <p className="cdetail-company">{customer.company_name}</p>
              )}
            </div>
          </div>
        </div>
        <div className="cdetail-header__right">
          <span className={`cdetail-status-badge ${customer.is_active ? 'active' : 'inactive'}`}>
            {customer.is_active ? 'Aktiv' : 'Inaktiv'}
          </span>
          <span className="cdetail-type-badge">
            {customer.customer_type === 'business' ? 'Geschäftskunde' : 'Privatkunde'}
          </span>
        </div>
      </header>

      {/* Tabs */}
      <div className="cdetail-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'stammdaten'}
          className={`cdetail-tab ${activeTab === 'stammdaten' ? 'active' : ''}`}
          onClick={() => setActiveTab('stammdaten')}
        >
          Stammdaten
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'masse'}
          className={`cdetail-tab ${activeTab === 'masse' ? 'active' : ''}`}
          onClick={() => setActiveTab('masse')}
        >
          Maßbibliothek
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'auftraege'}
          className={`cdetail-tab ${activeTab === 'auftraege' ? 'active' : ''}`}
          onClick={() => setActiveTab('auftraege')}
        >
          Auftragshistorie
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'rechnungen'}
          className={`cdetail-tab ${activeTab === 'rechnungen' ? 'active' : ''}`}
          onClick={() => setActiveTab('rechnungen')}
        >
          Rechnungen
        </button>
      </div>

      {/* Tab Content */}
      <div className="cdetail-tab-content" role="tabpanel">
        {activeTab === 'stammdaten' && (
          <StammdatenTab customer={customer} onEdit={() => setIsEditModalOpen(true)} />
        )}
        {activeTab === 'masse' && <MasseTab customer={customer} />}
        {activeTab === 'auftraege' && <AuftraegeTab customerId={customerId} />}
        {activeTab === 'rechnungen' && <RechnungenTab customerId={customerId} />}
      </div>

      {/* Edit Customer Modal */}
      <CustomerFormModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onSubmit={handleEditSubmit}
        customer={customer}
        isLoading={isSaving}
      />
    </div>
  );
};
