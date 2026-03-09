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

export interface SkillDetail {
  id: string;
  name: string;
  description: string;
  trigger: Record<string, unknown>;
  mode: string;
  ai_prompt: string;
  actions: unknown[];
  notify: boolean;
  active: boolean;
}

export interface SkillCreate {
  id: string;
  name: string;
  description: string;
  trigger?: Record<string, unknown>;
  mode?: string;
  ai_prompt?: string;
  actions?: unknown[];
  notify?: boolean;
}

export interface SkillUpdate {
  name?: string;
  description?: string;
  trigger?: Record<string, unknown>;
  mode?: string;
  ai_prompt?: string;
  actions?: unknown[];
  notify?: boolean;
}

export interface EventLogEntry {
  entity_id: string;
  old_state: string;
  new_state: string;
  event_type: string;
  details: string;
  ts: string;
}

export interface EventsResponse {
  events: EventLogEntry[];
  hours: number;
}

export interface MemoryFact {
  key: string;
  value: string;
}

export interface MemoryResponse {
  facts: MemoryFact[];
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

export interface ThreadInfo {
  chat_id: number;
  message_count: number;
  last_ts: string;
  last_message: string;
}

export interface ThreadsResponse {
  threads: ThreadInfo[];
}

export interface HistoryMessage {
  role: string;
  text: string;
  ts: string;
}

export interface HistoryResponse {
  chat_id: number;
  messages: HistoryMessage[];
}

// --- Dashboard config types ---

export type WidgetSize = "sm" | "md" | "lg" | "full";

export type WidgetType =
  | "stat"
  | "toggle_group"
  | "sensor_grid"
  | "camera"
  | "quick_actions"
  | "weather"
  | "scene_buttons";

export interface DashboardWidget {
  id: string;
  type: WidgetType;
  title: string;
  config: Record<string, unknown>;
  size: WidgetSize;
}

export interface DashboardConfig {
  widgets: DashboardWidget[];
}

export interface DashboardEditResponse {
  config: DashboardConfig;
  message: string;
}
