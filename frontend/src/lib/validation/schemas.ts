/**
 * Zod validation schemas for all frontend forms.
 *
 * Field names and constraints are kept in sync with:
 *   - backend Pydantic models in src/goldsmith_erp/models/
 *   - TypeScript types in frontend/src/types.ts
 *
 * All error messages are in German (UI language).
 */

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** ISO date string (YYYY-MM-DD) that must be in the future or today. */
const futureDateString = z
  .string()
  .min(1, 'Pflichtfeld')
  .refine((v) => {
    const date = new Date(v);
    if (isNaN(date.getTime())) return false;
    // Compare against start of today so today itself is valid
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date >= today;
  }, 'Datum muss in der Zukunft liegen');

/** Optional phone: either empty string or a basic phone pattern. */
const optionalPhone = z
  .string()
  .optional()
  .refine(
    (v) => !v || /^[\d\s+\-()\/]+$/.test(v),
    'Ungültige Telefonnummer – nur Ziffern, +, -, () erlaubt'
  );

// ---------------------------------------------------------------------------
// Order
// ---------------------------------------------------------------------------

export const OrderStatusValues = [
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
] as const;
export type OrderStatusValue = (typeof OrderStatusValues)[number];

export const MetalTypeValues = [
  'gold_24k',
  'gold_22k',
  'gold_18k',
  'gold_14k',
  'gold_9k',
  'silver_999',
  'silver_925',
  'silver_800',
  'platinum_950',
  'platinum_900',
  'palladium',
  'white_gold_18k',
  'white_gold_14k',
  'rose_gold_18k',
  'rose_gold_14k',
] as const;

export const CostingMethodValues = ['fifo', 'lifo', 'average', 'specific'] as const;

/**
 * Schema for creating a new order.
 * Maps to backend OrderCreate Pydantic model (src/goldsmith_erp/models/order.py).
 *
 * Note: the form keeps numeric fields as strings and coerces them here so
 * that HTML <input type="number"> values round-trip without manual parsing.
 */
export const OrderCreateSchema = z
  .object({
    title: z
      .string()
      .min(2, 'Mindestens 2 Zeichen erforderlich')
      .max(200, 'Maximal 200 Zeichen erlaubt'),
    description: z
      .string()
      .min(1, 'Pflichtfeld')
      .max(2000, 'Maximal 2000 Zeichen erlaubt'),
    customer_id: z
      .number({ message: 'Pflichtfeld' })
      .int('Muss eine ganze Zahl sein')
      .positive('Bitte einen Kunden auswählen'),
    deadline: futureDateString,
    status: z.enum(OrderStatusValues).default('new'),
    current_location: z.string().max(50, 'Maximal 50 Zeichen erlaubt').optional(),

    // Metal fields
    metal_type: z.enum(MetalTypeValues).optional(),
    estimated_weight_g: z.number({ message: 'Muss eine Zahl sein' }).positive('Gewicht muss größer als 0 sein').optional(),
    scrap_percentage: z.number().min(0, 'Darf nicht negativ sein').max(50, 'Maximal 50 % Verschnitt').optional(),
    costing_method: z.enum(CostingMethodValues).default('fifo'),
    specific_metal_purchase_id: z.number().int().positive('Muss eine positive Ganzzahl sein').optional(),

    // Pricing fields (all optional — backend calculates from parts)
    price: z.number().min(0, 'Preis darf nicht negativ sein').max(1_000_000, 'Preis überschreitet das Maximum').optional(),
    labor_hours: z.number().min(0, 'Arbeitsstunden dürfen nicht negativ sein').optional(),
    hourly_rate: z.number().min(0, 'Stundensatz darf nicht negativ sein').optional(),
    profit_margin_percent: z.number().min(0).max(100, 'Maximal 100 %').optional(),
    vat_rate: z.number().min(0).max(100, 'Maximal 100 %').optional(),

    // Goldsmith Intake Fields (Pflichtfelder fuer Auftragsbestaetigung)
    alloy: z.string().max(20, 'Maximal 20 Zeichen erlaubt').optional(),
    ring_size_mm: z.number().min(30, 'Mindestens 30 mm').max(100, 'Maximal 100 mm').optional(),
    surface_finish: z.string().max(50, 'Maximal 50 Zeichen erlaubt').optional(),
    fitting_date: z.string().optional(),
    has_scrap_gold: z.boolean().optional(),
    special_instructions: z.string().max(2000, 'Maximal 2000 Zeichen erlaubt').optional(),
  })
  .refine(
    (data) => {
      // If a metal type is chosen, estimated weight becomes required
      if (data.metal_type && !data.estimated_weight_g) return false;
      return true;
    },
    {
      message: 'Gewicht ist erforderlich wenn eine Metallart ausgewählt ist',
      path: ['estimated_weight_g'],
    }
  )
  .refine(
    (data) => {
      // SPECIFIC costing method requires a purchase ID
      if (data.costing_method === 'specific' && !data.specific_metal_purchase_id) return false;
      return true;
    },
    {
      message: 'Charge-ID ist erforderlich für die Methode "Spezifische Charge"',
      path: ['specific_metal_purchase_id'],
    }
  );

