// Materials Page Component
import React, { useEffect, useState } from 'react';
import { materialsApi } from '../api';
import { MaterialType, MaterialCreateInput, MaterialUpdateInput, PurchaseListItem } from '../types';
import { MaterialFormModal } from '../components/materials/MaterialFormModal';
import { useToast, useConfirm } from '../contexts';
import '../styles/pages.css';
import '../styles/materials.css';

// ── helpers ─────────────────────────────────────────────────────────────────

function isLowStock(material: MaterialType): boolean {
  return material.stock < (material.min_stock ?? 10);
}

// ── Purchase list modal ──────────────────────────────────────────────────────

interface PurchaseListModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PurchaseListModal: React.FC<PurchaseListModalProps> = ({ isOpen, onClose }) => {
  const [groups, setGroups] = useState<PurchaseListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    setError(null);
    materialsApi
      .getPurchaseList()
      .then(setGroups)
      .catch((err: any) => {
        setError(err.response?.data?.detail || 'Fehler beim Laden der Bestellliste');
      })
      .finally(() => setIsLoading(false));
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: 700, width: '95vw' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>Bestellliste</h2>
          <button className="modal-close" onClick={onClose} type="button">
            ×
          </button>
        </div>

        <div style={{ padding: '1rem 1.5rem 1.5rem' }}>
          {isLoading && <p>Lade Bestellliste...</p>}
          {error && <p style={{ color: 'var(--color-error, red)' }}>{error}</p>}
          {!isLoading && !error && groups.length === 0 && (
            <p style={{ color: '#666' }}>Alle Materialien haben ausreichend Bestand.</p>
          )}
          {!isLoading &&
            groups.map((group) => (
              <div key={group.supplier ?? '__none__'} style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ marginBottom: '0.5rem', borderBottom: '1px solid #e5e7eb', paddingBottom: '0.25rem' }}>
                  {group.supplier ?? 'Kein Lieferant'}
                </h3>
                <table className="data-table" style={{ width: '100%' }}>
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>Bestand</th>
                      <th>Mindestbestand</th>
                      <th>Einheit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.materials.map((m) => (
                      <tr key={m.id}>
                        <td>
                          {m.webshop_url ? (
                            <a href={m.webshop_url} target="_blank" rel="noopener noreferrer">
                              {m.name}
                            </a>
                          ) : (
                            m.name
                          )}
                        </td>
                        <td style={{ color: 'var(--color-error, #dc2626)' }}>{m.stock}</td>
                        <td>{m.min_stock ?? 10}</td>
                        <td>{m.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>
            Schliessen
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Main Page ────────────────────────────────────────────────────────────────

export const MaterialsPage: React.FC = () => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [materials, setMaterials] = useState<MaterialType[]>([]);
  const [filteredMaterials, setFilteredMaterials] = useState<MaterialType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedMaterial, setSelectedMaterial] = useState<MaterialType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterLowStock, setFilterLowStock] = useState(false);
  const [sortBy, setSortBy] = useState<'name' | 'price' | 'stock'>('name');
  const [isPurchaseListOpen, setIsPurchaseListOpen] = useState(false);

  useEffect(() => {
    fetchMaterials();
  }, []);

  useEffect(() => {
    filterAndSortMaterials();
  }, [materials, searchQuery, filterLowStock, sortBy]);

  const fetchMaterials = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await materialsApi.getAll();
      setMaterials(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Materialien');
    } finally {
      setIsLoading(false);
    }
  };

  const filterAndSortMaterials = () => {
    let filtered = [...materials];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (m) =>
          m.name.toLowerCase().includes(query) ||
          (m.description && m.description.toLowerCase().includes(query))
      );
    }

