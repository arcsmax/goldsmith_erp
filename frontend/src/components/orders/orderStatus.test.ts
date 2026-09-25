// orderStatus — transition mirror, Weiter target and error text (W2-08, DOM-18).
import { describe, expect, it } from 'vitest';
import {
  allowedNextStatuses,
  canChangeOrderStatus,
  ORDER_STATUS_LABELS,
  primaryNextStatus,
  secondaryStatuses,
  statusChangeErrorMessage,
  statusLabel,
} from './orderStatus';

describe('orderStatus', () => {
  it('labels every status in German, including Pausiert and Storniert', () => {
    expect(ORDER_STATUS_LABELS.on_hold).toBe('Pausiert');
    expect(ORDER_STATUS_LABELS.cancelled).toBe('Storniert');
    expect(ORDER_STATUS_LABELS.ready_for_setting).toBe('Bereit zum Fassen');
    expect(ORDER_STATUS_LABELS.quality_check).toBe('Qualitätskontrolle');
    expect(statusLabel('something_new')).toBe('something_new');
  });

  it('mirrors the backend transition table at the edges', () => {
    expect(allowedNextStatuses('draft')).toEqual(['confirmed', 'cancelled']);
    expect(allowedNextStatuses('completed')).toEqual(['in_progress', 'quality_check', 'delivered']);
    expect(allowedNextStatuses('delivered')).toEqual([]);
    expect(allowedNextStatuses('cancelled')).toEqual(['draft']);
    expect(allowedNextStatuses('in_progress')).not.toContain('delivered');
    expect(allowedNextStatuses('in_progress')).not.toContain('in_progress');
  });

  it('picks one obvious next status that is always allowed', () => {
    const statuses = Object.keys(ORDER_STATUS_LABELS);
    statuses.forEach((status) => {
      const next = primaryNextStatus(status);
      if (next !== null) expect(allowedNextStatuses(status)).toContain(next);
    });
    expect(primaryNextStatus('quality_check')).toBe('completed');
    expect(primaryNextStatus('delivered')).toBeNull();
    expect(primaryNextStatus('cancelled')).toBeNull();
  });

  it('lists the other transitions without the primary one and cancel last', () => {
    const others = secondaryStatuses('in_progress');
    expect(others).not.toContain('quality_check');
    expect(others[others.length - 1]).toBe('cancelled');
    expect(secondaryStatuses('cancelled')).toEqual(['draft']);
  });

  it('allows status changes only for ADMIN and GOLDSMITH', () => {
    expect(canChangeOrderStatus('GOLDSMITH')).toBe(true);
    expect(canChangeOrderStatus('admin')).toBe(true);
    expect(canChangeOrderStatus('VIEWER')).toBe(false);
    expect(canChangeOrderStatus(undefined)).toBe(false);
  });

  it('extracts the backend German message from 409, 422 and string details', () => {
    expect(
      statusChangeErrorMessage({ response: { data: { detail: { message: 'Nicht erlaubt.' } } } })
    ).toBe('Nicht erlaubt.');
    expect(statusChangeErrorMessage({ response: { data: { detail: 'Order not found' } } })).toBe(
      'Order not found'
    );
    expect(statusChangeErrorMessage(new Error('Network Error'))).toBe(
      'Status konnte nicht geändert werden. Bitte erneut versuchen.'
    );
  });
});
