// Actions of one invoice in the detail region (W4-03).
//
// - "Als bezahlt markieren" for SENT and OVERDUE (the frequent action).
// - "Stornieren" (W2-04 open item): reverses an issued invoice, also a paid
//   one, with a linked negative Stornorechnung (POST /invoices/{id}/storno).
//   A reason is asked first; the new Storno opens right after.
// - "Entwurf stornieren": a DRAFT was never issued, it is only voided.
// Destructive actions sit apart from the frequent one and are ADMIN only,
// like the backend permission (INVOICE_DELETE).
import React from 'react';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import type { Invoice } from '../../types';
import { Button, usePromptDialog } from '../../ui';
import { canCreateStorno, canMarkPaid, canVoidDraft } from './invoiceFormat';
import type { InvoiceMutations } from './useInvoiceQueries';

const MAX_REASON_LENGTH = 500;

interface InvoiceActionsProps {
  invoice: Invoice;
  mutations: InvoiceMutations;
  /** ADMIN: may void drafts and create a Stornorechnung. */
  canCancel: boolean;
  onMarkPaid: (invoice: Invoice) => void;
  onVoidDraft: (invoice: Invoice) => void;
  /** Opens the new Stornorechnung. */
  onStornoCreated: (stornoId: number) => void;
  onClose: () => void;
}

export const InvoiceActions: React.FC<InvoiceActionsProps> = ({
  invoice,
  mutations,
  canCancel,
  onMarkPaid,
  onVoidDraft,
  onStornoCreated,
  onClose,
}) => {
  const { showToast } = useToast();
  const { prompt, dialog } = usePromptDialog();
  const { storno } = mutations;

  const handleStorno = async () => {
    const reason = await prompt({
      title: 'Rechnung stornieren',
      description: `Für ${invoice.invoice_number} wird eine Stornorechnung mit negativem Betrag erstellt, die auf diese Rechnung verweist. Die Rechnung selbst bleibt unverändert und wird als storniert markiert.`,
      label: 'Grund der Stornierung (optional)',
      multiline: true,
      maxLength: MAX_REASON_LENGTH,
      confirmLabel: 'Stornorechnung erstellen',
    });
    if (reason === null) return;
    try {
      const created = await storno.mutateAsync({ id: invoice.id, reason });
      showToast(`Stornorechnung ${created.invoice_number} erstellt.`, 'success');
      onStornoCreated(created.id);
    } catch (err) {
      logError('invoice.storno', err);
      showToast(getErrorMessage(err, 'Stornorechnung konnte nicht erstellt werden.'), 'error');
    }
  };

  return (
    <div className="invoice-actions invoice-no-print">
      <div className="invoice-actions__main">
        {canMarkPaid(invoice) && (
          <Button icon="check" onClick={() => onMarkPaid(invoice)}>
            Als bezahlt markieren
          </Button>
        )}
        <Button variant="secondary" icon="file-text" onClick={() => window.print()}>
          Drucken
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Schließen
        </Button>
      </div>
      {canCancel && (canCreateStorno(invoice) || canVoidDraft(invoice)) && (
        <div className="invoice-actions__danger">
          {canCreateStorno(invoice) && (
            <Button variant="danger" onClick={() => void handleStorno()} loading={storno.isPending}>
              Stornieren
            </Button>
          )}
          {canVoidDraft(invoice) && (
            <Button variant="danger" onClick={() => onVoidDraft(invoice)}>
              Entwurf stornieren
            </Button>
          )}
        </div>
      )}
      {dialog}
    </div>
  );
};
