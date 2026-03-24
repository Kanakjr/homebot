import type {
  ChatRequest,
  ChatResponse,
  HealthResponse,
  ToolInfo,
  SkillDetail,
  SkillCreate,
  SkillUpdate,
  SkillExecuteResponse,
  EntitiesResponse,
  ThreadsResponse,
  HistoryResponse,
  EventsResponse,
  MemoryResponse,
  DashboardConfig,
  DashboardEditResponse,
  DashboardSummary,
  EnergyResponse,
  NetworkResponse,
  AnalyticsResponse,
  DeviceAliasesResponse,
  DeviceAlias,
  NotificationRulesResponse,
  NotificationRule,
  HealthDataResponse,
  ScenesResponse,
  Scene,
  SceneCreate as SceneCreatePayload,
  FloorplanConfig,
  MediaOverview,
  TorrentsResponse,
  SonarrResponse,
  RadarrResponse,
  JellyfinLibraryResponse,
  JellyseerrRequestsResponse,
  MediaSearchResponse,
  DiscoverResponse,
  ServerContainersResponse,
  TunnelRoutesResponse,
  BackupStatus,
  ReportSummary,
  TranscoderLibrary,
  TranscoderPreset,
  TranscoderJob,
  TranscoderJobProgress,
  TranscoderStats,
  TranscoderScan,
  TranscoderHealth,
  TranscoderBrowseResult,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEEP_AGENT_URL =
  process.env.NEXT_PUBLIC_DEEP_AGENT_URL ?? "http://localhost:8322";
const TRANSCODER_URL =
  process.env.NEXT_PUBLIC_TRANSCODER_URL ?? "http://localhost:8323";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

function authHeaders(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(API_KEY && { "X-API-Key": API_KEY }),
    ...extra,
  };
}

async function* parseSSEStream(
  res: Response,
  _signal?: AbortSignal,
): AsyncGenerator<{ type: string; data: string }> {
  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  let eventType = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (eventType) {
          yield { type: eventType, data };
          eventType = "";
        }
      }
    }
  }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: authHeaders(init?.headers as Record<string, string>),
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  return fetchJSON<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/**
 * POST-based SSE stream using fetch. Returns an async iterable of events.
 */
export async function* streamChatEvents(
  req: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<{ type: string; data: string }> {
  const res = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }

  yield* parseSSEStream(res, signal);
}

/**
 * POST-based SSE stream to the Deep Agent service. Same event format as standard backend.
 */
export async function getDeepAgentModels(): Promise<{ models: import("./types").ModelInfo[] }> {
  const res = await fetch(`${DEEP_AGENT_URL}/api/models`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Deep Agent models API ${res.status}`);
  return res.json();
}

export async function* streamDeepAgentEvents(
  req: { message: string; thread_id?: string; model?: string },
  signal?: AbortSignal
): AsyncGenerator<{ type: string; data: string }> {
  const res = await fetch(`${DEEP_AGENT_URL}/api/chat/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    throw new Error(`Deep Agent API ${res.status}: ${await res.text()}`);
  }

  yield* parseSSEStream(res, signal);
}

export function getSnapshotUrl(filename: string): string {
  return `${BASE_URL}/api/snapshots/${encodeURIComponent(filename)}`;
}

export function getCameraStreamUrl(entityId: string): string {
  return `${BASE_URL}/api/cameras/${encodeURIComponent(entityId)}/stream`;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>("/api/health");
}

export async function getModels(): Promise<{ models: import("./types").ModelInfo[] }> {
  return fetchJSON<{ models: import("./types").ModelInfo[] }>("/api/models");
}

export async function getTools(): Promise<ToolInfo[]> {
  return fetchJSON<ToolInfo[]>("/api/tools");
}

export async function getSkills(): Promise<SkillDetail[]> {
  return fetchJSON<SkillDetail[]>("/api/skills");
}

export async function createSkill(skill: SkillCreate): Promise<SkillDetail> {
  return fetchJSON<SkillDetail>("/api/skills", {
    method: "POST",
    body: JSON.stringify(skill),
  });
}

