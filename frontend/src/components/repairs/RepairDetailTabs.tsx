// Tab panels of the repair page (W4-03), mirroring the order page's five
// tabs: Übersicht, Arbeit, Fotos (RepairPhotosTab), Kunde, Verlauf.
//
// Financial data (Kostenvoranschlag, tatsächliche Kosten, Versicherungswert)
// renders only for FINANCIAL_VIEW roles, in code, never hidden by CSS.
import React from 'react';
import { Link } from 'react-router-dom';
import { formatEur, MISSING_VALUE, MONEY_CLASS } from '../../lib/format';
import type { RepairJob, RepairJobStatus } from '../../types';
import { Button, Card, EmptyState, Icon } from '../../ui';
import { RepairCustomerUpdatePanel } from './RepairCustomerUpdatePanel';
import { customerName, formatRepairDate, formatRepairDateTime, itemTypeLabel } from './repairFormat';

export type RepairPageTab = 'uebersicht' | 'arbeit' | 'fotos' | 'kunde' | 'verlauf';

export const REPAIR_TAB_LABELS: Readonly<Record<RepairPageTab, string>> = {
  uebersicht: 'Übersicht',
  arbeit: 'Arbeit',
  fotos: 'Fotos',
  kunde: 'Kunde',
  verlauf: 'Verlauf',
};

/** DESIGN_VIEW gates the Fotos tab (its endpoints 403 without it). */
export function repairTabs(canDesign: boolean): RepairPageTab[] {
  return canDesign
    ? ['uebersicht', 'arbeit', 'fotos', 'kunde', 'verlauf']
    : ['uebersicht', 'arbeit', 'kunde', 'verlauf'];
}

interface FactProps {
  label: string;
  value: React.ReactNode;
  isMoney?: boolean;
}

const Fact: React.FC<FactProps> = ({ label, value, isMoney }) => (
  <div className="repair-fact">
    <dt className="repair-fact__label">{label}</dt>
    <dd className={isMoney ? `repair-fact__value ${MONEY_CLASS}` : 'repair-fact__value'}>{value}</dd>
  </div>
);

// ─── Übersicht ──────────────────────────────────────────────────────────────

interface OverviewProps {
  repair: RepairJob;
  canFinance: boolean;
  /** Offered only to REPAIR_EDIT roles and open repairs. */
  onCancel?: () => void;
  isCancelling: boolean;
}

export const RepairOverviewTab: React.FC<OverviewProps> = ({ repair, canFinance, onCancel, isCancelling }) => (
  <div className="repair-tab-body">
    <h2 className="ui-visually-hidden">Übersicht</h2>
    <Card title="Schmuckstück" headingLevel={3}>
      <dl className="repair-facts">
        <Fact label="Beschreibung" value={repair.item_description} />
        <Fact label="Art" value={itemTypeLabel(repair.item_type)} />
        <Fact label="Metall" value={repair.metal_type ?? MISSING_VALUE} />
        <Fact label="Tüte" value={repair.bag_number} />
        {canFinance && <Fact label="Versicherungswert" value={formatEur(repair.estimated_value)} isMoney />}
      </dl>
    </Card>
    <Card title="Termine" headingLevel={3}>
      <dl className="repair-facts">
        <Fact label="Angenommen" value={formatRepairDateTime(repair.created_at)} />
        <Fact label="Zugesagt bis" value={formatRepairDate(repair.estimated_completion_date)} />
        <Fact label="Fertiggestellt" value={formatRepairDate(repair.actual_completion_date)} />
        <Fact label="Abgeholt" value={formatRepairDateTime(repair.picked_up_at)} />
      </dl>
    </Card>
    {onCancel && (
      <Card title="Reparatur stornieren" headingLevel={3}>
        <p className="repair-tab-body__hint">
          Storniert die Reparatur. Das Stück bleibt in Tüte {repair.bag_number}, bis es abgeholt wird.
        </p>
        <Button variant="danger" icon="circle-x" onClick={onCancel} loading={isCancelling}>
          Reparatur stornieren
        </Button>
      </Card>
    )}
  </div>
);

// ─── Arbeit ─────────────────────────────────────────────────────────────────

interface WorkProps {
  repair: RepairJob;
  canFinance: boolean;
  /** Present while the next step is "Diagnose stellen". */
  onDiagnose?: () => void;
}

