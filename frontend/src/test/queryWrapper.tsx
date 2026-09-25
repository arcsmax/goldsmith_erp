// QueryClientProvider test wrapper (W3-03).
//
//   const { client } = renderWithQuery(<OrdersPage />, { route: '/orders' });
//
// Each call gets a fresh client (no cache shared between tests), no retries
// (a failing request shows the error state at once) and staleTime 0 so an
// invalidation always refetches.
import React from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function QueryWrapper({
  client,
  children,
}: {
  client: QueryClient;
  children: React.ReactNode;
}): React.ReactElement {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

interface RenderWithQueryOptions extends Omit<RenderOptions, 'wrapper'> {
  client?: QueryClient;
  /** Wrap in a MemoryRouter at this entry; pass null to skip the router. */
  route?: string | null;
}

export function renderWithQuery(
  ui: React.ReactElement,
  { client = createTestQueryClient(), route = '/', ...options }: RenderWithQueryOptions = {},
): RenderResult & { client: QueryClient } {
  const tree =
    route === null ? ui : <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>;
  const result = render(<QueryWrapper client={client}>{tree}</QueryWrapper>, options);
  return {
    ...result,
    client,
    rerender: (next: React.ReactNode) =>
      result.rerender(
        <QueryWrapper client={client}>
          {route === null ? next : <MemoryRouter initialEntries={[route]}>{next}</MemoryRouter>}
        </QueryWrapper>,
      ),
  };
}
