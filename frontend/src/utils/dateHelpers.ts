/**
 * Shared date utility functions
 * Used across components for consistent date handling
 */

/**
 * Get the start of today (00:00:00)
 * @returns Date object representing start of today
 */
export const getTodayStart = (): Date => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
};

/**
 * Get the end of today (23:59:59.999)
 * @returns Date object representing end of today
 */
export const getTodayEnd = (): Date => {
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  return today;
};

/**
 * Get the start of the current week (Monday 00:00:00)
 * @returns Date object representing start of week
 */
export const getWeekStart = (): Date => {
  const now = new Date();
  const dayOfWeek = now.getDay();
  // Adjust so Monday is 0, Sunday is 6
  const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const monday = new Date(now);
  monday.setDate(now.getDate() + diff);
  monday.setHours(0, 0, 0, 0);
  return monday;
};

/**
 * Get the end of the current week (Sunday 23:59:59.999)
 * @returns Date object representing end of week
 */
export const getWeekEnd = (): Date => {
  const weekStart = getWeekStart();
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);
  weekEnd.setHours(23, 59, 59, 999);
  return weekEnd;
};

/**
 * Get the start of the current month (1st day, 00:00:00)
 * @returns Date object representing start of month
 */
export const getMonthStart = (): Date => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0);
};

/**
 * Get the end of the current month (last day, 23:59:59.999)
 * @returns Date object representing end of month
 */
export const getMonthEnd = (): Date => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);
};

/**
 * Get a date N days from now
 * @param days - Number of days to add (negative for past dates)
 * @returns Date object
 */
export const addDays = (days: number, fromDate: Date = new Date()): Date => {
  const result = new Date(fromDate);
  result.setDate(result.getDate() + days);
  return result;
};

/**
 * Get a date N weeks from now
 * @param weeks - Number of weeks to add (negative for past weeks)
 * @returns Date object
 */
export const addWeeks = (weeks: number, fromDate: Date = new Date()): Date => {
  return addDays(weeks * 7, fromDate);
};

/**
 * Get a date N months from now
 * @param months - Number of months to add (negative for past months)
 * @returns Date object
 */
export const addMonths = (months: number, fromDate: Date = new Date()): Date => {
  const result = new Date(fromDate);
  result.setMonth(result.getMonth() + months);
  return result;
};

/**
 * Calculate the difference in days between two dates
 * @param date1 - First date
 * @param date2 - Second date
 * @returns Number of days between dates (can be negative)
 */
export const daysDifference = (date1: Date, date2: Date): number => {
  const msPerDay = 1000 * 60 * 60 * 24;
  const utc1 = Date.UTC(date1.getFullYear(), date1.getMonth(), date1.getDate());
  const utc2 = Date.UTC(date2.getFullYear(), date2.getMonth(), date2.getDate());
  return Math.floor((utc2 - utc1) / msPerDay);
};

/**
 * Check if a date is today
 * @param date - Date to check
 * @returns True if the date is today
 */
export const isToday = (date: Date): boolean => {
  const today = new Date();
  return (
    date.getDate() === today.getDate() &&
    date.getMonth() === today.getMonth() &&
    date.getFullYear() === today.getFullYear()
  );
};

/**
 * Check if a date is in the past
 * @param date - Date to check
 * @returns True if the date is before today
 */
export const isPast = (date: Date): boolean => {
  const today = getTodayStart();
  return date < today;
};

/**
 * Check if a date is in the future
 * @param date - Date to check
 * @returns True if the date is after today
 */
export const isFuture = (date: Date): boolean => {
  const today = getTodayEnd();
  return date > today;
};

/**
 * Check if a date is within a range
 * @param date - Date to check
 * @param start - Start of range
 * @param end - End of range
 * @returns True if date is within range (inclusive)
 */
export const isWithinRange = (date: Date, start: Date, end: Date): boolean => {
  return date >= start && date <= end;
};

/**
 * Convert ISO date string to Date object
 * @param isoString - ISO date string
 * @returns Date object or null if invalid
 */
export const parseISODate = (isoString: string): Date | null => {
  try {
    const date = new Date(isoString);
    return isNaN(date.getTime()) ? null : date;
  } catch {
    return null;
  }
};

/**
 * Format date as ISO string for API requests
 * @param date - Date object
 * @returns ISO string (e.g., "2025-11-11T00:00:00.000Z")
 */
export const toISOString = (date: Date): string => {
  return date.toISOString();
};
