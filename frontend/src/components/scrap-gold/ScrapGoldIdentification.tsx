// Ausweisdaten for the Altgold Ankaufsbuch (W2-16, DOM-21; decision D-16).
//
// Optional below the configured value threshold, required (before the
// signature) above it — the backend decides and reports `id_required`.
// Reads carry only the last four characters of the number.
import { useId, useState } from 'react';
import { ID_DOCUMENT_OPTIONS, scrapGoldApi, type IdDocumentType, type ScrapGold } from '../../api/scrap-gold';
import { useToast } from '../../contexts';
import { logError } from '../../lib/logError';

interface ScrapGoldIdentificationProps {
  scrapGold: ScrapGold;
  isEditable: boolean;
  onSaved: (updated: ScrapGold) => void;
}

export function identificationSummary(scrapGold: ScrapGold): string {
  const type = ID_DOCUMENT_OPTIONS.find((o) => o.value === scrapGold.id_document_type)?.label;
  return [
    type ?? scrapGold.id_document_type ?? '',
    scrapGold.id_document_number_last4 ? `Nr. endet auf ${scrapGold.id_document_number_last4}` : '',
    scrapGold.id_issuing_authority ?? '',
  ]
    .filter(Boolean)
    .join(' · ');
}

export function ScrapGoldIdentification({ scrapGold, isEditable, onSaved }: ScrapGoldIdentificationProps) {
  const { showToast } = useToast();
  const id = useId();
  const [documentType, setDocumentType] = useState<IdDocumentType | ''>(
    (scrapGold.id_document_type as IdDocumentType | null) ?? ''
  );
  const [documentNumber, setDocumentNumber] = useState('');
  const [authority, setAuthority] = useState(scrapGold.id_issuing_authority ?? '');
  const [isSaving, setIsSaving] = useState(false);

  const heading = scrapGold.id_required ? 'Ausweisdaten' : 'Ausweisdaten (optional)';
  const canSave = documentType !== '' && documentNumber.trim().length >= 4 && authority.trim().length >= 2;

  const handleSave = async () => {
    if (documentType === '' || !canSave) return;
    setIsSaving(true);
    try {
      const updated = await scrapGoldApi.setIdentification(scrapGold.id, {
        id_document_type: documentType,
        id_document_number: documentNumber.trim(),
        id_issuing_authority: authority.trim(),
      });
      setDocumentNumber('');
      onSaved(updated);
      showToast('Ausweisdaten gespeichert', 'success');
    } catch (err: unknown) {
      logError('ScrapGoldIdentification.save', err);
      showToast('Ausweisdaten konnten nicht gespeichert werden.', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="scrap-gold-identification">
      <h3>{heading}</h3>
      {scrapGold.id_required && !scrapGold.has_identification && (
        <p role="note">
          Ausweisdaten sind bei diesem Ankaufswert Pflicht und müssen vor der Unterschrift erfasst werden.
        </p>
      )}
      {scrapGold.has_identification && <p>Erfasst: {identificationSummary(scrapGold)}</p>}
      {isEditable && (
        <div className="scrap-gold-identification-form">
          <div className="form-group">
            <label htmlFor={`${id}-type`}>Ausweisart</label>
            <select
              id={`${id}-type`}
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value as IdDocumentType | '')}
            >
              <option value="">-- Ausweisart auswählen --</option>
              {ID_DOCUMENT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor={`${id}-number`}>Ausweisnummer</label>
            <input
              id={`${id}-number`}
              type="text"
              autoComplete="off"
              value={documentNumber}
              onChange={(e) => setDocumentNumber(e.target.value)}
              placeholder={scrapGold.has_identification ? 'Nur zum Ändern neu eingeben' : ''}
            />
          </div>
          <div className="form-group">
            <label htmlFor={`${id}-authority`}>Ausstellende Behörde</label>
            <input
              id={`${id}-authority`}
              type="text"
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              placeholder="z.B. Stadt München"
            />
          </div>
          <button type="button" className="btn-secondary" onClick={() => void handleSave()} disabled={!canSave || isSaving}>
            Ausweisdaten speichern
          </button>
        </div>
      )}
    </div>
  );
}

export default ScrapGoldIdentification;
