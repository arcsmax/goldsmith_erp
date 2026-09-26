// Ausweisdaten for the Altgold Ankaufsbuch (W2-16, DOM-21; decision D-16).
//
// Optional below the configured value threshold, required (before the
// signature) above it — the backend decides and reports `id_required`.
// Reads carry only the last four characters of the number.
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ID_DOCUMENT_OPTIONS, scrapGoldApi, type IdDocumentType, type ScrapGold } from '../../api/scrap-gold';
import { useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import { Button, Field } from '../../ui';

const MIN_NUMBER_LENGTH = 4;
const MIN_AUTHORITY_LENGTH = 2;

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
  const [documentType, setDocumentType] = useState<IdDocumentType | ''>(
    (scrapGold.id_document_type as IdDocumentType | null) ?? ''
  );
  const [documentNumber, setDocumentNumber] = useState('');
  const [authority, setAuthority] = useState(scrapGold.id_issuing_authority ?? '');

  const save = useMutation({
    mutationFn: (type: IdDocumentType) =>
      scrapGoldApi.setIdentification(scrapGold.id, {
        id_document_type: type,
        id_document_number: documentNumber.trim(),
        id_issuing_authority: authority.trim(),
      }),
    onSuccess: (updated) => {
      setDocumentNumber('');
      onSaved(updated);
      showToast('Ausweisdaten gespeichert', 'success');
    },
    onError: (err: unknown) => {
      logError('ScrapGoldIdentification.save', err);
      showToast('Ausweisdaten konnten nicht gespeichert werden.', 'error');
    },
  });

  const heading = scrapGold.id_required ? 'Ausweisdaten' : 'Ausweisdaten (optional)';
  const canSave =
    documentType !== '' &&
    documentNumber.trim().length >= MIN_NUMBER_LENGTH &&
    authority.trim().length >= MIN_AUTHORITY_LENGTH;

  return (
    <section className="scrap-gold-section" aria-labelledby={`scrap-gold-id-${scrapGold.id}`}>
      <h3 id={`scrap-gold-id-${scrapGold.id}`}>{heading}</h3>
      {scrapGold.id_required && !scrapGold.has_identification && (
        <p role="note" className="scrap-gold-hint">
          Ausweisdaten sind bei diesem Ankaufswert Pflicht und müssen vor der Unterschrift erfasst werden.
        </p>
      )}
      {scrapGold.has_identification && <p>Erfasst: {identificationSummary(scrapGold)}</p>}
      {isEditable && (
        <div className="scrap-gold-form">
          <Field label="Ausweisart" name="scrap-gold-id-type">
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value as IdDocumentType | '')}
            >
              <option value="">Ausweisart auswählen</option>
              {ID_DOCUMENT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Ausweisnummer"
            name="scrap-gold-id-number"
            help={scrapGold.has_identification ? 'Nur zum Ändern neu eingeben.' : 'Mindestens 4 Zeichen.'}
          >
            <input
              type="text"
              autoComplete="off"
              value={documentNumber}
              onChange={(e) => setDocumentNumber(e.target.value)}
            />
          </Field>
          <Field label="Ausstellende Behörde" name="scrap-gold-id-authority">
            <input
              type="text"
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              placeholder="z. B. Stadt München"
            />
          </Field>
          <Button
            variant="secondary"
            onClick={() => documentType !== '' && save.mutate(documentType)}
            disabled={!canSave}
            loading={save.isPending}
          >
            Ausweisdaten speichern
          </Button>
        </div>
      )}
    </section>
  );
}

export default ScrapGoldIdentification;
