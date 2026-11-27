// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductionEventStream } from "./events";
import type { EventView } from "./types";

class CapturingEventSource {
  static instances: CapturingEventSource[] = [];
  readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(
    readonly url: string,
    readonly options?: { withCredentials?: boolean },
  ) {
    CapturingEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(type, listener);
  }

  emit(type: string, data: string, lastEventId = ""): void {
    const handler = this.listeners.get(type) ?? (type === "message" ? this.onmessage : undefined);
    handler?.call(this, new MessageEvent(type, { data, lastEventId }));
  }

  close(): void {
    this.closed = true;
  }
}

const EVENT_TYPES = ["stage.started", "stage.completed", "stage.failed", "production.updated"];

describe("ProductionEventStream", () => {
  beforeEach(() => {
    CapturingEventSource.instances.length = 0;
    vi.stubGlobal("EventSource", CapturingEventSource);
    vi.useRealTimers();
  });

  it("entrega eventos nomeados com tipo, id e payload reais", () => {
    const received: EventView[] = [];
    const stream = new ProductionEventStream(
      "prod-1",
      { onEvent: (event) => received.push(event), onStatus: () => undefined },
      "server-cursor",
    );

    stream.connect();
    CapturingEventSource.instances[0]?.emit(
      "stage.completed",
      JSON.stringify({ stage: "research", timestamp: "2026-11-26T00:00:00+00:00" }),
      "evt-1",
    );

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      id: "evt-1",
      type: "stage.completed",
      production_id: "prod-1",
      payload: { stage: "research" },
    });
    expect(stream.resumeCursor()).toBe("evt-1");
  });

  it("aumenta o backoff entre reconexões sem zerar a contagem", () => {
    vi.useFakeTimers();
    const delays: number[] = [];
    vi.spyOn(window, "setTimeout").mockImplementation(((_handler: () => void, delay: number) => {
      delays.push(delay);
      return 1;
    }) as typeof window.setTimeout);
    const stream = new ProductionEventStream(
      "prod-1",
      { onEvent: () => undefined, onStatus: () => undefined },
      null,
    );

    stream.connect();
    CapturingEventSource.instances.at(-1)?.onerror?.();
    CapturingEventSource.instances.at(-1)?.onerror?.();

    expect(delays).toEqual([1000, 2000]);
    stream.close();
  });

  it("pede novo snapshot após falhas repetidas sem apagar dados locais", () => {
    vi.useFakeTimers();
    let snapshots = 0;
    const stream = new ProductionEventStream(
      "prod-1",
      {
        onEvent: () => undefined,
        onStatus: () => undefined,
        onSnapshotRequired: () => { snapshots += 1; },
      },
      null,
    );

    stream.connect();
    for (let attempt = 0; attempt < 3; attempt += 1) {
      CapturingEventSource.instances.at(-1)?.onerror?.();
      vi.runOnlyPendingTimers();
    }

    expect(snapshots).toBe(1);
    expect(stream.resumeCursor()).toBeNull();
    stream.close();
  });

  it("registra todos os tipos de evento operacionais", () => {
    for (const type of EVENT_TYPES) {
      const received: EventView[] = [];
      const stream = new ProductionEventStream(
        "prod-1",
        { onEvent: (event) => received.push(event), onStatus: () => undefined },
        null,
      );
      stream.connect();
      CapturingEventSource.instances.at(-1)?.emit(type, "{}", `id-${type}`);
      expect(received[0]?.type).toBe(type);
      stream.close();
    }
  });
});
