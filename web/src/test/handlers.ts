import { http, HttpResponse } from "msw";

const BASE = "/api/v1";

function production(id: string, title: string, profileId: string) {
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
