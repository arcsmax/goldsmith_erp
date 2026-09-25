// One quote in the page's detail region (W4-03): header with status and
// actions, the key dates, the line items (editable while DRAFT), the
// EstimatorPanel (DRAFT only, role-gated inside the panel) and the totals.
import React from 'react';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import type { Quote, QuoteLineItemInput } from '../../types';
import { IconButton } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { EstimatorPanel } from '../estimator/EstimatorPanel';
import { EditableLineItems, QuoteTotals, ReadOnlyLineItems } from './QuoteLineItems';
import { QuoteActions } from './QuoteActions';
import { formatDate, VALIDITY_HINT, validityTone } from './quoteFormat';
import { useLinkedOrder, type QuoteMutations } from './useQuoteQueries';

interface QuoteEditorProps {
  quote: Quote;
  mutations: QuoteMutations;
  onClose: () => void;
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="quote-meta__item">
      <dt>{label}</dt>
      <dd className="ui-num">{children}</dd>
    </div>
  );
}

export const QuoteEditor: React.FC<QuoteEditorProps> = ({ quote, mutations, onClose }) => {
  const { showToast } = useToast();
  const linkedOrder = useLinkedOrder(quote.order_id).data;
  const { addLine, saveLine, removeLine } = mutations;
  const isDraft = quote.status === 'draft';
  const isBusy = addLine.isPending || saveLine.isPending || removeLine.isPending;
  const tone = validityTone(quote.valid_until, quote.status);

  const run = async (context: string, fallback: string, action: () => Promise<unknown>) => {
    try {
      await action();
    } catch (err) {
      logError(context, err);
      showToast(getErrorMessage(err, fallback), 'error');
    }
  };

  const handleAdd = (data: QuoteLineItemInput) =>
    run('quote.addLineItem', 'Position konnte nicht hinzugefügt werden.', () =>
      addLine.mutateAsync({ quoteId: quote.id, data }),
    );
  const handleSave = (itemId: number, data: QuoteLineItemInput) =>
    run('quote.updateLineItem', 'Position konnte nicht gespeichert werden.', () =>
      saveLine.mutateAsync({ quoteId: quote.id, itemId, data }),
    );
  const handleRemove = (itemId: number) =>
    run('quote.deleteLineItem', 'Position konnte nicht entfernt werden.', () =>
      removeLine.mutateAsync({ quoteId: quote.id, itemId }),
    );

  const handleEstimatorPatch = async ({ addLineItem }: { addLineItem: QuoteLineItemInput }) => {
    try {
      await addLine.mutateAsync({ quoteId: quote.id, data: addLineItem });
      showToast('Schätzung übernommen.', 'success');
      return true;
    } catch (err) {
      logError('quote.estimatorPatch', err);
      showToast(getErrorMessage(err, 'Schätzung konnte nicht übernommen werden.'), 'error');
      return false;
    }
  };

  return (
    <section className="quote-editor" aria-labelledby="quote-editor-title">
      <header className="quote-editor__header">
        <div className="quote-editor__title">
          <h2 id="quote-editor-title" className="ui-num">
            {quote.quote_number}
          </h2>
          <StatusBadge kind="quote" status={quote.status} />
        </div>
        <IconButton icon="close" label="Kostenvoranschlag schließen" onClick={onClose} />
      </header>

      <QuoteActions quote={quote} mutations={mutations} onDeleted={onClose} />

      <dl className="quote-meta">
        <MetaItem label="Erstellt am">{formatDate(quote.created_at)}</MetaItem>
        <MetaItem label="Gültig bis">
          {formatDate(quote.valid_until)}
          {VALIDITY_HINT[tone] && <span className={`quote-validity quote-validity--${tone}`}> ({VALIDITY_HINT[tone]})</span>}
        </MetaItem>
        {quote.order_id && <MetaItem label="Auftragsnr.">#{quote.order_id}</MetaItem>}
        {quote.approved_at && <MetaItem label="Genehmigt am">{formatDate(quote.approved_at)}</MetaItem>}
        {quote.converted_at && <MetaItem label="Umgewandelt am">{formatDate(quote.converted_at)}</MetaItem>}
      </dl>

      {isDraft ? (
        <>
          <p className="quote-editor__hint">
            Entwurf: Positionen und Beträge lassen sich hier anpassen. Der Kostenvoranschlag
            friert erst beim Versenden ein.
          </p>
          <EditableLineItems
            items={quote.line_items}
            disabled={isBusy}
            onAdd={handleAdd}
            onSave={handleSave}
            onRemove={handleRemove}
          />
          <EstimatorPanel
            quote={quote}
            order={
              linkedOrder
                ? {
                    id: linkedOrder.id,
                    order_type: linkedOrder.order_type ?? null,
                    surface_finish: linkedOrder.surface_finish ?? null,
                    alloy: linkedOrder.alloy ?? null,
                  }
                : null
            }
            onPatch={handleEstimatorPatch}
          />
        </>
      ) : (
        quote.line_items.length > 0 && <ReadOnlyLineItems items={quote.line_items} />
      )}

      {(isDraft || quote.line_items.length > 0) && <QuoteTotals quote={quote} />}

      {quote.notes && (
        <div className="quote-editor__notes">
          <h3>Anmerkungen</h3>
          <p>{quote.notes}</p>
        </div>
      )}
    </section>
  );
};
