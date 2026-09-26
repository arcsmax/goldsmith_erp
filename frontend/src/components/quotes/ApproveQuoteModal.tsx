// "Angebot genehmigen" (W4-03): how the customer agreed (DOM-11d, required)
// plus an optional signature, on the Modal primitive.
import React, { useState } from 'react';
import type { QuoteApprovalMethod } from '../../api/quotes';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { Quote } from '../../types';
import { Button, Modal } from '../../ui';
import { SignatureCanvas } from '../SignatureCanvas';
import { APPROVAL_METHOD_OPTIONS, formatDate } from './quoteFormat';

const SIGNATURE_WIDTH = 500;
const SIGNATURE_HEIGHT = 160;

interface ApproveQuoteModalProps {
  quote: Quote | null;
  onClose: () => void;
  onApprove: (signatureData: string | null, method: QuoteApprovalMethod) => Promise<void>;
}

export const ApproveQuoteModal: React.FC<ApproveQuoteModalProps> = ({ quote, onClose, onApprove }) => {
  const [signatureData, setSignatureData] = useState<string | null>(null);
  const [method, setMethod] = useState<QuoteApprovalMethod | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isDirty = Boolean(method || signatureData);

  const close = () => {
    setSignatureData(null);
    setMethod(null);
    onClose();
  };

  const approve = async () => {
    if (!method) return;
    setIsSubmitting(true);
    try {
      await onApprove(signatureData, method);
      setSignatureData(null);
      setMethod(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open={quote !== null}
      onClose={close}
      title="Angebot genehmigen"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Abbrechen
          </Button>
          <Button onClick={() => void approve()} loading={isSubmitting} disabled={isSubmitting || !method}>
            Angebot genehmigen
          </Button>
        </>
      }
    >
      {quote && (
        <>
          <dl className="quote-summary">
            <div>
              <dt>KV-Nummer</dt>
              <dd className="ui-num">{quote.quote_number}</dd>
            </div>
            <div>
              <dt>Gesamtbetrag</dt>
              <dd className={`ui-num ${MONEY_CLASS}`}>{formatEur(quote.total)}</dd>
            </div>
            <div>
              <dt>Gültig bis</dt>
              <dd className="ui-num">{formatDate(quote.valid_until)}</dd>
            </div>
          </dl>

          <fieldset className="quote-approval">
            <legend className="ui-field__label">
              Wie hat der Kunde zugestimmt?
              <span className="ui-field__required" aria-hidden="true">
                Pflichtfeld
              </span>
            </legend>
            {APPROVAL_METHOD_OPTIONS.map((option) => (
              <label key={option.value} className="quote-approval__option">
                <input
                  type="radio"
                  name="approval-method"
                  value={option.value}
                  checked={method === option.value}
                  onChange={() => setMethod(option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>

          <div className="quote-signature">
            <p className="ui-field__label" id="quote-signature-label">
              Unterschrift des Kunden (optional)
            </p>
            <SignatureCanvas onSave={setSignatureData} width={SIGNATURE_WIDTH} height={SIGNATURE_HEIGHT} />
            <p className="ui-field__help" aria-live="polite">
              {signatureData ? 'Unterschrift erfasst' : 'Feld leer lassen, falls keine Unterschrift vorhanden.'}
            </p>
          </div>
        </>
      )}
    </Modal>
  );
};
