// Calendar API Service
import apiClient from './client';
import {
  CalendarEvent,
  CalendarDeadlineEvent,
  CalendarEventCreate,
  CalendarEventUpdate,
} from '../types';

export const calendarApi = {
  /**
   * List stored calendar events in a date range.
   * Maps to GET /api/v1/calendar/events
   */
  getEvents: async (
    start: string,
    end: string,
    eventType?: string
  ): Promise<CalendarEvent[]> => {
    const params = new URLSearchParams({ date_from: start, date_to: end });
    if (eventType) params.append('event_type', eventType);
    const { data } = await apiClient.get<CalendarEvent[]>(
      `/calendar/events?${params}`
    );
    return data;
  },

  /**
   * Fetch a single stored calendar event by ID.
   * Maps to GET /api/v1/calendar/events/{id}
   */
  getEvent: async (id: number): Promise<CalendarEvent> => {
    const { data } = await apiClient.get<CalendarEvent>(`/calendar/events/${id}`);
    return data;
  },

  /**
   * Get order deadlines as virtual calendar events in a date range.
   * Maps to GET /api/v1/calendar/deadlines
   */
  getDeadlines: async (
    start: string,
    end: string
  ): Promise<CalendarDeadlineEvent[]> => {
    const params = new URLSearchParams({ start, end });
    const { data } = await apiClient.get<CalendarDeadlineEvent[]>(
      `/calendar/deadlines?${params}`
    );
    return data;
  },

  /**
   * Create a new calendar event.
   * Maps to POST /api/v1/calendar/events
   */
  createEvent: async (data: CalendarEventCreate): Promise<CalendarEvent> => {
    const { data: created } = await apiClient.post<CalendarEvent>(
      '/calendar/events',
      data
    );
    return created;
  },

  /**
   * Partially update a stored calendar event.
   * Maps to PUT /api/v1/calendar/events/{id}
   */
  updateEvent: async (
    id: number,
    data: CalendarEventUpdate
  ): Promise<CalendarEvent> => {
    const { data: updated } = await apiClient.put<CalendarEvent>(
      `/calendar/events/${id}`,
      data
    );
    return updated;
  },

  /**
   * Delete a stored calendar event.
   * Maps to DELETE /api/v1/calendar/events/{id}
   */
  deleteEvent: async (id: number): Promise<void> => {
    await apiClient.delete(`/calendar/events/${id}`);
  },
};
