/** Friendly aliases over the OpenAPI-generated schemas. */
import type { components } from "./generated";

export const API_PREFIX = "/api/v1";

type Schemas = components["schemas"];

export type StageName = Schemas["StageName"];
export type StageStatus = Schemas["StageStatus"];
export type ProductionMode = Schemas["ProductionMode"];
export type ProgressUnit = Schemas["ProgressUnit"];
export type Progress = Schemas["Progress"];
export type ActionAvailability = Schemas["ActionAvailability"];
export type ProblemView = Schemas["ProblemView"];
export type ArtifactView = Schemas["ArtifactView"];
export type StageView = Schemas["StageView"];
export type ProductionView = Schemas["ProductionView"];
export type ProductionPage = Schemas["ProductionPage"];
export type EventView = Schemas["EventView"];
export type EventPage = Schemas["EventPage"];
export type CapabilitiesView = Schemas["CapabilitiesView"];
export type OperationReceipt = Schemas["OperationReceipt"];
export type MemoryView = Schemas["MemoryView"];
export type MemoryPage = Schemas["MemoryPage"];
export type ProfileView = Schemas["ProfileView"];
export type PreflightView = Schemas["PreflightView"];
export type JobView = Schemas["JobView"];
export type JobStatus = Schemas["JobStatus"];
export type ProductionCreateRequest = Schemas["ProductionCreateRequest"];
export type ProfilePage = Schemas["ProfilePage"];
export type ProfileCreateRequest = Schemas["ProfileCreateRequest"];
export type ProfilePatchRequest = Schemas["ProfilePatchRequest"];
export type FeedbackRequest = Schemas["FeedbackRequest"];
export type SuspendRequest = Schemas["SuspendRequest"];
