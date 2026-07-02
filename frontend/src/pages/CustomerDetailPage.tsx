// CustomerDetailPage — Kunden 360° Detailansicht
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { customersApi, ordersApi } from '../api';
import apiClient from '../api/client';
import { photosApi } from '../api/photos';
import AuthenticatedImage from '../components/AuthenticatedImage';
import { CustomerFormModal } from '../components/CustomerFormModal';
import { Customer, CustomerCreateInput, CustomerUpdateInput, OrderType } from '../types';
import '../styles/customer-detail.css';
// Pulls the `.invoice-status-badge.status-{draft|sent|paid|overdue|cancelled}`
// rules used by the Rechnungen tab below. Without this the badges render
// unstyled — the same case-mismatch failure mode as the main /invoices page.
import '../styles/invoices.css';

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

/**
 * German labels for invoice status — keyed by the lowercase backend enum
 * value (see types.ts). The earlier UPPERCASE-leaning code rendered the
 * raw enum value because the lookup never matched.
 */
const INVOICE_STATUS_LABELS = {
  draft: 'Entwurf',
  sent: 'Versendet',
  paid: 'Bezahlt',
  overdue: 'Überfällig',
  cancelled: 'Storniert',
} as const;

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
// Maßbibliothek (measurements) — extracted to MeasurementPanel (Task 6) so
// it can be reused as consultation-wizard step 5. Re-export the helpers so
// `frontend/src/test/MeasurementForm.test.tsx` keeps importing them from
// this module unchanged.
export {
  HAND_OPTIONS,
  FINGER_OPTIONS,
  MEASUREMENT_TYPES,
  buildMeasurementPayload,
  extractMeasurementErrorMessage,
} from '../components/measurements/MeasurementPanel';
export type { MeasurementFormState } from '../components/measurements/MeasurementPanel';
import { MeasurementPanel } from '../components/measurements/MeasurementPanel';

export const MasseTab: React.FC<{ customer: Customer }> = ({ customer }) => (
  <MeasurementPanel customer={customer} />
);

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
      const response = await apiClient.get(`/invoices/${invoiceId}/pdf`, {
        responseType: 'blob',
      });
      const blob = response.data;
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
        const data = await invoicesApi.getInvoices({ limit: 200 });
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
              <span className={`invoice-status-badge status-${inv.status || 'draft'}`}>
                {INVOICE_STATUS_LABELS[inv.status as keyof typeof INVOICE_STATUS_LABELS] ?? 'Entwurf'}
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
