/**
 * Material Form - Create/Edit materials
 * Smart form with conditional fields based on material type
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getMaterial,
  createMaterial,
  updateMaterial,
  type MaterialCreate,
} from '../../lib/api/materials';
import './MaterialForm.css';

const MATERIAL_TYPES = [
  { value: 'gold', label: '🥇 Gold' },
  { value: 'silver', label: '⚪ Silber' },
  { value: 'platinum', label: '💫 Platin' },
  { value: 'stone', label: '💎 Edelsteine' },
  { value: 'tool', label: '🔧 Werkzeuge' },
  { value: 'other', label: '📦 Sonstiges' },
];

const GOLD_PURITIES = ['333', '585', '750', '900', '999'];
const STONE_COLORS = ['Weiß', 'Gelb', 'Rosa', 'Rot', 'Blau', 'Grün', 'Schwarz', 'Farblos'];
const STONE_SHAPES = ['Rund', 'Oval', 'Rechteckig', 'Quadratisch', 'Tropfen', 'Herz', 'Marquise'];
const STONE_QUALITIES = ['AAA', 'AA', 'A', 'B', 'C'];
const UNITS = [
  { value: 'g', label: 'Gramm (g)' },
  { value: 'kg', label: 'Kilogramm (kg)' },
  { value: 'ct', label: 'Karat (ct)' },
  { value: 'pcs', label: 'Stück (pcs)' },
];

export default function MaterialForm() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditMode = !!id;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Form fields
  const [name, setName] = useState('');
  const [materialType, setMaterialType] = useState('gold');
  const [description, setDescription] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [stock, setStock] = useState('');
  const [unit, setUnit] = useState('g');
  const [minStock, setMinStock] = useState('');

  // Type-specific properties
  const [goldPurity, setGoldPurity] = useState('585');
  const [stoneSize, setStoneSize] = useState('');
  const [stoneColor, setStoneColor] = useState('');
  const [stoneShape, setStoneShape] = useState('');
  const [stoneQuality, setStoneQuality] = useState('');
  const [toolCondition, setToolCondition] = useState('');
  const [toolLocation, setToolLocation] = useState('');

  useEffect(() => {
    if (isEditMode && id) {
      loadMaterial(parseInt(id));
    }
  }, [id, isEditMode]);

  const loadMaterial = async (materialId: number) => {
    try {
      setLoading(true);
      const material = await getMaterial(materialId);

      setName(material.name);
      setMaterialType(material.material_type);
      setDescription(material.description || '');
      setUnitPrice(material.unit_price.toString());
      setStock(material.stock.toString());
      setUnit(material.unit);
      setMinStock(material.min_stock.toString());

      // Load type-specific properties
      if (material.properties) {
        if (material.material_type === 'gold' && material.properties.purity) {
          setGoldPurity(material.properties.purity.toString());
        }
        if (material.material_type === 'stone') {
          setStoneSize(material.properties.size || '');
          setStoneColor(material.properties.color || '');
          setStoneShape(material.properties.shape || '');
          setStoneQuality(material.properties.quality || '');
        }
        if (material.material_type === 'tool') {
          setToolCondition(material.properties.condition || '');
          setToolLocation(material.properties.location || '');
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Materials');
    } finally {
      setLoading(false);
    }
  };

  const buildProperties = () => {
    const properties: Record<string, any> = {};

    switch (materialType) {
      case 'gold':
        if (goldPurity) properties.purity = parseInt(goldPurity);
        break;
      case 'stone':
        if (stoneSize) properties.size = parseFloat(stoneSize);
        if (stoneColor) properties.color = stoneColor;
        if (stoneShape) properties.shape = stoneShape;
        if (stoneQuality) properties.quality = stoneQuality;
        break;
      case 'tool':
        if (toolCondition) properties.condition = toolCondition;
        if (toolLocation) properties.location = toolLocation;
        break;
    }

    return Object.keys(properties).length > 0 ? properties : undefined;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!name.trim()) {
      setError('Bitte geben Sie einen Namen ein');
      return;
    }

    if (!unitPrice || parseFloat(unitPrice) < 0) {
      setError('Bitte geben Sie einen gültigen Preis ein');
      return;
    }

    if (!stock || parseFloat(stock) < 0) {
      setError('Bitte geben Sie einen gültigen Bestand ein');
      return;
    }

    if (!minStock || parseFloat(minStock) < 0) {
      setError('Bitte geben Sie einen gültigen Mindestbestand ein');
      return;
    }

    try {
      setSaving(true);

      const materialData: MaterialCreate = {
        name: name.trim(),
        material_type: materialType,
        description: description.trim() || undefined,
        unit_price: parseFloat(unitPrice),
        stock: parseFloat(stock),
        unit,
        min_stock: parseFloat(minStock),
        properties: buildProperties(),
      };

      if (isEditMode && id) {
        await updateMaterial(parseInt(id), materialData);
      } else {
        await createMaterial(materialData);
      }

      navigate('/materials');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Speichern des Materials');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    navigate('/materials');
  };

  // Set default unit based on material type
  useEffect(() => {
    switch (materialType) {
      case 'gold':
      case 'silver':
      case 'platinum':
        setUnit('g');
        break;
      case 'stone':
        setUnit('ct');
        break;
      case 'tool':
      case 'other':
        setUnit('pcs');
        break;
    }
  }, [materialType]);

  if (loading) {
    return (
      <div className="material-form-loading">
        <div className="spinner"></div>
        <p>Lade Material...</p>
      </div>
    );
  }

  return (
    <div className="material-form-container">
      <div className="material-form-header">
        <h1>{isEditMode ? 'Material bearbeiten' : 'Neues Material hinzufügen'}</h1>
      </div>

      <form onSubmit={handleSubmit} className="material-form">
        {error && (
          <div className="form-error">
            ❌ {error}
          </div>
        )}

        {/* Basic Information */}
        <div className="form-section">
          <h2>Grundinformationen</h2>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="name">
                Name <span className="required">*</span>
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Gold 585 Barren"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="materialType">
                Material-Typ <span className="required">*</span>
              </label>
              <select
                id="materialType"
                value={materialType}
                onChange={(e) => setMaterialType(e.target.value)}
                required
              >
                {MATERIAL_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="description">Beschreibung</label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional: Zusätzliche Informationen"
              rows={3}
            />
          </div>
        </div>

        {/* Type-specific fields */}
        {materialType === 'gold' && (
          <div className="form-section">
            <h2>🥇 Gold-spezifische Eigenschaften</h2>
            <div className="form-group">
              <label htmlFor="goldPurity">Feinheit</label>
              <select
                id="goldPurity"
                value={goldPurity}
                onChange={(e) => setGoldPurity(e.target.value)}
              >
                {GOLD_PURITIES.map((purity) => (
                  <option key={purity} value={purity}>
                    {purity} ({(parseInt(purity) / 1000 * 24).toFixed(1)}K)
                  </option>
                ))}
              </select>
              <small className="field-hint">
                Gebräuchliche Goldlegierungen
              </small>
            </div>
          </div>
        )}

        {materialType === 'stone' && (
          <div className="form-section">
            <h2>💎 Edelstein-Eigenschaften</h2>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="stoneSize">Größe (mm)</label>
                <input
                  id="stoneSize"
                  type="number"
                  step="0.01"
                  value={stoneSize}
                  onChange={(e) => setStoneSize(e.target.value)}
                  placeholder="z.B. 5.5"
                />
              </div>

              <div className="form-group">
                <label htmlFor="stoneColor">Farbe</label>
                <select
                  id="stoneColor"
                  value={stoneColor}
                  onChange={(e) => setStoneColor(e.target.value)}
                >
                  <option value="">Farbe wählen...</option>
                  {STONE_COLORS.map((color) => (
                    <option key={color} value={color}>
                      {color}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="stoneShape">Form</label>
                <select
                  id="stoneShape"
                  value={stoneShape}
                  onChange={(e) => setStoneShape(e.target.value)}
                >
                  <option value="">Form wählen...</option>
                  {STONE_SHAPES.map((shape) => (
                    <option key={shape} value={shape}>
                      {shape}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="stoneQuality">Qualität</label>
                <select
                  id="stoneQuality"
                  value={stoneQuality}
                  onChange={(e) => setStoneQuality(e.target.value)}
                >
                  <option value="">Qualität wählen...</option>
                  {STONE_QUALITIES.map((quality) => (
                    <option key={quality} value={quality}>
                      {quality}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {materialType === 'tool' && (
          <div className="form-section">
            <h2>🔧 Werkzeug-Eigenschaften</h2>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="toolCondition">Zustand</label>
                <input
                  id="toolCondition"
                  type="text"
                  value={toolCondition}
                  onChange={(e) => setToolCondition(e.target.value)}
                  placeholder="z.B. Neu, Gut, Abgenutzt"
                />
              </div>

              <div className="form-group">
                <label htmlFor="toolLocation">Lagerort</label>
                <input
                  id="toolLocation"
                  type="text"
                  value={toolLocation}
                  onChange={(e) => setToolLocation(e.target.value)}
                  placeholder="z.B. Werkbank 3, Schublade A"
                />
              </div>
            </div>
          </div>
        )}

        {/* Pricing and Stock */}
        <div className="form-section">
          <h2>Preis und Bestand</h2>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="unitPrice">
                Einheitspreis (€) <span className="required">*</span>
              </label>
              <input
                id="unitPrice"
                type="number"
                step="0.01"
                value={unitPrice}
                onChange={(e) => setUnitPrice(e.target.value)}
                placeholder="0.00"
                required
              />
              <small className="field-hint">
                Preis pro Einheit
              </small>
            </div>

            <div className="form-group">
              <label htmlFor="unit">
                Einheit <span className="required">*</span>
              </label>
              <select
                id="unit"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                required
              >
                {UNITS.map((u) => (
                  <option key={u.value} value={u.value}>
                    {u.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="stock">
                Aktueller Bestand <span className="required">*</span>
              </label>
              <input
                id="stock"
                type="number"
                step="0.01"
                value={stock}
                onChange={(e) => setStock(e.target.value)}
                placeholder="0"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="minStock">
                Mindestbestand <span className="required">*</span>
              </label>
              <input
                id="minStock"
                type="number"
                step="0.01"
                value={minStock}
                onChange={(e) => setMinStock(e.target.value)}
                placeholder="0"
                required
              />
              <small className="field-hint">
                Warnung bei Unterschreitung
              </small>
            </div>
          </div>

          {/* Stock value preview */}
          {unitPrice && stock && (
            <div className="stock-value-preview">
              <strong>Lagerwert:</strong>{' '}
              <span className="value-amount">
                {new Intl.NumberFormat('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                }).format(parseFloat(unitPrice) * parseFloat(stock))}
              </span>
            </div>
          )}
        </div>

        {/* Form Actions */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-cancel"
            onClick={handleCancel}
            disabled={saving}
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="btn-submit"
            disabled={saving}
          >
            {saving ? (
              <>
                <span className="btn-spinner"></span>
                Speichert...
              </>
            ) : (
              <>💾 {isEditMode ? 'Änderungen speichern' : 'Material hinzufügen'}</>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
