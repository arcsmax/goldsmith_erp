// CustomerInfoCard - Display customer information with data fetching
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { customersApi } from '../../api';

interface Customer {
  id: number;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  email: string;
  phone?: string | null;
  mobile?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country?: string | null;
  customer_type: 'private' | 'business';
  is_active: boolean;
}

interface CustomerInfoCardProps {
  customerId: number;
}

export const CustomerInfoCard: React.FC<CustomerInfoCardProps> = ({ customerId }) => {
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCustomer();
  }, [customerId]);

  const fetchCustomer = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await customersApi.getById(customerId);
      setCustomer(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Kundendaten');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="customer-info-card loading">
        <div className="loading-spinner">Lade Kundendaten...</div>
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="customer-info-card error">
        <div className="error-message">
          ❌ {error || 'Kunde nicht gefunden'}
        </div>
        <div className="customer-id-fallback">Kunde-ID: #{customerId}</div>
      </div>
    );
  }

  const fullName = `${customer.first_name} ${customer.last_name}`;
  const primaryPhone = customer.mobile || customer.phone;

  return (
    <div className="customer-info-card">
      {/* Customer Name */}
      <div className="customer-header">
        <div className="customer-name">
          <span className="customer-icon">👤</span>
          {fullName}
        </div>
        {customer.company_name && (
          <div className="customer-company">{customer.company_name}</div>
        )}
      </div>

      {/* Customer Details */}
      <div className="customer-details">
        {customer.email && (
          <div className="customer-detail-line">
            <span className="detail-icon">📧</span>
            <a href={`mailto:${customer.email}`} className="detail-link">
              {customer.email}
            </a>
          </div>
        )}

        {primaryPhone && (
          <div className="customer-detail-line">
            <span className="detail-icon">📱</span>
            <a href={`tel:${primaryPhone}`} className="detail-link">
              {primaryPhone}
            </a>
          </div>
        )}

        {(customer.street || customer.city || customer.postal_code || customer.country) && (
          <div className="customer-detail-line">
            <span className="detail-icon">📍</span>
            <span className="detail-text">
              {[
                customer.street,
                customer.postal_code && customer.city
                  ? `${customer.postal_code} ${customer.city}`
                  : customer.postal_code || customer.city,
                customer.country,
              ]
                .filter(Boolean)
                .join(', ')}
            </span>
          </div>
        )}

        <div className="customer-detail-line">
          <span className="detail-icon">
            {customer.customer_type === 'business' ? '🏢' : '👤'}
          </span>
          <span className="detail-text">
            {customer.customer_type === 'business' ? 'Geschäftskunde' : 'Privatkunde'}
          </span>
        </div>

        {!customer.is_active && (
          <div className="customer-detail-line inactive">
            <span className="detail-icon">⛔</span>
            <span className="detail-text">Inaktiv</span>
          </div>
        )}
      </div>

      {/* Link to Customer Profile */}
      <div className="customer-actions">
        <button
          className="btn-customer-link"
          onClick={() => navigate(`/customers/${customer.id}`)}
        >
          🔗 Kundenprofil ansehen
        </button>
      </div>
    </div>
  );
};