export type OrderCreateFormData = z.input<typeof OrderCreateSchema>;
export type OrderCreateValidated = z.output<typeof OrderCreateSchema>;

// ---------------------------------------------------------------------------
// Material
// ---------------------------------------------------------------------------

/**
 * The units the form offers. Kept as a superset of the task spec to match
 * the options rendered in MaterialFormModal.
 */
export const MaterialUnitValues = ['Stück', 'g', 'kg', 'ml', 'l', 'cm', 'm', 'ct'] as const;
export type MaterialUnitValue = (typeof MaterialUnitValues)[number];

/**
 * Schema for creating/updating a material.
 * Maps to backend MaterialCreate (src/goldsmith_erp/models/material.py).
 */
export const MaterialCreateSchema = z.object({
  name: z
    .string()
    .min(2, 'Mindestens 2 Zeichen erforderlich')
    .max(200, 'Maximal 200 Zeichen erlaubt'),
  description: z.string().max(1000, 'Maximal 1000 Zeichen erlaubt').optional(),
  unit_price: z
    .number({ message: 'Muss eine Zahl sein' })
    .positive('Preis muss größer als 0 sein')
    .max(100_000, 'Preis überschreitet das Maximum (100.000)'),
  stock: z
    .number({ message: 'Muss eine Zahl sein' })
    .min(0, 'Bestand darf nicht negativ sein')
    .max(1_000_000, 'Bestand überschreitet das Maximum (1.000.000)'),
  unit: z
    .string()
    .min(1, 'Pflichtfeld')
    .max(20, 'Maximal 20 Zeichen erlaubt'),
  supplier: z.string().max(200, 'Maximal 200 Zeichen erlaubt').optional(),
  webshop_url: z.string().url('Ungültige URL').max(500, 'Maximal 500 Zeichen erlaubt').optional().or(z.literal('')),
  min_stock: z
    .number({ message: 'Muss eine Zahl sein' })
    .min(0, 'Mindestbestand darf nicht negativ sein')
    .max(1_000_000, 'Mindestbestand überschreitet das Maximum')
    .default(10),
});

export type MaterialCreateFormData = z.input<typeof MaterialCreateSchema>;
export type MaterialCreateValidated = z.output<typeof MaterialCreateSchema>;

// ---------------------------------------------------------------------------
// Customer
// ---------------------------------------------------------------------------

export const CustomerTypeValues = ['private', 'business'] as const;
export type CustomerTypeValue = (typeof CustomerTypeValues)[number];

/**
 * Schema for creating a customer.
 * Maps to backend CustomerCreate (src/goldsmith_erp/models/customer.py).
 *
 * Phone number pattern mirrors the backend field_validator for phone/mobile.
 */
