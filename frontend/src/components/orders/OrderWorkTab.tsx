// Arbeit tab of the order page (W2-08, DOM-17): everything done at the
// bench and what it costs. Replaces the former Zeiterfassung, Materialien,
// Metall, Arbeitszettel, Kosten, Soll/Ist, Altgold and Übergabe tabs.
//
// Role gates are unchanged from the old tabs: Kosten and Soll/Ist need
// FINANCIAL_VIEW, material unit prices likewise (GDPR-03, SEC-01).
import { useEffect, type ReactNode } from 'react';
import type { MaterialType, OrderType } from '../../types';
import { canViewFinancials } from '../../lib/roles';
import TimeTrackingTab from '../TimeTrackingTab';
import { ScrapGoldTab } from '../scrap-gold';
import { CostBreakdownCard } from './CostBreakdownCard';
import { CostChangeSection } from './CostChangeSection';
import { MetalInventoryCard } from './MetalInventoryCard';
import { SollIstTab } from './SollIstTab';
import HandoffTab from './HandoffTab';
import ArbeitszettelTab from './ArbeitszettelTab';
import { workSectionId, type WorkSection } from './orderPageTabs';

interface OrderWorkTabProps {
  order: OrderType;
  materials: MaterialType[];
  role?: string | null;
  /** Section to scroll to once (legacy tab links such as "kosten"). */
  focusSection: WorkSection | null;
  onFocusSectionDone: () => void;
  onOrderUpdated: (order: OrderType) => void;
  onCostChangeUpdated: () => void;
}

interface WorkSectionProps {
  section: WorkSection;
  title: string;
  children: ReactNode;
}

function WorkSectionBlock({ section, title, children }: WorkSectionProps) {
  const id = workSectionId(section);
  return (
    <section id={id} className="details-section order-work-section" aria-labelledby={`${id}-title`} tabIndex={-1}>
      <h3 id={`${id}-title`}>{title}</h3>
      {children}
    </section>
  );
}

function MaterialsTable({ materials, canFinance }: { materials: MaterialType[]; canFinance: boolean }) {
  if (materials.length === 0) {
    return <p className="empty-message">Keine Materialien zugeordnet.</p>;
  }
  return (
    <table className="materials-table">
      <thead>
        <tr>
          <th>Material</th>
          <th>Beschreibung</th>
          {canFinance && <th>Preis/Einheit</th>}
          <th>Einheit</th>
        </tr>
      </thead>
      <tbody>
        {materials.map((material) => (
          <tr key={material.id}>
            <td>{material.name}</td>
            <td>{material.description || '—'}</td>
            {/* FINANCIAL_VIEW (GDPR-03): unit_price is stripped for a
                caller without it; the column is omitted. */}
            {canFinance && (
              <td className="tabular-nums">
                {material.unit_price != null ? `${material.unit_price.toFixed(2)} €` : '—'}
              </td>
            )}
            <td>{material.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function OrderWorkTab({
  order,
  materials,
  role,
  focusSection,
  onFocusSectionDone,
  onOrderUpdated,
  onCostChangeUpdated,
}: OrderWorkTabProps) {
  const canFinance = canViewFinancials(role);
  const isFinished = order.status === 'completed' || order.status === 'delivered';

  useEffect(() => {
    if (focusSection === null) return;
    const element = document.getElementById(workSectionId(focusSection));
    element?.scrollIntoView?.({ block: 'start' });
    element?.focus({ preventScroll: true });
    onFocusSectionDone();
  }, [focusSection, onFocusSectionDone]);

  return (
    <div className="tab-panel">
      <h2>Arbeit</h2>

      <WorkSectionBlock section="zeit" title="Zeiterfassung">
        <TimeTrackingTab orderId={order.id} />
      </WorkSectionBlock>

      <WorkSectionBlock section="material" title="Materialien">
        <MaterialsTable materials={materials} canFinance={canFinance} />
      </WorkSectionBlock>

      {order.metal_type && (
        <WorkSectionBlock section="metall" title="Metall">
          <MetalInventoryCard order={order} />
        </WorkSectionBlock>
      )}

      {order.status !== 'draft' && (
        <WorkSectionBlock section="arbeitszettel" title="Arbeitszettel">
          <ArbeitszettelTab order={order} onOrderUpdated={onOrderUpdated} />
        </WorkSectionBlock>
      )}

      {canFinance && (
        <WorkSectionBlock section="kosten" title="Kosten">
          <CostBreakdownCard order={order} />
          <CostChangeSection orderId={order.id} onChanged={onCostChangeUpdated} />
        </WorkSectionBlock>
      )}

      {canFinance && isFinished && (
        <WorkSectionBlock section="soll-ist" title="Soll/Ist">
          <SollIstTab orderId={order.id} orderStatus={order.status} />
        </WorkSectionBlock>
      )}

      <WorkSectionBlock section="altgold" title="Altgold">
        <ScrapGoldTab orderId={order.id} customerId={order.customer_id} />
      </WorkSectionBlock>

      <WorkSectionBlock section="uebergabe" title="Übergabe">
        <HandoffTab orderId={order.id} />
      </WorkSectionBlock>
    </div>
  );
}

export default OrderWorkTab;
