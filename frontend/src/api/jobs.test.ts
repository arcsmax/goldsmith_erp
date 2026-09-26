// api/jobs: the repeatable `status` filter must reach FastAPI as
// `status=a&status=b` (axios' default would send `status[]=a`), and a
// response without the Page envelope fails loudly.
import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mockGet = vi.fn();
vi.mock('./client', () => ({ default: { get: (...a: unknown[]) => mockGet(...a) } }));

import { jobsApi } from './jobs';

afterEach(() => mockGet.mockReset());

describe('jobsApi.page', () => {
  it('serialises status as a repeated parameter and drops empty filters', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 200, offset: 0, next_offset: null } });

    await jobsApi.page({ status: ['draft', 'on_hold'], kind: undefined, limit: 200, offset: 0 });

    const [url, config] = mockGet.mock.calls[0];
    expect(url).toBe('/jobs/');
    expect(config.params).toEqual({ status: ['draft', 'on_hold'], limit: 200, offset: 0 });
    const query = axios.getUri({ url: '/jobs/', params: config.params, paramsSerializer: config.paramsSerializer });
    expect(query).toBe('/jobs/?status=draft&status=on_hold&limit=200&offset=0');
  });

  it('throws when the answer has no Page envelope', async () => {
    mockGet.mockResolvedValue({ data: [] });
    await expect(jobsApi.page({ limit: 1, offset: 0 })).rejects.toThrow('keine Seiten-Hülle');
  });
});
