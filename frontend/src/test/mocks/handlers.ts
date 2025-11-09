// MSW request handlers for API mocking
import { http, HttpResponse } from 'msw';
import { TimeEntry, Activity, TimeTrackingStats } from '../../types';

const API_BASE = 'http://localhost:8000/api';

// Mock data
export const mockActivities: Activity[] = [
  {
    id: 1,
    name: 'Polieren',
    category: 'fabrication',
    icon: '✨',
    color: '#3b82f6',
    usage_count: 150,
    average_duration_minutes: 45,
    last_used: '2025-01-09T10:00:00Z',
    is_custom: false,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Stein Fassen',
    category: 'fabrication',
    icon: '💎',
    color: '#8b5cf6',
    usage_count: 120,
    average_duration_minutes: 60,
    last_used: '2025-01-09T09:00:00Z',
    is_custom: false,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 3,
    name: 'Löten',
    category: 'fabrication',
    icon: '🔥',
    color: '#ef4444',
    usage_count: 100,
    average_duration_minutes: 30,
    last_used: '2025-01-09T08:00:00Z',
    is_custom: false,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 4,
    name: 'Kundenkontakt',
    category: 'administration',
    icon: '📞',
    color: '#10b981',
    usage_count: 80,
    average_duration_minutes: 15,
    last_used: '2025-01-09T07:00:00Z',
    is_custom: false,
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 5,
    name: 'Materialwartung',
    category: 'waiting',
    icon: '⏳',
    color: '#f59e0b',
    usage_count: 50,
    average_duration_minutes: 120,
    last_used: '2025-01-08T15:00:00Z',
    is_custom: false,
    created_at: '2025-01-01T00:00:00Z',
  },
];

export const mockTimeEntries: TimeEntry[] = [
  {
    id: '123e4567-e89b-12d3-a456-426614174000',
    order_id: 1,
    user_id: 1,
    activity_id: 1,
    start_time: '2025-01-09T09:00:00Z',
    end_time: '2025-01-09T10:30:00Z',
    duration_minutes: 90,
    location: 'workbench_1',
    complexity_rating: 4,
    quality_rating: 5,
    rework_required: false,
    notes: 'Polierarbeiten abgeschlossen',
    extra_metadata: null,
    created_at: '2025-01-09T09:00:00Z',
  },
  {
    id: '123e4567-e89b-12d3-a456-426614174001',
    order_id: 1,
    user_id: 1,
    activity_id: 2,
    start_time: '2025-01-08T14:00:00Z',
    end_time: '2025-01-08T15:30:00Z',
    duration_minutes: 90,
    location: 'workbench_1',
    complexity_rating: 5,
    quality_rating: 4,
    rework_required: false,
    notes: 'Stein erfolgreich gefasst',
    extra_metadata: null,
    created_at: '2025-01-08T14:00:00Z',
  },
];

export const mockRunningEntry: TimeEntry = {
  id: '123e4567-e89b-12d3-a456-426614174002',
  order_id: 1,
  user_id: 1,
  activity_id: 1,
  start_time: new Date().toISOString(),
  end_time: null,
  duration_minutes: null,
  location: 'workbench_1',
  complexity_rating: null,
  quality_rating: null,
  rework_required: false,
  notes: null,
  extra_metadata: null,
  created_at: new Date().toISOString(),
};

export const mockTimeTrackingStats: TimeTrackingStats = {
  total_duration_minutes: 180,
  entry_count: 2,
  average_complexity: 4.5,
  average_quality: 4.5,
  by_activity: {
    'Polieren': 90,
    'Stein Fassen': 90,
  },
};

