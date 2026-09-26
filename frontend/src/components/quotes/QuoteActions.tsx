// Status actions of one quote (W4-03): Versenden, Genehmigen (with the
// approval dialog), Ablehnen (reason via PromptDialog, was window.prompt),
// In Auftrag umwandeln (ConfirmDialog, was window.confirm), PDF and Löschen.
// The next step is the primary button; Löschen sits apart in its own group.
import React, { useState } from 'react';
import { quotesApi, type QuoteApprovalMethod } from '../../api/quotes';
import { useConfirm, useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import type { Quote } from '../../types';
import { Button, usePromptDialog } from '../../ui';
import { ApproveQuoteModal } from './ApproveQuoteModal';
import { sendOutcomeMessage } from './quoteFormat';
import type { QuoteMutations } from './useQuoteQueries';

const MAX_REASON_LENGTH = 500;

interface QuoteActionsProps {
  quote: Quote;
  mutations: QuoteMutations;
  /** Called after the quote was deleted, so the page can close the editor. */
  onDeleted: () => void;
}

export const QuoteActions: React.FC<QuoteActionsProps> = ({ quote, mutations, onDeleted }) => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const { prompt, dialog } = usePromptDialog();
  const [isApproveOpen, setIsApproveOpen] = useState(false);
  const { send, approve, reject, convert, remove } = mutations;
  const isBusy = [send, approve, reject, convert, remove].some((m) => m.isPending);

  const isDraft = quote.status === 'draft';
  const isOpen = isDraft || quote.status === 'sent';
  const isDeletable = isDraft || quote.status === 'rejected';

  const fail = (context: string, err: unknown, fallback: string) => {
    logError(context, err);
    showToast(getErrorMessage(err, fallback), 'error');
  };

  const handleSend = async () => {
    try {
      const updated = await send.mutateAsync(quote.id);
      if (updated.delivery_method !== 'email') {
        try {
          await quotesApi.downloadPdf(updated.id, updated.quote_number);
        } catch (downloadErr) {
          fail(
            'quote.sendDownloadPdf',
            downloadErr,
            'Kostenvoranschlag als versendet vermerkt, aber das PDF konnte nicht heruntergeladen werden.',
          );
          return;
        }
      }
      showToast(sendOutcomeMessage(updated), 'success');
    } catch (err) {
      fail('quote.send', err, 'Kostenvoranschlag konnte nicht versendet werden.');
    }
  };

  const handleApprove = async (signatureData: string | null, method: QuoteApprovalMethod) => {
    try {
      await approve.mutateAsync({
        id: quote.id,
        payload: { response_method: method, signature_data: signatureData ?? undefined },
      });
      setIsApproveOpen(false);
      showToast('Angebot genehmigt.', 'success');
    } catch (err) {
      fail('quote.approve', err, 'Angebot konnte nicht genehmigt werden.');
    }
  };

  const handleReject = async () => {
    const reason = await prompt({
      title: 'Angebot ablehnen',
      label: 'Ablehnungsgrund (optional)',
      multiline: true,
      maxLength: MAX_REASON_LENGTH,
      confirmLabel: 'Angebot ablehnen',
    });
    if (reason === null) return;
    try {
      await reject.mutateAsync({ id: quote.id, reason: reason.trim() || undefined });
      showToast('Angebot abgelehnt.', 'success');
    } catch (err) {
      fail('quote.reject', err, 'Angebot konnte nicht abgelehnt werden.');
    }
  };

  const handleConvert = async () => {
    const ok = await showConfirm({
      title: 'In Auftrag umwandeln',
      message: `Angebot ${quote.quote_number} in einen Auftrag umwandeln?`,
      confirmLabel: 'In Auftrag umwandeln',
    });
    if (!ok) return;
    try {
      await convert.mutateAsync(quote.id);
      showToast('Angebot in einen Auftrag umgewandelt.', 'success');
    } catch (err) {
      fail('quote.convert', err, 'Angebot konnte nicht umgewandelt werden.');
    }
  };

  const handleDelete = async () => {
    const ok = await showConfirm({
      title: 'Angebot löschen',
      message: `Angebot ${quote.quote_number} wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await remove.mutateAsync(quote.id);
      showToast('Angebot gelöscht.', 'success');
      onDeleted();
    } catch (err) {
      fail('quote.delete', err, 'Angebot konnte nicht gelöscht werden.');
    }
  };

  const handlePdf = async () => {
    try {
      await quotesApi.downloadPdf(quote.id, quote.quote_number);
    } catch (err) {
      fail('quote.downloadPdf', err, 'PDF-Download fehlgeschlagen.');
    }
  };

  return (
    <div className="quote-actions">
      <div className="quote-actions__main">
        {isDraft && (
          <Button icon="send" onClick={() => void handleSend()} loading={send.isPending} disabled={isBusy}>
            Versenden
          </Button>
        )}
        {isOpen && (
          <>
            <Button
              variant={isDraft ? 'secondary' : 'primary'}
              icon="check"
              onClick={() => setIsApproveOpen(true)}
              disabled={isBusy}
            >
              Genehmigen
            </Button>
            <Button variant="secondary" onClick={() => void handleReject()} disabled={isBusy}>
              Ablehnen
            </Button>
          </>
        )}
        {quote.status === 'approved' && (
          <Button icon="arrow-right" onClick={() => void handleConvert()} loading={convert.isPending} disabled={isBusy}>
            In Auftrag umwandeln
          </Button>
        )}
        <Button variant="ghost" icon="file-text" onClick={() => void handlePdf()} disabled={isBusy}>
          PDF herunterladen
        </Button>
      </div>
      {isDeletable && (
        <div className="quote-actions__danger">
          <Button variant="danger" icon="trash" onClick={() => void handleDelete()} disabled={isBusy}>
            Löschen
          </Button>
        </div>
      )}
      <ApproveQuoteModal
        quote={isApproveOpen ? quote : null}
        onClose={() => setIsApproveOpen(false)}
        onApprove={handleApprove}
      />
      {dialog}
    </div>
  );
};
