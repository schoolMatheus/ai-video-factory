export const queryKeys = {
  capabilities: () => ["capabilities"] as const,
  productions: (filters: {
    profileId?: string;
    state?: string;
    search?: string;
  }) =>
    [
      "productions",
      filters.profileId ?? null,
      filters.state ?? null,
      filters.search ?? null,
    ] as const,
  production: (productionId: string) => ["production", productionId] as const,
  events: (productionId: string) => ["events", productionId] as const,
  artifacts: (productionId: string) => ["artifacts", productionId] as const,
  bundle: (productionId: string, stage: string) => ["bundle", productionId, stage] as const,
  profiles: () => ["profiles"] as const,
  profile: (profileId: string) => ["profile", profileId] as const,
  memory: (profileId: string) => ["memory", profileId] as const,
};
