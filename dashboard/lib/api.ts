import type {
  ChatRequest,
  ChatResponse,
  HealthResponse,
  ToolInfo,
  SkillDetail,
  SkillCreate,
  SkillUpdate,
  EntitiesResponse,
  ThreadsResponse,
  HistoryResponse,
  EventsResponse,
  MemoryResponse,
  DashboardConfig,
  DashboardEditResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
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

export function streamChat(
  req: ChatRequest,
  signal?: AbortSignal
): EventSource | null {
  if (typeof window === "undefined") return null;

  const url = `${BASE_URL}/api/chat/stream`;

  const eventSource = new EventSource(url);

  // EventSource only supports GET -- use fetch for POST SSE
  return eventSource;
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }

  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let eventType = "";
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

export function getSnapshotUrl(filename: string): string {
  return `${BASE_URL}/api/snapshots/${encodeURIComponent(filename)}`;
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>("/api/health");
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
  await fetch(`${BASE_URL}/api/chat/${chatId}/history`, { method: "DELETE" });
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
