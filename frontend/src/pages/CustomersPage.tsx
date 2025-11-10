// CustomersPage - Customer Management
import React, { useEffect, useState } from 'react';
import { customersApi } from '../api';
import { CustomerListItem } from '../types';
import '../styles/pages.css';
import '../styles/customers.css';

export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<CustomerListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCustomers();
  }, []);

  const fetchCustomers = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await customersApi.getAll();
      setCustomers(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Kunden');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <div className="page-loading">Lade Kunden...</div>;
  }

  if (error) {
    return (
      <div className="page-error">
        {error}
        <button onClick={fetchCustomers} className="btn-primary">
          Erneut versuchen
        </button>
      </div>
    );
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Kunden</h1>
        <button className="btn-primary">+ Neuer Kunde</button>
      </header>

      {customers.length === 0 ? (
        <div className="empty-state">
          <p>Keine Kunden vorhanden.</p>
          <p className="error-hint">Erstellen Sie Ihren ersten Kunden, um loszulegen.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Firma</th>
                <th>E-Mail</th>
                <th>Typ</th>
                <th>Status</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => (
                <tr key={customer.id}>
                  <td>#{customer.id}</td>
                  <td>{customer.first_name} {customer.last_name}</td>
                  <td>{customer.company_name || '-'}</td>
                  <td>{customer.email}</td>
                  <td>
                    <span className="customer-type-badge">
                      {customer.customer_type === 'private' ? '👤 Privat' : '🏢 Geschäftskunde'}
                    </span>
                  </td>
                  <td>
                    <span className={`customer-status ${customer.is_active ? 'active' : 'inactive'}`}>
                      {customer.is_active ? '✅ Aktiv' : '⛔ Inaktiv'}
                    </span>
                  </td>
                  <td className="customer-actions">
                    <button
                      className="btn-action"
                      title="Bearbeiten"
                      onClick={() => console.log('Edit:', customer.id)}
                    >
                      ✏️
                    </button>
                    <button
                      className="btn-action btn-danger"
                      title="Löschen"
                      onClick={() => console.log('Delete:', customer.id)}
                    >
                      🗑️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
