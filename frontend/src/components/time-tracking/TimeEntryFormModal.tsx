// Time Entry Form Modal Component
import React, { useState, useEffect } from 'react';
import {
  TimeEntryType,
  TimeEntryCreateInput,
  TimeEntryUpdateInput,
  OrderType,
  ActivityType,
} from '../../types';
import { ordersApi, timeTrackingApi } from '../../api';
import '../../styles/time-tracking.css';

interface TimeEntryFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TimeEntryCreateInput | TimeEntryUpdateInput) => Promise<void>;
  entry?: TimeEntryType | null;
  isLoading?: boolean;
}

interface FormData {
  order_id: string;
  activity_id: string;
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  location: string;
  notes: string;
  complexity_rating: string;
  quality_rating: string;
  rework_required: boolean;
}

interface FormErrors {
  order_id?: string;
  activity_id?: string;
  start_time?: string;
  end_time?: string;
}

export const TimeEntryFormModal: React.FC<TimeEntryFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  entry,
  isLoading = false,
}) => {
  const isEditMode = Boolean(entry);

  const [orders, setOrders] = useState<OrderType[]>([]);
  const [activities, setActivities] = useState<ActivityType[]>([]);
  const [formData, setFormData] = useState<FormData>({
    order_id: '',
    activity_id: '',
    start_date: new Date().toISOString().split('T')[0],
    start_time: new Date().toTimeString().slice(0, 5),
    end_date: new Date().toISOString().split('T')[0],
    end_time: '',
    location: '',
    notes: '',
    complexity_rating: '',
    quality_rating: '',
    rework_required: false,
  });
  const [errors, setErrors] = useState<FormErrors>({});

  useEffect(() => {
    if (isOpen) {
      fetchOrders();
      fetchActivities();

      if (entry) {
        // Edit mode: populate form with entry data
        const startDate = new Date(entry.start_time);
        const endDate = entry.end_time ? new Date(entry.end_time) : new Date();

        setFormData({
          order_id: entry.order_id.toString(),
          activity_id: entry.activity_id.toString(),
          start_date: startDate.toISOString().split('T')[0],
          start_time: startDate.toTimeString().slice(0, 5),
          end_date: endDate.toISOString().split('T')[0],
          end_time: entry.end_time ? endDate.toTimeString().slice(0, 5) : '',
          location: entry.location || '',
          notes: entry.notes || '',
          complexity_rating: entry.complexity_rating?.toString() || '',
          quality_rating: entry.quality_rating?.toString() || '',
          rework_required: entry.rework_required || false,
        });
      } else {
        // Create mode: reset form
        resetForm();
      }
      setErrors({});
    }
  }, [isOpen, entry]);

  const fetchOrders = async () => {
    try {
      const data = await ordersApi.getAll({ limit: 1000 });
      const ordersList = Array.isArray(data) ? data : data.items || [];
      setOrders(ordersList);
    } catch (err: any) {
      console.error('Failed to fetch orders:', err);
    }
  };

  const fetchActivities = async () => {
    try {
      const data = await timeTrackingApi.getAllActivities();
      setActivities(data);
    } catch (err: any) {
      console.error('Failed to fetch activities:', err);
    }
  };

  const resetForm = () => {
    const now = new Date();
    setFormData({
      order_id: '',
      activity_id: '',
      start_date: now.toISOString().split('T')[0],
      start_time: now.toTimeString().slice(0, 5),
      end_date: now.toISOString().split('T')[0],
      end_time: '',
      location: '',
      notes: '',
      complexity_rating: '',
      quality_rating: '',
      rework_required: false,
    });
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));

    // Clear error for this field
    if (errors[name as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const combineDateTime = (date: string, time: string): string => {
    return `${date}T${time}:00`;
  };

  const calculateDuration = (): number | null => {
    if (!formData.end_time) return null;

    const startDateTime = combineDateTime(formData.start_date, formData.start_time);
    const endDateTime = combineDateTime(formData.end_date, formData.end_time);

    const start = new Date(startDateTime);
    const end = new Date(endDateTime);

    const diffMs = end.getTime() - start.getTime();
    return Math.floor(diffMs / 1000 / 60); // minutes
  };

  const formatDuration = (minutes: number | null): string => {
    if (minutes === null) return '-';
    const hrs = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hrs}h ${mins}m`;
  };

  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    if (!formData.order_id) {
      newErrors.order_id = 'Auftrag ist erforderlich';
    }

    if (!formData.activity_id) {
      newErrors.activity_id = 'Aktivität ist erforderlich';
    }

    if (!formData.start_time) {
      newErrors.start_time = 'Startzeit ist erforderlich';
    }

    if (formData.end_time) {
      const duration = calculateDuration();
      if (duration !== null && duration < 0) {
        newErrors.end_time = 'Endzeit muss nach Startzeit liegen';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const startDateTime = combineDateTime(formData.start_date, formData.start_time);
    const endDateTime = formData.end_time
      ? combineDateTime(formData.end_date, formData.end_time)
      : undefined;

    const submitData: TimeEntryCreateInput | TimeEntryUpdateInput = {
      order_id: parseInt(formData.order_id),
      activity_id: parseInt(formData.activity_id),
      start_time: startDateTime,
      end_time: endDateTime,
      duration_minutes: endDateTime ? calculateDuration() || undefined : undefined,
      location: formData.location || undefined,
      notes: formData.notes || undefined,
      complexity_rating: formData.complexity_rating
        ? parseInt(formData.complexity_rating)
        : undefined,
      quality_rating: formData.quality_rating ? parseInt(formData.quality_rating) : undefined,
      rework_required: formData.rework_required || undefined,
    };

    await onSubmit(submitData);
  };

  if (!isOpen) return null;

  const duration = calculateDuration();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content time-entry-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{isEditMode ? 'Zeiterfassung bearbeiten' : 'Manuelle Zeiterfassung'}</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-grid">
            {/* Order Selection */}
            <div className="form-group">
              <label htmlFor="order_id">
                Auftrag <span className="required">*</span>
              </label>
              <select
                id="order_id"
                name="order_id"
                value={formData.order_id}
                onChange={handleChange}
                required
                className={errors.order_id ? 'error' : ''}
              >
                <option value="">-- Auftrag wählen --</option>
                {orders.map((order) => (
                  <option key={order.id} value={order.id}>
                    #{order.id} - {order.title}
                  </option>
                ))}
              </select>
              {errors.order_id && <span className="error-text">{errors.order_id}</span>}
            </div>

            {/* Activity Selection */}
            <div className="form-group">
              <label htmlFor="activity_id">
                Aktivität <span className="required">*</span>
              </label>
              <select
                id="activity_id"
                name="activity_id"
                value={formData.activity_id}
                onChange={handleChange}
                required
                className={errors.activity_id ? 'error' : ''}
              >
                <option value="">-- Aktivität wählen --</option>
                {activities.map((activity) => (
                  <option key={activity.id} value={activity.id}>
                    {activity.icon && `${activity.icon} `}
                    {activity.name}
                  </option>
                ))}
              </select>
              {errors.activity_id && <span className="error-text">{errors.activity_id}</span>}
            </div>

            {/* Start Date */}
            <div className="form-group">
              <label htmlFor="start_date">
                Startdatum <span className="required">*</span>
              </label>
              <input
                type="date"
                id="start_date"
                name="start_date"
                value={formData.start_date}
                onChange={handleChange}
                required
              />
            </div>

            {/* Start Time */}
            <div className="form-group">
              <label htmlFor="start_time">
                Startzeit <span className="required">*</span>
              </label>
              <input
                type="time"
                id="start_time"
                name="start_time"
                value={formData.start_time}
                onChange={handleChange}
                required
                className={errors.start_time ? 'error' : ''}
              />
              {errors.start_time && <span className="error-text">{errors.start_time}</span>}
            </div>

            {/* End Date */}
            <div className="form-group">
              <label htmlFor="end_date">Enddatum</label>
              <input
                type="date"
                id="end_date"
                name="end_date"
                value={formData.end_date}
                onChange={handleChange}
              />
            </div>

            {/* End Time */}
            <div className="form-group">
              <label htmlFor="end_time">Endzeit</label>
              <input
                type="time"
                id="end_time"
                name="end_time"
                value={formData.end_time}
                onChange={handleChange}
                className={errors.end_time ? 'error' : ''}
              />
              {errors.end_time && <span className="error-text">{errors.end_time}</span>}
            </div>

            {/* Calculated Duration */}
            {formData.end_time && (
              <div className="form-group calculated-field">
                <label>Dauer</label>
                <div className="calculated-value">{formatDuration(duration)}</div>
              </div>
            )}

            {/* Location */}
            <div className="form-group">
              <label htmlFor="location">Standort</label>
              <input
                type="text"
                id="location"
                name="location"
                value={formData.location}
                onChange={handleChange}
                placeholder="z.B. Werkbank 1, Tresor"
              />
            </div>

            {/* Complexity Rating */}
            <div className="form-group">
              <label htmlFor="complexity_rating">Komplexität (1-5)</label>
              <select
                id="complexity_rating"
                name="complexity_rating"
                value={formData.complexity_rating}
                onChange={handleChange}
              >
                <option value="">-- Nicht bewertet --</option>
                <option value="1">1 - Sehr einfach</option>
                <option value="2">2 - Einfach</option>
                <option value="3">3 - Mittel</option>
                <option value="4">4 - Komplex</option>
                <option value="5">5 - Sehr komplex</option>
              </select>
            </div>

            {/* Quality Rating */}
            <div className="form-group">
              <label htmlFor="quality_rating">Qualität (1-5)</label>
              <select
                id="quality_rating"
                name="quality_rating"
                value={formData.quality_rating}
                onChange={handleChange}
              >
                <option value="">-- Nicht bewertet --</option>
                <option value="1">1 - Schlecht</option>
                <option value="2">2 - Unterdurchschnittlich</option>
                <option value="3">3 - Durchschnittlich</option>
                <option value="4">4 - Gut</option>
                <option value="5">5 - Exzellent</option>
              </select>
            </div>

            {/* Rework Required */}
            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  name="rework_required"
                  checked={formData.rework_required}
                  onChange={handleChange}
                />
                Nacharbeit erforderlich
              </label>
            </div>
          </div>

          {/* Notes */}
          <div className="form-group full-width">
            <label htmlFor="notes">Notizen</label>
            <textarea
              id="notes"
              name="notes"
              value={formData.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Detaillierte Notizen zur durchgeführten Arbeit..."
            />
          </div>

          {/* Form Actions */}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={isLoading}>
              Abbrechen
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading
                ? 'Wird gespeichert...'
                : isEditMode
                ? 'Speichern'
                : 'Zeiterfassung erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
