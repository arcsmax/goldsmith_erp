// WishStep — Beratungs-Wizard step 3: what the customer wants (piece type,
// free-text wishes), materials discussed (chip input), and any material the
// customer brought in themselves. The Altgold intake itself lives in its own
// module — this field is just a note for context, not an intake form.
import React, { useState } from 'react';
import type { WizardStepProps } from '../../pages/ConsultationWizardPage';
import { ConsultationPieceType, ConsultationUpdateInput } from '../../types';

/** Exported for reuse by the summary step (Task 8) and the list page (Task 9). */
export const PIECE_TYPE_LABELS: Record<ConsultationPieceType, string> = {
  ring: 'Ring',
  chain: 'Kette',
  pendant: 'Anhänger',
  earrings: 'Ohrringe',
  bracelet: 'Armband',
  brooch: 'Brosche',
  repair: 'Reparatur',
  custom: 'Sonderanfertigung',
};

const PIECE_TYPE_KEYS = Object.keys(PIECE_TYPE_LABELS) as ConsultationPieceType[];

interface WishStepProps extends WizardStepProps {
  onFieldsChange: (fields: ConsultationUpdateInput) => void;
}

/** Local snapshot of this step's editable fields, used to build a patch. */
interface WishFields {
  pieceType: ConsultationPieceType | null;
  wishes: string;
  materials: string[];
  sourceMaterial: string;
}

export const WishStep: React.FC<WishStepProps> = ({ consultation, onFieldsChange }) => {
  const [pieceType, setPieceType] = useState<ConsultationPieceType | null>(
    consultation.piece_type ?? null
  );
  const [wishes, setWishes] = useState(consultation.wishes ?? '');
  const [materials, setMaterials] = useState<string[]>(
    (consultation.materials_discussed ?? [])
      .map((entry) => entry.metal)
      .filter((metal): metal is string => Boolean(metal))
  );
  const [materialInput, setMaterialInput] = useState('');
  const [sourceMaterial, setSourceMaterial] = useState(consultation.source_material ?? '');

  const emit = (next: WishFields) => {
    onFieldsChange({
      piece_type: next.pieceType,
      wishes: next.wishes || null,
      materials_discussed: next.materials.map((metal) => ({ metal })),
      source_material: next.sourceMaterial || null,
    });
  };

  const handlePieceTypeSelect = (value: ConsultationPieceType) => {
    setPieceType(value);
    emit({ pieceType: value, wishes, materials, sourceMaterial });
  };

  const handleWishesChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setWishes(value);
    emit({ pieceType, wishes: value, materials, sourceMaterial });
  };

  const handleMaterialInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const value = materialInput.trim();
    if (!value || materials.includes(value)) {
      setMaterialInput('');
      return;
    }
    const nextMaterials = [...materials, value];
    setMaterials(nextMaterials);
    setMaterialInput('');
    emit({ pieceType, wishes, materials: nextMaterials, sourceMaterial });
  };

  const handleRemoveMaterial = (value: string) => {
    const nextMaterials = materials.filter((m) => m !== value);
    setMaterials(nextMaterials);
    emit({ pieceType, wishes, materials: nextMaterials, sourceMaterial });
  };

  const handleSourceMaterialChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setSourceMaterial(value);
    emit({ pieceType, wishes, materials, sourceMaterial: value });
  };

  return (
    <div className="wish-step">
      <div className="wizard-field">
        <label>Art des Schmuckstücks</label>
        <div className="chip-group" role="group" aria-label="Art des Schmuckstücks">
          {PIECE_TYPE_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={`chip${pieceType === key ? ' selected' : ''}`}
              aria-pressed={pieceType === key}
              onClick={() => handlePieceTypeSelect(key)}
            >
              {PIECE_TYPE_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      <div className="wizard-field">
        <label htmlFor="wishes">Was wünscht sich die Kundin?</label>
        <textarea
          id="wishes"
          value={wishes}
          onChange={handleWishesChange}
          placeholder="Erzählen Sie, was der Kundin vorschwebt — Anlass, Stil, besondere Wünsche..."
          rows={5}
        />
      </div>

      <div className="wizard-field">
        <label htmlFor="material_input">Besprochene Materialien</label>
        {materials.length > 0 && (
          <div className="chip-group">
            {materials.map((metal) => (
              <button
                key={metal}
                type="button"
                className="chip selected chip-removable"
                onClick={() => handleRemoveMaterial(metal)}
                aria-label={`${metal} entfernen`}
              >
                {metal}
              </button>
            ))}
          </div>
        )}
        <input
          type="text"
          id="material_input"
          value={materialInput}
          onChange={(e) => setMaterialInput(e.target.value)}
          onKeyDown={handleMaterialInputKeyDown}
          placeholder="Material eingeben und Enter drücken (z. B. Rotgold 585)"
        />
      </div>

      <div className="wizard-field">
        <label htmlFor="source_material">Mitgebrachtes Material (Altgold, Erbstück ...)</label>
        <textarea
          id="source_material"
          value={sourceMaterial}
          onChange={handleSourceMaterialChange}
          placeholder="z. B. Ehering der Großmutter, 3 Golddukaten..."
          rows={3}
        />
      </div>
    </div>
  );
};
