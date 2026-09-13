/** React binding for the singleton player: question playback state per page. */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ApiClient } from "../api/client";
import { createTtsPlayer } from "./player";
import type { PlayerState, TtsRequest } from "./player";

export interface UseTtsPlaybackOptions {
  client: ApiClient;
  voice?: string | null;
  playerFactory?: typeof createTtsPlayer;
}

export interface TtsPlaybackController {
  state: PlayerState;
  error: string | null;
  activeKey: string | null;
  speak(text: string): Promise<void>;
  stop(): void;
}

export function useTtsPlayback({
  client,
  voice = null,
  playerFactory = createTtsPlayer,
}: UseTtsPlaybackOptions): TtsPlaybackController {
  const [state, setState] = useState<PlayerState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const player = useMemo(() => {
    const instance = playerFactory({
      load: async (request: TtsRequest) => {
        const view = await client.synthesizeSpeech({ text: request.text, voice: request.voice ?? null });
        return client.fetchTtsAudio(view.url);
      },
    });
    return instance;
  }, [client, playerFactory]);

  useEffect(() => () => player.dispose(), [player]);

  const speak = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      if (activeKey === trimmed && player.state === "playing") {
        player.stop();
        setActiveKey(null);
        setState("idle");
        return;
      }
      await player.primeFromGesture();
      setActiveKey(trimmed);
      await player.play({ text: trimmed, voice, cacheKey: `${voice ?? "default"}|${trimmed}` });
      setState(player.state);
      setError(player.error);
    },
    [activeKey, player, voice],
  );

  const stop = useCallback(() => {
    player.stop();
    setActiveKey(null);
    setState("idle");
  }, [player]);

  return { state, error, activeKey, speak, stop };
}
