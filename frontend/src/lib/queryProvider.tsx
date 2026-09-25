/**
 * AppQueryProvider — mounts the per-session QueryClient (W3-03).
 *
 * Mounted inside ProtectedRoute in App.tsx, never for /login or /portal.
 * The client lives as long as this provider: logout unmounts the shell and
 * the cache is cleared. React Query Devtools load in development only; the
 * import.meta.env.DEV ternary lets Vite drop the chunk from production.
 */
import React, { Suspense, lazy, useEffect, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createAppQueryClient } from './queryClient';

const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({ default: m.ReactQueryDevtools })),
    )
  : null;

export const AppQueryProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [client] = useState(createAppQueryClient);

  // Drop every cached response when the session shell unmounts (logout).
  useEffect(() => () => client.clear(), [client]);

  return (
    <QueryClientProvider client={client}>
      {children}
      {ReactQueryDevtools && (
        <Suspense fallback={null}>
          <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
        </Suspense>
      )}
    </QueryClientProvider>
  );
};
