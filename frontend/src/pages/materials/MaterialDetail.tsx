/**
 * Material Detail Page - View and quickly adjust stock
 * Optimized for workshop use with quick stock adjustments
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getMaterial,
  deleteMaterial,
  adjustMaterialStock,
  type Material,
} from '../../lib/api/materials';
import './MaterialDetail.css';

const MATERIAL_TYPE_LABELS: Record<string, string> = {
  gold: '🥇 Gold',
  silver: '⚪ Silber',
  platinum: '💫 Platin',
  stone: '💎 Edelsteine',
  tool: '🔧 Werkzeuge',
  other: '📦 Sonstiges',
};

export default function MaterialDetail() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [material, setMaterial] = useState<Material | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stock adjustment
  const [adjusting, setAdjusting] = useState(false);
  const [adjustAmount, setAdjustAmount] = useState('');
  const [adjustOperation, setAdjustOperation] = useState<'add' | 'subtract'>('add');
  const [adjustNote, setAdjustNote] = useState('');

  useEffect(() => {
    if (id) {
      loadMaterial(parseInt(id));
    }
  }, [id]);

  const loadMaterial = async (materialId: number) => {
    try {
      setLoading(true);
      setError(null);
      const data = await getMaterial(materialId);
      setMaterial(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Materials');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!material) return;

    if (!confirm(`Möchten Sie "${material.name}" wirklich löschen?`)) {
      return;
    }

    try {
      await deleteMaterial(material.id);
      navigate('/materials');
    } catch (err: any) {
      alert(`Fehler beim Löschen: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    }
  };

  const handleQuickAdjust = async (amount: number) => {
    if (!material) return;

    try {
      setAdjusting(true);
      const operation = amount > 0 ? 'add' : 'subtract';
      const absAmount = Math.abs(amount);

      const updated = await adjustMaterialStock(material.id, absAmount, operation);
      setMaterial(updated);
    } catch (err: any) {
      alert(`Fehler: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    } finally {
      setAdjusting(false);
    }
  };

  const handleAdjustSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!material || !adjustAmount) return;

    const amount = parseFloat(adjustAmount);
    if (isNaN(amount) || amount <= 0) {
      alert('Bitte geben Sie eine gültige Menge ein');
      return;
    }

    try {
      setAdjusting(true);
      const updated = await adjustMaterialStock(material.id, amount, adjustOperation);
      setMaterial(updated);
      setAdjustAmount('');
      setAdjustNote('');
    } catch (err: any) {
      alert(`Fehler: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    } finally {
      setAdjusting(false);
    }
  };

  const getStockStatus = () => {
    if (!material) return { status: 'good', label: 'Gut', color: '#10b981' };

    if (material.stock <= 0) {
      return { status: 'empty', label: 'Leer', color: '#dc2626' };
    }
    if (material.stock <= material.min_stock) {
      return { status: 'low', label: 'Niedrig', color: '#f59e0b' };
    }
    if (material.stock <= material.min_stock * 1.5) {
      return { status: 'medium', label: 'Mittel', color: '#3b82f6' };
    }
    return { status: 'good', label: 'Gut', color: '#10b981' };
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(price);
  };

  const getStockValue = () => {
    if (!material) return 0;
    return material.stock * material.unit_price;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="material-detail-loading">
        <div className="spinner"></div>
        <p>Lade Material...</p>
      </div>
    );
  }

  if (error || !material) {
    return (
      <div className="material-detail-error">
        <h2>❌ Fehler</h2>
        <p>{error || 'Material nicht gefunden'}</p>
        <button onClick={() => navigate('/materials')} className="btn-back">
          Zurück zur Liste
        </button>
      </div>
    );
  }

  const stockStatus = getStockStatus();

  return (
    <div className="material-detail-container">
      {/* Header */}
      <div className="detail-header">
        <button onClick={() => navigate('/materials')} className="btn-back-small">
          ← Zurück
        </button>
        <div className="header-actions">
          <button
            onClick={() => navigate(`/materials/${material.id}/edit`)}
            className="btn-edit"
          >
            ✏️ Bearbeiten
          </button>
          <button onClick={handleDelete} className="btn-delete">
            🗑️ Löschen
          </button>
        </div>
      </div>

      {/* Material Info Card */}
      <div className="material-info-card">
        <div className="info-header">
          <h1>{material.name}</h1>
          <span
            className="stock-badge-large"
            style={{ backgroundColor: stockStatus.color }}
          >
            {stockStatus.label}
          </span>
        </div>

        <div className="info-grid">
          <div className="info-item">
            <span className="info-label">Typ</span>
            <span className="info-value">
              {MATERIAL_TYPE_LABELS[material.material_type] || material.material_type}
            </span>
          </div>

          <div className="info-item">
            <span className="info-label">Aktueller Bestand</span>
            <span className="info-value stock-highlight">
              <strong>{material.stock}</strong> {material.unit}
            </span>
          </div>

          <div className="info-item">
            <span className="info-label">Mindestbestand</span>
            <span className="info-value">
              {material.min_stock} {material.unit}
            </span>
          </div>

          <div className="info-item">
            <span className="info-label">Einheitspreis</span>
            <span className="info-value">{formatPrice(material.unit_price)}</span>
          </div>

          <div className="info-item highlight">
            <span className="info-label">Lagerwert</span>
            <span className="info-value stock-value-large">
              {formatPrice(getStockValue())}
            </span>
          </div>

          {material.description && (
            <div className="info-item full-width">
              <span className="info-label">Beschreibung</span>
              <span className="info-value">{material.description}</span>
            </div>
          )}
        </div>

        {/* Type-specific properties */}
        {material.properties && Object.keys(material.properties).length > 0 && (
          <div className="properties-section">
            <h3>Eigenschaften</h3>
            <div className="properties-grid">
              {Object.entries(material.properties).map(([key, value]) => (
                <div key={key} className="property-item">
                  <span className="property-key">{key}:</span>
                  <span className="property-value">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="info-footer">
          <small>Erstellt: {formatDate(material.created_at)}</small>
          <small>Aktualisiert: {formatDate(material.updated_at)}</small>
        </div>
      </div>

      {/* Quick Stock Adjustment */}
      <div className="stock-adjustment-card">
        <h2>Bestandsanpassung</h2>

        {/* Quick Buttons */}
        <div className="quick-adjust-section">
          <h3>Schnellanpassung</h3>
          <div className="quick-buttons">
            <button
              onClick={() => handleQuickAdjust(-10)}
              disabled={adjusting || material.stock < 10}
              className="btn-quick subtract"
            >
              -10
            </button>
            <button
              onClick={() => handleQuickAdjust(-5)}
              disabled={adjusting || material.stock < 5}
              className="btn-quick subtract"
            >
              -5
            </button>
            <button
              onClick={() => handleQuickAdjust(-1)}
              disabled={adjusting || material.stock < 1}
              className="btn-quick subtract"
            >
              -1
            </button>
            <div className="current-stock-display">
              <strong>{material.stock}</strong>
              <small>{material.unit}</small>
            </div>
            <button
              onClick={() => handleQuickAdjust(1)}
              disabled={adjusting}
              className="btn-quick add"
            >
              +1
            </button>
            <button
              onClick={() => handleQuickAdjust(5)}
              disabled={adjusting}
              className="btn-quick add"
            >
              +5
            </button>
            <button
              onClick={() => handleQuickAdjust(10)}
              disabled={adjusting}
              className="btn-quick add"
            >
              +10
            </button>
          </div>
        </div>

        {/* Custom Adjustment Form */}
        <form onSubmit={handleAdjustSubmit} className="custom-adjust-section">
          <h3>Individuelle Anpassung</h3>

          <div className="adjust-controls">
            <div className="adjust-type">
              <label>
                <input
                  type="radio"
                  value="add"
                  checked={adjustOperation === 'add'}
                  onChange={() => setAdjustOperation('add')}
                />
                <span>➕ Hinzufügen</span>
              </label>
              <label>
                <input
                  type="radio"
                  value="subtract"
                  checked={adjustOperation === 'subtract'}
                  onChange={() => setAdjustOperation('subtract')}
                />
                <span>➖ Entnehmen</span>
              </label>
            </div>

            <div className="adjust-input-group">
              <input
                type="number"
                step="0.01"
                value={adjustAmount}
                onChange={(e) => setAdjustAmount(e.target.value)}
                placeholder="Menge eingeben"
                className="adjust-input"
                required
              />
              <span className="adjust-unit">{material.unit}</span>
            </div>

            <input
              type="text"
              value={adjustNote}
              onChange={(e) => setAdjustNote(e.target.value)}
              placeholder="Notiz (optional)"
              className="adjust-note"
            />

            <button
              type="submit"
              disabled={adjusting || !adjustAmount}
              className="btn-adjust-submit"
            >
              {adjusting ? 'Wird angepasst...' : '✓ Bestand anpassen'}
            </button>
          </div>
        </form>
      </div>

      {/* Stock History (Placeholder) */}
      <div className="stock-history-card">
        <h2>Bestandsverlauf</h2>
        <div className="coming-soon">
          📊 Bestandsverlauf wird in einer zukünftigen Version verfügbar sein.
        </div>
      </div>
    </div>
  );
}
