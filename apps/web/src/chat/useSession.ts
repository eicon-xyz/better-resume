/** Session state: who am I, and how do I sign in (dev session until M2). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import type { ApiClient } from "../api/client";
import type { Principal } from "../api/types";

export const sessionKeys = {
  me: ["auth", "me"] as const,
};

export interface SessionState {
  principal: Principal | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  query: UseQueryResult<Principal>;
  login: UseMutationResult<Principal, Error, string>;
}

export function useSession(client: ApiClient): SessionState {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: sessionKeys.me,
    queryFn: () => client.currentPrincipal(),
    retry: false,
  });

  const login = useMutation({
    mutationFn: (userId: string) => client.devLogin({ user_id: userId, roles: [] }),
    onSuccess: (principal) => {
      queryClient.setQueryData(sessionKeys.me, principal);
      void queryClient.invalidateQueries();
    },
  });

  return {
    principal: query.data ?? null,
    isAuthenticated: Boolean(query.data),
    isLoading: query.isLoading,
    query,
    login,
  };
}
