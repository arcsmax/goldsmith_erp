import React, { useState } from 'react';
import '../styles/components/LocationPicker.css';

interface Location {
  id: string;
  name: string;
  icon: string;
  category: 'workshop' | 'storage' | 'external';
}

interface LocationPickerProps {
  currentLocation: string | null;
  onSelectLocation: (location: string) => void;
  onCancel?: () => void;
}

const LOCATIONS: Location[] = [
  // Workshop (Werkstatt)
  { id: 'workbench_1', name: 'Werkbank 1', icon: '🔨', category: 'workshop' },
  { id: 'workbench_2', name: 'Werkbank 2', icon: '🔨', category: 'workshop' },
  { id: 'workbench_3', name: 'Werkbank 3', icon: '🔨', category: 'workshop' },
  { id: 'polishing_station', name: 'Polierstation', icon: '✨', category: 'workshop' },

  // Storage (Lager)
  { id: 'vault', name: 'Tresor', icon: '🔐', category: 'storage' },
  { id: 'shelf_1', name: 'Regal 1', icon: '📦', category: 'storage' },
  { id: 'shelf_2', name: 'Regal 2', icon: '📦', category: 'storage' },
  { id: 'drawer', name: 'Schublade', icon: '🗄️', category: 'storage' },

  // External (Extern)
  { id: 'electroplating', name: 'Galvanik', icon: '⚡', category: 'external' },
  { id: 'customer', name: 'Kunde', icon: '👤', category: 'external' },
  { id: 'shipping', name: 'Versand', icon: '📮', category: 'external' },
  { id: 'repair', name: 'Reparatur', icon: '🔧', category: 'external' },
];

const CATEGORY_LABELS = {
  workshop: '🔨 Werkstatt',
  storage: '📦 Lager',
  external: '🌍 Extern',
};

const LocationPicker: React.FC<LocationPickerProps> = ({
  currentLocation,
  onSelectLocation,
  onCancel,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<
    'all' | 'workshop' | 'storage' | 'external'
  >('all');

  const filteredLocations =
    selectedCategory === 'all'
      ? LOCATIONS
      : LOCATIONS.filter((loc) => loc.category === selectedCategory);

  // Group locations by category
  const groupedLocations: Record<string, Location[]> = {
    workshop: [],
    storage: [],
    external: [],
  };

  filteredLocations.forEach((location) => {
    groupedLocations[location.category].push(location);
  });

  const handleLocationSelect = (locationId: string) => {
    onSelectLocation(locationId);
  };

  return (
    <div className="location-picker">
      <div className="location-picker-header">
        <h2>Lagerort wählen</h2>
        {onCancel && (
          <button onClick={onCancel} className="location-close-button">
            ✕
          </button>
        )}
      </div>

      {/* Category Filters */}
      <div className="location-category-filters">
        <button
          onClick={() => setSelectedCategory('all')}
          className={`location-category-filter ${selectedCategory === 'all' ? 'active' : ''}`}
        >
          Alle
        </button>
        <button
          onClick={() => setSelectedCategory('workshop')}
          className={`location-category-filter ${selectedCategory === 'workshop' ? 'active' : ''}`}
        >
          🔨 Werkstatt
        </button>
        <button
          onClick={() => setSelectedCategory('storage')}
          className={`location-category-filter ${selectedCategory === 'storage' ? 'active' : ''}`}
        >
          📦 Lager
        </button>
        <button
          onClick={() => setSelectedCategory('external')}
          className={`location-category-filter ${selectedCategory === 'external' ? 'active' : ''}`}
        >
          🌍 Extern
        </button>
      </div>

      {/* Locations Grid */}
      <div className="locations-list">
        {(Object.keys(groupedLocations) as Array<keyof typeof groupedLocations>).map(
          (category) => {
            const categoryLocations = groupedLocations[category];

            if (categoryLocations.length === 0) return null;

            return (
              <div key={category} className="location-category-section">
                <h3 className="location-category-header">
                  {CATEGORY_LABELS[category]}
                </h3>
                <div className="location-grid">
                  {categoryLocations.map((location) => {
                    const isSelected = currentLocation === location.id;
                    const categoryClass = `location-card-${category}`;

                    return (
                      <button
                        key={location.id}
                        onClick={() => handleLocationSelect(location.id)}
                        className={`location-card ${categoryClass} ${isSelected ? 'selected' : ''}`}
                      >
                        <div className="location-card-icon">{location.icon}</div>
                        <div className="location-card-name">{location.name}</div>
                        {isSelected && (
                          <div className="location-selected-badge">✓ Aktuell</div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          }
        )}
      </div>

      {filteredLocations.length === 0 && (
        <div className="location-picker-empty">
          Keine Lagerorte in dieser Kategorie gefunden.
        </div>
      )}
    </div>
  );
};

export default LocationPicker;
