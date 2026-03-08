export interface ChatRequest {
  message: string;
  chat_id?: number;
}

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  result?: string;
  duration_ms?: number;
}

export interface ChatResponse {
  response: string;
  tool_calls: ToolCallInfo[];
  duration_ms: number;
}

export interface HealthResponse {
  status: string;
  tools_registered: number;
  entities_loaded: number;
  model: string;
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  mode: string;
  trigger_type: string;
  active: boolean;
}

export interface EntityInfo {
  entity_id: string;
  state: string;
  friendly_name: string;
}

export interface DomainGroup {
  count: number;
  entities: EntityInfo[];
}

export interface EntitiesResponse {
  total: number;
  domains: Record<string, DomainGroup>;
}

export type StreamEventType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "response"
  | "image"
  | "error"
  | "done";

export interface StreamEvent {
  type: StreamEventType;
  name?: string;
  args?: Record<string, unknown>;
  content?: string;
  duration_ms?: number;
  id?: string;
  filename?: string;
  path?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallInfo[];
  images?: string[];
  timestamp: number;
}
