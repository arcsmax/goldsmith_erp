// Alloy Calculator Widget - Calculates fine gold content from alloy and weight
import React, { useState, useMemo } from 'react';
import { useMetalTypes } from '../../hooks/useMetalTypes';

export interface AlloyOption {
  /** Permille fineness, used for the <select> value and the %-preview math. */
  value: number;
  /**
   * Canonical alloy code sent to the backend — matches
   * ``goldsmith_erp.db.models.AlloyType`` exactly (e.g. "585", "ag925",
   * "pt950"). Gold codes are the bare permille number; silver and
   * platinum are prefixed ("ag"/"pt") because the backend enum
   * disambiguates them that way (DOM-19: the old UI sent the bare
   * permille number for every metal, which is wrong for silver/platinum
   * and — being a number, not a string — was rejected outright for all
   * three).
   */
  code: string;
  label: string;
  metalType: 'gold' | 'silver' | 'platinum';
}

/** Derive the canonical backend AlloyType code from a permille value and metal family. */
function alloyCodeForMetal(value: number, metalType: AlloyOption['metalType']): string {
  if (metalType === 'silver') return `ag${value}`;
  if (metalType === 'platinum') return `pt${value}`;
  return String(value);
}

export const ALLOY_OPTIONS: AlloyOption[] = [
  { value: 999, code: alloyCodeForMetal(999, 'gold'), label: '999 / 24K Feingold', metalType: 'gold' },
  { value: 750, code: alloyCodeForMetal(750, 'gold'), label: '750 / 18K', metalType: 'gold' },
  { value: 585, code: alloyCodeForMetal(585, 'gold'), label: '585 / 14K', metalType: 'gold' },
  { value: 375, code: alloyCodeForMetal(375, 'gold'), label: '375 / 9K', metalType: 'gold' },
  { value: 333, code: alloyCodeForMetal(333, 'gold'), label: '333 / 8K', metalType: 'gold' },
  { value: 925, code: alloyCodeForMetal(925, 'silver'), label: 'Silber 925', metalType: 'silver' },
  { value: 800, code: alloyCodeForMetal(800, 'silver'), label: 'Silber 800', metalType: 'silver' },
  { value: 950, code: alloyCodeForMetal(950, 'platinum'), label: 'Platin 950', metalType: 'platinum' },
];

interface AlloyCalculatorProps {
  onAddItem: (description: string, alloy: string, weightG: number) => void;
  isDisabled?: boolean;
}

export const AlloyCalculator: React.FC<AlloyCalculatorProps> = ({
  onAddItem,
  isDisabled = false,
}) => {
  const { groupedMetalTypes, isLoading: isLoadingMetalTypes } = useMetalTypes();

  const [selectedAlloy, setSelectedAlloy] = useState<number>(585);
  const [weightG, setWeightG] = useState<string>('');
  const [description, setDescription] = useState<string>('');

  // Build the full option list from the API (converted to permille integers)
  // plus any custom types, merged with the static fallback.
  const dynamicOptions: AlloyOption[] = useMemo(() => {
    if (isLoadingMetalTypes || Object.keys(groupedMetalTypes).length === 0) {
      return ALLOY_OPTIONS;
    }
    const result: AlloyOption[] = [];
    for (const [base, types] of Object.entries(groupedMetalTypes)) {
      const metalType: 'gold' | 'silver' | 'platinum' =
        base === 'silver' ? 'silver' : base === 'platinum' || base === 'palladium' ? 'platinum' : 'gold';
      for (const t of types) {
        const permille = Math.round(t.fine_content_ratio * 1000);
        result.push({
          value: permille,
          code: alloyCodeForMetal(permille, metalType),
          label: t.display_name,
          metalType,
        });
      }
    }
    // Deduplicate by value — keep first occurrence (built-ins take priority)
    const seen = new Set<number>();
    return result.filter((o) => {
      if (seen.has(o.value)) return false;
      seen.add(o.value);
      return true;
    });
  }, [groupedMetalTypes, isLoadingMetalTypes]);

  const fineContent = useMemo(() => {
    const weight = parseFloat(weightG);
    if (isNaN(weight) || weight <= 0) return null;
    return weight * selectedAlloy / 1000;
  }, [weightG, selectedAlloy]);

  const finePercentage = useMemo(() => {
    return selectedAlloy / 10;
  }, [selectedAlloy]);

  const selectedOption = useMemo(() => {
    return dynamicOptions.find((opt) => opt.value === selectedAlloy)
      ?? ALLOY_OPTIONS.find((opt) => opt.value === selectedAlloy);
  }, [dynamicOptions, selectedAlloy]);

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
    // selectedOption carries the canonical backend alloy code (DOM-19) — if
    // somehow unresolved (should not happen; every <select> value comes from
    // dynamicOptions/ALLOY_OPTIONS), fail loudly rather than send a bad value.
    if (!selectedOption) return;

    onAddItem(description.trim(), selectedOption.code, weight);

    // Reset form
    setDescription('');
    setWeightG('');
  };

  const canAdd = description.trim().length > 0 && fineContent !== null && fineContent > 0;

  const goldOptions = dynamicOptions.filter((o) => o.metalType === 'gold');
  const silverOptions = dynamicOptions.filter((o) => o.metalType === 'silver');
  const platinumOptions = dynamicOptions.filter((o) => o.metalType === 'platinum');

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
              disabled={isDisabled || isLoadingMetalTypes}
            >
              {goldOptions.length > 0 && (
                <optgroup label="Gold">
                  {goldOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </optgroup>
              )}
              {silverOptions.length > 0 && (
                <optgroup label="Silber">
                  {silverOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </optgroup>
              )}
              {platinumOptions.length > 0 && (
                <optgroup label="Platin">
                  {platinumOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </optgroup>
              )}
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
