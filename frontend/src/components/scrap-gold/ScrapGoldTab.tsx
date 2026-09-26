// Scrap Gold Tab — Altgold for one order, on TanStack Query (W4-03).
//
// GET /orders/{id}/scrap-gold is a single legacy resource (null = none yet).
// Every write answers with the updated record or triggers a refetch of the
// ['scrap-gold'] key. Altgold values are financial data; the tab is only
// mounted for permitted roles by the order detail page.
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { scrapGoldApi, type ScrapGold, type ScrapGoldItem } from '../../api/scrap-gold';
import apiClient from '../../api/client';
import { queryKeys } from '../../api/queryKeys';
import { AlloyCalculator, ALLOY_OPTIONS } from './AlloyCalculator';
import { formatGrams, formatWeight } from './scrapGoldFormat';
import { SignatureCanvas } from '../SignatureCanvas';
import { ScrapGoldIdentification } from './ScrapGoldIdentification';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Card, EmptyState, IconButton, PageState, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import '../../styles/scrap-gold.css';

interface ScrapGoldTabProps {
  orderId: number;
  customerId: number;
}

const SIGNATURE_HEIGHT = 180;

/**
 * Formats an alloy code (e.g. "585", "ag925", "pt950") to a readable label.
 * Falls back to the raw code for an alloy the static option list does not
 * know (e.g. a custom metal type added via Verwaltung).
 */
const getAlloyLabel = (alloy: string): string =>
  ALLOY_OPTIONS.find((o) => o.code === alloy)?.label ?? alloy;