export const RepairWorkTab: React.FC<WorkProps> = ({ repair, canFinance, onDiagnose }) => {
  const hasDiagnosis = Boolean(repair.diagnosis_notes) || repair.estimated_cost != null;
  return (
    <div className="repair-tab-body">
      <h2 className="ui-visually-hidden">Arbeit</h2>
      {!hasDiagnosis ? (
        <EmptyState
          icon="search"
          headingLevel={3}
          title="Noch keine Diagnose"
          body="Befund und Kostenvoranschlag erfassen, bevor die Arbeit beginnt."
          action={onDiagnose ? <Button icon="search" onClick={onDiagnose}>Diagnose stellen</Button> : undefined}
        />
      ) : (
        <>
          {repair.diagnosis_notes && (
            <Card title="Befund" headingLevel={3}>
              <p className="repair-diagnosis">{repair.diagnosis_notes}</p>
            </Card>
          )}
          {canFinance && (
            <Card title="Kosten" headingLevel={3}>
              <dl className="repair-facts">
                <Fact label="Kostenvoranschlag" value={formatEur(repair.estimated_cost)} isMoney />
                <Fact label="Tatsächliche Kosten" value={formatEur(repair.actual_cost)} isMoney />
              </dl>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

// ─── Kunde ──────────────────────────────────────────────────────────────────

interface CustomerProps {
  repair: RepairJob;
  onRepairRefresh: () => void;
}

export const RepairCustomerTab: React.FC<CustomerProps> = ({ repair, onRepairRefresh }) => {
  const name = customerName(repair.customer);
  return (
    <div className="repair-tab-body">
      <h2 className="ui-visually-hidden">Kunde</h2>
      {repair.customer ? (
        <Card
          title="Kundendaten"
          headingLevel={3}
          action={<Link to={`/customers/${repair.customer.id}`}>Zur Kundin / zum Kunden</Link>}
        >
          <dl className="repair-facts">
            <Fact label="Name" value={name} />
            <Fact label="E-Mail" value={repair.customer.email ?? MISSING_VALUE} />
            <Fact label="Telefon" value={repair.customer.phone ?? MISSING_VALUE} />
            <Fact label="Benachrichtigt" value={formatRepairDateTime(repair.customer_notified_at)} />
          </dl>
        </Card>
      ) : (
        <EmptyState icon="user-check" headingLevel={3} title="Laufkunde" body="Diese Reparatur hat keine Kundin und keinen Kunden." />
      )}
      <RepairCustomerUpdatePanel repair={repair} onRepairRefresh={onRepairRefresh} />
    </div>
  );
};

// ─── Verlauf ────────────────────────────────────────────────────────────────
// A repair has no job_id and no event log yet, so the Verlauf is built from
// the repair's own status and timestamps (the order page reads
// /orders/{id}/timeline instead).

const STATUS_ORDER: RepairJobStatus[] = [
  'received',
  'diagnosed',
  'quoted',
  'approved',
  'in_repair',
  'quality_check',
  'ready',
  'picked_up',
];

interface Milestone {
  label: string;
  date?: string | null;
  isDone: boolean;
}

export function repairMilestones(repair: RepairJob): Milestone[] {
  const reached = STATUS_ORDER.indexOf(repair.status);
  const at = (status: RepairJobStatus) => reached >= STATUS_ORDER.indexOf(status);
  return [
    { label: 'Eingang', date: repair.created_at, isDone: true },
    { label: 'Diagnose', isDone: at('diagnosed') },
    { label: 'Angebot', isDone: at('quoted') },
    { label: 'Genehmigt', isDone: at('approved') },
    { label: 'In Arbeit', isDone: at('in_repair') },
    { label: 'Qualitätskontrolle', isDone: at('quality_check') },
    { label: 'Abholbereit', date: repair.actual_completion_date, isDone: at('ready') },
    { label: 'Kunde benachrichtigt', date: repair.customer_notified_at, isDone: Boolean(repair.customer_notified_at) },
    { label: 'Abgeholt', date: repair.picked_up_at, isDone: repair.status === 'picked_up' },
  ];
}

export const RepairHistoryTab: React.FC<{ repair: RepairJob }> = ({ repair }) => (
  <div className="repair-tab-body">
    <h2 className="ui-visually-hidden">Verlauf</h2>
    {repair.status === 'cancelled' && (
      <Card tone="danger">
        <p>Diese Reparatur wurde storniert.</p>
      </Card>
    )}
    <ol className="repair-timeline">
      {repairMilestones(repair).map((m) => (
        <li key={m.label} className={m.isDone ? 'repair-timeline__item repair-timeline__item--done' : 'repair-timeline__item'}>
          <span className="repair-timeline__marker" aria-hidden="true">
            {m.isDone && <Icon name="check" />}
          </span>
          <span className="repair-timeline__label">
            {m.label}
            <span className="ui-visually-hidden">{m.isDone ? ' (erledigt)' : ' (offen)'}</span>
          </span>
          {m.date && <span className="repair-timeline__time">{formatRepairDateTime(m.date)}</span>}
        </li>
      ))}
    </ol>
  </div>
);
