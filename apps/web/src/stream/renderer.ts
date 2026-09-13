/**
 * Stream renderer: turn network bursts into a typewriter rhythm.
 *
 * Ports the old `streamLimiter.ts` idea (40ms / 12 chars) and keeps it testable with fake
 * timers: two independent channels (content, reasoning), stale-chunk rejection and an
 * explicit stop() so a cancelled request can never write into a newer message.
 */

export type StreamChannel = "content" | "reasoning";

export interface StreamRendererOptions {
  onContent?(text: string): void;
  onReasoning?(text: string): void;
  onDone?(): void;
  /** Called when a chunk is discarded because the request is no longer active. */
  onStale?(): void;
  /** Window length; 40ms matches the behaviour users know from the old build. */
  intervalMs?: number;
  /** Characters emitted per window. */
  charsPerTick?: number;
  /** Owner of "is this request still the current one?". */
  isActive?(): boolean;
}

export interface StreamRenderer {
  push(channel: StreamChannel, text: string): void;
  flush(): void;
  done(): void;
  stop(): void;
  pending(): Record<StreamChannel, number>;
}

interface ChannelOptions {
  intervalMs: number;
  charsPerTick: number;
  active(options: StreamRendererOptions): boolean;
}

class Channel {
  private buffer = "";
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly emit: (text: string) => void,
    private readonly options: ChannelOptions,
    private readonly rendererOptions: StreamRendererOptions,
  ) {}

  push(text: string): void {
    if (!text) return;
    if (!this.options.active(this.rendererOptions)) {
      this.rendererOptions.onStale?.();
      return;
    }
    this.buffer += text;
    this.schedule();
  }

  flush(): void {
    this.clearTimer();
    if (!this.buffer) return;
    const out = this.buffer;
    this.buffer = "";
    this.emit(out);
  }

  stop(): void {
    this.clearTimer();
    this.buffer = "";
  }

  size(): number {
    return this.buffer.length;
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private schedule(): void {
    if (this.timer !== null) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.tick();
    }, this.options.intervalMs);
  }

  private tick(): void {
    if (!this.buffer) return;
    if (!this.options.active(this.rendererOptions)) {
      this.buffer = "";
      this.rendererOptions.onStale?.();
      return;
    }
    const out = this.buffer.slice(0, this.options.charsPerTick);
    this.buffer = this.buffer.slice(this.options.charsPerTick);
    this.emit(out);
    if (this.buffer) {
      this.schedule();
    }
  }
}

export function createStreamRenderer(options: StreamRendererOptions = {}): StreamRenderer {
  const intervalMs = options.intervalMs ?? 40;
  const charsPerTick = options.charsPerTick ?? 12;
  const active = (current: StreamRendererOptions): boolean =>
    current.isActive ? current.isActive() : true;

  const channelOptions: ChannelOptions = { intervalMs, charsPerTick, active };
  const content = new Channel((text) => options.onContent?.(text), channelOptions, options);
  const reasoning = new Channel((text) => options.onReasoning?.(text), channelOptions, options);

  return {
    push(channel, text) {
      if (channel === "content") content.push(text);
      else reasoning.push(text);
    },
    flush() {
      content.flush();
      reasoning.flush();
    },
    done() {
      content.flush();
      reasoning.flush();
      options.onDone?.();
    },
    stop() {
      content.stop();
      reasoning.stop();
    },
    pending() {
      return { content: content.size(), reasoning: reasoning.size() };
    },
  };
}
