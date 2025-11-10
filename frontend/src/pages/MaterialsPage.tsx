// Materials Page Component
import React, { useEffect, useState } from 'react';
import { materialsApi } from '../api';
import { MaterialType, MaterialCreateInput, MaterialUpdateInput } from '../types';
import { MaterialFormModal } from '../components/materials/MaterialFormModal';
import '../styles/pages.css';
import '../styles/materials.css';

export const MaterialsPage: React.FC = () => {
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

    // Low stock filter
    if (filterLowStock) {
      filtered = filtered.filter((m) => m.stock < 10);
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
      alert('Material erfolgreich erstellt!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Erstellen des Materials');
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
      alert('Material erfolgreich aktualisiert!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktualisieren des Materials');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeleteMaterial = async (materialId: number, materialName: string) => {
    const confirmed = window.confirm(
      `Möchten Sie das Material "${materialName}" wirklich löschen?`
    );

    if (!confirmed) return;

    try {
      await materialsApi.delete(materialId);
      await fetchMaterials();
      alert('Material erfolgreich gelöscht!');
    } catch (err: any) {
      alert(
        err.response?.data?.detail ||
          'Fehler beim Löschen des Materials. Es wird möglicherweise noch in Aufträgen verwendet.'
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
        <button className="btn-primary" onClick={openCreateModal}>
          + Neues Material
        </button>
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
                <th>ID</th>
                <th>Name</th>
                <th>Beschreibung</th>
                <th>Preis/Einheit</th>
                <th>Bestand</th>
                <th>Einheit</th>
                <th>Wert</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {filteredMaterials.map((material) => (
                <tr key={material.id}>
                  <td>#{material.id}</td>
                  <td>{material.name}</td>
                  <td>{material.description || '-'}</td>
                  <td>{material.unit_price.toFixed(2)} €</td>
                  <td className={material.stock < 10 ? 'low-stock' : ''}>
                    <div className="stock-indicator">
                      {material.stock}
                      {material.stock < 10 && (
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
              ))}
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
    </div>
  );
};
