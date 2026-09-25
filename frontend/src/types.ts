// Frontend domain types. Read schemas and enums are aliases of the
// generated OpenAPI types (src/api/generated, FE-12 / W3-02); the rest is
// still hand-written and migrates module by module.
import type {
  ApiCalendarEventType,
  ApiConsultationOccasion,
  ApiConsultationPhotoKind,
  ApiConsultationStatus,
  ApiCostingMethod,
  ApiInvoiceLineType,
  ApiInvoiceStatus,
  ApiMeasurementType,
  ApiMetalPriceSource,
  ApiMetalType,
  ApiNoGoCategory,
  ApiNotificationSeverity,
  ApiOrderStatus,
  ApiQuoteLineType,
  ApiQuoteStatus,
  ApiRepairItemType,
  ApiRepairJobStatus,
  ApiRepairPhotoPhase,
  ApiUser,
  ApiUserRole,
  ApiCustomer,
  ApiCustomerListItem,
  ApiOrder,
  ApiTimeEntry,
  ApiNotification,
  ApiUnreadCount,
  ApiInvoice,
  ApiInvoiceListItem,
  ApiQuote,
  ApiQuoteListItem,
  ApiOrderTypeEnum,
  ApiActivity,
  Schemas,
  ApiRepairPhoto,
  ApiRepairJob,
  ApiRepairJobListItem,
  ApiConsultation,
  ApiConsultationListItem,
} from './api/generated';

// ==================== MATERIAL TYPES ====================

export interface MaterialType {
  id: number;
  name: string;
  description?: string;
  unit_price: number;
  stock: number;
  unit: string;
  stock_value?: number;
  image_url?: string;
  supplier?: string;
  webshop_url?: string;
  min_stock?: number;
}

export interface MaterialCreateInput {
  name: string;
  description?: string;
  unit_price: number;
  stock: number;
  unit: string;
  image_url?: string;
  supplier?: string;
  webshop_url?: string;
  min_stock?: number;
}

export interface MaterialUpdateInput {
  name?: string;
  description?: string;
  unit_price?: number;
  stock?: number;
  unit?: string;
  image_url?: string;
  supplier?: string;
  webshop_url?: string;
  min_stock?: number;
}

export interface PurchaseListItem {
  supplier: string | null;
  materials: MaterialType[];
}

// ==================== CUSTOMER TYPES ====================

export type CustomerCategory = 'private' | 'business';

// The backend declares `customer_type` as `str` but its validator only
// accepts "private" | "business", so the frontend keeps the narrow union.
export type Customer = Omit<ApiCustomer, 'customer_type'> & {
  customer_type: CustomerCategory;
  /**
   * Art. 9 health data (GDPR-02 / GDPR-11). Not part of `CustomerRead`:
   * customers.py `_customer_response` adds the key only for ADMIN/GOLDSMITH
   * callers when an active HEALTH_DATA consent exists; otherwise it is absent.
   */
  allergies?: string | null;
};

export type CustomerListItem = Omit<ApiCustomerListItem, 'customer_type'> & {
  customer_type: CustomerCategory;
};

export interface CustomerCreateInput {
  first_name: string;
  last_name: string;
  company_name?: string;
  email?: string;
  phone?: string;
  mobile?: string;
  street?: string;
  city?: string;
  postal_code?: string;
  country?: string;
  customer_type?: CustomerCategory;
  source?: string;
  notes?: string;
  tags?: string[];
  ring_size?: number | null;
  chain_length_cm?: number | null;
  bracelet_length_cm?: number | null;
  allergies?: string | null;
  preferences?: Record<string, string> | null;
  birthday?: string | null;
}

export interface CustomerUpdateInput {
  first_name?: string;
  last_name?: string;
  company_name?: string | null;
  email?: string;
  phone?: string | null;
  mobile?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country?: string;
  customer_type?: CustomerCategory;
  source?: string | null;
  notes?: string | null;
  tags?: string[];
  is_active?: boolean;
  ring_size?: number | null;
  chain_length_cm?: number | null;
  bracelet_length_cm?: number | null;
  allergies?: string | null;
  preferences?: Record<string, string> | null;
  birthday?: string | null;
}

export interface CustomerStats {
  customer_id: number;
  order_count: number;
  total_spent: number;
  last_order_date?: string | null;
}

// Maßbibliothek — persisted per-customer body measurements
// Values match backend MeasurementType enum exactly.
export type MeasurementType = ApiMeasurementType;

