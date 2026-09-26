// Read-only stones of an order for the Übersicht tab (W2-06, DOM-04).
// The backend strips cost and design details by role, so a VIEWER sees
// "3 × Diamant" and the Kundenstein flag only.
//
// W4-03: data through TanStack Query (queryKeys.orders.gemstones), shared
// with the order form (form/GemstoneFields) via `gemstonesQuery`; states via PageState.
import { queryOptions, useQuery } from '@tanstack/react-query';
import { gemstonesApi, type Gemstone } from '../../api/gemstones';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Card, EmptyState, PageState, type PageStateValue } from '../../ui';
import { describeGemstone } from './orderIntakeOptions';

export const GEMSTONES_EMPTY_TITLE = 'Noch keine Steine erfasst.';
const LOAD_ERROR = 'Steine konnten nicht geladen werden.';

/** One request for the stones of an order, shared by list and repeater. */
export const gemstonesQuery = (orderId: number) =>
  queryOptions({
    queryKey: queryKeys.orders.gemstones(orderId),
    queryFn: async (): Promise<Gemstone[]> => {
      try {
        return await gemstonesApi.list(orderId);
      } catch (err: unknown) {
        logError('Gemstones.load', err);
        throw err;
      }
    },
  });

/** Map a gemstones query to a PageState value (loading / error with retry / ready). */
export function gemstonesState(query: {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, LOAD_ERROR),
      retry: () => void query.refetch(),
    };
  }
  return { status: 'ready' };
}

export function GemstoneLines({ stones }: { stones: readonly Gemstone[] }) {
  if (stones.length === 0) {
    return <EmptyState icon="gem" title={GEMSTONES_EMPTY_TITLE} headingLevel={3} />;
  }
  return (
    <ul className="gemstone-list">
      {stones.map((stone) => (
        <li key={stone.id}>{describeGemstone(stone)}</li>
      ))}
    </ul>
  );
}

export function GemstoneList({ orderId }: { orderId: number }) {
  const query = useQuery(gemstonesQuery(orderId));
  return (
    <Card title="Steine" headingLevel={3}>
      <PageState state={gemstonesState(query)} skeleton="list" skeletonCount={2}>
        <GemstoneLines stones={query.data ?? []} />
      </PageState>
    </Card>
  );
}

export default GemstoneList;
