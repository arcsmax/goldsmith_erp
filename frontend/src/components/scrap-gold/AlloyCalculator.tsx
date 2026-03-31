// Alloy Calculator Widget - Calculates fine gold content from alloy and weight
import React, { useState, useMemo } from 'react';

export interface AlloyOption {
  value: number;
  label: string;
  metalType: 'gold' | 'silver' | 'platinum';
}

export const ALLOY_OPTIONS: AlloyOption[] = [
  { value: 999, label: '999 / 24K Feingold', metalType: 'gold' },
  { value: 750, label: '750 / 18K', metalType: 'gold' },
  { value: 585, label: '585 / 14K', metalType: 'gold' },
  { value: 375, label: '375 / 9K', metalType: 'gold' },
  { value: 333, label: '333 / 8K', metalType: 'gold' },
  { value: 925, label: 'Silber 925', metalType: 'silver' },
  { value: 800, label: 'Silber 800', metalType: 'silver' },
  { value: 950, label: 'Platin 950', metalType: 'platinum' },
];

interface AlloyCalculatorProps {
  onAddItem: (description: string, alloy: number, weightG: number) => void;
  isDisabled?: boolean;
}

export const AlloyCalculator: React.FC<AlloyCalculatorProps> = ({
  onAddItem,
  isDisabled = false,
}) => {
  const [selectedAlloy, setSelectedAlloy] = useState<number>(585);
  const [weightG, setWeightG] = useState<string>('');
  const [description, setDescription] = useState<string>('');

  const fineContent = useMemo(() => {
    const weight = parseFloat(weightG);
    if (isNaN(weight) || weight <= 0) return null;
    return weight * selectedAlloy / 1000;
  }, [weightG, selectedAlloy]);

  const finePercentage = useMemo(() => {
    return selectedAlloy / 10;
  }, [selectedAlloy]);

  const selectedOption = useMemo(() => {
    return ALLOY_OPTIONS.find((opt) => opt.value === selectedAlloy);
  }, [selectedAlloy]);

  const getFineLabel = (): string => {
    const metalType = selectedOption?.metalType;
    if (metalType === 'silver') return 'Feinsilber';
    if (metalType === 'platinum') return 'Feinplatin';
    return 'Feingold';
  };

  const handleAdd = () => {
    const weight = parseFloat(weightG);
    if (isNaN(weight) || weight <= 0) return;
    if (!description.trim()) return;

    onAddItem(description.trim(), selectedAlloy, weight);

    // Reset form
    setDescription('');
    setWeightG('');
  };

  const canAdd = description.trim().length > 0 && fineContent !== null && fineContent > 0;

  return (
    <div className="alloy-calculator">
      <div className="alloy-calculator-header">
        <h3>Legierungsrechner</h3>
      </div>

      <div className="alloy-calculator-form">
        {/* Description */}
        <div className="alloy-field">
          <label htmlFor="scrap-description">Beschreibung</label>
          <input
            id="scrap-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="z.B. Alter Ehering, Kette, Armband..."
            disabled={isDisabled}
          />
        </div>

        {/* Alloy Selection */}
        <div className="alloy-field-row">
          <div className="alloy-field">
            <label htmlFor="scrap-alloy">Legierung</label>
            <select
              id="scrap-alloy"
              value={selectedAlloy}
              onChange={(e) => setSelectedAlloy(Number(e.target.value))}
              disabled={isDisabled}
            >
              <optgroup label="Gold">
                {ALLOY_OPTIONS.filter((o) => o.metalType === 'gold').map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Silber">
                {ALLOY_OPTIONS.filter((o) => o.metalType === 'silver').map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Platin">
                {ALLOY_OPTIONS.filter((o) => o.metalType === 'platinum').map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>

          {/* Weight Input */}
          <div className="alloy-field">
            <label htmlFor="scrap-weight">Gewicht (g)</label>
            <input
              id="scrap-weight"
              type="number"
              step="0.01"
              min="0"
              value={weightG}
              onChange={(e) => setWeightG(e.target.value)}
              placeholder="0.00"
              disabled={isDisabled}
            />
          </div>
        </div>

        {/* Result Display */}
        {fineContent !== null && (
          <div className="alloy-result">
            <span className="alloy-result-value">
              {fineContent.toFixed(3)}g {getFineLabel()}
            </span>
            <span className="alloy-result-percentage">
              ({finePercentage.toFixed(1)}%)
            </span>
          </div>
        )}

        {/* Add Button */}
        <button
          className="btn-add-item"
          onClick={handleAdd}
          disabled={!canAdd || isDisabled}
        >
          Hinzufuegen
        </button>
      </div>
    </div>
  );
};