export interface CustomerMeasurement {
  id: number;
  customer_id: number;
  measurement_type: MeasurementType;
  value: number;
  unit: string;
  hand?: 'left' | 'right' | null;
  finger?: 'thumb' | 'index' | 'middle' | 'ring' | 'pinky' | null;
  notes?: string | null;
  measured_at: string;
  measured_by?: number | null;
}

// ==================== ORDER TYPES ====================

export type OrderStatus = ApiOrderStatus;

// MetalType defined in Metal Inventory section below

// Values match the backend CostingMethod enum (lowercase wire values).
export type CostingMethod = ApiCostingMethod;

/**
 * Fields that keep their old hand-written type for now, because the
 * components that read them (OrderDetailPage.tsx, components/orders/
 * CostBreakdownCard + MetalInventoryCard) are owned by another work item
 * and type their props as `number | undefined`. On the wire these are
 * nullable (`OrderRead`: the VIEWER role projection sends `null`), and
 * `materials` is `MaterialBase[]` ({id, name, unit_price}), not full
 * `MaterialType`. Drop this override once those callers accept the
 * generated types. Tracked in docs/technical/FRONTEND_API_TYPES.md.
 */
type OrderLegacyFields = {
  materials?: MaterialType[];
  hourly_rate?: number;
  scrap_percentage?: number;
  costing_method_used?: CostingMethod;
  profit_margin_percent?: number;
  vat_rate?: number;
};

export type OrderType = Omit<ApiOrder, keyof OrderLegacyFields> & OrderLegacyFields;

export interface OrderCreateInput {
  title: string;
  description: string;
  price?: number;
  customer_id: number;
  deadline?: string;
  status?: OrderStatus;

  // Metal & costing
  metal_type?: MetalType;
  estimated_weight_g?: number;
  scrap_percentage?: number;
  costing_method_used?: CostingMethod;

  // Goldsmith intake / Pflichtfelder
  alloy?: string;
  ring_size_mm?: number;
  surface_finish?: string;
  fitting_date?: string;
  has_scrap_gold?: boolean;
  special_instructions?: string;

  // Order classification
  order_type?: string;
  complexity_rating?: number;
  finish_type?: string;
}

export interface OrderUpdateInput {
  title?: string;
  description?: string;
  price?: number;
  deadline?: string | null;
  status?: OrderStatus;

  // Metal & costing
  metal_type?: MetalType | null;
  estimated_weight_g?: number | null;
  scrap_percentage?: number | null;
  costing_method_used?: CostingMethod | null;

  // Arbeitszettel (production work sheet) fields
  actual_weight_g?: number | null;
  labor_hours?: number | null;
  alloy?: string | null;
  ring_size_mm?: number | null;
  surface_finish?: string | null;
  fitting_date?: string | null;
  has_scrap_gold?: boolean | null;
  current_location?: string | null;
  location_id?: number | null;
  special_instructions?: string | null;

  // Order classification
  order_type?: string | null;
  complexity_rating?: number | null;
  finish_type?: string | null;
}

// ==================== USER TYPES ====================

// Generated from the backend (FE-12): the wire values are lowercase
// ("admin" | "goldsmith" | "viewer"); there is no "USER" role.
export type UserRole = ApiUserRole;

/**
 * Role literal accepted by `hasRole`. The check is case-insensitive, so the
 * uppercase spelling many callers still pass is allowed; comparisons against
 * `user.role` itself must use the lowercase `UserRole` values.
 */
export type RoleName = UserRole | Uppercase<UserRole>;

export type UserType = ApiUser;

