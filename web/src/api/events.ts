import { API_PREFIX } from "./types";
import type { EventView } from "./types";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "offline";

export interface StreamHandlers {
  onEvent: (event: EventView) => void;
  onStatus: (status: StreamStatus) => void;
  onSnapshotRequired?: () => void;
}

/** Read-only SSE subscription that resumes from the last received event id. */
export class ProductionEventStream {
  private source: EventSource | null = null;
  private lastEventId: string | null = null;
  private retry = 0;
  private closed = false;

  constructor(
    private readonly productionId: string,
    private readonly handlers: StreamHandlers,
    private readonly cursor: string | null,
  ) {}

  connect(): void {
    if (this.closed) return;
    this.handlers.onStatus(this.retry === 0 ? "connecting" : "reconnecting");
    const url = new URL(
      `${API_PREFIX}/productions/${encodeURIComponent(this.productionId)}/stream`,
      window.location.origin,
    );
    const source = new EventSource(url.toString(), { withCredentials: true });
    this.source = source;

    source.onopen = () => {
      this.retry = 0;
      this.handlers.onStatus("live");
    };
    source.onmessage = (message: MessageEvent<string>) => {
      this.accept(message);
    };
    source.addEventListener("heartbeat", () => {
      // A heartbeat keeps the connection alive; it is not production progress.
    });
    source.addEventListener("end", () => {
      source.close();
      if (!this.closed) this.scheduleReconnect();
    });
    source.addEventListener("connection.reset_required", () => {
      this.handlers.onSnapshotRequired?.();
    });
    source.onerror = () => {
      source.close();
      if (!this.closed) this.scheduleReconnect();
    };
  }

  private accept(message: MessageEvent<string>): void {
    if (message.lastEventId) this.lastEventId = message.lastEventId;
    try {
      const parsed = JSON.parse(message.data) as Record<string, unknown>;
      const event: EventView = {
        id: message.lastEventId || this.lastEventId || "stream-event",
        production_id: this.productionId,
        type: "production.updated",
        timestamp: null,
        scope: "production",
        severity: "info",
        attempt: null,
        payload: parsed,
      };
      this.handlers.onEvent(event);
    } catch {
      // Malformed frames are ignored; the snapshot remains authoritative.
    }
  }

  private scheduleReconnect(): void {
    this.retry += 1;
    this.handlers.onStatus(this.retry >= 3 ? "offline" : "reconnecting");
    if (this.retry >= 3) {
      this.handlers.onSnapshotRequired?.();
      return;
    }
    window.setTimeout(() => this.connect(), Math.min(500 * 2 ** this.retry, 4000));
  }

  /** Resume token: server-side cursor for the snapshot, last id after connect. */
  resumeCursor(): string | null {
    return this.lastEventId ?? this.cursor;
  }

  close(): void {
    this.closed = true;
    this.source?.close();
    this.source = null;
  }
}
