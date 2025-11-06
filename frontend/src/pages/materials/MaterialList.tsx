/**
 * Material List Page - Main material management interface
 * Designed for quick access and visual stock management
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMaterials, deleteMaterial, type Material } from '../../lib/api/materials';
import './MaterialList.css';

const MATERIAL_TYPES = [
  { value: '', label: 'Alle Materialien' },
  { value: 'gold', label: '🥇 Gold' },
  { value: 'silver', label: '⚪ Silber' },
  { value: 'platinum', label: '💫 Platin' },
  { value: 'stone', label: '💎 Edelsteine' },
  { value: 'tool', label: '🔧 Werkzeuge' },
  { value: 'other', label: '📦 Sonstiges' },
];

export default function MaterialList() {
  const navigate = useNavigate();
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [materialTypeFilter, setMaterialTypeFilter] = useState('');
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const limit = 20;

  useEffect(() => {
    loadMaterials();
  }, [page, materialTypeFilter, showLowStockOnly]);

  const loadMaterials = async () => {
    try {
      setLoading(true);
      setError(null);

      const params: Record<string, any> = {
        skip: (page - 1) * limit,
        limit,
      };

      if (materialTypeFilter) {
        params.material_type = materialTypeFilter;
      }

      if (showLowStockOnly) {
        params.low_stock_only = true;
      }

      const response = await getMaterials(params);
      setMaterials(response.items);
      setTotalPages(Math.ceil(response.total / limit));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Materialien');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Reset to page 1 when searching
    setPage(1);
    loadMaterials();
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Möchten Sie "${name}" wirklich löschen?`)) {
      return;
    }

    try {
      await deleteMaterial(id);
      loadMaterials(); // Reload list
    } catch (err: any) {
      alert(`Fehler beim Löschen: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    }
  };

  const getStockStatus = (material: Material) => {
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

  const getStockValue = (material: Material) => {
    return material.stock * material.unit_price;
  };

  const getTotalStockValue = () => {
    return materials.reduce((sum, m) => sum + getStockValue(m), 0);
  };

  const filteredMaterials = materials.filter(material => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      material.name.toLowerCase().includes(query) ||
      material.description?.toLowerCase().includes(query) ||
      material.material_type.toLowerCase().includes(query)
    );
  });

  // Extract gold purity from properties
  const getGoldPurity = (material: Material) => {
    if (material.material_type === 'gold' && material.properties?.purity) {
      return `${material.properties.purity}`;
    }
    return null;
  };

  // Extract stone properties
  const getStoneInfo = (material: Material) => {
    if (material.material_type === 'stone' && material.properties) {
      const parts = [];
      if (material.properties.size) parts.push(`${material.properties.size}mm`);
      if (material.properties.color) parts.push(material.properties.color);
      if (material.properties.shape) parts.push(material.properties.shape);
      return parts.length > 0 ? parts.join(', ') : null;
    }
    return null;
  };

  return (
    <div className="material-list-container">
      <div className="material-list-header">
        <div className="header-top">
          <h1>Material-Verwaltung</h1>
          <button
            className="btn-add-material"
            onClick={() => navigate('/materials/new')}
          >
            ➕ Material hinzufügen
          </button>
        </div>

        {/* Stock Value Summary */}
        <div className="stock-value-summary">
          <span className="stock-value-label">Gesamtwert Lager:</span>
          <span className="stock-value-amount">{formatPrice(getTotalStockValue())}</span>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="filters-section">
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            placeholder="🔍 Material suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </form>

        <div className="filter-controls">
          <select
            value={materialTypeFilter}
            onChange={(e) => {
              setMaterialTypeFilter(e.target.value);
              setPage(1);
            }}
            className="filter-select"
          >
            {MATERIAL_TYPES.map(type => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>

          <label className="filter-checkbox">
            <input
              type="checkbox"
              checked={showLowStockOnly}
              onChange={(e) => {
                setShowLowStockOnly(e.target.checked);
                setPage(1);
              }}
            />
            <span>⚠️ Nur niedriger Bestand</span>
          </label>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-banner">
          ❌ {error}
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Lade Materialien...</p>
        </div>
      ) : (
        <>
          {/* Materials Table */}
          <div className="materials-table-wrapper">
            <table className="materials-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Name</th>
                  <th>Typ</th>
                  <th>Details</th>
                  <th>Bestand</th>
                  <th>Einheitspreis</th>
                  <th>Lagerwert</th>
                  <th className="actions-col">Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {filteredMaterials.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="no-results">
                      {searchQuery
                        ? `Keine Materialien gefunden für "${searchQuery}"`
                        : 'Keine Materialien vorhanden. Fügen Sie das erste Material hinzu!'
                      }
                    </td>
                  </tr>
                ) : (
                  filteredMaterials.map((material) => {
                    const stockStatus = getStockStatus(material);
                    const goldPurity = getGoldPurity(material);
                    const stoneInfo = getStoneInfo(material);

                    return (
                      <tr key={material.id} className={`material-row status-${stockStatus.status}`}>
                        <td>
                          <span
                            className="stock-badge"
                            style={{ backgroundColor: stockStatus.color }}
                            title={`Min. Bestand: ${material.min_stock} ${material.unit}`}
                          >
                            {stockStatus.label}
                          </span>
                        </td>
                        <td className="material-name">
                          <strong>{material.name}</strong>
                          {material.description && (
                            <div className="material-description">{material.description}</div>
                          )}
                        </td>
                        <td>
                          <span className="material-type-badge">
                            {MATERIAL_TYPES.find(t => t.value === material.material_type)?.label || material.material_type}
                          </span>
                        </td>
                        <td className="material-details">
                          {goldPurity && <span className="detail-chip">🥇 {goldPurity}</span>}
                          {stoneInfo && <span className="detail-chip">💎 {stoneInfo}</span>}
                        </td>
                        <td className="stock-cell">
                          <strong>{material.stock}</strong> {material.unit}
                          {material.stock <= material.min_stock && (
                            <div className="stock-warning">
                              ⚠️ Min: {material.min_stock} {material.unit}
                            </div>
                          )}
                        </td>
                        <td>{formatPrice(material.unit_price)}</td>
                        <td className="stock-value">
                          <strong>{formatPrice(getStockValue(material))}</strong>
                        </td>
                        <td className="actions-cell">
                          <div className="action-buttons">
                            <button
                              className="btn-action btn-view"
                              onClick={() => navigate(`/materials/${material.id}`)}
                              title="Details anzeigen"
                            >
                              👁️
                            </button>
                            <button
                              className="btn-action btn-edit"
                              onClick={() => navigate(`/materials/${material.id}/edit`)}
                              title="Bearbeiten"
                            >
                              ✏️
                            </button>
                            <button
                              className="btn-action btn-stock"
                              onClick={() => navigate(`/materials/${material.id}/adjust`)}
                              title="Bestand anpassen"
                            >
                              📊
                            </button>
                            <button
                              className="btn-action btn-delete"
                              onClick={() => handleDelete(material.id, material.name)}
                              title="Löschen"
                            >
                              🗑️
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn-page"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                ← Zurück
              </button>
              <span className="page-info">
                Seite {page} von {totalPages}
              </span>
              <button
                className="btn-page"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Weiter →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
