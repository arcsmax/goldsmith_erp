// Select options for the order form (W3-06). Status labels come from
// src/design/status.ts, the single source for status wording.
import type { CostingMethod, OrderStatus } from '../../../types';
import { getStatusLabel } from '../../../design/status';
import type { OrderFormValues } from './orderFormSchema';

export type OrderFormTab = 'basic' | 'auftrag' | 'metal' | 'pricing';

export const COSTING_METHOD_OPTIONS: readonly { value: CostingMethod; label: string }[] = [
  { value: 'fifo', label: 'FIFO (First In, First Out)' },
  { value: 'lifo', label: 'LIFO (Last In, First Out)' },
  { value: 'average', label: 'Durchschnittspreis' },
  { value: 'specific', label: 'Spezifische Charge' },
];

export const SURFACE_FINISH_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'Hochglanz', label: 'Hochglanz' },
  { value: 'Matt', label: 'Matt' },
  { value: 'Gebuerstet', label: 'Gebürstet' },
  { value: 'Gehaemmert', label: 'Gehämmert' },
  { value: 'Oxidiert', label: 'Oxidiert' },
  { value: 'Sandgestrahlt', label: 'Sandgestrahlt' },
];

const FORM_STATUSES: readonly OrderStatus[] = [
  'new',
  'draft',
  'confirmed',
  'in_progress',
  'waiting_for_fitting',
  'fitting_done',
  'ready_for_setting',
  'quality_check',
  'completed',
  'delivered',
];

export const STATUS_OPTIONS = FORM_STATUSES.map((value) => ({
  value,
  label: getStatusLabel('order', value),
}));

/** Which tab shows a field, so an invalid submit can open it. */
const FIELD_TAB: Partial<Record<keyof OrderFormValues, OrderFormTab>> = {
  alloy: 'auftrag',
  ring_size_mm: 'auftrag',
  surface_finish: 'auftrag',
  fitting_date: 'auftrag',
  has_scrap_gold: 'auftrag',
  special_instructions: 'auftrag',
  gemstones: 'auftrag',
  metal_type: 'auftrag',
  estimated_weight_g: 'metal',
  scrap_percentage: 'metal',
  costing_method_used: 'metal',
  specific_metal_purchase_id: 'metal',
  price: 'pricing',
  labor_hours: 'pricing',
  hourly_rate: 'pricing',
  profit_margin_percent: 'pricing',
  vat_rate: 'pricing',
};

/** Field order across the tabs, first to last. */
const FIELD_ORDER: readonly (keyof OrderFormValues)[] = [
  'title',
  'description',
  'customer_id',
  'order_type',
  'deadline',
  'status',
  'current_location',
  'metal_type',
  'alloy',
  'surface_finish',
  'ring_size_mm',
  'fitting_date',
  'special_instructions',
  'gemstones',
  'estimated_weight_g',
  'scrap_percentage',
  'costing_method_used',
  'specific_metal_purchase_id',
  'price',
  'labor_hours',
  'hourly_rate',
  'profit_margin_percent',
  'vat_rate',
];

export function firstInvalidField(errorKeys: readonly string[]): keyof OrderFormValues | undefined {
  return FIELD_ORDER.find((field) => errorKeys.includes(field));
}

export const tabOfField = (field: keyof OrderFormValues): OrderFormTab => FIELD_TAB[field] ?? 'basic';
