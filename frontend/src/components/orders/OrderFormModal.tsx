// Order Form Modal Component with Tabs
import React, { useState, useEffect } from 'react';
import { OrderType, OrderCreateInput, OrderUpdateInput, Customer, MetalType, CostingMethod } from '../../types';
import { customersApi } from '../../api';
import '../../styles/orders.css';

interface OrderFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: OrderCreateInput | OrderUpdateInput) => Promise<void>;
  order?: OrderType | null;
  isLoading?: boolean;
}

type TabType = 'basic' | 'metal' | 'pricing';

const METAL_TYPE_OPTIONS: { value: MetalType; label: string }[] = [
  { value: 'gold_24k', label: 'Gold 24K (999)' },
  { value: 'gold_18k', label: 'Gold 18K (750)' },
  { value: 'gold_14k', label: 'Gold 14K (585)' },
  { value: 'silver_925', label: 'Silber 925' },
  { value: 'silver_999', label: 'Silber 999' },
  { value: 'platinum', label: 'Platin' },
];

const COSTING_METHOD_OPTIONS: { value: CostingMethod; label: string }[] = [
  { value: 'FIFO', label: 'FIFO (First In, First Out)' },
  { value: 'LIFO', label: 'LIFO (Last In, First Out)' },
  { value: 'AVERAGE', label: 'Durchschnittspreis' },
  { value: 'SPECIFIC', label: 'Spezifische Charge' },
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
    costing_method_used: 'FIFO' as CostingMethod,
    specific_metal_purchase_id: '',

    // Pricing fields
    price: '',
    labor_hours: '',
    hourly_rate: '75',
    profit_margin_percent: '40',
    vat_rate: '19',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  // Fetch customers on mount
  useEffect(() => {
    if (isOpen) {
      fetchCustomers();
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
        costing_method_used: order.costing_method_used || 'FIFO',
        specific_metal_purchase_id: order.specific_metal_purchase_id?.toString() || '',

        price: order.price?.toString() || '',
        labor_hours: order.labor_hours?.toString() || '',
        hourly_rate: order.hourly_rate?.toString() || '75',
        profit_margin_percent: order.profit_margin_percent?.toString() || '40',
        vat_rate: order.vat_rate?.toString() || '19',
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
        costing_method_used: 'FIFO',
        specific_metal_purchase_id: '',
        price: '',
        labor_hours: '',
        hourly_rate: '75',
        profit_margin_percent: '40',
        vat_rate: '19',
      });
    }
    setErrors({});
    setActiveTab('basic');
  }, [order, isOpen]);

  const fetchCustomers = async () => {
    try {
      setIsLoadingCustomers(true);
      const data = await customersApi.getAll({ limit: 1000 });
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

    if (errors[name]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Basic tab validation
    if (!formData.title.trim()) {
      newErrors.title = 'Titel ist erforderlich';
    }

    if (!formData.description.trim()) {
      newErrors.description = 'Beschreibung ist erforderlich';
    }

    if (!formData.customer_id) {
      newErrors.customer_id = 'Kunde ist erforderlich';
    }

    // Metal tab validation
    if (formData.metal_type) {
      if (!formData.estimated_weight_g || parseFloat(formData.estimated_weight_g) <= 0) {
        newErrors.estimated_weight_g = 'Gewicht ist erforderlich wenn Metall ausgewählt ist';
      }

      if (
        formData.costing_method_used === 'SPECIFIC' &&
        !formData.specific_metal_purchase_id
      ) {
        newErrors.specific_metal_purchase_id =
          'Charge-ID ist erforderlich für spezifische Methode';
      }
    }

    // Pricing validation
    if (formData.price && parseFloat(formData.price) < 0) {
      newErrors.price = 'Preis kann nicht negativ sein';
    }

    if (formData.labor_hours && parseFloat(formData.labor_hours) < 0) {
      newErrors.labor_hours = 'Arbeitsstunden können nicht negativ sein';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    const submitData: any = {
      title: formData.title.trim(),
      description: formData.description.trim(),
      customer_id: parseInt(formData.customer_id),
      deadline: formData.deadline || undefined,
      status: formData.status,
      current_location: formData.current_location.trim() || undefined,

      // Metal fields (only if metal_type is selected)
      metal_type: formData.metal_type || undefined,
      estimated_weight_g: formData.metal_type && formData.estimated_weight_g
        ? parseFloat(formData.estimated_weight_g)
        : undefined,
      scrap_percentage: formData.metal_type && formData.scrap_percentage
        ? parseFloat(formData.scrap_percentage)
        : undefined,
      costing_method_used: formData.metal_type ? formData.costing_method_used : undefined,
      specific_metal_purchase_id:
        formData.metal_type &&
        formData.costing_method_used === 'SPECIFIC' &&
        formData.specific_metal_purchase_id
          ? parseInt(formData.specific_metal_purchase_id)
          : undefined,

      // Pricing fields
      price: formData.price ? parseFloat(formData.price) : undefined,
      labor_hours: formData.labor_hours ? parseFloat(formData.labor_hours) : undefined,
      hourly_rate: formData.hourly_rate ? parseFloat(formData.hourly_rate) : undefined,
      profit_margin_percent: formData.profit_margin_percent
        ? parseFloat(formData.profit_margin_percent)
        : undefined,
      vat_rate: formData.vat_rate ? parseFloat(formData.vat_rate) : undefined,
    };

    await onSubmit(submitData);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{order ? 'Auftrag bearbeiten' : 'Neuer Auftrag'}</h2>
          <button className="modal-close" onClick={onClose} type="button">
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
            📋 Basisinformationen
          </button>
          <button
            type="button"
            className={`form-tab ${activeTab === 'metal' ? 'active' : ''}`}
            onClick={() => setActiveTab('metal')}
          >
            🥇 Metall
          </button>
          <button
            type="button"
            className={`form-tab ${activeTab === 'pricing' ? 'active' : ''}`}
            onClick={() => setActiveTab('pricing')}
          >
            💰 Preisgestaltung
          </button>
        </div>

        <form onSubmit={handleSubmit} className="order-form">
          <div className="form-body">
            {/* Basic Info Tab */}
            {activeTab === 'basic' && (
              <div className="tab-content-form">
                <div className="form-group">
                  <label htmlFor="title">
                    Titel <span className="required">*</span>
                  </label>
                  <input
                    type="text"
                    id="title"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    className={errors.title ? 'error' : ''}
                    placeholder="z.B. Goldring mit Diamant"
                  />
                  {errors.title && <span className="error-message">{errors.title}</span>}
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
                    className={errors.description ? 'error' : ''}
                    rows={4}
                    placeholder="Detaillierte Beschreibung des Auftrags"
                  />
                  {errors.description && (
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
                    className={errors.customer_id ? 'error' : ''}
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
                  {errors.customer_id && (
                    <span className="error-message">{errors.customer_id}</span>
                  )}
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="deadline">Deadline</label>
                    <input
                      type="date"
                      id="deadline"
                      name="deadline"
                      value={formData.deadline}
                      onChange={handleChange}
                    />
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
                      <option value="in_progress">In Bearbeitung</option>
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

            {/* Metal Tab */}
            {activeTab === 'metal' && (
              <div className="tab-content-form">
                <div className="form-group">
                  <label htmlFor="metal_type">Metalltyp</label>
                  <select
                    id="metal_type"
                    name="metal_type"
                    value={formData.metal_type}
                    onChange={handleChange}
                  >
                    <option value="">-- Kein Metall --</option>
                    {METAL_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <small style={{ color: '#666' }}>
                    Optional: Wählen Sie einen Metalltyp, wenn dieser Auftrag Metall verwendet
                  </small>
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

                    {formData.costing_method_used === 'SPECIFIC' && (
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
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? 'Speichern...' : order ? 'Aktualisieren' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
