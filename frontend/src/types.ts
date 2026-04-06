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

export interface Customer {
  id: number;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  email: string;
  phone?: string | null;
  mobile?: string | null;
  street?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country: string;
  customer_type: CustomerCategory;
  source?: string | null;
  notes?: string | null;
  tags: string[];
  is_active: boolean;
  ring_size?: number | null;
  chain_length_cm?: number | null;
  bracelet_length_cm?: number | null;
  allergies?: string | null;
  preferences?: Record<string, string> | null;
  birthday?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerListItem {
  id: number;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  email: string;
  phone?: string | null;
  customer_type: CustomerCategory;
  tags: string[];
  is_active: boolean;
}

export interface CustomerCreateInput {
  first_name: string;
  last_name: string;
  company_name?: string;
  email: string;
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
export type MeasurementType =
  | 'ring_size'
  | 'chain_length'
  | 'wrist_circumference'
  | 'finger_circumference'
  | 'neck_circumference'
  | 'ankle_circumference';

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

export type OrderStatus =
  | 'new'
  | 'draft'
  | 'confirmed'
  | 'in_progress'
  | 'waiting_for_fitting'
  | 'fitting_done'
  | 'ready_for_setting'
  | 'quality_check'
  | 'completed'
  | 'delivered';

// MetalType defined in Metal Inventory section below

export type CostingMethod = 'FIFO' | 'LIFO' | 'AVERAGE' | 'SPECIFIC';

export interface OrderType {
  id: number;
  title: string;
  description: string;
  price: number | null;
  status: OrderStatus;
  customer_id: number;
  customer?: Customer; // Optional - populated when fetching with relations
  deadline?: string | null;
  created_at: string;
  updated_at: string;
  materials?: MaterialType[];

  // Location
  current_location?: string | null;

  // Weight & Material
  estimated_weight_g?: number | null;
  actual_weight_g?: number | null;
  scrap_percentage?: number;

  // Metal Inventory
  metal_type?: MetalType | null;
  costing_method_used?: CostingMethod;
  specific_metal_purchase_id?: number | null;

  // Cost Calculation
  material_cost_calculated?: number | null;
  material_cost_override?: number | null;
  labor_hours?: number | null;
  hourly_rate?: number;
  labor_cost?: number | null;

  // Pricing
  profit_margin_percent?: number;
  vat_rate?: number;
  calculated_price?: number | null;

  // Goldsmith Intake Fields (Pflichtfelder)
  alloy?: string | null;
  ring_size_mm?: number | null;
  surface_finish?: string | null;
  fitting_date?: string | null;
  has_scrap_gold?: boolean | null;
  special_instructions?: string | null;
}

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
  special_instructions?: string | null;

