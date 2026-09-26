// repairKeys re-export (W7 followup): the canonical shape now lives in
// api/queryKeys.ts as queryKeys.repairs; this file keeps a deprecated
// re-export for one release. See docs/technical/FRONTEND_DATA_LAYER.md.
import { describe, expect, it } from 'vitest';

import { repairKeys } from './repairQueries';
import { queryKeys } from './queryKeys';

describe('repairKeys (deprecated re-export)', () => {
  it('is the same object as queryKeys.repairs', () => {
    expect(repairKeys).toBe(queryKeys.repairs);
  });

  it('builds the same keys as the canonical queryKeys.repairs root', () => {
    expect(repairKeys.all).toEqual(['repairs']);
    expect(repairKeys.detail(7)).toEqual(queryKeys.repairs.detail(7));
    expect(repairKeys.customerUpdates(7)).toEqual(queryKeys.repairs.customerUpdates(7));
    expect(repairKeys.page({ limit: 20, offset: 0 })).toEqual(
      queryKeys.repairs.page({ limit: 20, offset: 0 }),
    );
  });
});
