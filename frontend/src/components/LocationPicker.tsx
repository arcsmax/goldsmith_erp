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
  { id: 'Werkbank 1', name: 'Werkbank 1', icon: '🔨', category: 'workshop' },
  { id: 'Werkbank 2', name: 'Werkbank 2', icon: '🔨', category: 'workshop' },
  { id: 'Werkbank 3', name: 'Werkbank 3', icon: '🔨', category: 'workshop' },
  { id: 'Polierstation', name: 'Polierstation', icon: '✨', category: 'workshop' },
  { id: 'Prüfbank', name: 'Prüfbank', icon: '🔬', category: 'workshop' },

  // Storage (Lager)
  { id: 'Tresor', name: 'Tresor', icon: '🔐', category: 'storage' },
  { id: 'Materialregal', name: 'Materialregal', icon: '📦', category: 'storage' },
  { id: 'Eingang', name: 'Eingang', icon: '📥', category: 'storage' },
  { id: 'Ausgang', name: 'Ausgang', icon: '📤', category: 'storage' },

  // External (Extern)
  { id: 'Beim Kunden', name: 'Beim Kunden', icon: '👤', category: 'external' },
  { id: 'Labor', name: 'Labor', icon: '🧪', category: 'external' },
  { id: 'Partner-Werkstatt', name: 'Partner-Werkstatt', icon: '🤝', category: 'external' },
  { id: 'Versand', name: 'Versand', icon: '📮', category: 'external' },
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
