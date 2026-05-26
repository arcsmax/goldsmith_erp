// Order Form Modal Component with Tabs
import React, { useState, useEffect, useRef } from 'react';
import { OrderType, OrderCreateInput, OrderUpdateInput, Customer, MetalType, CostingMethod } from '../../types';
import { customersApi } from '../../api';
import { useMetalTypes } from '../../hooks/useMetalTypes';
import { OrderCreateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';
import '../../styles/orders.css';

interface OrderFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: OrderCreateInput | OrderUpdateInput) => Promise<void>;
  order?: OrderType | null;
  isLoading?: boolean;
}

type TabType = 'basic' | 'auftrag' | 'metal' | 'pricing';

// Kept as fallback while the metal-types API is loading
const METAL_TYPE_OPTIONS_FALLBACK: { value: MetalType; label: string }[] = [
  { value: 'gold_24k', label: 'Gold 24K (999)' },
  { value: 'gold_18k', label: 'Gold 18K (750)' },
  { value: 'gold_14k', label: 'Gold 14K (585)' },
  { value: 'silver_925', label: 'Silber 925' },
  { value: 'silver_999', label: 'Silber 999' },
  { value: 'platinum_950', label: 'Platin 950' },
];

const COSTING_METHOD_OPTIONS: { value: CostingMethod; label: string }[] = [
  { value: 'fifo', label: 'FIFO (First In, First Out)' },
  { value: 'lifo', label: 'LIFO (Last In, First Out)' },
  { value: 'average', label: 'Durchschnittspreis' },
  { value: 'specific', label: 'Spezifische Charge' },
];

const ALLOY_OPTIONS = [
  { value: '999', label: 'Gold 999 (24K, Feingold)' },
  { value: '900', label: 'Gold 900 (21,6K)' },
  { value: '750', label: 'Gold 750 (18K)' },
  { value: '585', label: 'Gold 585 (14K)' },
  { value: '375', label: 'Gold 375 (9K)' },
  { value: '333', label: 'Gold 333 (8K)' },
  { value: 'Ag925', label: 'Silber 925 (Sterling)' },
  { value: 'Ag800', label: 'Silber 800' },
  { value: 'Pt950', label: 'Platin 950' },
];

const SURFACE_FINISH_OPTIONS = [
  { value: 'Hochglanz', label: 'Hochglanz' },
  { value: 'Matt', label: 'Matt' },
  { value: 'Gebuerstet', label: 'Gebürstet' },
  { value: 'Gehaemmert', label: 'Gehämmert' },
  { value: 'Oxidiert', label: 'Oxidiert' },
  { value: 'Sandgestrahlt', label: 'Sandgestrahlt' },
];

