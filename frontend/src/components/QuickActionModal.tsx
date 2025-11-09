import React, { useState } from 'react';
import { OrderType } from '../types';
import ActivityPicker from './ActivityPicker';
import LocationPicker from './LocationPicker';
import '../styles/components/QuickActionModal.css';

interface QuickActionModalProps {
  order: OrderType;
  onClose: () => void;
  onStartTimeTracking: (activityId: number, location?: string) => Promise<void>;
  onChangeLocation: (location: string) => Promise<void>;
  onViewMaterials: () => void;
}

type ModalView = 'actions' | 'activity-picker' | 'location-picker';

const QuickActionModal: React.FC<QuickActionModalProps> = ({
  order,
  onClose,
  onStartTimeTracking,
  onChangeLocation,
  onViewMaterials,
}) => {
  const [currentView, setCurrentView] = useState<ModalView>('actions');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null);

  const handleTimeTrackingClick = () => {
    setCurrentView('activity-picker');
    setError(null);
  };

  const handleActivitySelect = async (activityId: number) => {
    setSelectedActivityId(activityId);
    // Optionally, could show location picker here
    // For now, start tracking without location
    try {
      setLoading(true);
      setError(null);
      await onStartTimeTracking(activityId);
      onClose();
    } catch (err) {
      console.error('Failed to start time tracking:', err);
      setError('Zeiterfassung konnte nicht gestartet werden');
      setLoading(false);
    }
  };

  const handleLocationClick = () => {
    setCurrentView('location-picker');
    setError(null);
  };

  const handleLocationSelect = async (location: string) => {
    try {
      setLoading(true);
      setError(null);
      await onChangeLocation(location);
      onClose();
    } catch (err) {
      console.error('Failed to change location:', err);
      setError('Lagerort konnte nicht geändert werden');
      setLoading(false);
    }
  };

  const handleMaterialsClick = () => {
    onViewMaterials();
    onClose();
  };

  const handleBack = () => {
    setCurrentView('actions');
    setError(null);
    setSelectedActivityId(null);
  };

  return (
    <div className="quick-action-modal-overlay" onClick={onClose}>
      <div
        className="quick-action-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {currentView === 'actions' && (
          <>
            <div className="quick-action-header">
              <h2>Schnellaktionen</h2>
              <button onClick={onClose} className="modal-close-button">
                ✕
              </button>
            </div>

            <div className="quick-action-order-info">
              <div className="order-info-badge">Auftrag #{order.id}</div>
              <h3>{order.title}</h3>
              {order.description && (
                <p className="order-description">{order.description}</p>
              )}
            </div>

            <div className="quick-actions-grid">
              <button
                onClick={handleTimeTrackingClick}
                className="quick-action-button quick-action-timer"
                disabled={loading}
              >
                <div className="quick-action-icon">⏱️</div>
                <div className="quick-action-label">Zeit erfassen</div>
                <div className="quick-action-hint">Aktivität wählen und starten</div>
              </button>

              <button
                onClick={handleLocationClick}
                className="quick-action-button quick-action-location"
                disabled={loading}
              >
                <div className="quick-action-icon">📍</div>
                <div className="quick-action-label">Lagerort ändern</div>
                <div className="quick-action-hint">Neuen Standort wählen</div>
              </button>

              <button
                onClick={handleMaterialsClick}
                className="quick-action-button quick-action-materials"
                disabled={loading}
              >
                <div className="quick-action-icon">💎</div>
                <div className="quick-action-label">Material</div>
                <div className="quick-action-hint">Materialien ansehen</div>
              </button>
            </div>

            {error && <div className="quick-action-error">{error}</div>}
          </>
        )}

        {currentView === 'activity-picker' && (
          <div className="quick-action-nested-view">
            <div className="nested-view-header">
              <button onClick={handleBack} className="back-button">
                ← Zurück
              </button>
              <button onClick={onClose} className="modal-close-button">
                ✕
              </button>
            </div>
            <ActivityPicker
              onSelectActivity={(activity) => handleActivitySelect(activity.id)}
              onCancel={handleBack}
              showTopActivities={true}
            />
            {error && <div className="quick-action-error">{error}</div>}
          </div>
        )}

        {currentView === 'location-picker' && (
          <div className="quick-action-nested-view">
            <div className="nested-view-header">
              <button onClick={handleBack} className="back-button">
                ← Zurück
              </button>
              <button onClick={onClose} className="modal-close-button">
                ✕
              </button>
            </div>
            <LocationPicker
              currentLocation={null}
              onSelectLocation={handleLocationSelect}
              onCancel={handleBack}
            />
            {error && <div className="quick-action-error">{error}</div>}
          </div>
        )}
      </div>
    </div>
  );
};

export default QuickActionModal;
