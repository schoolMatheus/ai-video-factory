import { http, HttpResponse } from "msw";
import type { MemoryView, ProfileView, ProductionView } from "../api/types";

const BASE = "/api/v1";

function production(id: string, title: string, profileId: string): ProductionView {
  return {
    id,
    mode: "legacy",
    title,
    topic: title,
    profile_id: profileId,
    profile_revision: null,
    snapshot_id: null,
    state: "running",
    observed_stages: ["research"],
    stages: [],
    artifacts: [],
    capabilities: [],
    problems: [],
    started_at: "2026-11-23T00:00:00+00:00",
    updated_at: "2026-11-23T01:00:00+00:00",
    cursor: null,
  };
}

export const capturedIdempotencyKeys: string[] = [];

export let currentProduction: ProductionView = production(
  "d".repeat(32),
  "Produção em acompanhamento",
  "canal-a",
);

export function setCurrentProduction(next: ProductionView): void {
  currentProduction = next;
}

export const profiles: ProfileView[] = [
  {
    id: "canal-a",
    name: "Canal A",
    niche: "astronomia",
    revision: 1,
    explicit_fields: ["language"],
    settings: { language: "pt-BR" },
    available: true,
    problem: null,
  },
  {
    id: "canal-b",
    name: "Canal B",
    niche: "geologia",
    revision: 2,
    explicit_fields: [],
    settings: {},
    available: true,
    problem: null,
  },
];

const memories: Record<string, MemoryView[]> = {
  "canal-a": [
    {
      id: "learn-a",
      profile_id: "canal-a",
      stage: "script",
      state: "active",
      summary: "Regra ativa do canal A",
      origin: "inferred",
      condition: "sempre",
      evidence: ["evidencia-a"],
      before: "sem regra",
      after: "com regra",
      revision: 2,
      updated_at: "2026-11-23T00:00:00+00:00",
    },
  ],
  "canal-b": [
    {
      id: "hyp-b",
      profile_id: "canal-b",
      stage: "media",
      state: "proposed",
      summary: "Hipótese do canal B",
      origin: "observed",
      condition: null,
      evidence: [],
      before: null,
      after: null,
      revision: null,
      updated_at: null,
    },
  ],
};

export const handlers = [
  http.get(`${BASE}/capabilities`, () =>
    HttpResponse.json({
      api_version: "v1",
      legacy_read: true,
      profiles: false,
      staged_flow: false,
      editor: false,
      stop_control: false,
      upload: false,
    }),
  ),
  http.get(`${BASE}/productions`, ({ request }) => {
    const profile = new URL(request.url).searchParams.get("profile_id");
    const items =
      profile === "canal-a"
        ? [production("a".repeat(32), "Tema do canal A", "canal-a")]
        : profile === "canal-b"
          ? [production("b".repeat(32), "Tema do canal B", "canal-b")]
          : [];
    return HttpResponse.json({ items, next_cursor: null });
  }),
  http.get(`${BASE}/productions/:id`, () =>
    HttpResponse.json(currentProduction),
  ),
  http.get(`${BASE}/productions/:id/events`, () =>
    HttpResponse.json({
      items: [
        {
          id: `${currentProduction.id}:0`,
          production_id: currentProduction.id,
          type: "stage.started",
          timestamp: "2026-11-23T00:00:00+00:00",
          scope: "production",
          severity: "info",
          attempt: 1,
          payload: { stage: "research" },
        },
      ],
      next_cursor: null,
    }),
  ),
  http.get(`${BASE}/profiles`, () => HttpResponse.json({ items: profiles })),
  http.get(`${BASE}/profiles/:id`, ({ params }) => {
    const found = profiles.find((profile) => profile.id === params.id);
    return found
      ? HttpResponse.json(found)
      : HttpResponse.json(
          { code: "not_found", message: "Perfil não encontrado", recoverable: true },
          { status: 404 },
        );
  }),
  http.get(`${BASE}/profiles/:id/memory`, ({ params }) =>
    HttpResponse.json({ items: memories[String(params.id)] ?? [] }),
  ),
  http.patch(`${BASE}/profiles/:id`, () =>
    HttpResponse.json(
      {
        code: "revision_conflict",
        message: "Revisão concorrente",
        recoverable: true,
      },
      { status: 409 },
    ),
  ),
  http.post(`${BASE}/productions/preflight`, async ({ request }) => {
    const body = (await request.json()) as { topic?: string };
    return HttpResponse.json({
      can_start: Boolean(body.topic?.trim()),
      through: body.topic?.trim() ? "media" : null,
      actions: [],
      problems: [],
    });
  }),
  http.post(`${BASE}/productions`, ({ request }) => {
    capturedIdempotencyKeys.push(request.headers.get("Idempotency-Key") ?? "");
    return HttpResponse.json(
      {
        job_id: "job-1",
        production_id: "c".repeat(32),
        status: "queued",
        accepted: true,
        problem: null,
      },
      { status: 202 },
    );
  }),
];
