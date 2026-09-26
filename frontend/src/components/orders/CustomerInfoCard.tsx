// CustomerInfoCard: the order's customer on the Übersicht tab.
//
// W4-03: data through TanStack Query (queryKeys.customers.detail, shared
// with the customer pages), states via PageState, the profile link as a
// ButtonLink. Contact data is PII: rendered, never logged.
import { useQuery } from '@tanstack/react-query';
import { customersApi } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import type { Customer } from '../../types';
import { getErrorMessage } from '../../lib/errors';
import { ButtonLink, Card, PageState, type PageStateValue } from '../../ui';

interface CustomerInfoCardProps {
  customerId: number;
}

function formatAddress(customer: Customer): string {
  const cityLine =
    customer.postal_code && customer.city
      ? `${customer.postal_code} ${customer.city}`
      : customer.postal_code || customer.city;
  return [customer.street, cityLine, customer.country].filter(Boolean).join(', ');
}

function CustomerDetails({ customer }: { customer: Customer }) {
  const primaryPhone = customer.mobile || customer.phone;
  const address = formatAddress(customer);
  return (
    <>
      <p className="customer-name">
        {customer.first_name} {customer.last_name}
      </p>
      {customer.company_name && <p className="customer-company">{customer.company_name}</p>}
      <dl className="customer-details">
        {customer.email && (
          <div className="customer-detail-line">
            <dt>E-Mail</dt>
            <dd>
              <a href={`mailto:${customer.email}`} className="detail-link">
                {customer.email}
              </a>
            </dd>
          </div>
        )}
        {primaryPhone && (
          <div className="customer-detail-line">
            <dt>Telefon</dt>
            <dd>
              <a href={`tel:${primaryPhone}`} className="detail-link">
                {primaryPhone}
              </a>
            </dd>
          </div>
        )}
        {address && (
          <div className="customer-detail-line">
            <dt>Adresse</dt>
            <dd>{address}</dd>
          </div>
        )}
        <div className="customer-detail-line">
          <dt>Kundenart</dt>
          <dd>{customer.customer_type === 'business' ? 'Geschäftskunde' : 'Privatkunde'}</dd>
        </div>
        {!customer.is_active && (
          <div className="customer-detail-line inactive">
            <dt>Status</dt>
            <dd>Inaktiv</dd>
          </div>
        )}
      </dl>
    </>
  );
}

export function CustomerInfoCard({ customerId }: CustomerInfoCardProps) {
  const query = useQuery({
    queryKey: queryKeys.customers.detail(customerId),
    queryFn: () => customersApi.getById(customerId),
  });

  const state: PageStateValue = query.isPending
    ? { status: 'loading' }
    : query.isError
      ? {
          status: 'error',
          error: getErrorMessage(query.error, 'Kundendaten konnten nicht geladen werden.'),
          retry: () => void query.refetch(),
        }
      : { status: 'ready' };

  return (
    // Untitled: the Übersicht section around it carries the "Kunde" heading.
    <Card
      className="customer-info-card"
      action={
        <ButtonLink to={`/customers/${customerId}`} variant="secondary">
          Kundenprofil ansehen
        </ButtonLink>
      }
    >
      <PageState state={state} skeleton="detail" skeletonCount={3}>
        {query.data && <CustomerDetails customer={query.data} />}
      </PageState>
    </Card>
  );
}

export default CustomerInfoCard;
