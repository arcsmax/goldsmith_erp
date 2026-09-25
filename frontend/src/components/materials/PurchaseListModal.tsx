// Purchase list (Bestellliste) — materials below their own minimum stock,
// grouped by supplier. GET /materials/purchase-list is a legacy plain list
// (no Page envelope); it runs inside useQuery only while the dialog is open.
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { materialsApi } from '../../api/materials';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { Button, Modal, PageState, type PageStateValue } from '../../ui';

const DEFAULT_MIN_STOCK = 10;

interface PurchaseListModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PurchaseListModal: React.FC<PurchaseListModalProps> = ({ isOpen, onClose }) => {
  const query = useQuery({
    queryKey: queryKeys.materials.purchaseList(),
    queryFn: () => materialsApi.getPurchaseList(),
    enabled: isOpen,
  });
  const groups = query.data ?? [];

  let state: PageStateValue = { status: groups.length ? 'ready' : 'empty' };
  if (query.isPending) state = { status: 'loading' };
  if (query.isError) {
    state = {
      status: 'error',
      error: getErrorMessage(query.error, 'Bestellliste konnte nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Bestellliste"
      size="lg"
      dismissOnBackdrop
      footer={
        <Button variant="secondary" onClick={onClose}>
          Schließen
        </Button>
      }
    >
      <PageState
        state={state}
        skeleton="list"
        empty={{ icon: 'circle-check', title: 'Alle Materialien haben ausreichend Bestand.' }}
      >
        {groups.map((group) => (
          <section key={group.supplier ?? '__none__'} className="purchase-list__group">
            <h3 className="purchase-list__supplier">{group.supplier ?? 'Kein Lieferant'}</h3>
            <table className="ui-table">
              <thead>
                <tr>
                  <th>Material</th>
                  <th className="ui-align-end">Bestand</th>
                  <th className="ui-align-end">Mindestbestand</th>
                  <th>Einheit</th>
                </tr>
              </thead>
              <tbody>
                {group.materials.map((m) => (
                  <tr key={m.id}>
                    <td>
                      {m.webshop_url ? (
                        <a href={m.webshop_url} target="_blank" rel="noopener noreferrer">
                          {m.name}
                        </a>
                      ) : (
                        m.name
                      )}
                    </td>
                    <td className="ui-align-end ui-num purchase-list__low">{m.stock}</td>
                    <td className="ui-align-end ui-num">{m.min_stock ?? DEFAULT_MIN_STOCK}</td>
                    <td>{m.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
      </PageState>
    </Modal>
  );
};
