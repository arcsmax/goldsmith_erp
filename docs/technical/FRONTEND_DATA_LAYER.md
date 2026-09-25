# Frontend data layer (TanStack Query)

Status 2026-09-25, W3-03 (review 04 section F item 3). Server state in the staff app goes through
`@tanstack/react-query`. Reference pages: `OrdersPage`, `DashboardPage` (with
`components/dashboard/*`) and `CustomersPage`. The other pages still use `useEffect` + `useState`
and the refetch bus, and move over one page at a time.

## Pieces

| File | Role |
|---|---|
| `src/lib/queryClient.ts` | `createAppQueryClient()`: `staleTime` 30 s, one retry (none on 4xx), refetch on window focus, no mutation retries |
| `src/lib/queryProvider.tsx` | `AppQueryProvider`: one client per session, mounted inside `ProtectedRoute` in `App.tsx`. Unmounting on logout clears the cache. Devtools load in development builds only |
| `src/api/queryKeys.ts` | The query-key factory. Every key starts with its domain root (`['orders']`, `['customers']`, `['dashboard']`, `['timer']`, ...) |
| `src/api/paged.ts` | Typed fetchers for `Page[T]` endpoints (`fetchPage`, `pagedApi.orders`), `compactParams`, `pageInfo` |
| `src/lib/realtimeInvalidation.ts` | The only place where WebSocket hints become `invalidateQueries` |
| `src/test/queryWrapper.tsx` | `renderWithQuery(ui, { route })` and `createTestQueryClient()` for Vitest |
| `src/components/Pager.tsx` | Previous and next buttons for paged lists (src/ui `Button`) |

`/portal` and `/login` have no QueryClient. Customer data never lands in a cache that outlives the
session.

## Adding a query

1. Add the key to `queryKeys.ts` under its domain root. Don't build keys inline in components.
2. Call the existing `api/*.ts` function in `queryFn`. Pass `signal` when the function accepts it.
3. Use the result's `isPending`, `isError`, `data` and `refetch` in place of your own flags. For a
   whole list or page, map them to `PageState` (`loading`, `error` with `retry`, `empty`, `ready`).

```ts
const query = useQuery({
  queryKey: queryKeys.dashboard.today(),
  queryFn: () => dashboardApi.getToday(),
});
```

When two components need the same data, give both the same `queryOptions(...)`. Then they share
one request. Example: `components/dashboard/dashboardQueries.ts`, where the KPIs and the alerts
share one `GET /orders/?limit=100`.

When a failure needs logging with context, log inside `queryFn` and rethrow (see `fetchToday` in
`TodayView.tsx`). Don't swallow the error: the query needs it to show the error state.

## Pagination (Page[T])

A backend list returns `{ items, total, limit, offset, next_offset }` when the request carries
`offset`. Without `offset` it returns the deprecated plain list (header `X-Deprecated-List`). See
`src/goldsmith_erp/models/pagination.py`.

- `fetchPage(path, params)` always sends `offset`. It throws if the answer has no envelope, so a
  list that isn't paged yet can't show up as an empty page.
- The types come from `api/generated/schema.d.ts`: `PageParams<'/api/v1/orders/'>` holds the
  endpoint's query params (filters, `q`), and `PageItem<...>` is the row type.
- Put the params object in the key (`queryKeys.orders.page(params)`). Run it through
  `compactParams` first, so empty filters don't split the cache.
- Use `placeholderData: keepPreviousData` so the old page stays visible while the next one loads.
- Take the page number, page count and "Weiter" from the envelope (`pageInfo`, `next_offset`),
  never from the rows on screen.
- Search: debounce the input with `useDebouncedValue` (300 ms), trim it and cap it at 100
  characters (the backend's `q` limit). A new filter starts again at page 1.
- To add a new paged endpoint, add a line to `pagedApi`. The path must answer with a `Page_…_`
  schema.

Customers aren't paged on the server yet. `CustomersPage` keeps the legacy `skip`/`limit` call
inside `useQuery` and shows "Weiter" while a page comes back full.

## Mutations and invalidation

```ts
const remove = useMutation({
  mutationFn: (id: number) => ordersApi.delete(id),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
    showToast('Auftrag gelöscht', 'success');
  },
  onError: (err) => showToast(getErrorMessage(err, 'Auftrag konnte nicht gelöscht werden'), 'error'),
});
```

- Invalidate the domain root (`queryKeys.orders.all`). That covers the list, every page and the
  details. Also invalidate `queryKeys.dashboard.all` when the change shows up on "Heute".
- Use `mutation.isPending` in place of an `isSubmitting` flag.
- If a form dialog expects `onSubmit` to throw (`CustomerFormModal`), call `mutateAsync` and
  rethrow with `getErrorMessage`.

## Realtime

`WebSocketProvider` passes server hints on. `RealtimeInvalidation` (mounted in `App.tsx`) maps them:

| Channel | Invalidated roots |
|---|---|
| `order_updates` | `['orders']`, `['dashboard']`, `['handoffs']`, `['calendar']` |
| `time_tracking_updates` | `['timer']`, `['dashboard']` |
| `notifications` | `['notifications']`, `['handoffs']` |

After a reconnect the provider sends a `resync` per channel, so every root is invalidated.
Invalidation refetches only the queries that are mounted. The others refetch when they mount
next.

The refetch bus (`lib/refetchBus.ts`, `useRefetchOn`) keeps working for pages that aren't migrated
yet. **A migrated page must not also call `useRefetchOn`**, or it refetches twice. When a new
screen needs a new channel or root, change `REALTIME_INVALIDATIONS`. Don't write a separate
`useRealtime` handler.

## When to keep a context

Keep a React context for client state that isn't a copy of the server: `AuthContext` (session),
`ToastContext`, the confirm dialog, `ScannerContext` (device state), theme. Server data (orders,
customers, time entries, notifications) belongs in queries. Once `TimeTrackingContext` and
`OrderContext` are migrated, they keep only UI state, or they go away. Don't copy query data into
a context or into `useState`. Derive it during render.

## Testing

```tsx
const { client } = renderWithQuery(<OrdersPage />, { route: '/orders?status=in_progress' });
await act(() => invalidateForChannel(client, 'order_updates')); // realtime hint
```

- Every render gets a fresh client with no retries and `staleTime: 0`.
- Mock `api/client` (or the `api/*` module) and assert on the request params. Examples:
  `OrdersPage.query.test.tsx`, `CustomersPage.query.test.tsx`.
- Pin request budgets with a call count per URL (`DashboardPage.requests.test.tsx`).

## Migration checklist (per page)

1. Replace the `useEffect` fetch and the `isLoading`/`error` state with `useQuery` and a key from
   `queryKeys`.
2. Remove `useRefetchOn` and check that the root is in `REALTIME_INVALIDATIONS`.
3. Turn create, update and delete into `useMutation` with root invalidation.
4. Use `pagedApi` for lists whose endpoint returns `Page[T]`.
5. Wrap the page's tests in `renderWithQuery`.

Still to migrate: RepairsPage, RepairDetailPage, OrderDetailPage, QuotesPage, InvoicesPage,
MaterialsPage, MetalInventoryPage, TimeTrackingPage and TimeTrackingContext, CustomerDetailPage,
AdminSystemPage, ConsultationsPage, and the unused
`DeadlinesWidget`.
