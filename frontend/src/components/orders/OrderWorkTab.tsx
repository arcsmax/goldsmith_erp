// Arbeit tab of the order page (W2-08, DOM-17): everything done at the
// bench and what it costs. Replaces the former Zeiterfassung, Materialien,
// Metall, Arbeitszettel, Kosten, Soll/Ist, Altgold and Übergabe tabs.
//
// Role gates are unchanged from the old tabs: Kosten and Soll/Ist need
// FINANCIAL_VIEW, material unit prices likewise (GDPR-03, SEC-01).
import { useEffect, type ReactNode } from 'react';
import type { MaterialType, OrderType } from '../../types';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { canViewFinancials } from '../../lib/roles';
import { DataTable, type Column } from '../../ui';
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
}

interface WorkSectionProps {
  section: WorkSection;
  title: string;
  children: ReactNode;
}

function WorkSectionBlock({ section, title, children }: WorkSectionProps) {
  const id = workSectionId(section);
  return (
    <section id={id} className="order-work-section" aria-labelledby={`${id}-title`} tabIndex={-1}>
      <h3 id={`${id}-title`} className="order-work-section__title">
        {title}
      </h3>
      {children}
    </section>
  );
}

function materialColumns(canFinance: boolean): Column<MaterialType>[] {
  const columns: Column<MaterialType>[] = [
    { key: 'name', header: 'Material', render: (m) => m.name },
    { key: 'description', header: 'Beschreibung', render: (m) => m.description || '—' },
  ];
  // FINANCIAL_VIEW (GDPR-03): unit_price is stripped for a caller without
  // it; the column is omitted, not hidden.
  if (canFinance) {
    columns.push({
      key: 'unit_price',
      header: 'Preis/Einheit',
      numeric: true,
      align: 'end',
      render: (m) => <span className={MONEY_CLASS}>{formatEur(m.unit_price)}</span>,
    });
  }
  columns.push({ key: 'unit', header: 'Einheit', render: (m) => m.unit });
  return columns;
}

function MaterialsTable({ materials, canFinance }: { materials: MaterialType[]; canFinance: boolean }) {
  return (
    <DataTable
      rows={materials}
      columns={materialColumns(canFinance)}
      getRowKey={(m) => m.id}
      caption="Materialien des Auftrags"
      empty={{
        icon: 'gem',
        title: 'Keine Materialien zugeordnet',
        body: 'Materialien ordnen Sie beim Bearbeiten des Auftrags zu.',
        headingLevel: 3,
      }}
    />
  );
}

export function OrderWorkTab({
  order,
  materials,
  role,
  focusSection,
  onFocusSectionDone,
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
    <div className="order-tab-body">
      <h2 className="ui-visually-hidden">Arbeit</h2>

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
          <ArbeitszettelTab order={order} />
        </WorkSectionBlock>
      )}

      {canFinance && (
        <WorkSectionBlock section="kosten" title="Kosten">
          <CostBreakdownCard order={order} />
          <CostChangeSection orderId={order.id} />
        </WorkSectionBlock>
      )}

      {canFinance && isFinished && (
        <WorkSectionBlock section="soll-ist" title="Soll/Ist">
          <SollIstTab orderId={order.id} orderStatus={order.status} role={role} />
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
