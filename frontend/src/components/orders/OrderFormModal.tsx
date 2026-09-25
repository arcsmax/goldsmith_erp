// Order Form Modal Component with Tabs
import React, { useState, useEffect, useRef } from 'react';
import { OrderType, OrderStatus, OrderCreateInput, OrderUpdateInput, CustomerListItem, MetalType, CostingMethod } from '../../types';
import { customersApi } from '../../api';
import { OrderCreateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';
import { NoGoWarning } from '../consultation/NoGoWarning';
import { GemstoneRepeater } from './GemstoneRepeater';
import {
  ALLOY_CHOICES,
  ORDER_TYPE_OPTIONS,
  alloyChoiceKey,
  findAlloyChoice,
} from './orderIntakeOptions';
import '../../styles/orders.css';

interface OrderFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: OrderCreateInput | OrderUpdateInput) => Promise<void>;
  order?: OrderType | null;
  isLoading?: boolean;
}

type TabType = 'basic' | 'auftrag' | 'metal' | 'pricing';

const COSTING_METHOD_OPTIONS: { value: CostingMethod; label: string }[] = [
  { value: 'fifo', label: 'FIFO (First In, First Out)' },
  { value: 'lifo', label: 'LIFO (Last In, First Out)' },
  { value: 'average', label: 'Durchschnittspreis' },
  { value: 'specific', label: 'Spezifische Charge' },
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
  const [customers, setCustomers] = useState<CustomerListItem[]>([]);
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);
  const firstInputRef = useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    customer_id: '',
    deadline: '',
    status: 'new' as OrderStatus,
    current_location: '',
    // W2-06 / DOM-09: drives the ring-size requirement and the estimator.
    order_type: '',

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
        order_type: order.order_type || '',

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
        order_type: '',
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
      setCustomers(data);
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

  // DOM-06: one "Legierung & Farbe" choice sets metal_type AND alloy.
  const alloyChoice = alloyChoiceKey(formData.metal_type, formData.alloy);
  const selectedAlloyChoice = findAlloyChoice(alloyChoice);
  const hasLegacyAlloyPair =
    alloyChoice === '' && (formData.metal_type !== '' || formData.alloy !== '');

  const handleAlloyChoiceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const choice = findAlloyChoice(e.target.value);
    setFormData((prev) => ({
      ...prev,
      metal_type: choice ? choice.metal_type : '',
      alloy: choice ? choice.alloy : '',
    }));
    clearError('metal_type');
    clearError('alloy');
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
  // DOM-05: driven by the order type, not by "ring" inside "Ohrring".
  const isRingOrder = formData.order_type === 'ring';
  const pflichtfelder = [
    { key: 'title', label: 'Bezeichnung', filled: formData.title.trim() !== '' },
    {
      key: 'alloy',
      label: 'Legierung & Farbe',
      filled: formData.metal_type !== '' && formData.alloy !== '',
    },
    { key: 'deadline', label: 'Abgabetermin', filled: formData.deadline !== '' },
    ...(isRingOrder ? [{ key: 'ring_size_mm', label: 'Ringmaß', filled: formData.ring_size_mm !== '' }] : []),
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
      // DOM-09: not in the Zod schema (it would be stripped); an edit may
      // clear it, a new order simply omits it.
      order_type: formData.order_type || (order ? null : undefined),
    };
    delete submitData.costing_method;

    await onSubmit(submitData);
  };

  // No-Go conflict candidates (Task 9): every field on this form that
  // carries material/appearance identity a customer could have blocked.
  // The alloy choice and surface finish resolve to their human-readable
  // labels — raw codes ("white_gold_18k", "750") won't textually match a
  // no-go value like "Weißgold". description stays a catch-all for
  // allergies and materials noted in free text.
  const selectedAlloyLabel = selectedAlloyChoice?.label;
  const selectedSurfaceFinishLabel = SURFACE_FINISH_OPTIONS.find(
    (o) => o.value === formData.surface_finish
  )?.label;
  const noGoCandidates = [
    selectedAlloyLabel,
    selectedSurfaceFinishLabel,
    formData.description,
  ].filter((v): v is string => Boolean(v && v.trim()));

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

                <div className="form-group">
                  <label htmlFor="order_type">Schmuckart</label>
                  <select
                    id="order_type"
                    name="order_type"
                    value={formData.order_type}
                    onChange={handleChange}
                  >
                    <option value="">-- Schmuckart auswählen --</option>
                    {ORDER_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
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

                {/* Legierung & Farbe (DOM-06): one choice sets metal type and alloy */}
                <div className="form-group">
                  <label htmlFor="alloy_choice">
                    Legierung & Farbe <span className="required">*</span>
                  </label>
                  <select
                    id="alloy_choice"
                    name="alloy_choice"
                    value={alloyChoice}
                    onChange={handleAlloyChoiceChange}
                    className={hasAttemptedSubmit && (errors.metal_type || errors.alloy) ? 'error' : ''}
                  >
                    <option value="">-- Legierung & Farbe auswählen --</option>
                    {ALLOY_CHOICES.map((choice) => (
                      <option key={choice.key} value={choice.key}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                  {hasLegacyAlloyPair && (
                    <small className="form-hint">
                      Bisher gespeichert: {formData.metal_type || '—'} / {formData.alloy || '—'}. Bitte
                      Legierung & Farbe neu wählen.
                    </small>
                  )}
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

                {/* Ringmaß — only for order type "Ring" (DOM-05) */}
                {isRingOrder && (
                  <div className="form-group">
                    <label htmlFor="ring_size_mm">
                      Ringmaß (mm Innenumfang) <span className="required">*</span>
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
                    placeholder="Besondere Anforderungen des Kunden (Gravur, Lieferbedingungen, …)"
                  />
                </div>

                {/* Steine (DOM-04): stored per stone, so only on a saved order */}
                {order ? (
                  <GemstoneRepeater orderId={order.id} canEdit canViewCost />
                ) : (
                  <p className="form-hint">
                    Steine lassen sich nach dem Anlegen des Auftrags erfassen (Auftrag bearbeiten → Auftrag).
                  </p>
                )}

              </div>
            )}

            {/* Metal Tab */}
            {activeTab === 'metal' && (
              <div className="tab-content-form">
                <p className="form-hint">
                  {selectedAlloyChoice
                    ? `Legierung & Farbe: ${selectedAlloyChoice.label}`
                    : 'Bitte zuerst im Tab „Auftrag“ Legierung & Farbe wählen.'}
                </p>
                {hasAttemptedSubmit && errors.metal_type && (
                  <span className="error-message">{errors.metal_type}</span>
                )}

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

          {/* No-Go conflict warning (Task 9) — purely additive; renders
              nothing without a selected customer or without any
              material-identity field filled in. */}
          <NoGoWarning
            customerId={Number(formData.customer_id) || null}
            candidates={noGoCandidates}
          />

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
