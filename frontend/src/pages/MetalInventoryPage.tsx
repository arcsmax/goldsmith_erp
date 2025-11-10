// Metal Inventory Page Component
import React, { useEffect, useState } from 'react';
import { metalInventoryApi } from '../api';
import { MetalPurchaseType, MetalPurchaseCreateInput, MetalPurchaseUpdateInput, MetalType } from '../types';
import { MetalSummaryCards } from '../components/metal/MetalSummaryCards';
import { MetalPurchaseFormModal } from '../components/metal/MetalPurchaseFormModal';
import '../styles/pages.css';
import '../styles/metal-inventory.css';

interface MetalConfig {
  label: string;
  icon: string;
}

const METAL_TYPE_CONFIG: Record<MetalType, MetalConfig> = {
  gold_24k: { label: 'Gold 24K (999.9)', icon: '🥇' },
  gold_22k: { label: 'Gold 22K (916)', icon: '🥇' },
  gold_18k: { label: 'Gold 18K (750)', icon: '🥇' },
  gold_14k: { label: 'Gold 14K (585)', icon: '🥇' },
  gold_9k: { label: 'Gold 9K (375)', icon: '🥇' },
  silver_999: { label: 'Silber 999', icon: '⚪' },
  silver_925: { label: 'Silber 925', icon: '⚪' },
  silver_800: { label: 'Silber 800', icon: '⚪' },
  platinum_950: { label: 'Platin 950', icon: '💎' },
  platinum_900: { label: 'Platin 900', icon: '💎' },
  palladium: { label: 'Palladium', icon: '💎' },
  white_gold_18k: { label: 'Weißgold 18K', icon: '🤍' },
  white_gold_14k: { label: 'Weißgold 14K', icon: '🤍' },
  rose_gold_18k: { label: 'Rotgold 18K', icon: '🌹' },
  rose_gold_14k: { label: 'Rotgold 14K', icon: '🌹' },
};