export const CustomerCreateSchema = z
  .object({
    first_name: z
      .string()
      .min(1, 'Pflichtfeld')
      .max(100, 'Maximal 100 Zeichen erlaubt'),
    last_name: z
      .string()
      .min(1, 'Pflichtfeld')
      .max(100, 'Maximal 100 Zeichen erlaubt'),
    email: z
      .string()
      .min(1, 'Pflichtfeld')
      .email('Ungültige E-Mail-Adresse'),
    phone: optionalPhone,
    mobile: optionalPhone,
    company_name: z.string().max(200, 'Maximal 200 Zeichen erlaubt').optional(),
    street: z.string().max(200, 'Maximal 200 Zeichen erlaubt').optional(),
    city: z.string().max(100, 'Maximal 100 Zeichen erlaubt').optional(),
    postal_code: z.string().max(20, 'Maximal 20 Zeichen erlaubt').optional(),
    country: z.string().max(100, 'Maximal 100 Zeichen erlaubt').default('Deutschland'),
    customer_type: z.enum(CustomerTypeValues).default('private'),
    source: z.string().max(100, 'Maximal 100 Zeichen erlaubt').optional(),
    notes: z.string().optional(),
    tags: z.array(z.string()).optional(),
    ring_size: z.number().min(30, 'EU-Ringgröße mindestens 30').max(80, 'EU-Ringgröße maximal 80').optional(),
    chain_length_cm: z.number().min(10, 'Mindestens 10 cm').max(120, 'Maximal 120 cm').optional(),
    bracelet_length_cm: z.number().min(10, 'Mindestens 10 cm').max(50, 'Maximal 50 cm').optional(),
    allergies: z.string().max(500, 'Maximal 500 Zeichen erlaubt').optional(),
    birthday: z.string().optional(),
  })
  .refine(
    (data) => {
      // Company name is required for business customers
      if (data.customer_type === 'business' && !data.company_name?.trim()) return false;
      return true;
    },
    {
      message: 'Firmenname ist für Geschäftskunden erforderlich',
      path: ['company_name'],
    }
  );

export type CustomerCreateFormData = z.input<typeof CustomerCreateSchema>;
export type CustomerCreateValidated = z.output<typeof CustomerCreateSchema>;

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

export const UserRoleValues = ['ADMIN', 'GOLDSMITH', 'VIEWER', 'USER'] as const;
export type UserRoleValue = (typeof UserRoleValues)[number];

/**
 * Schema for creating a new user (Admin only).
 * Maps to backend UserCreate Pydantic model.
 *
 * Password is required on create; it is omitted from the update schema.
 */
export const UserCreateSchema = z.object({
  email: z
    .string()
    .min(1, 'Pflichtfeld')
    .email('Ungültige E-Mail-Adresse'),
  password: z
    .string()
    .min(8, 'Passwort muss mindestens 8 Zeichen lang sein'),
  first_name: z
    .string()
    .max(100, 'Maximal 100 Zeichen erlaubt')
    .optional(),
  last_name: z
    .string()
    .max(100, 'Maximal 100 Zeichen erlaubt')
    .optional(),
});

export type UserCreateFormData = z.input<typeof UserCreateSchema>;
export type UserCreateValidated = z.output<typeof UserCreateSchema>;

/**
 * Schema for updating an existing user (Admin only).
 * Password is optional — leave blank to keep the current password.
 */
export const UserUpdateSchema = z.object({
  email: z
    .string()
    .min(1, 'Pflichtfeld')
    .email('Ungültige E-Mail-Adresse')
    .optional(),
  password: z
    .string()
    .min(8, 'Passwort muss mindestens 8 Zeichen lang sein')
    .optional()
    .or(z.literal('')),
  first_name: z
    .string()
    .max(100, 'Maximal 100 Zeichen erlaubt')
    .optional(),
  last_name: z
    .string()
    .max(100, 'Maximal 100 Zeichen erlaubt')
    .optional(),
});

export type UserUpdateFormData = z.input<typeof UserUpdateSchema>;
export type UserUpdateValidated = z.output<typeof UserUpdateSchema>;

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

/**
 * Schema for the login form.
 * Maps to LoginCredentials type and the backend /auth/login endpoint.
 */
export const LoginSchema = z.object({
  email: z
    .string()
    .min(1, 'Pflichtfeld')
    .email('Ungültige E-Mail-Adresse'),
  password: z
    .string()
    .min(8, 'Passwort muss mindestens 8 Zeichen lang sein'),
});

export type LoginFormData = z.input<typeof LoginSchema>;
export type LoginValidated = z.output<typeof LoginSchema>;
