/** Merge rules between server history (Query) and local run state (store). */

import type { ChatMessageView } from "../api/types";
import type { ChatMessage } from "./store";

export function toLocalMessage(view: ChatMessageView): ChatMessage {
  return {
    key: view.client_message_id ?? `server:${view.seq}`,
    role: view.role === "user" ? "user" : "assistant",
    content: view.content,
    reasoning: view.reasoning ?? "",
    streaming: false,
    error: view.error_message ?? null,
    clientMessageId: view.client_message_id ?? null,
    seq: view.seq,
  };
}

/**
 * Server history is the source of truth; local messages are only kept while they are not
 * represented there yet. User turns dedupe exactly by client_message_id; an assistant draft
 * is dropped once the refetched history contains the same answer.
 */
export function mergeHistory(server: ChatMessageView[], local: ChatMessage[]): ChatMessage[] {
  const serverMessages = server.map(toLocalMessage);

  const persistedClientIds = new Set(
    serverMessages
      .map((message) => message.clientMessageId)
      .filter((value): value is string => Boolean(value)),
  );
  const serverAssistantContent = new Set(
    serverMessages.filter((message) => message.role === "assistant").map((message) => message.content),
  );

  const pending = local.filter((message) => {
    if (message.clientMessageId && persistedClientIds.has(message.clientMessageId)) {
      return false; // optimistic user turn already stored on the server
    }
    if (message.role === "assistant" && !message.streaming && serverAssistantContent.has(message.content)) {
      return false; // draft already replayed from history
    }
    return true;
  });

  return [...serverMessages, ...pending];
}