export const MetalInventoryPage: React.FC = () => {
  const [purchases, setPurchases] = useState<MetalPurchaseType[]>([]);
  const [filteredPurchases, setFilteredPurchases] = useState<MetalPurchaseType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedPurchase, setSelectedPurchase] = useState<MetalPurchaseType | null>(null);

  // Filters & Sort
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMetalType, setFilterMetalType] = useState<MetalType | ''>('');
  const [filterDepleted, setFilterDepleted] = useState<'all' | 'active' | 'depleted'>('active');
  const [sortBy, setSortBy] = useState<'date' | 'metal_type' | 'value' | 'remaining'>('date');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    fetchPurchases();
  }, []);

  useEffect(() => {
    filterAndSortPurchases();
  }, [purchases, searchQuery, filterMetalType, filterDepleted, sortBy]);

  const fetchPurchases = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await metalInventoryApi.getAll();
      setPurchases(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Metalleinkäufe');
    } finally {
      setIsLoading(false);
    }
  };

  const filterAndSortPurchases = () => {
    let filtered = [...purchases];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (p) =>
          (p.supplier && p.supplier.toLowerCase().includes(query)) ||
          (p.invoice_number && p.invoice_number.toLowerCase().includes(query)) ||
          (p.lot_number && p.lot_number.toLowerCase().includes(query)) ||
          p.id.toString().includes(query)
      );
    }

    // Metal type filter
    if (filterMetalType) {
      filtered = filtered.filter((p) => p.metal_type === filterMetalType);
    }

    // Depleted filter
    if (filterDepleted === 'active') {
      filtered = filtered.filter((p) => p.remaining_weight_g > 0.01);
    } else if (filterDepleted === 'depleted') {
      filtered = filtered.filter((p) => p.remaining_weight_g <= 0.01);
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === 'date') {
        return new Date(b.date_purchased).getTime() - new Date(a.date_purchased).getTime();
      } else if (sortBy === 'metal_type') {
        return a.metal_type.localeCompare(b.metal_type);
      } else if (sortBy === 'value') {
        const aValue = a.remaining_weight_g * a.price_per_gram;
        const bValue = b.remaining_weight_g * b.price_per_gram;
        return bValue - aValue;
      } else if (sortBy === 'remaining') {
        return b.remaining_weight_g - a.remaining_weight_g;
      }
      return 0;
    });

    setFilteredPurchases(filtered);
  };

  const handleCreatePurchase = async (data: MetalPurchaseCreateInput) => {
    try {
      setIsFormLoading(true);
      await metalInventoryApi.create(data);
      await fetchPurchases();
      setIsModalOpen(false);
      alert('Metalleinkauf erfolgreich erstellt!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Erstellen des Metalleinkaufs');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleUpdatePurchase = async (data: MetalPurchaseUpdateInput) => {
    if (!selectedPurchase) return;

    try {
      setIsFormLoading(true);
      await metalInventoryApi.update(selectedPurchase.id, data);
      await fetchPurchases();
      setIsModalOpen(false);
      setSelectedPurchase(null);
      alert('Metalleinkauf erfolgreich aktualisiert!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktualisieren des Metalleinkaufs');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeletePurchase = async (purchaseId: number, metalType: string) => {
    const confirmed = window.confirm(
      `Möchten Sie diesen Metalleinkauf (${metalType}) wirklich löschen?`
    );

    if (!confirmed) return;

    try {
      await metalInventoryApi.delete(purchaseId);
      await fetchPurchases();
      alert('Metalleinkauf erfolgreich gelöscht!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Löschen des Metalleinkaufs');
    }
  };

  const openCreateModal = () => {
    setSelectedPurchase(null);
    setIsModalOpen(true);
  };

  const openEditModal = (purchase: MetalPurchaseType, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedPurchase(purchase);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedPurchase(null);
  };

  const handleFormSubmit = async (data: MetalPurchaseCreateInput | MetalPurchaseUpdateInput) => {
    if (selectedPurchase) {
      await handleUpdatePurchase(data);
    } else {
      await handleCreatePurchase(data as MetalPurchaseCreateInput);
    }
  };

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  const formatWeight = (grams: number): string => {
    if (grams >= 1000) {
      return `${(grams / 1000).toFixed(2)} kg`;
    }
    return `${grams.toFixed(2)} g`;
  };

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('de-DE');
  };

  const calculateUsagePercentage = (total: number, remaining: number): number => {
    if (total === 0) return 0;
    return ((total - remaining) / total) * 100;
  };

  if (isLoading) {
    return <div className="page-loading">Lade Metallinventar...</div>;
  }

  if (error) {
    return <div className="page-error">{error}</div>;
  }

  // Pagination
  const totalPages = Math.ceil(filteredPurchases.length / pageSize);
  const paginatedPurchases = filteredPurchases.slice(
    page * pageSize,
    (page + 1) * pageSize
  );

  const totalValue = filteredPurchases.reduce(
    (sum, p) => sum + p.remaining_weight_g * p.price_per_gram,
    0
  );

  return (
    <div className="page-container">
      {/* Summary Cards */}
      <MetalSummaryCards />

      {/* Page Header */}
      <header className="page-header">
        <div>
          <h1>Metalleinkäufe</h1>
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {filteredPurchases.length} Einkäufe • Wert: {formatCurrency(totalValue)}
          </p>
        </div>
        <button className="btn-primary" onClick={openCreateModal}>
          + Neuer Einkauf
        </button>
      </header>

      {/* Search and Filters */}
      <div className="metal-inventory-controls">
        <div className="search-box">
          <input
            type="text"
            placeholder="Suche nach Lieferant, Rechnung, Charge oder ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>Metalltyp:</label>
          <select
            value={filterMetalType}
            onChange={(e) => setFilterMetalType(e.target.value as MetalType | '')}
          >
            <option value="">Alle</option>
            {Object.entries(METAL_TYPE_CONFIG).map(([value, config]) => (
              <option key={value} value={value}>
                {config.icon} {config.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Status:</label>
          <select
            value={filterDepleted}
            onChange={(e) => setFilterDepleted(e.target.value as 'all' | 'active' | 'depleted')}
          >
            <option value="all">Alle</option>
            <option value="active">Aktiv (Bestand vorhanden)</option>
            <option value="depleted">Aufgebraucht</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Sortieren:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}>
            <option value="date">Kaufdatum</option>
            <option value="metal_type">Metalltyp</option>
            <option value="value">Wert</option>
            <option value="remaining">Verbleibend</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Pro Seite:</label>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(0);
            }}
          >
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      {filteredPurchases.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchQuery || filterMetalType || filterDepleted !== 'all'
              ? 'Keine Metalleinkäufe gefunden.'
              : 'Keine Metalleinkäufe vorhanden.'}
          </p>
        </div>
      ) : (
        <>
          <div className="table-container">
            <table className="metal-inventory-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Datum</th>
                  <th>Metalltyp</th>
                  <th>Gewicht</th>
                  <th>Verbleibend</th>
                  <th>Preis/g</th>
                  <th>Wert</th>
                  <th>Verbrauch</th>
                  <th>Lieferant</th>
                  <th>Charge</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {paginatedPurchases.map((purchase) => {
                  const config = METAL_TYPE_CONFIG[purchase.metal_type];
                  const usagePercentage = calculateUsagePercentage(
                    purchase.weight_g,
                    purchase.remaining_weight_g
                  );
                  const remainingValue = purchase.remaining_weight_g * purchase.price_per_gram;
                  const isDepleted = purchase.remaining_weight_g <= 0.01;

                  return (
                    <tr key={purchase.id} className={isDepleted ? 'depleted' : ''}>
                      <td>#{purchase.id}</td>
                      <td>{formatDate(purchase.date_purchased)}</td>
                      <td>
                        <span className="metal-type-badge">
                          {config.icon} {config.label}
                        </span>
                      </td>
                      <td>{formatWeight(purchase.weight_g)}</td>
                      <td>
                        <span className={isDepleted ? 'text-muted' : 'text-primary'}>
                          {formatWeight(purchase.remaining_weight_g)}
                        </span>
                      </td>
                      <td>{formatCurrency(purchase.price_per_gram)}</td>
                      <td>
                        <span className="price-display">
                          {formatCurrency(remainingValue)}
                        </span>
                      </td>
                      <td>
                        <div className="usage-indicator">
                          <div className="usage-bar-small">
                            <div
                              className="usage-bar-fill-small"
                              style={{ width: `${usagePercentage}%` }}
                            />
                          </div>
                          <span className="usage-text">{usagePercentage.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td>{purchase.supplier || '-'}</td>
                      <td>
                        <span className="lot-number">{purchase.lot_number || '-'}</span>
                      </td>
                      <td>
                        <div className="metal-page-actions">
                          <button
                            className="btn-icon btn-edit"
                            onClick={(e) => openEditModal(purchase, e)}
                            title="Bearbeiten"
                          >
                            ✏️
                          </button>
                          <button
                            className="btn-icon btn-delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeletePurchase(purchase.id, config.label);
                            }}
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

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <div className="pagination-info">
                Seite {page + 1} von {totalPages} • {filteredPurchases.length} Einkäufe
              </div>
              <div className="pagination-buttons">
                <button onClick={() => setPage(0)} disabled={page === 0}>
                  ‹‹ Erste
                </button>
                <button onClick={() => setPage(page - 1)} disabled={page === 0}>
                  ‹ Zurück
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages - 1}
                >
                  Weiter ›
                </button>
                <button
                  onClick={() => setPage(totalPages - 1)}
                  disabled={page >= totalPages - 1}
                >
                  Letzte ››
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Metal Purchase Form Modal */}
      <MetalPurchaseFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        purchase={selectedPurchase}
        isLoading={isFormLoading}
      />
    </div>
  );
};
