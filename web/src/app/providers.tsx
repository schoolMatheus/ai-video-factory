import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 5_000,
      },
    },
  });
}

export function Providers({
  children,
  client,
}: {
  children: ReactNode;
  client?: QueryClient;
}) {
  return (
    <QueryClientProvider client={client ?? createQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}
