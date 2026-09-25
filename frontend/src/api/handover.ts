// Abholprotokoll (W2-11, DOM-35): handover report PDF of a finished order.
import apiClient from './client';

export async function downloadHandoverPdf(orderId: number): Promise<Blob> {
  const response = await apiClient.get(`/orders/${orderId}/handover-pdf`, {
    responseType: 'blob',
  });
  return response.data as Blob;
}

/** Trigger the browser download for a PDF blob. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
