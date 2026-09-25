// Soll/Ist: estimated vs. actual for a finished order (Arbeit tab; the
// parent gates it by canViewFinancials and a finished status).
//
// W4-03: the comparison and the "is there already an invoice" check run as
// TanStack queries (queryKeys.orders.comparison, queryKeys.invoices.recent);
// "Rechnung erstellen" is a mutation that invalidates both roots. Metrics
// and activities render in DataTable; deviations are text (sign, arrow,
// "auffällig"), never colour alone.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { invoicesApi, ordersApi } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import type { ActivityBreakdownComparison, ComparisonMetric } from '../../types';
import {
  Button,
  ButtonLink,
  Card,
  DataTable,
  EmptyState,
  PageState,
  type Column,
  type PageStateValue,
} from '../../ui';

interface SollIstTabProps {
  orderId: number;
  orderStatus: string;
}

const COMPLETED_STATUSES = ['completed', 'delivered'];
const RECENT_INVOICE_LIMIT = 5;
const INVOICE_DUE_DAYS = 30;
const EMPTY_VALUE = '—';

const NUMBER_1 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NUMBER_0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });

function formatPct(pct: number | null): string {
  if (pct === null) return EMPTY_VALUE;
  const sign = pct > 0 ? '+' : '';
  const arrow = pct > 0 ? ' ↑' : pct < 0 ? ' ↓' : '';
  return `${sign}${NUMBER_1.format(pct)} %${arrow}`;
}

function deviationText(pct: number | null, isSignificant: boolean): string {
  const base = formatPct(pct);
  return isSignificant ? `${base} (auffällig)` : base;
}

type MetricUnit = 'h' | 'g' | 'eur';

interface MetricRow {
  key: string;
  label: string;
  unit: MetricUnit;
  metric: ComparisonMetric;
}

function formatMetricValue(value: number | null, unit: MetricUnit): string {
  if (value === null) return EMPTY_VALUE;
  if (unit === 'eur') return formatEur(value);
  return `${NUMBER_1.format(value)} ${unit}`;
}

const METRIC_COLUMNS: Column<MetricRow>[] = [
  { key: 'label', header: 'Kennzahl', render: (row) => row.label },
  {
    key: 'soll',
    header: 'Soll',
    numeric: true,
    align: 'end',
    render: (row) => (
      <span className={row.unit === 'eur' ? MONEY_CLASS : undefined}>
        {formatMetricValue(row.metric.soll, row.unit)}
      </span>
    ),
  },
  {
    key: 'ist',
    header: 'Ist',
    numeric: true,
    align: 'end',
    render: (row) => (
      <span className={row.unit === 'eur' ? MONEY_CLASS : undefined}>
        {formatMetricValue(row.metric.ist, row.unit)}
      </span>
    ),
  },
  {
    key: 'deviation',
    header: 'Abweichung',
    numeric: true,
    align: 'end',
    render: (row) => deviationText(row.metric.deviation_percent, row.metric.is_significant),
  },
];

const ACTIVITY_COLUMNS: Column<ActivityBreakdownComparison>[] = [
  { key: 'activity', header: 'Aktivität', render: (row) => row.activity_name },
  { key: 'category', header: 'Kategorie', hideBelow: 'tablet', render: (row) => row.activity_category },
  {
    key: 'soll',
    header: 'Soll (min)',
    numeric: true,
    align: 'end',
    render: (row) => (row.estimated_minutes !== null ? NUMBER_0.format(row.estimated_minutes) : EMPTY_VALUE),
  },
  {
    key: 'ist',
    header: 'Ist (min)',
    numeric: true,
    align: 'end',
    render: (row) => NUMBER_0.format(row.actual_minutes),
  },
  {
    key: 'deviation',
    header: 'Abweichung',
    numeric: true,
    align: 'end',
    render: (row) => deviationText(row.deviation_percent, row.is_significant),
  },
  { key: 'entries', header: 'Einträge', numeric: true, align: 'end', render: (row) => row.entry_count },
];

type RecentInvoiceList = RecentInvoice[] | null;

/** The invoice list is best-effort: a failure means "unknown", not an error. */
async function fetchRecentInvoiceItems(): Promise<RecentInvoiceList> {
  try {
    const response = await invoicesApi.getInvoices({ limit: RECENT_INVOICE_LIMIT });
    const raw = response as unknown;
    if (Array.isArray(raw)) return raw as RecentInvoiceList;
    return (response.items ?? []) as RecentInvoiceList;
  } catch (err: unknown) {
    logError('SollIstTab.loadInvoices', err);
    return null;
  }
}

