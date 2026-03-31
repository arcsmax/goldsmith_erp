// API Services Index - Central export for all API services
export { default as apiClient } from './client';
export { authApi } from './auth';
export { customersApi } from './customers';
export { materialsApi } from './materials';
export { metalInventoryApi } from './metal-inventory';
export { ordersApi } from './orders';
export { timeTrackingApi } from './time-tracking';
export { usersApi } from './users';
export { calendarApi } from './calendar';
export { commentsApi } from './comments';
export type { OrderComment } from './comments';
