/**
 * Jobs spine API (ARCH-02, docs/architecture/ADR-2026-09-25-jobs-spine.md).
 *
 * `GET /jobs` lists orders and repairs together (Page envelope). The
 * Werkstatt board reads one page per unified status column. `status` is a
 * repeatable query parameter, so arrays go out as `status=a&status=b`
 * (FastAPI's list form), not axios' default `status[]=a`.
 *
 * `POST /repairs/{id}/invoice` bills a finished repair through the regular
 * invoice path (numbering, snapshot, §14 UStG).
 */
import apiClient from './client';
import type { ApiInvoice, Schema } from './generated';
import { compactParams, type PageParams, type PageResponse } from './paged';

export type JobStatus = Schema<'JobStatus'>;
export type JobKind = Schema<'JobKind'>;
export type JobsPage = PageResponse<'/api/v1/jobs/'>;
export type JobListItem = JobsPage['items'][number];
export type JobPageParams = PageParams<'/api/v1/jobs/'>;
export type RepairInvoiceInput = Schema<'RepairInvoiceCreate'>;

function isJobsPage(body: unknown): body is JobsPage {
  if (body === null || typeof body !== 'object') return false;
  const candidate = body as { items?: unknown; total?: unknown };
  return Array.isArray(candidate.items) && typeof candidate.total === 'number';
}

export const jobsApi = {
  /** One page of jobs; empty filters are dropped. */
  page: async (params: JobPageParams, signal?: AbortSignal): Promise<JobsPage> => {
    const response = await apiClient.get<unknown>('/jobs/', {
      params: compactParams(params),
      paramsSerializer: { indexes: null },
      signal,
    });
    if (!isJobsPage(response.data)) {
      throw new Error('Unerwartete Antwort von /jobs/: keine Seiten-Hülle (items/total).');
    }
    return response.data;
  },

  /** Invoice a READY / PICKED_UP repair. 409: already invoiced; 422: not billable. */
  invoiceRepair: async (repairId: number, data: RepairInvoiceInput): Promise<ApiInvoice> => {
    const response = await apiClient.post<ApiInvoice>(`/repairs/${repairId}/invoice`, data);
    return response.data;
  },
};