  // Order classification
  order_type?: string | null;
  complexity_rating?: number | null;
  finish_type?: string | null;
}

// ==================== USER TYPES ====================

export type UserRole = 'ADMIN' | 'GOLDSMITH' | 'VIEWER' | 'USER';

export interface UserType {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

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
  hasRole: (roles: UserRole | UserRole[]) => boolean;
  isAdmin: boolean;
}

// ==================== METAL INVENTORY TYPES ====================

export type MetalType = 'gold_24k' | 'gold_22k' | 'gold_18k' | 'gold_14k' | 'gold_9k' | 'silver_999' | 'silver_925' | 'silver_800' | 'platinum_950' | 'platinum_900' | 'palladium' | 'white_gold_18k' | 'white_gold_14k' | 'rose_gold_18k' | 'rose_gold_14k';

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

export type MetalPriceSource = 'api' | 'manual' | 'fallback';

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

export interface Activity {
  id: number;
  name: string;
  category: ActivityCategory;
  icon?: string | null;
  color?: string | null;
  usage_count: number;
  average_duration_minutes?: number | null;
  last_used?: string | null;
  is_custom: boolean;
  created_by?: number | null;
  created_at: string;
}

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

export interface TimeEntry {
  id: string; // UUID
  order_id: number;
  user_id: number;
  activity_id: number;
  start_time: string; // ISO datetime
  end_time?: string | null; // ISO datetime
  duration_minutes?: number | null;
  location?: string | null;
  complexity_rating?: number | null; // 1-5
  quality_rating?: number | null; // 1-5
  rework_required: boolean;
  notes?: string | null;
  extra_metadata?: Record<string, any> | null;
  created_at: string; // ISO datetime
}

export interface TimeEntryWithDetails extends TimeEntry {
  activity?: Activity | null;
  order_title?: string | null;
  user_name?: string | null;
}

export interface TimeEntryStartInput {
  order_id: number;
  activity_id: number;
  location?: string;
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

export interface ActivityBreakdownData {
  activity_name: string;
  hours: number;
  percentage: number;
  color: string;
}

// ==================== NOTIFICATION TYPES ====================

export type NotificationSeverity = 'INFO' | 'WARNING' | 'URGENT';

export interface Notification {
  id: number;
  title: string;
  message: string;
  severity: NotificationSeverity;
  is_read: boolean;
  created_at: string; // ISO datetime
  link?: string | null; // optional deep-link (e.g. /orders/42)
}

export interface NotificationUnreadCount {
  unread_count: number;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
}

// ==================== INVOICE TYPES ====================

export type InvoiceStatus = 'DRAFT' | 'SENT' | 'PAID' | 'OVERDUE' | 'CANCELLED';

export type InvoiceLineType = 'material' | 'labor' | 'gemstone' | 'other';

export interface InvoiceLineItem {
  id: number;
  invoice_id: number;
  line_type: InvoiceLineType;
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}

/** Full invoice including line items (used for detail view). */
export interface Invoice {
  id: number;
  invoice_number: string; // RE-YYYY-NNNN
  order_id: number;
  customer_id: number;
  created_by: number;
  status: InvoiceStatus;
  issue_date: string;   // ISO datetime
  due_date: string;     // ISO datetime
  paid_date?: string | null;
  subtotal: number;     // Zwischensumme (net)
  tax_rate: number;     // MwSt-Satz in Prozent
  tax_amount: number;   // MwSt-Betrag
  total: number;        // Gesamtbetrag (gross)
  notes?: string | null;
  payment_method?: string | null;
  created_at: string;
  updated_at: string;
  line_items: InvoiceLineItem[];
}

/** Lightweight invoice for list views. */
export interface InvoiceListItem {
  id: number;
  invoice_number: string;
  order_id: number;
  customer_id: number;
  status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  paid_date?: string | null;
  total: number;
  created_at: string;
}

export interface InvoiceListResponse {
  items: InvoiceListItem[];
  total: number;
  skip: number;
  limit: number;
}

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

export type QuoteStatus = 'DRAFT' | 'SENT' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CONVERTED';

export type QuoteLineType = 'material' | 'labor' | 'gemstone' | 'other';

export interface QuoteLineItem {
  id: number;
  quote_id: number;
  line_type: QuoteLineType;
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}

/** Full quote including line items (used for detail view). */
export interface Quote {
  id: number;
  quote_number: string; // KV-YYYY-NNNN
  order_id?: number | null;
  customer_id: number;
  created_by: number;
  status: QuoteStatus;
  valid_until: string;    // ISO datetime
  approved_at?: string | null;
  rejected_at?: string | null;
  converted_at?: string | null;
  subtotal: number;       // Zwischensumme (net)
  tax_rate: number;       // MwSt-Satz in Prozent
  tax_amount: number;     // MwSt-Betrag
  total: number;          // Gesamtbetrag (gross)
  customer_signature_data?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  line_items: QuoteLineItem[];
}

/** Lightweight quote for list views. */
export interface QuoteListItem {
  id: number;
  quote_number: string;
  order_id?: number | null;
  customer_id: number;
  status: QuoteStatus;
  valid_until: string;
  total: number;
  created_at: string;
}

export interface QuoteListResponse {
  items: QuoteListItem[];
  total: number;
  skip: number;
  limit: number;
}

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

// ==================== CALENDAR TYPES ====================

/** Mirror of CalendarEventType enum from db/models.py */
export type CalendarEventType =
  | 'ORDER_DEADLINE'
  | 'WORKSHOP_TASK'
  | 'APPOINTMENT'
  | 'REMINDER';

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
  event_type: 'ORDER_DEADLINE';
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

export type RepairJobStatus =
  | 'received'
  | 'diagnosed'
  | 'quoted'
  | 'approved'
  | 'in_repair'
  | 'quality_check'
  | 'ready'
  | 'picked_up'
  | 'cancelled';

export type RepairItemType =
  | 'ring'
  | 'chain'
  | 'bracelet'
  | 'earring'
  | 'watch'
  | 'brooch'
  | 'other';

export type RepairPhotoPhase = 'intake' | 'during_repair' | 'completed';

export interface RepairCustomerSummary {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
}

export interface RepairPhoto {
  id: number;
  repair_job_id: number;
  phase: RepairPhotoPhase;
  file_path: string;
  timestamp: string;
  taken_by?: number | null;
  notes?: string | null;
}

export interface RepairJob {
  id: number;
  repair_number: string;
  bag_number: string;
  customer_id?: number | null;
  customer?: RepairCustomerSummary | null;
  received_by?: number | null;
  item_description: string;
  item_type: RepairItemType;
  metal_type?: string | null;
  estimated_value?: number | null;
  status: RepairJobStatus;
  diagnosis_notes?: string | null;
  estimated_cost?: number | null;
  actual_cost?: number | null;
  estimated_completion_date?: string | null;
  actual_completion_date?: string | null;
  customer_notified_at?: string | null;
  picked_up_at?: string | null;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  photos: RepairPhoto[];
}

export interface RepairJobListItem {
  id: number;
  repair_number: string;
  bag_number: string;
  customer_id?: number | null;
  customer?: RepairCustomerSummary | null;
  item_description: string;
  item_type: RepairItemType;
  metal_type?: string | null;
  status: RepairJobStatus;
  estimated_cost?: number | null;
  estimated_completion_date?: string | null;
  created_at: string;
  updated_at: string;
}

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