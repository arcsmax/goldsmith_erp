// Tests for the Customer Updates & §649 Cost-Change API client (V1.2)
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPost = vi.fn();
const mockGet = vi.fn();
vi.mock('./client', () => ({
  default: {
    post: (...a: unknown[]) => mockPost(...a),
    get: (...a: unknown[]) => mockGet(...a),
  },
}));

import { customerUpdatesApi } from './customer-updates';
import type {
  CustomerUpdate,
  CustomerUpdateCreateInput,
  CustomerUpdateSendResult,
  CostChange,
  CostChangeCreateInput,
  CostChangeRecordResponseInput,
  ProjectedCost,
} from './customer-updates';

beforeEach(() => vi.clearAllMocks());

const mockUpdate: CustomerUpdate = {
  id: 1,
  order_id: 42,
  repair_job_id: null,
  kind: 'progress',
  subject: 'Zwischenstand',
  body: 'Ihr Ring ist in Bearbeitung.',
  photo_ids: [],
  cost_change_request_id: null,
  token: 'abc123',
  status: 'draft',
  sent_at: null,
  sent_by: 1,
  delivery_method: null,
  created_at: '2026-07-03T10:00:00Z',
  updated_at: '2026-07-03T10:00:00Z',
};

const mockCostChange: CostChange = {
  id: 5,
  order_id: 42,
  quote_id: 3,
  original_amount: 500,
  new_amount: 650,
  delta_percent: 30,
  reason: 'Zusaetzlicher Materialaufwand fuer Fassung',
  line_items: [],
  status: 'draft',
  response_method: null,
  response_evidence: null,
  responded_at: null,
  recorded_by: null,
  created_at: '2026-07-03T10:00:00Z',
  created_by: 1,
  updated_at: '2026-07-03T10:00:00Z',
};

describe('customerUpdatesApi', () => {
  describe('listUpdates', () => {
    it('GETs the order updates history', async () => {
      mockGet.mockResolvedValue({ data: [mockUpdate] });
      const result = await customerUpdatesApi.listUpdates(42);

      expect(mockGet).toHaveBeenCalledWith('/orders/42/updates');
      expect(result).toEqual([mockUpdate]);
    });
  });

  describe('createUpdate', () => {
    it('POSTs a new draft update for the order', async () => {
      mockPost.mockResolvedValue({ data: mockUpdate });
      const input: CustomerUpdateCreateInput = { kind: 'progress', subject: 'Zwischenstand' };
      const result = await customerUpdatesApi.createUpdate(42, input);

      expect(mockPost).toHaveBeenCalledWith('/orders/42/updates', input);
      expect(result).toEqual(mockUpdate);
    });
  });

  describe('sendUpdate', () => {
    it('POSTs to send an existing update', async () => {
      const sendResult: CustomerUpdateSendResult = {
        update: { ...mockUpdate, status: 'sent' },
        delivered: true,
        method: 'email',
      };
      mockPost.mockResolvedValue({ data: sendResult });
      const result = await customerUpdatesApi.sendUpdate(1);

      expect(mockPost).toHaveBeenCalledWith('/updates/1/send', {});
      expect(result).toEqual(sendResult);
    });
  });

  describe('markDelivered', () => {
    it('POSTs pdf_manual delivery confirmation', async () => {
      const delivered: CustomerUpdate = { ...mockUpdate, delivery_method: 'pdf_manual' };
      mockPost.mockResolvedValue({ data: delivered });
      const result = await customerUpdatesApi.markDelivered(1);

      expect(mockPost).toHaveBeenCalledWith('/updates/1/mark-delivered', {
        method: 'pdf_manual',
      });
      expect(result).toEqual(delivered);
    });
  });

  describe('downloadUpdatePdf', () => {
    it('GETs the update PDF as a blob', async () => {
      const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' });
      mockGet.mockResolvedValue({ data: blob });
      const result = await customerUpdatesApi.downloadUpdatePdf(1);

      expect(mockGet).toHaveBeenCalledWith('/updates/1/pdf', { responseType: 'blob' });
      expect(result).toBe(blob);
    });
  });

  describe('listCostChanges', () => {
    it('GETs the order cost-change history', async () => {
      mockGet.mockResolvedValue({ data: [mockCostChange] });
      const result = await customerUpdatesApi.listCostChanges(42);

      expect(mockGet).toHaveBeenCalledWith('/orders/42/cost-changes');
      expect(result).toEqual([mockCostChange]);
    });
  });

  describe('createCostChange', () => {
    it('POSTs a new cost-change request for the order', async () => {
      mockPost.mockResolvedValue({ data: mockCostChange });
      const input: CostChangeCreateInput = {
        new_amount: 650,
        reason: 'Zusaetzlicher Materialaufwand fuer Fassung',
      };
      const result = await customerUpdatesApi.createCostChange(42, input);

      expect(mockPost).toHaveBeenCalledWith('/orders/42/cost-changes', input);
      expect(result).toEqual(mockCostChange);
    });
  });

  describe('sendCostChange', () => {
    it('POSTs to send an existing cost-change request', async () => {
      const sendResult: CustomerUpdateSendResult = {
        update: mockUpdate,
        delivered: false,
        method: null,
      };
      mockPost.mockResolvedValue({ data: sendResult });
      const result = await customerUpdatesApi.sendCostChange(5);

      expect(mockPost).toHaveBeenCalledWith('/cost-changes/5/send', {});
      expect(result).toEqual(sendResult);
    });
  });

  describe('recordCostChangeResponse', () => {
    it('POSTs the recorded customer response', async () => {
      const responded: CostChange = {
        ...mockCostChange,
        status: 'approved',
        response_method: 'email_reply',
        response_evidence: 'Kunde hat per Email zugestimmt',
      };
      mockPost.mockResolvedValue({ data: responded });
      const input: CostChangeRecordResponseInput = {
        status: 'approved',
        response_method: 'email_reply',
        response_evidence: 'Kunde hat per Email zugestimmt',
      };
      const result = await customerUpdatesApi.recordCostChangeResponse(5, input);

      expect(mockPost).toHaveBeenCalledWith('/cost-changes/5/record-response', input);
      expect(result).toEqual(responded);
    });
  });

  describe('getProjectedCost', () => {
    it('GETs the projected cost for the order', async () => {
      const projected: ProjectedCost = {
        material_cost: 100,
        gemstone_cost: 50,
        labor_minutes_billable: 120,
        labor_cost: 150,
        projected_total: 300,
        quote_id: 3,
        quote_total: 250,
        delta_percent: 20,
        delta_abs: 50,
        over_threshold: true,
        baseline_source: 'quote',
      };
      mockGet.mockResolvedValue({ data: projected });
      const result = await customerUpdatesApi.getProjectedCost(42);

      expect(mockGet).toHaveBeenCalledWith('/orders/42/projected-cost');
      expect(result).toEqual(projected);
    });
  });
});