export async function updateSkill(id: string, updates: SkillUpdate): Promise<SkillDetail> {
  return fetchJSON<SkillDetail>(`/api/skills/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function deleteSkill(id: string): Promise<void> {
  await fetchJSON(`/api/skills/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function toggleSkill(id: string, active: boolean): Promise<SkillDetail> {
  return fetchJSON<SkillDetail>(
    `/api/skills/${encodeURIComponent(id)}/toggle?active=${active}`,
    { method: "POST" },
  );
}

export async function executeSkill(id: string): Promise<SkillExecuteResponse> {
  return fetchJSON<SkillExecuteResponse>(
    `/api/skills/${encodeURIComponent(id)}/execute`,
    { method: "POST" },
  );
}

export async function getEntities(): Promise<EntitiesResponse> {
  return fetchJSON<EntitiesResponse>("/api/entities");
}

export async function getThreads(): Promise<ThreadsResponse> {
  return fetchJSON<ThreadsResponse>("/api/chat/threads");
}

export async function getHistory(chatId: number, limit = 50): Promise<HistoryResponse> {
  return fetchJSON<HistoryResponse>(`/api/chat/${chatId}/history?limit=${limit}`);
}

export async function clearHistory(chatId: number): Promise<void> {
  await fetch(`${BASE_URL}/api/chat/${chatId}/history`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function toggleEntity(
  entityId: string,
  action: "toggle" | "turn_on" | "turn_off" = "toggle",
): Promise<{ status: string; entity_id: string; action: string }> {
  return fetchJSON(`/api/entities/${encodeURIComponent(entityId)}/toggle`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function takeCameraSnapshot(
  entityId: string,
): Promise<{ status: string; filename: string; entity_id: string }> {
  return fetchJSON(`/api/cameras/${encodeURIComponent(entityId)}/snapshot`, {
    method: "POST",
  });
}

export async function getEvents(hours = 24, limit = 200): Promise<EventsResponse> {
  return fetchJSON<EventsResponse>(`/api/events?hours=${hours}&limit=${limit}`);
}

export async function getMemory(): Promise<MemoryResponse> {
  return fetchJSON<MemoryResponse>("/api/memory");
}

export async function addMemory(key: string, value: string): Promise<void> {
  await fetchJSON("/api/memory", {
    method: "POST",
    body: JSON.stringify({ key, value }),
  });
}

export async function deleteMemory(key: string): Promise<void> {
  await fetchJSON(`/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
}

export async function getDashboardConfig(): Promise<DashboardConfig> {
  return fetchJSON<DashboardConfig>("/api/dashboard");
}

export async function saveDashboardConfig(config: DashboardConfig): Promise<void> {
  await fetchJSON("/api/dashboard", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function editDashboard(message: string): Promise<DashboardEditResponse> {
  return fetchJSON<DashboardEditResponse>("/api/dashboard/edit", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function getDashboardSummary(regenerate = false): Promise<DashboardSummary> {
  const qs = regenerate ? "?regenerate=true" : "";
  return fetchJSON<DashboardSummary>(`/api/dashboard/summary${qs}`);
}

export async function generateWidget(
  entity_ids: string[],
  description: string,
  size = "md",
): Promise<{
  spec: { root: string; elements: Record<string, unknown> };
  summary: string;
}> {
  return fetchJSON("/api/dashboard/generate-widget", {
    method: "POST",
    body: JSON.stringify({ entity_ids, description, size }),
  });
}

export async function suggestWidget(
  entity_ids: string[],
): Promise<{ title: string; description: string }> {
  return fetchJSON("/api/dashboard/suggest-widget", {
    method: "POST",
    body: JSON.stringify({ entity_ids }),
  });
}

export async function setLightState(
  entityId: string,
  params: { brightness?: number; color_temp_kelvin?: number; rgb_color?: [number, number, number] },
): Promise<{ status: string; entity_id: string }> {
  return fetchJSON(`/api/entities/${encodeURIComponent(entityId)}/light`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function setClimateState(
  entityId: string,
  params: { preset_mode?: string; fan_mode?: string; temperature?: number },
): Promise<{ status: string; entity_id: string; updated: string[] }> {
  return fetchJSON(`/api/entities/${encodeURIComponent(entityId)}/climate`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getEnergy(hours = 24): Promise<EnergyResponse> {
  return fetchJSON<EnergyResponse>(`/api/energy?hours=${hours}`);
}

export async function getNetwork(hours = 24): Promise<NetworkResponse> {
  return fetchJSON<NetworkResponse>(`/api/network?hours=${hours}`);
}

export async function getAnalytics(metric: string, hours = 168): Promise<AnalyticsResponse> {
  return fetchJSON<AnalyticsResponse>(`/api/analytics?metric=${metric}&hours=${hours}`);
}

export async function getDeviceAliases(): Promise<DeviceAliasesResponse> {
  return fetchJSON<DeviceAliasesResponse>("/api/devices/aliases");
}

export async function setDeviceAlias(
  mac: string,
  alias: string,
  device_type = "",
  icon = "",
  is_presence = false,
): Promise<DeviceAlias> {
  return fetchJSON<DeviceAlias>(`/api/devices/aliases/${encodeURIComponent(mac)}`, {
    method: "PUT",
    body: JSON.stringify({ alias, device_type, icon, is_presence }),
  });
}

export async function deleteDeviceAlias(mac: string): Promise<void> {
  await fetchJSON(`/api/devices/aliases/${encodeURIComponent(mac)}`, { method: "DELETE" });
}

export async function getNotificationRules(): Promise<NotificationRulesResponse> {
  return fetchJSON<NotificationRulesResponse>("/api/notifications/rules");
}

export async function updateNotificationRule(
  ruleId: string,
  updates: { enabled?: boolean; config?: Record<string, unknown>; cooldown_seconds?: number },
): Promise<NotificationRule> {
  return fetchJSON<NotificationRule>(`/api/notifications/rules/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function getHealthData(hours = 24): Promise<HealthDataResponse> {
  return fetchJSON<HealthDataResponse>(`/api/health/data?hours=${hours}`);
}

// --- Scenes ---

export async function getScenes(): Promise<Scene[]> {
  const res = await fetchJSON<ScenesResponse>("/api/scenes");
  return res.scenes;
}

export async function createScene(data: SceneCreatePayload): Promise<Scene> {
  return fetchJSON<Scene>("/api/scenes", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function activateScene(id: string): Promise<{ status: string; scene: string; restored: number }> {
  return fetchJSON(`/api/scenes/${encodeURIComponent(id)}/activate`, {
    method: "POST",
  });
}

export async function deleteScene(id: string): Promise<void> {
  await fetchJSON(`/api/scenes/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// --- Floorplan ---

export async function getFloorplanConfig(): Promise<FloorplanConfig> {
  return fetchJSON<FloorplanConfig>("/api/floorplan/config");
}

// --- Media ---

export async function getMediaOverview(): Promise<MediaOverview> {
  return fetchJSON<MediaOverview>("/api/media/overview");
}

export async function mediaSearch(q: string, type = ""): Promise<MediaSearchResponse> {
  const params = new URLSearchParams({ q });
  if (type) params.set("type", type);
  return fetchJSON<MediaSearchResponse>(`/api/media/search?${params}`);
}

export async function getMediaDownloads(): Promise<TorrentsResponse> {
  return fetchJSON<TorrentsResponse>("/api/media/downloads");
}

export async function addMediaDownload(url: string): Promise<{ status: string; name: string; id?: number }> {
  return fetchJSON("/api/media/downloads", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function mediaDownloadAction(
  torrentId: number,
  action: "pause" | "resume",
): Promise<{ status: string }> {
  return fetchJSON(`/api/media/downloads/${torrentId}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function getMediaTV(): Promise<SonarrResponse> {
  return fetchJSON<SonarrResponse>("/api/media/tv");
}

export async function addMediaTV(
  tvdbId: number,
  qualityProfileId = 1,
  rootFolderPath = "/data/tv",
): Promise<{ status: string; title: string; id: number }> {
  return fetchJSON("/api/media/tv", {
    method: "POST",
    body: JSON.stringify({ tvdb_id: tvdbId, quality_profile_id: qualityProfileId, root_folder_path: rootFolderPath }),
  });
}

export async function getMediaMovies(): Promise<RadarrResponse> {
  return fetchJSON<RadarrResponse>("/api/media/movies");
}

export async function addMediaMovie(
  tmdbId: number,
  qualityProfileId = 1,
  rootFolderPath = "/data/movies",
): Promise<{ status: string; title: string; id: number }> {
  return fetchJSON("/api/media/movies", {
    method: "POST",
    body: JSON.stringify({ tmdb_id: tmdbId, quality_profile_id: qualityProfileId, root_folder_path: rootFolderPath }),
  });
}

export async function getMediaLibrary(): Promise<JellyfinLibraryResponse> {
  return fetchJSON<JellyfinLibraryResponse>("/api/media/library");
}

export async function getMediaRequests(): Promise<JellyseerrRequestsResponse> {
  return fetchJSON<JellyseerrRequestsResponse>("/api/media/requests");
}

export async function createMediaRequest(
  mediaId: number,
  mediaType: "movie" | "tv",
): Promise<{ id: number }> {
  return fetchJSON("/api/media/requests", {
    method: "POST",
    body: JSON.stringify({ media_id: mediaId, media_type: mediaType }),
  });
}

export async function getMediaDiscover(refresh = false, cats?: string): Promise<DiscoverResponse> {
  const params = new URLSearchParams();
  if (refresh) params.set("refresh", "true");
  if (cats) params.set("cats", cats);
  const qs = params.toString();
  return fetchJSON<DiscoverResponse>(`/api/media/discover${qs ? `?${qs}` : ""}`);
}

// --- Server / Tunnel ---

export async function getServerContainers(): Promise<ServerContainersResponse> {
  return fetchJSON<ServerContainersResponse>("/api/server/containers");
}

export async function getServerTunnel(): Promise<TunnelRoutesResponse> {
  return fetchJSON<TunnelRoutesResponse>("/api/server/tunnel");
}

export async function addTunnelRoute(
  subdomain: string,
  service: string,
): Promise<{ status: string; hostname: string; service: string }> {
  return fetchJSON("/api/server/tunnel", {
    method: "POST",
    body: JSON.stringify({ subdomain, service }),
  });
}

export async function removeTunnelRoute(
  subdomain: string,
): Promise<{ status: string; hostname: string }> {
  return fetchJSON(`/api/server/tunnel/${encodeURIComponent(subdomain)}`, {
    method: "DELETE",
  });
}

export async function getServerBackups(): Promise<BackupStatus | { status: "no_data" }> {
  return fetchJSON("/api/server/backups");
}

// --- Reports ---

export async function getReportsSummary(hours = 720): Promise<ReportSummary> {
  return fetchJSON<ReportSummary>(`/api/reports/summary?hours=${hours}`);
}

// --- Transcoder ---

async function fetchTranscoder<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${TRANSCODER_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY && { "X-API-Key": API_KEY }),
      ...(init?.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    throw new Error(`Transcoder API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function getTranscoderHealth(): Promise<TranscoderHealth> {
  return fetchTranscoder<TranscoderHealth>("/api/health");
}

export async function getTranscoderStats(): Promise<TranscoderStats> {
  return fetchTranscoder<TranscoderStats>("/api/stats");
}

export async function getTranscoderLibraries(): Promise<TranscoderLibrary[]> {
  return fetchTranscoder<TranscoderLibrary[]>("/api/libraries");
}

export async function createTranscoderLibrary(data: Partial<TranscoderLibrary>): Promise<TranscoderLibrary> {
  return fetchTranscoder<TranscoderLibrary>("/api/libraries", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTranscoderLibrary(id: number, data: Partial<TranscoderLibrary>): Promise<TranscoderLibrary> {
  return fetchTranscoder<TranscoderLibrary>(`/api/libraries/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteTranscoderLibrary(id: number): Promise<void> {
  await fetchTranscoder<void>(`/api/libraries/${id}`, { method: "DELETE" });
}

export async function scanTranscoderLibrary(id: number): Promise<{ message: string }> {
  return fetchTranscoder<{ message: string }>(`/api/libraries/${id}/scan`, { method: "POST" });
}

export async function getTranscoderPresets(): Promise<TranscoderPreset[]> {
  return fetchTranscoder<TranscoderPreset[]>("/api/presets");
}

export async function createTranscoderPreset(data: Partial<TranscoderPreset>): Promise<TranscoderPreset> {
  return fetchTranscoder<TranscoderPreset>("/api/presets", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteTranscoderPreset(id: number): Promise<void> {
  await fetchTranscoder<void>(`/api/presets/${id}`, { method: "DELETE" });
}

export async function getTranscoderJobs(params?: {
  status?: string;
  library_id?: number;
  limit?: number;
  offset?: number;
}): Promise<TranscoderJob[]> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.library_id) sp.set("library_id", String(params.library_id));
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  return fetchTranscoder<TranscoderJob[]>(`/api/jobs${qs ? `?${qs}` : ""}`);
}

export async function startTranscoderJobs(library_id: number, preset_id?: number): Promise<{ message: string }> {
  return fetchTranscoder<{ message: string }>("/api/jobs/start", {
    method: "POST",
    body: JSON.stringify({ library_id, preset_id }),
  });
}

export async function cancelTranscoderJob(id: number): Promise<{ message: string }> {
  return fetchTranscoder<{ message: string }>(`/api/jobs/${id}/cancel`, { method: "POST" });
}

export async function getTranscoderProgress(): Promise<Record<string, TranscoderJobProgress>> {
  return fetchTranscoder<Record<string, TranscoderJobProgress>>("/api/jobs/progress");
}

export async function getTranscoderScans(): Promise<TranscoderScan[]> {
  return fetchTranscoder<TranscoderScan[]>("/api/scans");
}

export async function browseTranscoderLibrary(id: number, subpath = ""): Promise<TranscoderBrowseResult> {
  const sp = new URLSearchParams();
  if (subpath) sp.set("subpath", subpath);
  const qs = sp.toString();
  return fetchTranscoder<TranscoderBrowseResult>(`/api/libraries/${id}/browse${qs ? `?${qs}` : ""}`);
}

export async function startPathTranscode(library_id: number, path: string, preset_id?: number): Promise<{ message: string; jobs: number }> {
  return fetchTranscoder<{ message: string; jobs: number }>("/api/jobs/start-path", {
    method: "POST",
    body: JSON.stringify({ library_id, path, preset_id }),
  });
}
