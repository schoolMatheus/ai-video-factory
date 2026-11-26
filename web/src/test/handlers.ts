import { http, HttpResponse } from "msw";

const BASE = "/api/v1";

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
  http.get(`${BASE}/productions`, () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
];
