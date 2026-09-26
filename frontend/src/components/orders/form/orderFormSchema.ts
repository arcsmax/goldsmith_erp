// Order form model (W3-06): react-hook-form values, the zod resolver schema
// and the mapping to the API payloads.
//
// The form keeps inputs as strings (what the browser gives us); the business
// rules stay in lib/validation/schemas.ts#OrderCreateSchema, which runs on the
// coerced values inside superRefine, so there is exactly one rule set.
import { z } from 'zod';
import type { CostingMethod, MetalType, OrderCreateInput, OrderStatus, OrderType, OrderUpdateInput } from '../../../types';
import type { Gemstone, GemstoneCreateInput } from '../../../api/gemstones';
import { OrderCreateSchema } from '../../../lib/validation/schemas';

export const DEFAULT_SCRAP_PERCENT = '5';
export const DEFAULT_HOURLY_RATE = '75';
export const DEFAULT_MARGIN_PERCENT = '40';
export const DEFAULT_VAT_PERCENT = '19';

export interface GemstoneRow {
  /** Set for a stone already saved on the order. */
  gemstoneId?: number;
  type: string;
  quantity: string;
  carat: string;
  color: string;
  quality: string;
  shape: string;
  setting_type: string;
  is_customer_stone: boolean;
  cost: string;
}

export interface OrderFormValues {
  title: string;
  description: string;
  customer_id: string;
  deadline: string;
  status: OrderStatus;
  current_location: string;
  /** W8 Standort id as a string ('' = none / legacy text only). */
  location_id: string;
  order_type: string;
  metal_type: MetalType | '';
  estimated_weight_g: string;
  scrap_percentage: string;
  costing_method_used: CostingMethod;
  specific_metal_purchase_id: string;
  price: string;
  labor_hours: string;
  hourly_rate: string;
  profit_margin_percent: string;
  vat_rate: string;
  alloy: string;
  ring_size_mm: string;
  surface_finish: string;
  fitting_date: string;
  has_scrap_gold: boolean;
  special_instructions: string;
  gemstones: GemstoneRow[];
}

export const EMPTY_GEMSTONE: GemstoneRow = {
  type: '',
  quantity: '1',
  carat: '',
  color: '',
  quality: '',
  shape: '',
  setting_type: '',
  is_customer_stone: false,
  cost: '',
};

const dateOnly = (iso?: string | null): string => (iso ? iso.split('T')[0] : '');
const text = (value?: string | number | null, fallback = ''): string =>
  value === null || value === undefined ? fallback : String(value);

/** Form values for a new order, or the saved values of `order`. */
export function toFormValues(order?: OrderType | null): OrderFormValues {
  return {
    title: order?.title ?? '',
    description: order?.description ?? '',
    customer_id: order ? String(order.customer_id) : '',
    deadline: dateOnly(order?.deadline),
    status: order?.status ?? 'new',
    current_location: order?.current_location ?? '',
    location_id: order?.location_id != null ? String(order.location_id) : '',
    order_type: order?.order_type ?? '',
    metal_type: (order?.metal_type ?? '') as MetalType | '',
    estimated_weight_g: text(order?.estimated_weight_g),
    scrap_percentage: text(order?.scrap_percentage, DEFAULT_SCRAP_PERCENT),
    costing_method_used: order?.costing_method_used ?? 'fifo',
    specific_metal_purchase_id: text(order?.specific_metal_purchase_id),
    price: text(order?.price),
    labor_hours: text(order?.labor_hours),
    hourly_rate: text(order?.hourly_rate, DEFAULT_HOURLY_RATE),
    profit_margin_percent: text(order?.profit_margin_percent, DEFAULT_MARGIN_PERCENT),
    vat_rate: text(order?.vat_rate, DEFAULT_VAT_PERCENT),
    alloy: order?.alloy ?? '',
    ring_size_mm: text(order?.ring_size_mm),
    surface_finish: order?.surface_finish ?? '',
    fitting_date: dateOnly(order?.fitting_date),
    has_scrap_gold: order?.has_scrap_gold ?? false,
    special_instructions: order?.special_instructions ?? '',
    gemstones: [],
  };
}

const optionalNumber = (value: string): number | undefined => {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed.replace(',', '.')) : undefined;
};

/** Coerce the string inputs into the shape OrderCreateSchema expects. */
function toSchemaInput(v: OrderFormValues) {
  return {
    title: v.title.trim(),
    description: v.description.trim(),
    customer_id: v.customer_id ? Number.parseInt(v.customer_id, 10) : Number.NaN,
    deadline: v.deadline,
    status: v.status,
    current_location: v.current_location.trim() || undefined,
    metal_type: v.metal_type || undefined,
    estimated_weight_g: optionalNumber(v.estimated_weight_g),
    scrap_percentage: optionalNumber(v.scrap_percentage),
    costing_method: v.costing_method_used,
    specific_metal_purchase_id: v.specific_metal_purchase_id
      ? Number.parseInt(v.specific_metal_purchase_id, 10)
      : undefined,
    price: optionalNumber(v.price),
    labor_hours: optionalNumber(v.labor_hours),
    hourly_rate: optionalNumber(v.hourly_rate),
    profit_margin_percent: optionalNumber(v.profit_margin_percent),
    vat_rate: optionalNumber(v.vat_rate),
    alloy: v.alloy || undefined,
    ring_size_mm: optionalNumber(v.ring_size_mm),
    surface_finish: v.surface_finish || undefined,
    fitting_date: v.fitting_date || undefined,
    has_scrap_gold: v.has_scrap_gold,
    special_instructions: v.special_instructions.trim() || undefined,
  };
}

