// UsageHistoryPanel — metal consumption history from GET /metal-inventory/usage
// (legacy plain list, W4-03). Filterable by metal type; order ids link to the
// order detail page. A booking invalidates the ['metal-inventory'] root, so
// the panel refreshes without a refresh key.
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { MaterialUsageRead, MetalType } from '../../types';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MISSING_VALUE, MONEY_CLASS } from '../../lib/format';
import { Button, DataTable, Field, type Column, type PageStateValue } from '../../ui';
import { formatPreciseWeight, metalLabel, METAL_TYPES } from './metalLabels';
import { usageQuery } from './metalQueries';

const COSTING_METHOD_LABELS: Record<string, string> = {
  fifo: 'FIFO',
  lifo: 'LIFO',
  average: 'Durchschnitt',
  specific: 'Spezifisch',
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const COLUMNS: Column<MaterialUsageRead>[] = [
  { key: 'used_at', header: 'Datum', render: (r) => <span className="ui-num">{formatDateTime(r.used_at)}</span> },
  {
    key: 'order',
    header: 'Auftrag',
    render: (r) => <Link to={`/orders/${r.order_id}`}>Auftrag #{r.order_id}</Link>,
  },
  { key: 'metal', header: 'Metalltyp', render: (r) => metalLabel(r.metal_type) },
  { key: 'weight', header: 'Gewicht', numeric: true, align: 'end', render: (r) => formatPreciseWeight(r.weight_used_g) },
  {
    key: 'price',
    header: 'Preis/g',
    numeric: true,
    align: 'end',
    hideBelow: 'tablet',
    render: (r) => <span className={MONEY_CLASS}>{formatEur(r.price_per_gram_at_time)}</span>,
  },
  {
    key: 'cost',
    header: 'Kosten',
    numeric: true,
    align: 'end',
    render: (r) => <span className={MONEY_CLASS}>{formatEur(r.cost_at_time)}</span>,
  },
  {
    key: 'method',
    header: 'Methode',
    hideBelow: 'tablet',
    render: (r) => COSTING_METHOD_LABELS[r.costing_method] ?? r.costing_method,
  },
  { key: 'batch', header: 'Charge', hideBelow: 'tablet', render: (r) => `#${r.metal_purchase_id}` },
  { key: 'notes', header: 'Notiz', hideBelow: 'tablet', render: (r) => r.notes ?? MISSING_VALUE },
];

interface UsageHistoryPanelProps {
  /** Opens the booking dialog from the empty state (next action). */
  onRecordUsage?: () => void;
}

export const UsageHistoryPanel: React.FC<UsageHistoryPanelProps> = ({ onRecordUsage }) => {
  const [filterMetalType, setFilterMetalType] = useState<MetalType | ''>('');
  const query = useQuery({ ...usageQuery(filterMetalType), placeholderData: keepPreviousData });
  const records = query.data ?? [];

  let state: PageStateValue = { status: records.length ? 'ready' : 'empty' };
  if (query.isPending) state = { status: 'loading' };
  if (query.isError && !query.data) {
    state = {
      status: 'error',
      error: getErrorMessage(query.error, 'Verbrauchshistorie konnte nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }

  return (
    <section className="usage-history" aria-labelledby="usage-history-title">
      <div className="usage-history__header">
        <h2 id="usage-history-title">Verbrauchshistorie</h2>
        <Field label="Metalltyp" name="usage-filter-metal">
          <select value={filterMetalType} onChange={(e) => setFilterMetalType(e.target.value as MetalType | '')}>
            <option value="">Alle Metalle</option>
            {METAL_TYPES.map((value) => (
              <option key={value} value={value}>
                {metalLabel(value)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <DataTable
        rows={records}
        columns={COLUMNS}
        getRowKey={(r) => r.id}
        caption="Verbrauchshistorie"
        state={state}
        empty={{
          icon: 'inbox',
          title: filterMetalType ? 'Kein Verbrauch für diesen Metalltyp' : 'Noch kein Verbrauch erfasst',
          action: onRecordUsage ? (
            <Button variant="secondary" onClick={onRecordUsage}>
              Verbrauch erfassen
            </Button>
          ) : undefined,
        }}
      />
    </section>
  );
};

