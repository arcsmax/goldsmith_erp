// MeasurementPanel smoke test — Task 6 (V1.1 consultation wizard).
//
// Full behavioral coverage (payload shape, error surfacing, form submit)
// already lives in frontend/src/test/MeasurementForm.test.tsx and exercises
// the same code via the CustomerDetailPage re-exports. This test just
// verifies the extracted, reusable component renders a fetched list given
// its narrowed `customer` prop.
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../api/measurements', () => ({
  measurementsApi: {
    getForCustomer: vi.fn().mockResolvedValue({
      data: [
        { id: 1, customer_id: 1, measurement_type: 'chain_length', value: 45, unit: 'cm', measured_at: '2026-01-01T00:00:00Z' },
      ],
    }),
    add: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    getRingSize: vi.fn(),
  },
}));

import { MeasurementPanel } from './MeasurementPanel';
import { measurementsApi } from '../../api/measurements';

describe('MeasurementPanel', () => {
  it('loads and renders the measurement list for the given customer', async () => {
    render(
      <MeasurementPanel
        customer={{ id: 1, ring_size: 53, chain_length_cm: null, bracelet_length_cm: null }}
      />
    );

    await waitFor(() => expect(measurementsApi.getForCustomer).toHaveBeenCalledWith(1));

    expect(await screen.findByText(/45 cm/)).toBeInTheDocument();
    // Legacy field from the Pick<Customer, ...> prop still renders.
    expect(screen.getByText(/53 mm/)).toBeInTheDocument();
  });
});