async function downloadReceipt(scrapGoldId: number): Promise<void> {
  // Authenticated fetch: a plain <a href> would answer 401.
  const response = await apiClient.get(`/scrap-gold/${scrapGoldId}/receipt.pdf`, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `Ankaufsbeleg_${scrapGoldId}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

function useScrapGold(orderId: number) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const queryKey = queryKeys.scrapGold.forOrder(orderId);
  const query = useQuery({ queryKey, queryFn: () => scrapGoldApi.getForOrder(orderId) });

  const setRecord = (record: ScrapGold) => queryClient.setQueryData(queryKey, record);
  const refetchRecord = () => queryClient.invalidateQueries({ queryKey });
  const fail = (context: string, message: string) => (err: unknown) => {
    console.error(`ScrapGoldTab.${context} failed`, { orderId, err });
    showToast(getErrorMessage(err, message), 'error');
  };

  const create = useMutation({
    mutationFn: () => scrapGoldApi.create(orderId),
    onSuccess: setRecord,
    onError: fail('create', 'Altgold-Eintrag konnte nicht angelegt werden.'),
  });
  const addItem = useMutation({
    mutationFn: ({ id, description, alloy, weightG }: { id: number; description: string; alloy: string; weightG: number }) =>
      // alloy is the canonical backend code (e.g. "585", "ag925"); DOM-19.
      scrapGoldApi.addItem(id, { description, alloy, weight_g: weightG }),
    onSuccess: refetchRecord,
    onError: fail('addItem', 'Position konnte nicht hinzugefügt werden.'),
  });
  const removeItem = useMutation({
    mutationFn: ({ id, itemId }: { id: number; itemId: number }) => scrapGoldApi.removeItem(id, itemId),
    onSuccess: refetchRecord,
    onError: fail('removeItem', 'Position konnte nicht entfernt werden.'),
  });
  const uploadPhoto = useMutation({
    mutationFn: ({ id, item, file }: { id: number; item: ScrapGoldItem; file: File }) =>
      scrapGoldApi.uploadItemPhoto(id, item.id, file),
    onSuccess: async () => {
      await refetchRecord();
      showToast('Foto hochgeladen', 'success');
    },
    onError: fail('uploadPhoto', 'Foto konnte nicht hochgeladen werden.'),
  });
  const calculate = useMutation({
    mutationFn: (id: number) => scrapGoldApi.calculate(id),
    onSuccess: setRecord,
    onError: fail('calculate', 'Berechnung fehlgeschlagen.'),
  });
  const sign = useMutation({
    mutationFn: ({ id, signature }: { id: number; signature: string }) => scrapGoldApi.sign(id, signature),
    onSuccess: setRecord,
    onError: fail('sign', 'Unterschrift konnte nicht gespeichert werden.'),
  });
  const receipt = useMutation({
    mutationFn: (id: number) => downloadReceipt(id),
    onError: fail('receipt', 'PDF konnte nicht heruntergeladen werden.'),
  });

  return { query, setRecord, create, addItem, removeItem, uploadPhoto, calculate, sign, receipt };
}

type ScrapGoldActions = ReturnType<typeof useScrapGold>;

const ItemsTable: React.FC<{ scrapGold: ScrapGold; isEditable: boolean; actions: ScrapGoldActions }> = ({
  scrapGold,
  isEditable,
  actions,
}) => (
  <div className="ui-table-scroll">
    <table className="ui-table">
      <caption className="ui-visually-hidden">Altgold-Positionen</caption>
      <thead>
        <tr>
          <th>Beschreibung</th>
          <th>Legierung</th>
          <th className="ui-align-end">Gewicht</th>
          <th className="ui-align-end">Feingehalt</th>
          <th>Foto</th>
          {isEditable && <th>Aktion</th>}
        </tr>
      </thead>
      <tbody>
        {scrapGold.items.map((item) => (
          <tr key={item.id}>
            <td>{item.description}</td>
            <td>{getAlloyLabel(item.alloy)}</td>
            <td className="ui-align-end ui-num">{formatWeight(item.weight_g)}</td>
            <td className="ui-align-end ui-num">{formatGrams(item.fine_content_g)}</td>
            <td>
              {item.photo_path ? (
                <img
                  src={scrapGoldApi.getItemPhotoUrl(scrapGold.id, item.id)}
                  alt={`Foto: ${item.description}`}
                  width={40}
                  height={40}
                  className="scrap-gold-thumb"
                />
              ) : isEditable ? (
                <label className="scrap-gold-upload">
                  <span className="ui-visually-hidden">Foto zu {item.description} hochladen</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) actions.uploadPhoto.mutate({ id: scrapGold.id, item, file });
                    }}
                  />
                </label>
              ) : (
                <span className="scrap-gold-muted">Kein Foto</span>
              )}
            </td>
            {isEditable && (
              <td>
                <IconButton
                  icon="trash"
                  variant="danger"
                  label={`Position ${item.description} entfernen`}
                  disabled={actions.removeItem.isPending}
                  onClick={() => actions.removeItem.mutate({ id: scrapGold.id, itemId: item.id })}
                />
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const Summary: React.FC<{ scrapGold: ScrapGold; isEditable: boolean; actions: ScrapGoldActions }> = ({
  scrapGold,
  isEditable,
  actions,
}) => (
  <Card title="Zusammenfassung" headingLevel={3}>
    <dl className="scrap-gold-summary">
      <div>
        <dt>Gesamt Feingold</dt>
        <dd className="ui-num">{formatGrams(scrapGold.total_fine_gold_g)}</dd>
      </div>
      <div>
        <dt>Goldpreis/g</dt>
        <dd className={MONEY_CLASS}>{scrapGold.gold_price_per_g ? formatEur(scrapGold.gold_price_per_g) : '—'}</dd>
      </div>
      <div className="scrap-gold-summary__total">
        <dt>Gesamtwert</dt>
        <dd className={MONEY_CLASS}>{formatEur(scrapGold.total_value_eur)}</dd>
      </div>
      {scrapGold.price_source && (
        <div>
          <dt>Preisquelle</dt>
          <dd>{scrapGold.price_source}</dd>
        </div>
      )}
    </dl>
    {isEditable && scrapGold.items.length > 0 && (
      <Button onClick={() => actions.calculate.mutate(scrapGold.id)} loading={actions.calculate.isPending}>
        Wert berechnen
      </Button>
    )}
  </Card>
);

const Signature: React.FC<{ scrapGold: ScrapGold; actions: ScrapGoldActions }> = ({ scrapGold, actions }) => {
  const isIdMissing = scrapGold.id_required && !scrapGold.has_identification; // W2-16 / D-16
  if (scrapGold.signed_at) {
    return (
      <>
        <p>
          <span aria-hidden="true">✓ </span>Unterschrieben am{' '}
          <span className="ui-num">{new Date(scrapGold.signed_at).toLocaleString('de-DE')}</span>
        </p>
        {scrapGold.signature_data?.startsWith('data:image/') && (
          <img
            src={scrapGold.signature_data}
            alt="Gespeicherte Unterschrift des Kunden"
            className="scrap-gold-signature-image"
          />
        )}
        <Button
          variant="secondary"
          icon="file-text"
          onClick={() => actions.receipt.mutate(scrapGold.id)}
          loading={actions.receipt.isPending}
        >
          Ankaufsbeleg herunterladen
        </Button>
      </>
    );
  }
  if (scrapGold.status === 'received' && scrapGold.items.length === 0) {
    return (
      <p className="scrap-gold-hint">
        Bitte zuerst Positionen erfassen und berechnen, bevor die Unterschrift eingeholt wird.
      </p>
    );
  }
  if (isIdMissing) {
    return (
      <p className="scrap-gold-hint">Bitte zuerst die Ausweisdaten erfassen, bevor die Unterschrift eingeholt wird.</p>
    );
  }
  return (
    <SignatureCanvas
      onSave={(signature) => actions.sign.mutate({ id: scrapGold.id, signature })}
      height={SIGNATURE_HEIGHT}
    />
  );
};

export const ScrapGoldTab: React.FC<ScrapGoldTabProps> = ({ orderId }) => {
  const actions = useScrapGold(orderId);
  const { query } = actions;
  const scrapGold = query.data ?? null;

  let state: PageStateValue = { status: 'ready' };
  if (query.isPending) state = { status: 'loading' };
  if (query.isError) {
    state = {
      status: 'error',
      error: getErrorMessage(query.error, 'Altgold-Daten konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }

  if (state.status !== 'ready' || !scrapGold) {
    return (
      <div className="scrap-gold-tab">
        <PageState state={state} skeleton="detail">
          <EmptyState
            icon="receipt"
            title="Altgold vorhanden?"
            body="Hat der Kunde Altgold zur Verrechnung mitgebracht?"
            action={
              <Button onClick={() => actions.create.mutate()} loading={actions.create.isPending}>
                Altgold erfassen
              </Button>
            }
          />
        </PageState>
      </div>
    );
  }

  const isEditable = scrapGold.status === 'received' || scrapGold.status === 'calculated';

  return (
    <div className="scrap-gold-tab">
      <div className="scrap-gold-header">
        <h2>Altgold</h2>
        <StatusBadge kind="scrapGold" status={scrapGold.status} />
      </div>

      {isEditable && (
        <AlloyCalculator
          onAddItem={(description, alloy, weightG) =>
            actions.addItem.mutate({ id: scrapGold.id, description, alloy, weightG })
          }
          isDisabled={actions.addItem.isPending}
        />
      )}

      <section className="scrap-gold-section" aria-labelledby="scrap-gold-items-title">
        <h3 id="scrap-gold-items-title">Positionen ({scrapGold.items.length})</h3>
        {scrapGold.items.length === 0 ? (
          <p className="scrap-gold-muted">
            Noch keine Positionen erfasst. Mit dem Legierungsrechner oben Altgold hinzufügen.
          </p>
        ) : (
          <ItemsTable scrapGold={scrapGold} isEditable={isEditable} actions={actions} />
        )}
      </section>

      <Summary scrapGold={scrapGold} isEditable={isEditable} actions={actions} />

      {/* Ausweisdaten (W2-16, Ankaufsbuch) */}
      <ScrapGoldIdentification
        key={`${scrapGold.id}-${scrapGold.id_checked_at ?? 'neu'}`}
        scrapGold={scrapGold}
        isEditable={isEditable}
        onSaved={actions.setRecord}
      />

      <section className="scrap-gold-section" aria-labelledby="scrap-gold-signature-title">
        <h3 id="scrap-gold-signature-title">Unterschrift</h3>
        <Signature scrapGold={scrapGold} actions={actions} />
      </section>

      {scrapGold.notes && (
        <section className="scrap-gold-section" aria-labelledby="scrap-gold-notes-title">
          <h3 id="scrap-gold-notes-title">Notizen</h3>
          <p>{scrapGold.notes}</p>
        </section>
      )}
    </div>
  );
};