const DECIMAL = /^\d+([.,]\d+)?$/;
const optionalDecimal = (message: string) =>
  z.string().trim().refine((v) => v === '' || DECIMAL.test(v), message);

export const gemstoneRowSchema = z.object({
  gemstoneId: z.number().int().optional(),
  type: z.string().trim().min(1, 'Steinart fehlt. Bitte die Steinart eingeben.'),
  quantity: z
    .string()
    .trim()
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 1, 'Anzahl bitte als ganze Zahl ab 1 eingeben.'),
  carat: optionalDecimal('Karat bitte als Zahl eingeben, z. B. 0,25.'),
  color: z.string(),
  quality: z.string(),
  shape: z.string(),
  setting_type: z.string(),
  is_customer_stone: z.boolean(),
  cost: optionalDecimal('Einkaufspreis bitte als Betrag in Euro eingeben, z. B. 120,50.'),
});

/** OrderCreateSchema names the field costing_method; the form shows costing_method_used. */
const FORM_PATH: Record<string, keyof OrderFormValues> = { costing_method: 'costing_method_used' };

export const orderFormSchema = z
  .object({
    title: z.string(),
    description: z.string(),
    customer_id: z.string(),
    deadline: z.string(),
    status: z.string(),
    current_location: z.string(),
    location_id: z.string(),
    order_type: z.string(),
    metal_type: z.string(),
    estimated_weight_g: z.string(),
    scrap_percentage: z.string(),
    costing_method_used: z.string(),
    specific_metal_purchase_id: z.string(),
    price: z.string(),
    labor_hours: z.string(),
    hourly_rate: z.string(),
    profit_margin_percent: z.string(),
    vat_rate: z.string(),
    alloy: z.string(),
    ring_size_mm: z.string(),
    surface_finish: z.string(),
    fitting_date: z.string(),
    has_scrap_gold: z.boolean(),
    special_instructions: z.string(),
    gemstones: z.array(gemstoneRowSchema),
  })
  .superRefine((values, ctx) => {
    const result = OrderCreateSchema.safeParse(toSchemaInput(values as OrderFormValues));
    if (result.success) return;
    for (const issue of result.error.issues) {
      const [head, ...rest] = issue.path.map(String);
      ctx.addIssue({ code: 'custom', message: issue.message, path: [FORM_PATH[head] ?? head, ...rest] });
    }
  });

/** The payload OrdersPage sends (same shape as before W3-06). */
export function toOrderPayload(
  values: OrderFormValues,
  isEdit: boolean,
): OrderCreateInput | OrderUpdateInput {
  const { costing_method, ...rest } = OrderCreateSchema.parse(toSchemaInput(values));
  return {
    ...rest,
    costing_method_used: costing_method,
    // DOM-09: not in the Zod schema; an edit may clear it, a new order omits it.
    order_type: values.order_type || (isEdit ? null : undefined),
    // W8: the Standort id travels next to its name (not in the Zod schema).
    location_id: values.location_id
      ? Number.parseInt(values.location_id, 10)
      : isEdit
        ? null
        : undefined,
  } as OrderCreateInput | OrderUpdateInput;
}

const decimalOrNull = (value: string): number | null => {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed.replace(',', '.')) : null;
};

export function toGemstoneRow(stone: Gemstone): GemstoneRow {
  const german = (value?: number | null) => (value != null ? String(value).replace('.', ',') : '');
  return {
    gemstoneId: stone.id,
    type: stone.type,
    quantity: String(stone.quantity ?? 1),
    carat: german(stone.carat),
    color: stone.color ?? '',
    quality: stone.quality ?? '',
    shape: stone.shape ?? '',
    setting_type: stone.setting_type ?? '',
    is_customer_stone: Boolean(stone.is_customer_stone),
    cost: german(stone.cost),
  };
}

/** A Kundenstein never carries a purchase price. */
export function toGemstonePayload(row: GemstoneRow, canViewCost: boolean): GemstoneCreateInput {
  const payload: GemstoneCreateInput = {
    type: row.type.trim(),
    quantity: Math.max(1, Number.parseInt(row.quantity, 10) || 1),
    carat: decimalOrNull(row.carat),
    color: row.color.trim() || null,
    quality: row.quality.trim() || null,
    shape: row.shape.trim() || null,
    setting_type: (row.setting_type || null) as GemstoneCreateInput['setting_type'],
    is_customer_stone: row.is_customer_stone,
  };
  if (canViewCost && !row.is_customer_stone) {
    return { ...payload, cost: decimalOrNull(row.cost) ?? 0 };
  }
  return payload;
}
