import { QueryClient } from "@tanstack/react-query";

/** App defaults: no retry storms for a demo UI, no refetch noise while typing. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}
