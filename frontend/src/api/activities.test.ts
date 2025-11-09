// Tests for Activities API Client
import { describe, it, expect } from 'vitest';
import { activitiesApi } from './activities';
import { ActivityCategory, ActivityCreateInput, ActivityUpdateInput } from '../types';
import { mockActivities } from '../test/mocks/handlers';

describe('activitiesApi', () => {
  describe('getAll', () => {
    it('should return all activities', async () => {
      const activities = await activitiesApi.getAll();

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
      expect(activities.length).toBeGreaterThan(0);
    });

    it('should filter by category', async () => {
      const activities = await activitiesApi.getAll({
        category: 'fabrication' as ActivityCategory
      });

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
      // All returned activities should be fabrication category
      activities.forEach(activity => {
        expect(activity.category).toBe('fabrication');
      });
    });

    it('should support sort by usage', async () => {
      const activities = await activitiesApi.getAll({ sortByUsage: true });

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
      // Check if sorted by usage_count descending
      for (let i = 0; i < activities.length - 1; i++) {
        expect(activities[i].usage_count).toBeGreaterThanOrEqual(
          activities[i + 1].usage_count
        );
      }
    });

    it('should support pagination', async () => {
      const activities = await activitiesApi.getAll({ skip: 0, limit: 2 });

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
    });

    it('should support all options together', async () => {
      const activities = await activitiesApi.getAll({
        category: 'fabrication' as ActivityCategory,
        sortByUsage: true,
        skip: 0,
        limit: 5,
      });

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
    });
  });

  describe('getMostUsed', () => {
    it('should return most used activities', async () => {
      const activities = await activitiesApi.getMostUsed(5);

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
      expect(activities.length).toBeLessThanOrEqual(5);
    });

    it('should return activities sorted by usage', async () => {
      const activities = await activitiesApi.getMostUsed(5);

      // Check if sorted by usage_count descending
      for (let i = 0; i < activities.length - 1; i++) {
        expect(activities[i].usage_count).toBeGreaterThanOrEqual(
          activities[i + 1].usage_count
        );
      }
    });

    it('should default to 10 activities when limit not specified', async () => {
      const activities = await activitiesApi.getMostUsed();

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
    });
  });

  describe('getById', () => {
    it('should return an activity by id', async () => {
      const activity = await activitiesApi.getById(1);

      expect(activity).toBeDefined();
      expect(activity.id).toBe(1);
      expect(activity.name).toBeDefined();
      expect(activity.category).toBeDefined();
    });

    it('should return activity with all expected fields', async () => {
      const activity = await activitiesApi.getById(1);

      expect(activity).toHaveProperty('id');
      expect(activity).toHaveProperty('name');
      expect(activity).toHaveProperty('category');
      expect(activity).toHaveProperty('icon');
      expect(activity).toHaveProperty('color');
      expect(activity).toHaveProperty('usage_count');
      expect(activity).toHaveProperty('average_duration_minutes');
      expect(activity).toHaveProperty('last_used');
      expect(activity).toHaveProperty('is_custom');
      expect(activity).toHaveProperty('created_at');
    });
  });

  describe('create', () => {
    it('should create a new activity', async () => {
      const newActivity: ActivityCreateInput = {
        name: 'Test Activity',
        category: 'fabrication',
        icon: '🔧',
        color: '#ff0000',
      };

      const activity = await activitiesApi.create(newActivity);

      expect(activity).toBeDefined();
      expect(activity.name).toBe('Test Activity');
      expect(activity.category).toBe('fabrication');
      expect(activity.icon).toBe('🔧');
      expect(activity.color).toBe('#ff0000');
      expect(activity.is_custom).toBe(true);
      expect(activity.usage_count).toBe(0);
    });

    it('should create activity with minimal data', async () => {
      const newActivity: ActivityCreateInput = {
        name: 'Minimal Activity',
        category: 'administration',
      };

      const activity = await activitiesApi.create(newActivity);

      expect(activity).toBeDefined();
      expect(activity.name).toBe('Minimal Activity');
      expect(activity.category).toBe('administration');
    });
  });

  describe('update', () => {
    it('should update an activity', async () => {
      const updates: ActivityUpdateInput = {
        name: 'Updated Name',
        icon: '🆕',
      };

      const activity = await activitiesApi.update(1, updates);

      expect(activity).toBeDefined();
      expect(activity.id).toBe(1);
    });

    it('should allow partial updates', async () => {
      const updates: ActivityUpdateInput = {
        color: '#00ff00',
      };

      const activity = await activitiesApi.update(1, updates);

      expect(activity).toBeDefined();
      expect(activity.id).toBe(1);
    });
  });

  describe('delete', () => {
    it('should delete an activity', async () => {
      await expect(activitiesApi.delete(1)).resolves.not.toThrow();
    });

    it('should handle deleting a custom activity', async () => {
      // Assuming activity with id 10 is custom
      await expect(activitiesApi.delete(10)).resolves.not.toThrow();
    });
  });

  describe('Activity categories', () => {
    it('should have fabrication activities', async () => {
      const activities = await activitiesApi.getAll({
        category: 'fabrication' as ActivityCategory
      });

      expect(activities.length).toBeGreaterThan(0);
      activities.forEach(activity => {
        expect(activity.category).toBe('fabrication');
      });
    });

    it('should have administration activities', async () => {
      const activities = await activitiesApi.getAll({
        category: 'administration' as ActivityCategory
      });

      expect(activities.length).toBeGreaterThan(0);
      activities.forEach(activity => {
        expect(activity.category).toBe('administration');
      });
    });

    it('should have waiting activities', async () => {
      const activities = await activitiesApi.getAll({
        category: 'waiting' as ActivityCategory
      });

      expect(activities.length).toBeGreaterThan(0);
      activities.forEach(activity => {
        expect(activity.category).toBe('waiting');
      });
    });
  });

  describe('Activity metadata', () => {
    it('should track usage count', async () => {
      const activity = await activitiesApi.getById(1);

      expect(activity.usage_count).toBeGreaterThanOrEqual(0);
    });

    it('should track average duration', async () => {
      const activity = await activitiesApi.getById(1);

      if (activity.average_duration_minutes !== null) {
        expect(activity.average_duration_minutes).toBeGreaterThan(0);
      }
    });

    it('should track last used timestamp', async () => {
      const activity = await activitiesApi.getById(1);

      if (activity.last_used !== null) {
        expect(new Date(activity.last_used)).toBeInstanceOf(Date);
      }
    });

    it('should distinguish custom vs predefined activities', async () => {
      const activity = await activitiesApi.getById(1);

      expect(typeof activity.is_custom).toBe('boolean');
    });
  });
});