export const OrderFormModal: React.FC<OrderFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  order,
  isLoading = false,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('basic');
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);
  const { metalTypes: allMetalTypes, isLoading: isLoadingMetalTypes } = useMetalTypes();
  const firstInputRef = useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    customer_id: '',
    deadline: '',
    status: 'new' as const,
    current_location: '',

    // Metal fields
    metal_type: '' as MetalType | '',
    estimated_weight_g: '',
    scrap_percentage: '5',
    costing_method_used: 'fifo' as CostingMethod,
    specific_metal_purchase_id: '',

    // Pricing fields
    price: '',
    labor_hours: '',
    hourly_rate: '75',
    profit_margin_percent: '40',
    vat_rate: '19',

    // Goldsmith Intake Fields (Pflichtfelder)
    alloy: '',
    ring_size_mm: '',
    surface_finish: '',
    fitting_date: '',
    has_scrap_gold: false,
    special_instructions: '',
  });

  const { validate: zodValidate, errors, clearErrors, clearError } = useFormValidation(OrderCreateSchema);
  const [hasAttemptedSubmit, setHasAttemptedSubmit] = useState(false);

  // Fetch customers on mount
  useEffect(() => {
    if (isOpen) {
      fetchCustomers();
    }
  }, [isOpen]);

  // Focus the first input when modal opens
  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => firstInputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // Initialize form with order data if editing
  useEffect(() => {
    if (order) {
      setFormData({
        title: order.title,
        description: order.description,
        customer_id: order.customer_id.toString(),
        deadline: order.deadline ? order.deadline.split('T')[0] : '',
        status: order.status,
        current_location: order.current_location || '',

        metal_type: order.metal_type || '',
        estimated_weight_g: order.estimated_weight_g?.toString() || '',
        scrap_percentage: order.scrap_percentage?.toString() || '5',
        costing_method_used: order.costing_method_used || 'fifo',
        specific_metal_purchase_id: order.specific_metal_purchase_id?.toString() || '',

        price: order.price?.toString() || '',
        labor_hours: order.labor_hours?.toString() || '',
        hourly_rate: order.hourly_rate?.toString() || '75',
        profit_margin_percent: order.profit_margin_percent?.toString() || '40',
        vat_rate: order.vat_rate?.toString() || '19',

        alloy: order.alloy || '',
        ring_size_mm: order.ring_size_mm?.toString() || '',
        surface_finish: order.surface_finish || '',
        fitting_date: order.fitting_date ? order.fitting_date.split('T')[0] : '',
        has_scrap_gold: order.has_scrap_gold ?? false,
        special_instructions: order.special_instructions || '',
      });
    } else {
      setFormData({
        title: '',
        description: '',
        customer_id: '',
        deadline: '',
        status: 'new',
        current_location: '',
        metal_type: '',
        estimated_weight_g: '',
        scrap_percentage: '5',
        costing_method_used: 'fifo',
        specific_metal_purchase_id: '',
        price: '',
        labor_hours: '',
        hourly_rate: '75',
        profit_margin_percent: '40',
        vat_rate: '19',

        alloy: '',
        ring_size_mm: '',
        surface_finish: '',
        fitting_date: '',
        has_scrap_gold: false,
        special_instructions: '',
      });
    }
    clearErrors();
    setHasAttemptedSubmit(false);
    setActiveTab('basic');
  }, [order, isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchCustomers = async () => {
    try {
      setIsLoadingCustomers(true);
      const data = await customersApi.getAll({ limit: 100 }); // dropdown — 100 is ample for picker UI
      setCustomers(Array.isArray(data) ? data : data.items || []);
    } catch (err) {
      console.error('Failed to fetch customers', err);
    } finally {
      setIsLoadingCustomers(false);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    clearError(name);
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    setFormData((prev) => ({ ...prev, [name]: checked }));
    clearError(name);
  };


  // Check if base required fields are filled (for button disable state)
  const isFormValid =
    formData.title.trim() !== '' &&
    formData.description.trim() !== '' &&
    formData.customer_id !== '' &&
    formData.deadline !== '' &&
    formData.metal_type !== '' &&
    formData.alloy !== '';

  // Pflichtfelder completion indicator for the Auftrag tab
  // These are the fields needed before status can be set to 'confirmed'
  const isRingOrder = formData.metal_type !== '' &&
    (formData.title.toLowerCase().includes('ring') ||
     formData.description.toLowerCase().includes('ring'));
  const pflichtfelder = [
    { key: 'title', label: 'Bezeichnung', filled: formData.title.trim() !== '' },
    { key: 'metal_type', label: 'Metallart', filled: formData.metal_type !== '' },
    { key: 'alloy', label: 'Legierung', filled: formData.alloy !== '' },
    { key: 'deadline', label: 'Abgabetermin', filled: formData.deadline !== '' },
    ...(isRingOrder ? [{ key: 'ring_size_mm', label: 'Ringmass', filled: formData.ring_size_mm !== '' }] : []),
  ];
  const filledCount = pflichtfelder.filter((f) => f.filled).length;
  const totalCount = pflichtfelder.length;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setHasAttemptedSubmit(true);

    // Coerce string form fields to the numeric types Zod expects
    const toValidate = {
      title: formData.title.trim(),
      description: formData.description.trim(),
      customer_id: formData.customer_id ? parseInt(formData.customer_id) : NaN,
      deadline: formData.deadline || '',
      status: formData.status,
      current_location: formData.current_location.trim() || undefined,

      metal_type: (formData.metal_type || undefined) as MetalType | undefined,
      estimated_weight_g: formData.estimated_weight_g
        ? parseFloat(formData.estimated_weight_g)
        : undefined,
      scrap_percentage: formData.scrap_percentage
        ? parseFloat(formData.scrap_percentage)
        : undefined,
      costing_method: formData.costing_method_used as CostingMethod,
      specific_metal_purchase_id:
        formData.specific_metal_purchase_id
          ? parseInt(formData.specific_metal_purchase_id)
          : undefined,

      price: formData.price ? parseFloat(formData.price) : undefined,
      labor_hours: formData.labor_hours ? parseFloat(formData.labor_hours) : undefined,
      hourly_rate: formData.hourly_rate ? parseFloat(formData.hourly_rate) : undefined,
      profit_margin_percent: formData.profit_margin_percent
        ? parseFloat(formData.profit_margin_percent)
        : undefined,
      vat_rate: formData.vat_rate ? parseFloat(formData.vat_rate) : undefined,

      // Goldsmith Intake Fields
      alloy: formData.alloy || undefined,
      ring_size_mm: formData.ring_size_mm ? parseFloat(formData.ring_size_mm) : undefined,
      surface_finish: formData.surface_finish || undefined,
      fitting_date: formData.fitting_date || undefined,
      has_scrap_gold: formData.has_scrap_gold,
      special_instructions: formData.special_instructions.trim() || undefined,
    };

    const result = zodValidate(toValidate);
    if (!result.success) {
      return;
    }

    // Map validated data to the shape the parent component expects
    const submitData: any = {
      ...result.data,
      // The form field is costing_method_used for display; backend expects costing_method
      costing_method_used: result.data.costing_method,
    };
    delete submitData.costing_method;

    await onSubmit(submitData);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="order-modal-title"
      onClick={onClose}
    >
      <div className="modal-content modal-large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 id="order-modal-title">{order ? 'Auftrag bearbeiten' : 'Neuer Auftrag'}</h2>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Modal schließen">
            ×
          </button>
        </div>

        {/* Tabs */}
        <div className="form-tabs">
          <button
            type="button"
            className={`form-tab ${activeTab === 'basic' ? 'active' : ''}`}
            onClick={() => setActiveTab('basic')}
          >
            Basisinformationen
          </button>
          <button
            type="button"
            className={`form-tab ${activeTab === 'auftrag' ? 'active' : ''}`}
            onClick={() => setActiveTab('auftrag')}
          >
            Auftrag
            {filledCount < totalCount && (
              <span className="tab-badge tab-badge--warn">{filledCount}/{totalCount}</span>
            )}
            {filledCount === totalCount && totalCount > 0 && (
              <span className="tab-badge tab-badge--ok">{filledCount}/{totalCount}</span>
            )}
          </button>
          <button
            type="button"
            className={`form-tab ${activeTab === 'metal' ? 'active' : ''}`}
            onClick={() => setActiveTab('metal')}
          >
            Metall
          </button>
          <button
            type="button"
            className={`form-tab ${activeTab === 'pricing' ? 'active' : ''}`}
            onClick={() => setActiveTab('pricing')}
          >
            Preisgestaltung
          </button>
        </div>

        <form onSubmit={handleSubmit} className="order-form">
          <div className="form-body">
            {/* Basic Info Tab */}
            {activeTab === 'basic' && (
              <div className="tab-content-form">
                <div className="form-group">
                  <label htmlFor="title">
                    Bezeichnung <span className="required">*</span>
                  </label>
                  <input
                    type="text"
                    id="title"
                    name="title"
                    ref={firstInputRef}
                    value={formData.title}
                    onChange={handleChange}
                    className={hasAttemptedSubmit && errors.title ? 'error' : ''}
                    placeholder="z.B. Goldring mit Diamant"
                  />
                  {hasAttemptedSubmit && errors.title && (
                    <span className="error-message">{errors.title}</span>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="description">
                    Beschreibung <span className="required">*</span>
                  </label>
                  <textarea
                    id="description"
                    name="description"
                    value={formData.description}
                    onChange={handleChange}
                    className={hasAttemptedSubmit && errors.description ? 'error' : ''}
                    rows={4}
                    placeholder="Detaillierte Beschreibung des Auftrags"
                  />
                  {hasAttemptedSubmit && errors.description && (
                    <span className="error-message">{errors.description}</span>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="customer_id">
                    Kunde <span className="required">*</span>
                  </label>
                  <select
                    id="customer_id"
                    name="customer_id"
                    value={formData.customer_id}
                    onChange={handleChange}
                    className={hasAttemptedSubmit && errors.customer_id ? 'error' : ''}
                    disabled={isLoadingCustomers}
                  >
                    <option value="">
                      {isLoadingCustomers ? 'Laden...' : '-- Kunde auswählen --'}
                    </option>
                    {customers.map((customer) => (
                      <option key={customer.id} value={customer.id}>
                        {customer.first_name} {customer.last_name}
                        {customer.company_name && ` (${customer.company_name})`}
                      </option>
                    ))}
                  </select>
                  {hasAttemptedSubmit && errors.customer_id && (
                    <span className="error-message">{errors.customer_id}</span>
                  )}
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="deadline">
                      Abgabetermin <span className="required">*</span>
                    </label>
                    <input
                      type="date"
                      id="deadline"
                      name="deadline"
                      value={formData.deadline}
                      onChange={handleChange}
                      className={hasAttemptedSubmit && errors.deadline ? 'error' : ''}
                    />
                    {hasAttemptedSubmit && errors.deadline && (
                      <span className="error-message">{errors.deadline}</span>
                    )}
                  </div>

                  <div className="form-group">
                    <label htmlFor="status">Status</label>
                    <select
                      id="status"
                      name="status"
                      value={formData.status}
                      onChange={handleChange}
                    >
                      <option value="new">Neu</option>
                      <option value="draft">Entwurf</option>
                      <option value="confirmed">Bestätigt</option>
                      <option value="in_progress">In Bearbeitung</option>
                      <option value="waiting_for_fitting">Wartet auf Anprobe</option>
                      <option value="fitting_done">Anprobe abgeschlossen</option>
                      <option value="ready_for_setting">Bereit für Steinbesatz</option>
                      <option value="quality_check">Endkontrolle</option>
                      <option value="completed">Fertiggestellt</option>
                      <option value="delivered">Ausgeliefert</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="current_location">Aktueller Standort</label>
                  <input
                    type="text"
                    id="current_location"
                    name="current_location"
                    value={formData.current_location}
                    onChange={handleChange}
                    placeholder="z.B. Werkstatt, Tresor, Versand"
                  />
                </div>
              </div>
            )}

            {/* Auftrag Tab — Goldsmith Intake Pflichtfelder */}
            {activeTab === 'auftrag' && (
              <div className="tab-content-form">

                {/* Pflichtfelder completion indicator */}
                <div className="pflichtfelder-indicator">
                  <span className="pflichtfelder-label">Pflichtfelder:</span>
                  <span className={`pflichtfelder-count ${filledCount === totalCount ? 'pflichtfelder-count--ok' : 'pflichtfelder-count--warn'}`}>
                    {filledCount}/{totalCount} ausgefüllt
                  </span>
                  {filledCount < totalCount && (
                    <span className="pflichtfelder-missing">
                      {' — Fehlend: '}
                      {pflichtfelder.filter((f) => !f.filled).map((f) => f.label).join(', ')}
                    </span>
                  )}
                </div>

                {/* Legierung */}
                <div className="form-group">
                  <label htmlFor="alloy">
                    Legierung <span className="required">*</span>
                  </label>
                  <select
                    id="alloy"
                    name="alloy"
                    value={formData.alloy}
                    onChange={handleChange}
                  >
                    <option value="">-- Legierung auswählen --</option>
                    {ALLOY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <small style={{ color: '#666' }}>
                    Feingehalt der Legierung (z.B. 585 = 58,5% Feingold)
                  </small>
                </div>

                {/* Oberfläche */}
                <div className="form-group">
                  <label htmlFor="surface_finish">Oberfläche</label>
                  <select
                    id="surface_finish"
                    name="surface_finish"
                    value={formData.surface_finish}
                    onChange={handleChange}
                  >
                    <option value="">-- Oberfläche auswählen --</option>
                    {SURFACE_FINISH_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Ringmass — only shown when the order appears to be a ring */}
                {isRingOrder && (
                  <div className="form-group">
                    <label htmlFor="ring_size_mm">
                      Ringmass (mm Innenumfang) <span className="required">*</span>
                    </label>
                    <input
                      type="number"
                      id="ring_size_mm"
                      name="ring_size_mm"
                      value={formData.ring_size_mm}
                      onChange={handleChange}
                      placeholder="z.B. 52.5"
                      step="0.5"
                      min="30"
                      max="100"
                    />
                    <small style={{ color: '#666' }}>
                      EU-Innendurchmesser in mm (Ringgröße 52 = 52 mm)
                    </small>
                  </div>
                )}

                {/* Anprobe-Datum */}
                <div className="form-group">
                  <label htmlFor="fitting_date">Anprobe-Datum</label>
                  <input
                    type="date"
                    id="fitting_date"
                    name="fitting_date"
                    value={formData.fitting_date}
                    onChange={handleChange}
                  />
                  {!formData.fitting_date && (
                    <small className="form-hint" style={{ color: '#888' }}>
                      Ohne Anprobe-Datum wird der Status nach Bestätigung auf "Warten auf Anprobe" gesetzt.
                    </small>
                  )}
                </div>

                {/* Altgold */}
                <div className="form-group form-group--checkbox">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      name="has_scrap_gold"
                      checked={formData.has_scrap_gold}
                      onChange={handleCheckboxChange}
                    />
                    <span>Altgold vorhanden (Altgold-Verrechnung erforderlich)</span>
                  </label>
                </div>

                {/* Sonderwünsche */}
                <div className="form-group">
                  <label htmlFor="special_instructions">Sonderwünsche</label>
                  <textarea
                    id="special_instructions"
                    name="special_instructions"
                    value={formData.special_instructions}
                    onChange={handleChange}
                    rows={4}
                    placeholder="Besondere Anforderungen des Kunden (Gravur, Fassungsart, Lieferbedingungen, ...)"
                  />
                </div>

              </div>
            )}

            {/* Metal Tab */}
            {activeTab === 'metal' && (
              <div className="tab-content-form">
                <div className="form-group">
                  <label htmlFor="metal_type">
                    Metallart <span className="required">*</span>
                  </label>
                  <select
                    id="metal_type"
                    name="metal_type"
                    value={formData.metal_type}
                    onChange={handleChange}
                    className={hasAttemptedSubmit && errors.metal_type ? 'error' : ''}
                    disabled={isLoadingMetalTypes}
                  >
                    <option value="">-- Metallart auswählen --</option>
                    {(isLoadingMetalTypes || allMetalTypes.length === 0
                      ? METAL_TYPE_OPTIONS_FALLBACK
                      : allMetalTypes.map((o) => ({ value: o.code, label: o.display_name }))
                    ).map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {hasAttemptedSubmit && errors.metal_type && (
                    <span className="error-message">{errors.metal_type}</span>
                  )}
                </div>

                {formData.metal_type && (
                  <>
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor="estimated_weight_g">
                          Geschätztes Gewicht (g) <span className="required">*</span>
                        </label>
                        <input
                          type="number"
                          id="estimated_weight_g"
                          name="estimated_weight_g"
                          value={formData.estimated_weight_g}
                          onChange={handleChange}
                          className={errors.estimated_weight_g ? 'error' : ''}
                          placeholder="0.00"
                          step="0.01"
                          min="0"
                        />
                        {errors.estimated_weight_g && (
                          <span className="error-message">{errors.estimated_weight_g}</span>
                        )}
                      </div>

                      <div className="form-group">
                        <label htmlFor="scrap_percentage">Verschnitt (%)</label>
                        <input
                          type="number"
                          id="scrap_percentage"
                          name="scrap_percentage"
                          value={formData.scrap_percentage}
                          onChange={handleChange}
                          placeholder="5"
                          step="0.1"
                          min="0"
                          max="100"
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label htmlFor="costing_method_used">Kalkulationsmethode</label>
                      <select
                        id="costing_method_used"
                        name="costing_method_used"
                        value={formData.costing_method_used}
                        onChange={handleChange}
                      >
                        {COSTING_METHOD_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {formData.costing_method_used === 'specific' && (
                      <div className="form-group">
                        <label htmlFor="specific_metal_purchase_id">
                          Charge-ID <span className="required">*</span>
                        </label>
                        <input
                          type="number"
                          id="specific_metal_purchase_id"
                          name="specific_metal_purchase_id"
                          value={formData.specific_metal_purchase_id}
                          onChange={handleChange}
                          className={errors.specific_metal_purchase_id ? 'error' : ''}
                          placeholder="Charge-ID eingeben"
                        />
                        {errors.specific_metal_purchase_id && (
                          <span className="error-message">
                            {errors.specific_metal_purchase_id}
                          </span>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Pricing Tab */}
            {activeTab === 'pricing' && (
              <div className="tab-content-form">
                <div className="form-group">
                  <label htmlFor="price">Manueller Preis Override (€)</label>
                  <input
                    type="number"
                    id="price"
                    name="price"
                    value={formData.price}
                    onChange={handleChange}
                    className={errors.price ? 'error' : ''}
                    placeholder="Leer lassen für automatische Berechnung"
                    step="0.01"
                    min="0"
                  />
                  {errors.price && <span className="error-message">{errors.price}</span>}
                  <small style={{ color: '#666' }}>
                    Optional: Überschreibt die automatische Preisberechnung
                  </small>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="labor_hours">Arbeitsstunden</label>
                    <input
                      type="number"
                      id="labor_hours"
                      name="labor_hours"
                      value={formData.labor_hours}
                      onChange={handleChange}
                      className={errors.labor_hours ? 'error' : ''}
                      placeholder="0.00"
                      step="0.5"
                      min="0"
                    />
                    {errors.labor_hours && (
                      <span className="error-message">{errors.labor_hours}</span>
                    )}
                  </div>

                  <div className="form-group">
                    <label htmlFor="hourly_rate">Stundensatz (€/h)</label>
                    <input
                      type="number"
                      id="hourly_rate"
                      name="hourly_rate"
                      value={formData.hourly_rate}
                      onChange={handleChange}
                      placeholder="75.00"
                      step="0.01"
                      min="0"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="profit_margin_percent">Gewinnmarge (%)</label>
                    <input
                      type="number"
                      id="profit_margin_percent"
                      name="profit_margin_percent"
                      value={formData.profit_margin_percent}
                      onChange={handleChange}
                      placeholder="40"
                      step="1"
                      min="0"
                      max="100"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="vat_rate">MwSt. (%)</label>
                    <input
                      type="number"
                      id="vat_rate"
                      name="vat_rate"
                      value={formData.vat_rate}
                      onChange={handleChange}
                      placeholder="19"
                      step="0.1"
                      min="0"
                      max="100"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary"
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isLoading || !isFormValid}
              title={!isFormValid ? 'Bitte alle Pflichtfelder ausfüllen' : ''}
            >
              {isLoading ? 'Speichern...' : order ? 'Aktualisieren' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