function useCreateInvoice(orderId: number) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => {
      const due = new Date();
      due.setDate(due.getDate() + INVOICE_DUE_DAYS);
      return invoicesApi.createFromOrder({ order_id: orderId, due_date: due.toISOString() });
    },
    onSuccess: async (invoice) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.invoices.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.orders.detail(orderId) }),
      ]);
      showToast(`Rechnung ${invoice.invoice_number} erstellt. Sie steht jetzt unter Rechnungen.`, 'success');
    },
    onError: (err: unknown) =>
      showToast(getErrorMessage(err, 'Rechnung konnte nicht erstellt werden.'), 'error'),
  });
}

type RecentInvoice = { id: number; order_id?: number | null };

function InvoiceAction({ orderId, invoices }: { orderId: number; invoices: RecentInvoice[] | null | undefined }) {
  const create = useCreateInvoice(orderId);
  // Still loading: offer nothing yet. A failed list (null) counts as
  // "no invoice found" and offers the button, as before.
  if (invoices === undefined) return null;
  const existing = invoices?.find((inv) => inv.order_id === orderId);
  if (existing) {
    return (
      <p className="soll-ist-invoice-action">
        Rechnung vorhanden (Nr.&nbsp;{existing.id}).{' '}
        <ButtonLink to="/invoices" variant="ghost">
          Rechnungen öffnen
        </ButtonLink>
      </p>
    );
  }
  return (
    <div className="soll-ist-invoice-action">
      <Button variant="primary" icon="receipt" loading={create.isPending} onClick={() => create.mutate()}>
        Rechnung erstellen
      </Button>
    </div>
  );
}

export function SollIstTab({ orderId, orderStatus }: SollIstTabProps) {
  const isEligible = COMPLETED_STATUSES.includes(orderStatus);
  const comparison = useQuery({
    queryKey: queryKeys.orders.comparison(orderId),
    queryFn: () => ordersApi.getComparison(orderId),
    enabled: isEligible,
  });
  // In parallel with the comparison; decides "Rechnung erstellen" vs. "vorhanden".
  const invoices = useQuery({
    queryKey: queryKeys.invoices.recent(RECENT_INVOICE_LIMIT),
    queryFn: fetchRecentInvoiceItems,
    enabled: isEligible,
  });

  if (!isEligible) {
    return (
      <EmptyState
        icon="circle-help"
        headingLevel={3}
        title="Soll/Ist gibt es erst für abgeschlossene Aufträge."
        body="Den Status auf „Fertiggestellt“ oder „Ausgeliefert“ setzen, um den Vergleich zu sehen."
      />
    );
  }

  const data = comparison.data;
  const state: PageStateValue = comparison.isPending
    ? { status: 'loading' }
    : comparison.isError
      ? {
          status: 'error',
          error: getErrorMessage(comparison.error, 'Vergleichsdaten konnten nicht geladen werden.'),
          retry: () => void comparison.refetch(),
        }
      : data
        ? { status: 'ready' }
        : { status: 'empty' };

  const metrics: MetricRow[] = data
    ? [
        { key: 'hours', label: 'Arbeitsstunden', unit: 'h', metric: data.hours },
        { key: 'weight', label: 'Materialgewicht', unit: 'g', metric: data.material_weight },
        { key: 'material-cost', label: 'Materialkosten', unit: 'eur', metric: data.material_cost },
        { key: 'total-price', label: 'Gesamtpreis', unit: 'eur', metric: data.total_price },
      ]
    : [];

  return (
    <PageState
      state={state}
      skeleton="detail"
      skeletonCount={2}
      empty={{ icon: 'circle-help', title: 'Keine Vergleichsdaten vorhanden.', headingLevel: 3 }}
    >
      {data && (
        <div className="soll-ist">
          {data.overall_accuracy_score !== null && (
            <p className="soll-ist-accuracy">
              Genauigkeit: <strong className="tabular-nums">{NUMBER_0.format(data.overall_accuracy_score)} %</strong>
            </p>
          )}
          {data.has_significant_deviation && (
            <Card tone="waiting">
              <p>Mindestens eine Kennzahl weicht um mehr als 20&nbsp;% ab.</p>
            </Card>
          )}
          <DataTable
            caption="Kennzahlen Soll und Ist"
            showCaption
            rows={metrics}
            columns={METRIC_COLUMNS}
            getRowKey={(row) => row.key}
          />
          <DataTable
            caption="Aufschlüsselung nach Aktivität"
            showCaption
            rows={data.activity_breakdown}
            columns={ACTIVITY_COLUMNS}
            getRowKey={(row) => row.activity_id}
            empty={{ icon: 'clock', title: 'Keine Aktivitätsdaten vorhanden.', headingLevel: 3 }}
          />
          <InvoiceAction orderId={orderId} invoices={invoices.data} />
        </div>
      )}
    </PageState>
  );
}

export default SollIstTab;
