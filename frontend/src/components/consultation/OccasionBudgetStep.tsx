// OccasionBudgetStep — Beratungs-Wizard step 2: occasion (single-select
// chip), optional occasion date, and budget range (von/bis).
//
// Every local edit is reported up via onFieldsChange with the full field set
// of this step so the shared Weiter button can PATCH it. When the budget
// range is invalid (von > bis, or a negative value) the step reports itself
// INVALID via onFieldsChange(null) and a German error is shown inline — the
// wizard engine (ConsultationWizardPage.navigateToStep) blocks forward
// navigation entirely until the range is fixed (null is a distinct signal
// from {}, which means "valid, nothing to save").
import React, { useState } from 'react';
import type { WizardStepProps } from '../../pages/ConsultationWizardPage';
import { ConsultationOccasion, ConsultationUpdateInput } from '../../types';
import { ConsultationOccasionSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';

/** Exported for reuse by the summary step (Task 8) and the list page (Task 9). */
export const OCCASION_LABELS: Record<ConsultationOccasion, string> = {
  engagement: 'Verlobung',
  wedding: 'Hochzeit',
  anniversary: 'Jahrestag',
  birthday: 'Geburtstag',
  self: 'Für mich selbst',
  redesign: 'Umarbeitung',
  repair_consult: 'Reparatur-Beratung',
  other: 'Anderer Anlass',
};

const OCCASION_KEYS = Object.keys(OCCASION_LABELS) as ConsultationOccasion[];

interface OccasionBudgetStepProps extends WizardStepProps {
  onFieldsChange: (fields: ConsultationUpdateInput | null) => void;
}

/** Local snapshot of this step's editable fields, used to build a patch. */
interface OccasionFields {
  occasion: ConsultationOccasion;
  occasionDate: string;
  budgetMin: string;
  budgetMax: string;
}

export const OccasionBudgetStep: React.FC<OccasionBudgetStepProps> = ({
  consultation,
  onFieldsChange,
}) => {
  const [occasion, setOccasion] = useState<ConsultationOccasion>(consultation.occasion);
  const [occasionDate, setOccasionDate] = useState(consultation.occasion_date ?? '');
  const [budgetMin, setBudgetMin] = useState(
    consultation.budget_min != null ? String(consultation.budget_min) : ''
  );
  const [budgetMax, setBudgetMax] = useState(
    consultation.budget_max != null ? String(consultation.budget_max) : ''
  );
  const { validate, errors } = useFormValidation(ConsultationOccasionSchema);

  // Re-validates the full field set and reports it up. On failure the step
  // reports itself INVALID (null) — see file header.
  const emit = (next: OccasionFields) => {
    const result = validate({
      occasion: next.occasion,
      occasion_date: next.occasionDate || undefined,
      budget_min: next.budgetMin !== '' ? Number(next.budgetMin) : undefined,
      budget_max: next.budgetMax !== '' ? Number(next.budgetMax) : undefined,
    });
    if (!result.success) {
      onFieldsChange(null);
      return;
    }
    onFieldsChange({
      occasion: next.occasion,
      occasion_date: next.occasionDate || null,
      budget_min: next.budgetMin !== '' ? Number(next.budgetMin) : null,
      budget_max: next.budgetMax !== '' ? Number(next.budgetMax) : null,
    });
  };

  const handleOccasionSelect = (value: ConsultationOccasion) => {
    setOccasion(value);
    emit({ occasion: value, occasionDate, budgetMin, budgetMax });
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setOccasionDate(value);
    emit({ occasion, occasionDate: value, budgetMin, budgetMax });
  };

  const handleBudgetMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBudgetMin(value);
    emit({ occasion, occasionDate, budgetMin: value, budgetMax });
  };

  const handleBudgetMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBudgetMax(value);
    emit({ occasion, occasionDate, budgetMin, budgetMax: value });
  };

  return (
    <div className="occasion-budget-step">
      <div className="wizard-field">
        <label>Anlass</label>
        <div className="chip-group" role="group" aria-label="Anlass">
          {OCCASION_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={`chip${occasion === key ? ' selected' : ''}`}
              aria-pressed={occasion === key}
              onClick={() => handleOccasionSelect(key)}
            >
              {OCCASION_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      <div className="wizard-field">
        <label htmlFor="occasion_date">Datum (optional)</label>
        <input type="date" id="occasion_date" value={occasionDate} onChange={handleDateChange} />
        <p className="field-hint">z. B. Hochzeitstermin</p>
      </div>

      <div className="wizard-field-row">
        <div className="wizard-field">
          <label htmlFor="budget_min">Budget von €</label>
          <input
            type="number"
            id="budget_min"
            min="0"
            value={budgetMin}
            onChange={handleBudgetMinChange}
          />
          {/* HTML min="0" only constrains the spinner arrows — a typed
              negative value still fails Zod .min(0) and must surface here. */}
          {errors.budget_min && <div className="error-message">{errors.budget_min}</div>}
        </div>
        <div className="wizard-field">
          <label htmlFor="budget_max">Budget bis €</label>
          <input
            type="number"
            id="budget_max"
            min="0"
            value={budgetMax}
            onChange={handleBudgetMaxChange}
          />
        </div>
      </div>
      {errors.budget_max && <div className="error-message">{errors.budget_max}</div>}
    </div>
  );
};
