// Tests for Time Tracking API Client
import { describe, it, expect, beforeEach } from 'vitest';
import { timeTrackingApi } from './timeTracking';
import { TimeEntryStartInput, TimeEntryStopInput } from '../types';
import {
  mockTimeEntries,
  mockRunningEntry,
  mockTimeTrackingStats,
} from '../test/mocks/handlers';

describe('timeTrackingApi', () => {
  describe('start', () => {
    it('should start a new time entry', async () => {
      const startData: TimeEntryStartInput = {
        order_id: 1,
        activity_id: 1,
        location: 'workbench_1',
      };

      const entry = await timeTrackingApi.start(startData);

      expect(entry).toBeDefined();
      expect(entry.order_id).toBe(1);
      expect(entry.activity_id).toBe(1);
      expect(entry.location).toBe('workbench_1');
      expect(entry.start_time).toBeDefined();
      expect(entry.end_time).toBeNull();
      expect(entry.duration_minutes).toBeNull();
    });

    it('should start a time entry without location', async () => {
      const startData: TimeEntryStartInput = {
        order_id: 1,
        activity_id: 1,
      };

      const entry = await timeTrackingApi.start(startData);

      expect(entry).toBeDefined();
      expect(entry.order_id).toBe(1);
      expect(entry.activity_id).toBe(1);
      expect(entry.location).toBeNull();
    });
  });

  describe('stop', () => {
    it('should stop a running time entry', async () => {
      const stopData: TimeEntryStopInput = {
        complexity_rating: 4,
        quality_rating: 5,
        rework_required: false,
        notes: 'Test completed',
      };

      const entry = await timeTrackingApi.stop(mockRunningEntry.id, stopData);

      expect(entry).toBeDefined();
      expect(entry.id).toBe(mockRunningEntry.id);
      expect(entry.end_time).toBeDefined();
      expect(entry.duration_minutes).toBeDefined();
      expect(entry.complexity_rating).toBe(4);
      expect(entry.quality_rating).toBe(5);
      expect(entry.rework_required).toBe(false);
      expect(entry.notes).toBe('Test completed');
    });

    it('should stop a time entry with minimal data', async () => {
      const stopData: TimeEntryStopInput = {
        rework_required: false,
      };

      const entry = await timeTrackingApi.stop(mockRunningEntry.id, stopData);

      expect(entry).toBeDefined();
      expect(entry.end_time).toBeDefined();
      expect(entry.duration_minutes).toBeDefined();
    });
  });

  describe('getRunning', () => {
    it('should return null when no entry is running', async () => {
      const entry = await timeTrackingApi.getRunning();

      expect(entry).toBeNull();
    });
  });

  describe('getForOrder', () => {
    it('should return time entries for an order', async () => {
      const entries = await timeTrackingApi.getForOrder(1);

      expect(entries).toBeDefined();
      expect(Array.isArray(entries)).toBe(true);
      expect(entries.length).toBeGreaterThan(0);
      expect(entries[0].order_id).toBe(1);
    });

    it('should return empty array for order with no entries', async () => {
      const entries = await timeTrackingApi.getForOrder(999);

      expect(entries).toBeDefined();
      expect(Array.isArray(entries)).toBe(true);
      expect(entries.length).toBe(0);
    });

    it('should support pagination parameters', async () => {
      const entries = await timeTrackingApi.getForOrder(1, 0, 10);

      expect(entries).toBeDefined();
      expect(Array.isArray(entries)).toBe(true);
    });
  });

  describe('getTotalForOrder', () => {
    it('should return statistics for an order', async () => {
      const stats = await timeTrackingApi.getTotalForOrder(1);

      expect(stats).toBeDefined();
      expect(stats.total_duration_minutes).toBeDefined();
      expect(stats.entry_count).toBeDefined();
      expect(stats.average_complexity).toBeDefined();
      expect(stats.average_quality).toBeDefined();
      expect(stats.by_activity).toBeDefined();
    });

    it('should return correct values', async () => {
      const stats = await timeTrackingApi.getTotalForOrder(1);

      expect(stats.total_duration_minutes).toBe(180);
      expect(stats.entry_count).toBe(2);
      expect(stats.average_complexity).toBe(4.5);
      expect(stats.average_quality).toBe(4.5);
      expect(stats.by_activity).toHaveProperty('Polieren');
      expect(stats.by_activity).toHaveProperty('Stein Fassen');
    });
  });

  describe('getForUser', () => {
    it('should return time entries for a user', async () => {
      const entries = await timeTrackingApi.getForUser(1);

      expect(entries).toBeDefined();
      expect(Array.isArray(entries)).toBe(true);
      expect(entries.length).toBeGreaterThan(0);
      expect(entries[0].user_id).toBe(1);
    });

    it('should support date range filtering', async () => {
      const startDate = '2025-01-01';
      const endDate = '2025-01-31';
      const entries = await timeTrackingApi.getForUser(1, startDate, endDate);

      expect(entries).toBeDefined();
      expect(Array.isArray(entries)).toBe(true);
    });
  });

  describe('getById', () => {
    it('should return a time entry by id', async () => {
      const entry = await timeTrackingApi.getById(mockTimeEntries[0].id);

      expect(entry).toBeDefined();
      expect(entry.id).toBe(mockTimeEntries[0].id);
      expect(entry.order_id).toBe(mockTimeEntries[0].order_id);
    });
  });

  describe('createManual', () => {
    it('should create a manual time entry', async () => {
      const manualEntry = {
        order_id: 1,
        activity_id: 1,
        start_time: '2025-01-09T10:00:00Z',
        end_time: '2025-01-09T11:00:00Z',
        duration_minutes: 60,
        location: 'workbench_1',
        complexity_rating: 3,
        quality_rating: 4,
        rework_required: false,
        notes: 'Manual entry test',
      };

      const entry = await timeTrackingApi.createManual(manualEntry);

      expect(entry).toBeDefined();
      expect(entry.order_id).toBe(1);
      expect(entry.activity_id).toBe(1);
      expect(entry.duration_minutes).toBe(60);
    });
  });

  describe('update', () => {
    it('should update a time entry', async () => {
      const updates = {
        notes: 'Updated notes',
        complexity_rating: 5,
      };

      const entry = await timeTrackingApi.update(mockTimeEntries[0].id, updates);

      expect(entry).toBeDefined();
      expect(entry.id).toBe(mockTimeEntries[0].id);
    });
  });

  describe('delete', () => {
    it('should delete a time entry', async () => {
      await expect(
        timeTrackingApi.delete(mockTimeEntries[0].id)
      ).resolves.not.toThrow();
    });
  });

  describe('addInterruption', () => {
    it('should add an interruption to a time entry', async () => {
      const interruption = {
        reason: 'Customer call',
        duration_minutes: 15,
      };

      const entry = await timeTrackingApi.addInterruption(
        mockRunningEntry.id,
        interruption
      );

      expect(entry).toBeDefined();
      expect(entry.id).toBe(mockRunningEntry.id);
    });
  });
});