// Request handlers
export const handlers = [
  // Activities endpoints
  http.get(`${API_BASE}/activities/`, () => {
    return HttpResponse.json(mockActivities);
  }),

  http.get(`${API_BASE}/activities/most-used`, () => {
    return HttpResponse.json(mockActivities.slice(0, 5));
  }),

  http.get(`${API_BASE}/activities/:id`, ({ params }) => {
    const { id } = params;
    const activity = mockActivities.find((a) => a.id === Number(id));
    if (activity) {
      return HttpResponse.json(activity);
    }
    return new HttpResponse(null, { status: 404 });
  }),

  http.post(`${API_BASE}/activities/`, async ({ request }) => {
    const body = await request.json();
    const newActivity: Activity = {
      id: mockActivities.length + 1,
      ...(body as Omit<Activity, 'id'>),
      usage_count: 0,
      is_custom: true,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json(newActivity, { status: 201 });
  }),

  http.put(`${API_BASE}/activities/:id`, async ({ params, request }) => {
    const { id } = params;
    const body = await request.json();
    const activity = mockActivities.find((a) => a.id === Number(id));
    if (activity) {
      const updated = { ...activity, ...body };
      return HttpResponse.json(updated);
    }
    return new HttpResponse(null, { status: 404 });
  }),

  http.delete(`${API_BASE}/activities/:id`, ({ params }) => {
    const { id } = params;
    const activity = mockActivities.find((a) => a.id === Number(id));
    if (activity) {
      return new HttpResponse(null, { status: 204 });
    }
    return new HttpResponse(null, { status: 404 });
  }),

  // Time tracking endpoints
  http.post(`${API_BASE}/time-tracking/start`, async ({ request }) => {
    const body = await request.json();
    const newEntry: TimeEntry = {
      id: '123e4567-e89b-12d3-a456-' + Date.now(),
      order_id: (body as any).order_id,
      user_id: 1,
      activity_id: (body as any).activity_id,
      start_time: new Date().toISOString(),
      end_time: null,
      duration_minutes: null,
      location: (body as any).location || null,
      complexity_rating: null,
      quality_rating: null,
      rework_required: false,
      notes: null,
      extra_metadata: null,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json(newEntry, { status: 201 });
  }),

  http.post(`${API_BASE}/time-tracking/:id/stop`, async ({ params, request }) => {
    const { id } = params;
    const body = await request.json();
    const stoppedEntry: TimeEntry = {
      ...mockRunningEntry,
      id: id as string,
      end_time: new Date().toISOString(),
      duration_minutes: 90,
      complexity_rating: (body as any).complexity_rating,
      quality_rating: (body as any).quality_rating,
      rework_required: (body as any).rework_required || false,
      notes: (body as any).notes || null,
    };
    return HttpResponse.json(stoppedEntry);
  }),

  http.get(`${API_BASE}/time-tracking/running`, () => {
    // Return null to simulate no running entry (can be overridden in tests)
    return HttpResponse.json(null);
  }),

  http.get(`${API_BASE}/time-tracking/order/:orderId`, ({ params }) => {
    const { orderId } = params;
    return HttpResponse.json(
      mockTimeEntries.filter((e) => e.order_id === Number(orderId))
    );
  }),

  http.get(`${API_BASE}/time-tracking/order/:orderId/total`, ({ params }) => {
    const { orderId } = params;
    return HttpResponse.json(mockTimeTrackingStats);
  }),

  http.get(`${API_BASE}/time-tracking/user/:userId`, ({ params }) => {
    const { userId } = params;
    return HttpResponse.json(
      mockTimeEntries.filter((e) => e.user_id === Number(userId))
    );
  }),

  http.get(`${API_BASE}/time-tracking/:id`, ({ params }) => {
    const { id } = params;
    const entry = mockTimeEntries.find((e) => e.id === id);
    if (entry) {
      return HttpResponse.json(entry);
    }
    return new HttpResponse(null, { status: 404 });
  }),

  http.post(`${API_BASE}/time-tracking/manual`, async ({ request }) => {
    const body = await request.json();
    const newEntry: TimeEntry = {
      id: '123e4567-e89b-12d3-a456-' + Date.now(),
      ...(body as Omit<TimeEntry, 'id' | 'created_at'>),
      user_id: 1,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json(newEntry, { status: 201 });
  }),

  http.put(`${API_BASE}/time-tracking/:id`, async ({ params, request }) => {
    const { id } = params;
    const body = await request.json();
    const entry = mockTimeEntries.find((e) => e.id === id);
    if (entry) {
      const updated = { ...entry, ...body };
      return HttpResponse.json(updated);
    }
    return new HttpResponse(null, { status: 404 });
  }),

  http.delete(`${API_BASE}/time-tracking/:id`, ({ params }) => {
    const { id } = params;
    const entry = mockTimeEntries.find((e) => e.id === id);
    if (entry) {
      return new HttpResponse(null, { status: 204 });
    }
    return new HttpResponse(null, { status: 404 });
  }),

  http.post(`${API_BASE}/time-tracking/:id/interruption`, async ({ params, request }) => {
    const { id } = params;
    const body = await request.json();
    // Return the entry with interruption added
    return HttpResponse.json(mockRunningEntry);
  }),
];
