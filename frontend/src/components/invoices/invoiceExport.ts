// Accounting export download (DATEV / Lexoffice CSV), ADMIN only.
//
// Goes through the axios client, so the session is sent the same way as for
// every other request; the token never lands in a URL (server logs, history).
import apiClient from '../../api/client';
import type { InvoiceListFilter } from './useInvoiceQueries';

export type ExportFormat = 'datev' | 'lexoffice';

export const EXPORT_LABELS: Record<ExportFormat, string> = {
  datev: 'DATEV-Export',
  lexoffice: 'Lexoffice-Export',
};

function exportParams(format: ExportFormat, filter: InvoiceListFilter): URLSearchParams {
  const params = new URLSearchParams();
  if (filter.from) params.set('date_from', new Date(filter.from).toISOString());
  if (filter.to) params.set('date_to', new Date(filter.to).toISOString());
  if (filter.status && format === 'datev') params.set('status', filter.status);
  return params;
}

export async function downloadAccountingExport(
  format: ExportFormat,
  filter: InvoiceListFilter,
): Promise<void> {
  const response = await apiClient.get(`/invoices/export/${format}?${exportParams(format, filter)}`, {
    responseType: 'blob',
  });
  const blobUrl = URL.createObjectURL(response.data);
  const stamp = new Date().toISOString().substring(0, 10).replace(/-/g, '');
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = `${format}_export_${stamp}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(blobUrl);
}
