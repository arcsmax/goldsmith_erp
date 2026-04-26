// MeasurementForm (MasseTab) tests — Bug #4 fix.
//
// Scope:
//   * "Maß speichern" submits the EXACT shape the backend MeasurementCreate
//     model expects — `measurement_type` (not `type`), `unit` derived from
//     the chosen type, and `hand`/`finger` as backend enum values
//     ("left"/"right", "ring") not the German UI labels.
//   * Backend 422 errors no longer fail silently — the form surfaces the
//     validation message via role="alert".
//   * Pure helper `buildMeasurementPayload` returns correct shapes for all
//     measurement types.

import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the API client BEFORE importing the component.
vi.mock('../api/measurements', () => ({
  measurementsApi: {
    getForCustomer: vi.fn().mockResolvedValue({ data: [] }),
    add: vi.fn().mockResolvedValue({ data: {} }),
    update: vi.fn(),
    remove: vi.fn(),
    getRingSize: vi.fn(),
  },
}));

// Avoid pulling in axios/photos transitive deps.
vi.mock('../api', () => ({
  customersApi: { get: vi.fn(), update: vi.fn() },
  ordersApi: { getAll: vi.fn().mockResolvedValue([]) },
}));
vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../api/photos', () => ({
  photosApi: { getForOrder: vi.fn().mockResolvedValue({ data: [] }) },
}));

import {
  MasseTab,
  buildMeasurementPayload,
  extractMeasurementErrorMessage,
} from '../pages/CustomerDetailPage';
import { measurementsApi } from '../api/measurements';
import type { Customer } from '../types';

const mockCustomer: Customer = {
  id: 1,
  first_name: 'Anna',
  last_name: 'Test',
  email: 'anna@test.de',
  country: 'DE',
  customer_type: 'private',
  tags: [],
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

afterEach(() => {
  vi.clearAllMocks();
});

describe('buildMeasurementPayload', () => {
  it('builds the correct shape for ring_size with enum hand/finger and unit=mm', () => {
    const payload = buildMeasurementPayload({
      type: 'ring_size',
      value: '53',
      hand: 'left',
      finger: 'ring',
    });
    expect(payload).toEqual({
      measurement_type: 'ring_size',
      value: 53,
      unit: 'mm',
      hand: 'left',
      finger: 'ring',
    });
    // `type` (the form's local state key) must NOT appear in the request body.
    expect((payload as Record<string, unknown>).type).toBeUndefined();
    // measurement_type must NOT carry a "_mm" suffix (the original bug).
    expect(payload.measurement_type).toBe('ring_size');
  });

  it('builds chain_length without hand/finger and unit=cm', () => {
    const payload = buildMeasurementPayload({
      type: 'chain_length',
      value: '45',
      hand: 'left',
      finger: 'ring',
    });
    expect(payload).toEqual({
      measurement_type: 'chain_length',
      value: 45,
      unit: 'cm',
    });
    expect(payload.hand).toBeUndefined();
    expect(payload.finger).toBeUndefined();
  });

  it('builds finger_circumference with hand/finger and unit=mm', () => {
    const payload = buildMeasurementPayload({
      type: 'finger_circumference',
      value: '52.5',
      hand: 'right',
      finger: 'middle',
    });
    expect(payload).toEqual({
      measurement_type: 'finger_circumference',
      value: 52.5,
      unit: 'mm',
      hand: 'right',
      finger: 'middle',
    });
  });
});

describe('extractMeasurementErrorMessage', () => {
  it('extracts FastAPI 422 detail array first message', () => {
    const err = {
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'unit'], msg: 'Field required', type: 'missing' },
          ],
        },
      },
    };
    expect(extractMeasurementErrorMessage(err)).toBe('unit: Field required');
  });

  it('extracts string detail', () => {
    expect(
      extractMeasurementErrorMessage({
        response: { data: { detail: 'Customer not found' } },
      }),
    ).toBe('Customer not found');
  });

  it('falls back to message', () => {
    expect(extractMeasurementErrorMessage({ message: 'Network error' })).toBe(
      'Network error',
    );
  });

  it('has a default for unknown errors', () => {
    expect(extractMeasurementErrorMessage({})).toBe('Speichern fehlgeschlagen');
  });
});

describe('MasseTab — "Maß speichern" submits correct payload', () => {
  it('sends measurement_type + value + unit + hand + finger as enum values', async () => {
    const user = userEvent.setup();
    render(<MasseTab customer={mockCustomer} />);

    // Wait for initial load (measurements list).
    await waitFor(() =>
      expect(measurementsApi.getForCustomer).toHaveBeenCalledWith(1),
    );

    // Open the form.
    await user.click(screen.getByRole('button', { name: /\+ Maß hinzufügen/ }));

    // The default selection is ring_size + left + ring; just set a value.
    // Use fireEvent.change because happy-dom + userEvent.type on number inputs
    // doesn't always commit the React state synchronously.
    const valueInput = screen.getByPlaceholderText(/53\.4/) as HTMLInputElement;
    fireEvent.change(valueInput, { target: { value: '53' } });
    expect(valueInput.value).toBe('53');

    const submitBtn = screen.getByRole('button', { name: /Maß speichern/ });
    expect(submitBtn).not.toBeDisabled();
    // happy-dom: submit the form directly (button click doesn't always bubble).
    const form = submitBtn.closest('form') as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => expect(measurementsApi.add).toHaveBeenCalledTimes(1));

    const [customerIdArg, payloadArg] = (measurementsApi.add as ReturnType<
      typeof vi.fn
    >).mock.calls[0];
    expect(customerIdArg).toBe(1);
    expect(payloadArg).toEqual({
      measurement_type: 'ring_size',
      value: 53,
      unit: 'mm',
      hand: 'left',
      finger: 'ring',
    });
  });

  it('surfaces backend 422 errors instead of silently swallowing them', async () => {
    (measurementsApi.add as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'value'], msg: 'ring_size value must be between 38 and 80 mm' },
          ],
        },
      },
    });

    const user = userEvent.setup();
    render(<MasseTab customer={mockCustomer} />);
    await waitFor(() =>
      expect(measurementsApi.getForCustomer).toHaveBeenCalledWith(1),
    );

    await user.click(screen.getByRole('button', { name: /\+ Maß hinzufügen/ }));
    const valInput = screen.getByPlaceholderText(/53\.4/) as HTMLInputElement;
    fireEvent.change(valInput, { target: { value: '999' } });
    const submitBtn2 = screen.getByRole('button', { name: /Maß speichern/ });
    const form2 = submitBtn2.closest('form') as HTMLFormElement;
    fireEvent.submit(form2);

    // Error must be visible to the user — not silently swallowed.
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/value/);
    expect(alert.textContent).toMatch(/between 38 and 80/);
  });
});
