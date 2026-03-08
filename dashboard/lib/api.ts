import type {
  ChatRequest,
  ChatResponse,
  HealthResponse,
  ToolInfo,
  SkillInfo,
  EntitiesResponse,
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

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>("/api/health");
}

export async function getTools(): Promise<ToolInfo[]> {
  return fetchJSON<ToolInfo[]>("/api/tools");
}

export async function getSkills(): Promise<SkillInfo[]> {
  return fetchJSON<SkillInfo[]>("/api/skills");
}

export async function getEntities(): Promise<EntitiesResponse> {
  return fetchJSON<EntitiesResponse>("/api/entities");
}
