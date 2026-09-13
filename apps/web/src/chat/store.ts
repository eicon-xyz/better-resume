/** Chat run state only. Server state belongs to TanStack Query (§5.5 of the analysis). */

import { create } from "zustand";

export interface ChatMessage {
  /** Stable local key: client_message_id for user turns, request id for assistant drafts. */
  key: string;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  streaming: boolean;
  error: string | null;
  clientMessageId: string | null;
  seq: number | null;
}

export interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  streaming: boolean;
  activeRequestId: string | null;
  error: string | null;

  openSession(sessionId: string | null): void;
  appendUser(input: { clientMessageId: string; content: string }): void;
  startAssistant(requestId: string): void;
  appendContent(requestId: string, text: string): void;
  appendReasoning(requestId: string, text: string): void;
  finishAssistant(requestId: string, error?: string | null): void;
  setError(message: string | null): void;
  reset(): void;
}

const EMPTY: Pick<ChatState, "sessionId" | "messages" | "streaming" | "activeRequestId" | "error"> = {
  sessionId: null,
  messages: [],
  streaming: false,
  activeRequestId: null,
  error: null,
};

function patchMessage(
  messages: ChatMessage[],
  key: string,
  patch: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) => (message.key === key ? patch(message) : message));
}

export const useChatStore = create<ChatState>((set) => ({
  ...EMPTY,

  openSession: (sessionId) => {
    set({ ...EMPTY, sessionId });
  },

  appendUser: ({ clientMessageId, content }) => {
    set((state) => ({
      messages: [
        ...state.messages,
        {
          key: clientMessageId,
          role: "user",
          content,
          reasoning: "",
          streaming: false,
          error: null,
          clientMessageId,
          seq: null,
        },
      ],
      error: null,
    }));
  },

  startAssistant: (requestId) => {
    set((state) => ({
      messages: [
        ...state.messages,
        {
          key: requestId,
          role: "assistant",
          content: "",
          reasoning: "",
          streaming: true,
          error: null,
          clientMessageId: null,
          seq: null,
        },
      ],
      streaming: true,
      activeRequestId: requestId,
      error: null,
    }));
  },

  // Second guard after the renderer: a finished request must never grow again (§7.2).
  appendContent: (requestId, text) => {
    set((state) => ({
      messages: patchMessage(state.messages, requestId, (message) =>
        message.streaming ? { ...message, content: message.content + text } : message,
      ),
    }));
  },

  appendReasoning: (requestId, text) => {
    set((state) => ({
      messages: patchMessage(state.messages, requestId, (message) =>
        message.streaming ? { ...message, reasoning: message.reasoning + text } : message,
      ),
    }));
  },

  finishAssistant: (requestId, error = null) => {
    set((state) => ({
      messages: patchMessage(state.messages, requestId, (message) => ({
        ...message,
        streaming: false,
        error,
      })),
      streaming: false,
      activeRequestId: null,
      error: error ?? state.error,
    }));
  },

  setError: (message) => {
    set({ error: message });
  },

  reset: () => {
    set({ ...EMPTY });
  },
}));
