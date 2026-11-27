import { API_PREFIX } from "./types";
import type {
  CapabilitiesView,
  EventPage,
  FeedbackRequest,
  MemoryPage,
  OperationReceipt,
  PreflightView,
  ProfileCreateRequest,
  ProfilePatchRequest,
  ProfileView,
  ProductionCreateRequest,
  ProductionPage,
  ProductionView,
  ProblemView,
  ProfilePage,
} from "./types";

export class ApiError extends Error {
  readonly problem: ProblemView;
  readonly status: number;

  constructor(status: number, problem: ProblemView) {
    super(problem.message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

function csrfToken(): string | undefined {
  const match = document.cookie.match(/(?:^|;\s*)avf_session_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

async function request<T>(
  method: string,
  path: string,
  options: { body?: unknown; headers?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = { ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  const url = new URL(`${API_PREFIX}${path}`, window.location.origin);
  const response = await fetch(url.toString(), {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({
      code: "network_error",
      message: "Não foi possível concluir a solicitação.",
      recoverable: true,
      suggested_action: null,
      diagnostic_reference: null,
    }))) as ProblemView;
    throw new ApiError(response.status, problem);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function bootstrapSession(token: string): Promise<void> {
  await request<void>("POST", "/session/bootstrap", { body: { token } });
}

export function getCapabilities(): Promise<CapabilitiesView> {
  return request<CapabilitiesView>("GET", "/capabilities");
}

export function listProductions(params: {
  profile_id?: string;
  state?: string;
  search?: string;
  cursor?: string;
}): Promise<ProductionPage> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ProductionPage>("GET", `/productions${suffix}`);
}

export function getProduction(id: string): Promise<ProductionView> {
  return request<ProductionView>("GET", `/productions/${encodeURIComponent(id)}`);
}

export type StageBundle = Record<string, unknown>;

export function getStageBundle(id: string, stage: string): Promise<StageBundle> {
  return request<StageBundle>(
    "GET",
    `/productions/${encodeURIComponent(id)}/stages/${encodeURIComponent(stage)}/bundle`,
  );
}

export function requestProductionAction(
  id: string,
  action: string,
  payload: Record<string, unknown> = {},
  idempotencyKey?: string,
): Promise<OperationReceipt> {
  return request<OperationReceipt>(
    "POST",
    `/productions/${encodeURIComponent(id)}/actions`,
    {
      body: { action, payload },
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    },
  );
}

export function listEvents(
  id: string,
  afterCursor?: string,
): Promise<EventPage> {
  const suffix = afterCursor
    ? `?after_cursor=${encodeURIComponent(afterCursor)}`
    : "";
  return request<EventPage>(
    "GET",
    `/productions/${encodeURIComponent(id)}/events${suffix}`,
  );
}

export function preflightProduction(
  payload: ProductionCreateRequest,
): Promise<PreflightView> {
  return request<PreflightView>("POST", "/productions/preflight", { body: payload });
}

export function listProfiles(): Promise<ProfilePage> {
  return request<ProfilePage>("GET", "/profiles");
}

export function getProfile(profileId: string): Promise<ProfileView> {
  return request<ProfileView>("GET", `/profiles/${encodeURIComponent(profileId)}`);
}

export function createProfile(payload: ProfileCreateRequest): Promise<ProfileView> {
  return request<ProfileView>("POST", "/profiles", { body: payload });
}

export function reviseProfile(
  profileId: string,
  payload: ProfilePatchRequest,
): Promise<ProfileView> {
  return request<ProfileView>(
    "PATCH",
    `/profiles/${encodeURIComponent(profileId)}`,
    { body: payload },
  );
}

export function listMemory(profileId: string): Promise<MemoryPage> {
  return request<MemoryPage>("GET", `/profiles/${encodeURIComponent(profileId)}/memory`);
}

export function addFeedback(
  profileId: string,
  payload: FeedbackRequest,
): Promise<unknown> {
  return request<unknown>(
    "POST",
    `/profiles/${encodeURIComponent(profileId)}/feedback`,
    { body: payload },
  );
}

export function suspendLearning(
  profileId: string,
  learningId: string,
  expectedRevision: number,
  reason: string,
): Promise<unknown> {
  return request<unknown>(
    "POST",
    `/profiles/${encodeURIComponent(profileId)}/memory/${encodeURIComponent(learningId)}/suspend`,
    { body: { expected_revision: expectedRevision, reason } },
  );
}

export function createProduction(
  payload: ProductionCreateRequest,
  idempotencyKey: string,
): Promise<OperationReceipt> {
  return request<OperationReceipt>("POST", "/productions", {
    body: payload,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
