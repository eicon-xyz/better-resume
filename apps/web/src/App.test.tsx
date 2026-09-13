import { render, screen } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { ApiClient } from "./api/client";
import { App } from "./App";

function fakeClient(): ApiClient {
  return {
    currentPrincipal: () =>
      Promise.resolve({ user_id: "u1", roles: [] }),
    listChatSessions: () => Promise.resolve([]),
    listChatMessages: () => Promise.resolve([]),
    listModels: () => Promise.resolve([]),
  } as unknown as ApiClient;
}

describe("App", () => {
  it("renders the chat shell for an authenticated visitor", async () => {
    render(<App client={fakeClient()} queryClient={new QueryClient()} />);

    expect(await screen.findByRole("heading", { name: "better-resume" })).toBeInTheDocument();
    expect(screen.getByText("还没有消息")).toBeInTheDocument();
  });
});