export interface UserCreateInput {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export interface UserUpdateInput {
  email?: string;
  password?: string;
  first_name?: string;
  last_name?: string;
  is_active?: boolean;
}

// ==================== AUTH TYPES ====================

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AuthContextType {
  user: UserType | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (userData: UserCreateInput) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasRole(roles: RoleName | RoleName[]): boolean;
  isAdmin: boolean;
}

// ==================== METAL INVENTORY TYPES ====================

export type MetalType = ApiMetalType;

// ==================== CUSTOM METAL TYPES ====================

/** Unified dropdown entry: one item for built-in types, one for custom DB rows. */
export interface MetalTypeOption {
  code: string;
  display_name: string;
  fine_content_ratio: number;
  base_metal: string;
  color?: string | null;
  is_builtin: boolean;
  /** Only set for custom types */
  id?: number | null;
}

export interface CustomMetalTypeCreate {
  code: string;
  display_name: string;
  fine_content_ratio: number;
  base_metal: string;
  color?: string | null;
}

export interface CustomMetalTypeUpdate {
  display_name?: string;
  fine_content_ratio?: number;
  base_metal?: string;
  color?: string | null;
  is_active?: boolean;
}

export interface CustomMetalTypeRead {
  id: number;
  code: string;
  display_name: string;
  fine_content_ratio: number;
  base_metal: string;
  color?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MetalPurchaseType {
  id: number;
  date_purchased: string;
  metal_type: MetalType;
  weight_g: number;
  remaining_weight_g: number;
  price_total: number;
  price_per_gram: number;
  supplier?: string | null;
  invoice_number?: string | null;
  notes?: string | null;
  lot_number?: string | null;
  created_at: string;
  updated_at: string;
  // Computed properties
  used_weight_g?: number;
  usage_percentage?: number;
  is_depleted?: boolean;
  remaining_value?: number;
}

export interface MetalPurchaseCreateInput {
  date_purchased?: string;
  metal_type: MetalType;
  weight_g: number;
  price_total: number;
  supplier?: string;
  invoice_number?: string;
  notes?: string;
  lot_number?: string;
}

export interface MetalPurchaseUpdateInput {
  supplier?: string;
  invoice_number?: string;
  notes?: string;
  lot_number?: string;
}

/** Matches MetalPurchaseListItem in backend models/metal_inventory.py */
export interface MetalPurchaseListItem {
  id: number;
  metal_type: MetalType;
  date_purchased: string;
  weight_g: number;
  remaining_weight_g: number;
  price_per_gram: number;
  remaining_value: number;
  supplier?: string | null;
  invoice_number?: string | null;
  lot_number?: string | null;
  is_depleted: boolean;
}

/** Matches MetalInventorySummary in backend models/metal_inventory.py */
export interface MetalInventorySummary {
  metal_type: MetalType;
  total_weight_g: number;
  total_value: number;
  average_price_per_gram: number;
  batch_count: number;
  oldest_batch_date?: string | null;
  newest_batch_date?: string | null;
}

/** Matches InventoryStatistics in backend models/metal_inventory.py */
export interface InventoryStatistics {
  total_value: number;
  total_weight_g: number;
  metal_types: MetalInventorySummary[];
  depleted_batches_count: number;
  low_stock_alerts: string[];
}

/** Matches MaterialUsageCreate in backend models/metal_inventory.py */
export interface MaterialUsageCreateInput {
  order_id: number;
  weight_used_g: number;
  notes?: string;
  costing_method?: CostingMethod;
  metal_purchase_id?: number;
}

/** Matches MaterialUsageRead in backend models/metal_inventory.py */
export interface MaterialUsageRead {
  id: number;
  order_id: number;
  metal_purchase_id: number;
  weight_used_g: number;
  cost_at_time: number;
  price_per_gram_at_time: number;
  costing_method: CostingMethod;
  used_at: string;
  created_at: string;
  notes?: string | null;
  metal_type?: MetalType | null;
}

/** Matches MetalAllocation in backend models/metal_inventory.py */
export interface MetalAllocation {
  metal_purchase_id: number;
  metal_type: MetalType;
  weight_allocated_g: number;
  price_per_gram: number;
  cost: number;
  date_purchased: string;
}

/** Matches OrderMaterialAllocation in backend models/metal_inventory.py */
export interface OrderMaterialAllocation {
  order_id: number;
  required_weight_g: number;
  allocations: MetalAllocation[];
  total_cost: number;
  costing_method: CostingMethod;
}

export type MetalPriceSource = ApiMetalPriceSource;

/** Matches MetalPriceResponse in backend models/metal_price.py */
export interface MetalPriceResponse {
  metal_type: MetalType;
  price_per_gram: number;
  currency: string;
  source: MetalPriceSource;
  updated_at: string;
}

/** Matches MetalPriceListResponse in backend models/metal_price.py */
export interface MetalPriceListResponse {
  prices: MetalPriceResponse[];
  count: number;
}

// ==================== TIME TRACKING TYPES ====================

export type ActivityCategory = 'fabrication' | 'administration' | 'waiting';

export type Activity = Omit<ApiActivity, 'category'> & { category: ActivityCategory };

export interface ActivityCreateInput {
  name: string;
  category: ActivityCategory;
  icon?: string;
  color?: string;
  is_custom?: boolean;
  created_by?: number;
}

export interface ActivityUpdateInput {
  name?: string;
  category?: ActivityCategory;
  icon?: string;
  color?: string;
}

export type TimeEntry = ApiTimeEntry;

export interface TimeEntryWithDetails extends TimeEntry {
  activity?: Activity | null;
  order_title?: string | null;
  user_name?: string | null;
}

export interface TimeEntryStartInput {
  order_id: number;
  activity_id: number;
  location?: string;
  location_id?: number | null;
  extra_metadata?: Record<string, any>;
}

/** Payload for creating a manual time entry (POST /time-tracking/). */
export interface TimeEntryCreateInput {
  order_id: number;
  activity_id: number;
  start_time: string; // ISO datetime
  end_time?: string; // ISO datetime
  duration_minutes?: number;
  location?: string;
  location_id?: number | null;
  complexity_rating?: number; // 1-5
  quality_rating?: number; // 1-5
  rework_required?: boolean;
  notes?: string;
  extra_metadata?: Record<string, any>;
}

export interface TimeEntryStopInput {
  complexity_rating?: number; // 1-5
  quality_rating?: number; // 1-5
  rework_required?: boolean;
  notes?: string;
}

export interface TimeEntryUpdateInput {
  end_time?: string;
  duration_minutes?: number;
  location?: string;
  location_id?: number | null;
  complexity_rating?: number; // 1-5
  quality_rating?: number; // 1-5
  rework_required?: boolean;
  notes?: string;
  extra_metadata?: Record<string, any>;
}

export interface Interruption {
  id: number;
  time_entry_id: string; // UUID
  reason: string;
  duration_minutes: number;
  timestamp: string; // ISO datetime
}

export interface InterruptionCreateInput {
  time_entry_id: string;
  reason: string;
  duration_minutes: number;
}

export interface LocationHistory {
  id: number;
  order_id: number;
  location: string;
  timestamp: string; // ISO datetime
  changed_by: number;
}

export interface TimeTrackingStats {
  total_duration_minutes: number;
  entry_count: number;
  average_complexity?: number | null;
  average_quality?: number | null;
  by_activity?: Record<string, number>;
}

export interface TimeSummaryStats {
  total_hours: number;
  billable_hours: number;
  entries_count: number;
  average_session_minutes: number;
  most_used_activity?: string;
  comparison_previous_period?: number; // percentage change
}

export interface WeeklyTimeData {
  week_start: string;
  total_hours: number;
  entries_count: number;
  breakdown_by_day: {
    day: string; // 'Mon', 'Tue', etc.
    hours: number;
  }[];
}

export type ActivityBreakdownData = {
  activity_name: string;
  hours: number;
  percentage: number;
  color: string;
};

// ==================== NOTIFICATION TYPES ====================

export type NotificationSeverity = ApiNotificationSeverity;

export type Notification = ApiNotification;

export type NotificationUnreadCount = ApiUnreadCount;

// ==================== INVOICE TYPES ====================

/**
 * Invoice lifecycle status — MUST match the backend `InvoiceStatus` enum
 * VALUES (lowercase), not its enum NAMES. The backend serialises the enum
 * value as the JSON string, so payloads carry `"draft"`, `"sent"`, etc.
 *
 * Earlier this was typed as the uppercase NAMES (`'DRAFT' | 'SENT' | ...`),
 * which compiled fine but produced a silent runtime mismatch: the status
 * badge label map missed every key, the CSS modifier class never matched
 * (`.status-DRAFT` vs the actual `.status-draft`), and the row-level
 * action buttons (`status === 'SENT'`) were never shown.
 */
export type InvoiceStatus = ApiInvoiceStatus;

export type InvoiceLineType = ApiInvoiceLineType;

export type InvoiceLineItem = Schemas['InvoiceLineItemResponse'];

/** Full invoice including line items (used for detail view). */
export type Invoice = ApiInvoice;

/** Lightweight invoice for list views. */
export type InvoiceListItem = ApiInvoiceListItem;

export type InvoiceListResponse = Schemas['InvoiceListResponse'];

export interface InvoiceCreateInput {
  order_id: number;
  due_date: string; // ISO datetime
  tax_rate?: number; // defaults to 19.0
  notes?: string;
  payment_method?: string;
}

export interface InvoiceUpdateInput {
  status?: InvoiceStatus;
  due_date?: string;
  notes?: string;
  payment_method?: string;
}

export interface MarkPaidInput {
  paid_date?: string | null; // ISO datetime, defaults to now if omitted
  payment_method?: string;
}

// ==================== QUOTE TYPES ====================

/**
 * Quote lifecycle status — MUST match the backend `QuoteStatus` enum
 * VALUES (lowercase), not its enum NAMES. The backend serialises the enum
 * value as the JSON string, so payloads carry `"draft"`, `"sent"`, etc.
 */
export type QuoteStatus = ApiQuoteStatus;

export type QuoteLineType = ApiQuoteLineType;

export type QuoteLineItem = Schemas['QuoteLineItemResponse'];

/** Payload for creating/updating a quote line item (DRAFT quotes only). */
export interface QuoteLineItemInput {
  line_type: QuoteLineType;
  description: string;
  quantity: number;
  unit_price: number;
  estimator_metadata?: EstimatorMetadata;
}

/** Full quote including line items (used for detail view). */
export type Quote = ApiQuote;

/** Lightweight quote for list views. */
export type QuoteListItem = ApiQuoteListItem;

export type QuoteListResponse = Schemas['QuoteListResponse'];

export interface QuoteCreateInput {
  order_id?: number;
  customer_id: number;
  tax_rate?: number;   // defaults to 19.0
  valid_days?: number; // defaults to 14
  notes?: string;
}

export interface QuoteUpdateInput {
  status?: QuoteStatus;
  valid_until?: string;
  notes?: string;
  tax_rate?: number;
}

export interface ApproveQuoteInput {
  signature_data?: string | null; // base64 PNG
}

export interface RejectQuoteInput {
  reason?: string;
}

// V1.3 Phase 3 — Labor Estimator types

export type SimilarityLevel = "exact" | "type_finish" | "type" | "workshop" | "insufficient";

export interface LaborEstimateRequest {
  order_type: string;
  finish_type?: string | null;
  has_stone_setting?: boolean;
  alloy?: string | null;
  complexity_rating?: number | null;
}

export interface LaborEstimateResponse {
  hours_p50: number | null;
  hours_p20: number | null;
  hours_p80: number | null;
  labor_cost_p50: number | null;
  labor_cost_p20: number | null;
  labor_cost_p80: number | null;
  sample_size: number;
  similarity_level: SimilarityLevel;
  similar_orders: number[];
  insufficient_data: boolean;
}

export interface CalibrationResponse {
  rows_loaded: number;
  rows_considered_for_mape: number;
  rows_excluded_zero_actual: number;
  mape: number | null;
  bias_by_order_type: Record<string, number>;
}

export interface EstimatorMetadata {
  suggested_hours: number;
  quoted_hours: number;
  similarity_level: SimilarityLevel;
  sample_size: number;
  similar_orders: number[];
  estimator_version: string;
}

// ==================== CALENDAR TYPES ====================

/** Mirror of CalendarEventType enum from db/models.py */
export type CalendarEventType = ApiCalendarEventType;

/** Traffic light status for deadline events */
export type TrafficLight = 'green' | 'yellow' | 'red' | 'grey';

/** Stored calendar event — returned by GET /api/v1/calendar/events */
export interface CalendarEvent {
  id: number;
  title: string;
  description?: string | null;
  event_type: CalendarEventType;
  start_datetime: string; // ISO datetime
  end_datetime?: string | null; // ISO datetime
  all_day: boolean;
  order_id?: number | null;
  user_id: number;
  color?: string | null;
  recurrence?: string | null;
  created_at: string;
  updated_at: string;
}

/** Virtual deadline event — returned by GET /api/v1/calendar/deadlines */
export interface CalendarDeadlineEvent {
  id: number;
  title: string;
  event_type: 'order_deadline';
  start_datetime: string; // ISO datetime
  all_day: boolean;
  order_id: number;
  status: string;
  customer_name?: string | null;
  traffic_light: TrafficLight;
  days_until_deadline: number;
  color?: string | null;
}

/** Union type for anything rendered on the calendar grid */
export type AnyCalendarEvent = CalendarEvent | CalendarDeadlineEvent;

/** POST body for creating a new event */
export interface CalendarEventCreate {
  title: string;
  description?: string;
  event_type: CalendarEventType;
  start_datetime: string; // ISO datetime
  end_datetime?: string;  // ISO datetime
  all_day: boolean;
  order_id?: number;
  color?: string;
  recurrence?: string;
}

/** PUT body for updating an existing event (all fields optional) */
export interface CalendarEventUpdate {
  title?: string;
  description?: string;
  event_type?: CalendarEventType;
  start_datetime?: string;
  end_datetime?: string;
  all_day?: boolean;
  order_id?: number;
  color?: string;
  recurrence?: string;
}

// ==================== SOLL/IST COMPARISON TYPES ====================

export interface ComparisonMetric {
  soll: number | null;
  ist: number | null;
  deviation_percent: number | null;
  deviation_abs: number | null;
  is_significant: boolean;
}

export interface ActivityBreakdownComparison {
  activity_id: number;
  activity_name: string;
  activity_category: string;
  actual_minutes: number;
  estimated_minutes: number | null;
  deviation_minutes: number | null;
  deviation_percent: number | null;
  is_significant: boolean;
  entry_count: number;
}

export interface OrderComparison {
  order_id: number;
  order_title: string;
  order_type: string | null;
  status: string;
  completed_at: string | null;
  hours: ComparisonMetric;
  material_weight: ComparisonMetric;
  material_cost: ComparisonMetric;
  total_price: ComparisonMetric;
  activity_breakdown: ActivityBreakdownComparison[];
  overall_accuracy_score: number | null;
  has_significant_deviation: boolean;
}

// ==================== ORDER PHOTO TYPES ====================

export interface OrderPhoto {
  id: string;            // UUID
  order_id: number;
  file_path: string;
  notes?: string | null;
  timestamp: string;     // ISO datetime
  taken_by: number;
  user_name?: string | null;
  time_entry_id?: string | null;
}

// ==================== REPAIR TYPES ====================

export type RepairJobStatus = ApiRepairJobStatus;

export type RepairItemType = ApiRepairItemType;

export type RepairPhotoPhase = ApiRepairPhotoPhase;

export type RepairCustomerSummary = Schemas['CustomerSummary'];

export type RepairPhoto = ApiRepairPhoto;

export type RepairJob = ApiRepairJob;

export type RepairJobListItem = ApiRepairJobListItem;

export interface RepairJobCreateInput {
  customer_id?: number | null;
  item_description: string;
  item_type: RepairItemType;
  metal_type?: string | null;
  estimated_value?: number | null;
  estimated_completion_date?: string | null;
}

export interface RepairDiagnoseInput {
  diagnosis_notes: string;
  estimated_cost: number;
  estimated_completion_date?: string | null;
}

export interface RepairCompleteInput {
  actual_cost: number;
  notes?: string | null;
}

export interface RepairStatusUpdateInput {
  notes?: string | null;
}

// ==================== V1.1 REPAIR INTAKE CHECKLIST ====================

/**
 * Eingangs-Checkliste — dispute protection mirroring insurance-industry
 * intake practice: every item is satisfied EITHER by an intake-phase photo
 * ("photo", photo_id set) OR an explicit "nicht zutreffend" declaration
 * ("na", na_reason set, >=3 chars). "open" is the initial seeded state.
 * Mirrors backend IntakeChecklistItem (src/goldsmith_erp/models/repair.py).
 */
export type IntakeChecklistItemStatus = Schemas['IntakeChecklistItem']['status'];

export type IntakeChecklistItem = Schemas['IntakeChecklistItem'];

// ==================== V1.1 CONSULTATION (BERATUNG) ====================

export type ConsultationStatus = ApiConsultationStatus;

export type ConsultationOccasion = ApiConsultationOccasion;

export type ConsultationPhotoKind = ApiConsultationPhotoKind;

export type NoGoCategory = ApiNoGoCategory;

export type ConsultationPieceType = ApiOrderTypeEnum;

export type ConsultationPhoto = Schemas['ConsultationPhotoRead'];

export type Consultation = ApiConsultation;

export type ConsultationListItem = ApiConsultationListItem;

export interface ConsultationCreateInput {
  customer_id: number;
  occasion?: ConsultationOccasion;
}

export interface ConsultationUpdateInput {
  occasion?: ConsultationOccasion;
  occasion_date?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  piece_type?: ConsultationPieceType | null;
  wishes?: string | null;
  materials_discussed?: Array<Record<string, string>> | null;
  source_material?: string | null;
  notes?: string | null;
  follow_up_at?: string | null;
  status?: ConsultationStatus;
}

export interface NoGo {
  id: number;
  customer_id: number;
  category: NoGoCategory;
  value: string;
  note?: string | null;
  source_consultation_id?: number | null;
  created_at: string;
}

export interface NoGoCreateInput {
  category: NoGoCategory;
  value: string;
  note?: string;
}

export interface NoGoConflict {
  no_go_id: number;
  category: NoGoCategory;
  value: string;
  matched_against: string;
}

export interface StyleProfile {
  metal_tones: string[];
  finishes: string[];
  stone_preferences: string[];
  style_words: string[];
}