    // Low stock filter — per-material threshold
    if (filterLowStock) {
      filtered = filtered.filter(isLowStock);
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === 'name') {
        return a.name.localeCompare(b.name);
      } else if (sortBy === 'price') {
        return b.unit_price - a.unit_price;
      } else if (sortBy === 'stock') {
        return a.stock - b.stock;
      }
      return 0;
    });

    setFilteredMaterials(filtered);
  };

  const handleCreateMaterial = async (data: MaterialCreateInput) => {
    try {
      setIsFormLoading(true);
      await materialsApi.create(data);
      await fetchMaterials();
      setIsModalOpen(false);
      showToast('Material erfolgreich erstellt!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Erstellen des Materials', 'error');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleUpdateMaterial = async (data: MaterialUpdateInput) => {
    if (!selectedMaterial) return;

    try {
      setIsFormLoading(true);
      await materialsApi.update(selectedMaterial.id, data);
      await fetchMaterials();
      setIsModalOpen(false);
      setSelectedMaterial(null);
      showToast('Material erfolgreich aktualisiert!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Aktualisieren des Materials', 'error');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeleteMaterial = async (materialId: number, materialName: string) => {
    const confirmed = await showConfirm({
      title: 'Material loschen',
      message: `Mochten Sie das Material "${materialName}" wirklich loschen?`,
      confirmLabel: 'Loschen',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await materialsApi.delete(materialId);
      await fetchMaterials();
      showToast('Material erfolgreich geloscht!', 'success');
    } catch (err: any) {
      showToast(
        err.response?.data?.detail ||
          'Fehler beim Loschen des Materials. Es wird moglicherweise noch in Auftragen verwendet.',
        'error'
      );
    }
  };

  const openCreateModal = () => {
    setSelectedMaterial(null);
    setIsModalOpen(true);
  };

  const openEditModal = (material: MaterialType) => {
    setSelectedMaterial(material);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedMaterial(null);
  };

  const handleFormSubmit = async (data: MaterialCreateInput | MaterialUpdateInput) => {
    if (selectedMaterial) {
      await handleUpdateMaterial(data);
    } else {
      await handleCreateMaterial(data as MaterialCreateInput);
    }
  };

  if (isLoading) {
    return <div className="page-loading">Lade Materialien...</div>;
  }

  if (error) {
    return <div className="page-error">{error}</div>;
  }

  const totalValue = filteredMaterials.reduce(
    (sum, m) => sum + m.unit_price * m.stock,
    0
  );

  return (
    <div className="page-container">
      <header className="page-header">
        <div>
          <h1>Materialien</h1>
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {filteredMaterials.length} Materialien • Gesamtwert: {totalValue.toFixed(2)} €
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn-secondary" onClick={() => setIsPurchaseListOpen(true)}>
            Bestellliste
          </button>
          <button className="btn-primary" onClick={openCreateModal}>
            + Neues Material
          </button>
        </div>
      </header>

      {/* Search and Filters */}
      <div className="materials-controls">
        <div className="search-box">
          <input
            type="text"
            placeholder="Suche nach Name oder Beschreibung..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>Sortieren:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}>
            <option value="name">Name</option>
            <option value="price">Preis</option>
            <option value="stock">Bestand</option>
          </select>
        </div>

        <div className="filter-group">
          <label>
            <input
              type="checkbox"
              checked={filterLowStock}
              onChange={(e) => setFilterLowStock(e.target.checked)}
            />
            {' '}Nur niedriger Bestand
          </label>
        </div>
      </div>

      {filteredMaterials.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchQuery || filterLowStock
              ? 'Keine Materialien gefunden.'
              : 'Keine Materialien vorhanden.'}
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>Bild</th>
                <th>ID</th>
                <th>Name</th>
                <th>Lieferant</th>
                <th>Beschreibung</th>
                <th>Preis/Einheit</th>
                <th>Bestand</th>
                <th>Einheit</th>
                <th>Wert</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {filteredMaterials.map((material) => {
                const lowStock = isLowStock(material);
                return (
                  <tr key={material.id}>
                    {/* Thumbnail */}
                    <td>
                      {material.image_url ? (
                        <img
                          src={material.image_url}
                          alt={material.name}
                          style={{
                            width: 40,
                            height: 40,
                            objectFit: 'cover',
                            borderRadius: 4,
                            display: 'block',
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: 40,
                            height: 40,
                            borderRadius: 4,
                            background: '#f3f4f6',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '1.2rem',
                            color: '#9ca3af',
                          }}
                          title="Kein Bild"
                        >
                          &#128190;
                        </div>
                      )}
                    </td>
                    <td>#{material.id}</td>
                    <td>{material.name}</td>
                    {/* Lieferant with optional webshop link */}
                    <td>
                      {material.supplier ? (
                        material.webshop_url ? (
                          <a
                            href={material.webshop_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Im Webshop bestellen"
                            style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                          >
                            {material.supplier}
                            <span title="Bestellen" style={{ fontSize: '0.85rem' }}>&#128722;</span>
                          </a>
                        ) : (
                          material.supplier
                        )
                      ) : (
                        material.webshop_url ? (
                          <a
                            href={material.webshop_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Im Webshop bestellen"
                          >
                            <span title="Bestellen">&#128722;</span>
                          </a>
                        ) : (
                          '-'
                        )
                      )}
                    </td>
                    <td>{material.description || '-'}</td>
                    <td>{material.unit_price.toFixed(2)} €</td>
                    <td className={lowStock ? 'low-stock' : ''}>
                      <div className="stock-indicator">
                        {material.stock}
                        {lowStock && (
                          <span className="stock-badge low">Niedrig</span>
                        )}
                      </div>
                    </td>
                    <td>{material.unit}</td>
                    <td>{(material.unit_price * material.stock).toFixed(2)} €</td>
                    <td>
                      <div className="materials-page-actions">
                        <button
                          className="btn-icon btn-edit"
                          onClick={() => openEditModal(material)}
                          title="Bearbeiten"
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-icon btn-delete"
                          onClick={() => handleDeleteMaterial(material.id, material.name)}
                          title="Löschen"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Material Form Modal */}
      <MaterialFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        material={selectedMaterial}
        isLoading={isFormLoading}
      />

      {/* Purchase List Modal */}
      <PurchaseListModal
        isOpen={isPurchaseListOpen}
        onClose={() => setIsPurchaseListOpen(false)}
      />
    </div>
  );
};
