/**
 * Shared formatting utilities to eliminate code duplication
 * Used across multiple components for consistent formatting
 */

/**
 * Format a number as currency (EUR)
 * @param amount - The amount to format
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted currency string (e.g., "€1,234.56")
 */
export const formatCurrency = (amount: number, decimals: number = 2): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
};

/**
 * Format a number with thousand separators
 * @param value - The number to format
 * @param decimals - Number of decimal places (default: 0)
 * @returns Formatted number string (e.g., "1,234")
 */
export const formatNumber = (value: number, decimals: number = 0): string => {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};

/**
 * Format a date string as a localized date
 * @param dateString - ISO date string
 * @param options - Intl.DateTimeFormatOptions
 * @returns Formatted date string (e.g., "11.11.2025")
 */
export const formatDate = (
  dateString: string,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }
): string => {
  return new Date(dateString).toLocaleDateString('de-DE', options);
};

/**
 * Format a date string as a localized date and time
 * @param dateString - ISO date string
 * @returns Formatted datetime string (e.g., "11.11.2025, 10:30")
 */
export const formatDateTime = (dateString: string): string => {
  return new Date(dateString).toLocaleString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Format a duration in minutes as hours and minutes
 * @param minutes - Duration in minutes
 * @returns Formatted duration string (e.g., "2h 30m")
 */
export const formatDuration = (minutes: number): string => {
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);

  if (hours === 0) {
    return `${mins}m`;
  }

  if (mins === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${mins}m`;
};

/**
 * Format minutes as decimal hours
 * @param minutes - Duration in minutes
 * @param decimals - Number of decimal places (default: 1)
 * @returns Formatted hours string (e.g., "2.5h")
 */
export const formatHours = (minutes: number, decimals: number = 1): string => {
  const hours = minutes / 60;
  return `${hours.toFixed(decimals)}h`;
};

/**
 * Truncate text to a maximum length with ellipsis
 * @param text - The text to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text with ellipsis if needed
 */
export const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.substring(0, maxLength - 3)}...`;
};

/**
 * Format a weight in grams with appropriate unit
 * @param grams - Weight in grams
 * @returns Formatted weight string (e.g., "1.5kg" or "500g")
 */
export const formatWeight = (grams: number): string => {
  if (grams >= 1000) {
    return `${(grams / 1000).toFixed(2)}kg`;
  }
  return `${grams.toFixed(2)}g`;
};

/**
 * Format a percentage value
 * @param value - The percentage value (0-100 or 0-1)
 * @param asDecimal - Whether the input value is a decimal (0-1) vs percentage (0-100)
 * @param decimals - Number of decimal places
 * @returns Formatted percentage string (e.g., "12.5%")
 */
export const formatPercentage = (
  value: number,
  asDecimal: boolean = false,
  decimals: number = 1
): string => {
  const percentage = asDecimal ? value * 100 : value;
  return `${percentage.toFixed(decimals)}%`;
};
