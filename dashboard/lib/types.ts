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

export interface SkillExecuteResponse {
  status: string;
  skill_name: string;
  result: string;
  duration_ms: number;
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
  // Light attributes
  brightness?: number | null;
  color_mode?: string | null;
  supported_color_modes?: string[];
  color_temp_kelvin?: number | null;
  min_color_temp_kelvin?: number | null;
  max_color_temp_kelvin?: number | null;
  rgb_color?: [number, number, number] | null;
  hs_color?: [number, number] | null;
  // Climate attributes
  temperature?: number | null;
  current_temperature?: number | null;
  hvac_modes?: string[];
  preset_mode?: string | null;
  preset_modes?: string[];
  fan_mode?: string | null;
  fan_modes?: string[];
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
  | "scene_buttons"
  | "weather_card"
  | "gauge"
  | "light_control"
  | "climate_control"
  | "printer"
  | "air_purifier"
  | "room_environment"
  | "health"
  | "presence"
  | "power_chart"
  | "bandwidth_chart"
  | "smart_plug";

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

export interface DashboardSummary {
  summary: string;
  generated_at: string;
}

// --- Network types ---

export interface MeshNode {
  entity_id: string;
  friendly_name: string;
  state: string;
  ip: string;
  mac: string;
  model: string;
  hw_version: string;
  sw_version: string;
  master: boolean;
  internet_online: boolean;
}

export interface NetworkClient {
  entity_id: string;
  friendly_name: string;
  state: string;
  ip: string;
  mac: string;
  connection_type: string;
  deco_device: string;
  deco_mac: string;
  down_kbps: number;
  up_kbps: number;
}

export interface BandwidthSensor {
  entity_id: string;
  friendly_name: string;
  state: number;
  unit: string;
}

export interface BandwidthHistoryPoint {
  entity_id: string;
  value: number;
  ts: string;
}

export interface NetworkResponse {
  mesh_nodes: MeshNode[];
  clients: NetworkClient[];
  bandwidth_sensors: BandwidthSensor[];
  bandwidth_history: BandwidthHistoryPoint[];
  total_clients: number;
  online_clients: number;
  total_down_kbps: number;
  total_up_kbps: number;
  hours: number;
}

// --- Energy types ---

export interface EnergySensor {
  entity_id: string;
  friendly_name: string;
  device_class: "power" | "energy" | "battery";
  state: number;
  unit: string;
}

export interface EnergyHistoryPoint {
  entity_id: string;
  value: number;
  ts: string;
}

export interface EnergyCost {
  total: number;
  rate: number;
  currency: string;
}

export interface EnergyResponse {
  current: EnergySensor[];
  history: EnergyHistoryPoint[];
  hours: number;
  cost: EnergyCost;
}

// --- Analytics types ---

export interface AnalyticsDataPoint {
  day: string;
  entity_id?: string;
  domain?: string;
  state?: string;
  avg?: number;
  max?: number;
  samples?: number;
  events?: number;
  transitions?: number;
}

export interface AnalyticsResponse {
  metric: string;
  data: AnalyticsDataPoint[];
  hours: number;
}

// --- Device alias types ---

export interface DeviceAlias {
  mac: string;
  alias: string;
  device_type: string;
  icon: string;
  is_presence: boolean;
}

export interface DeviceAliasesResponse {
  aliases: DeviceAlias[];
}

// --- Notification rule types ---

export interface NotificationRule {
  id: string;
  name: string;
  enabled: boolean;
  rule_type: string;
  config: Record<string, unknown>;
  cooldown_seconds: number;
}

export interface NotificationRulesResponse {
  rules: NotificationRule[];
}

// --- Scene types ---

export interface SceneEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
}

export interface Scene {
  id: string;
  name: string;
  icon: string;
  entities: SceneEntity[];
  ts: string;
}

export interface ScenesResponse {
  scenes: Scene[];
}

export interface SceneCreate {
  name: string;
  icon?: string;
  entity_ids: string[];
}

// --- Floorplan types ---

export interface FloorplanDevice {
  svg_id: string;
  entity_id: string;
  type: string;
  label: string;
}

export interface FloorplanConfig {
  devices: FloorplanDevice[];
}

// --- Media types ---

export interface MediaOverviewSession {
  device: string;
  client: string;
  user: string;
  playing: string;
  type: string;
  series?: string;
  season?: number;
  episode?: number;
  paused: boolean;
}

export interface MediaOverview {
  sessions: { count: number; items: MediaOverviewSession[] };
  downloads: { count: number; active: number; download_speed: number; upload_speed: number };
  sonarr_queue: number;
  radarr_queue: number;
  requests_pending: number;
}

export interface Torrent {
  id: number;
  name: string;
  status: string;
  progress: number;
  download_speed: number;
  upload_speed: number;
  eta: number;
  size: number;
  downloaded: number;
  uploaded: number;
  added: number;
}

export interface TorrentsResponse {
  torrents: Torrent[];
  count: number;
}

export interface SonarrSeries {
  id: number;
  title: string;
  year: number;
  status: string;
  monitored: boolean;
  seasons: number;
  episodes_on_disk: number;
  total_episodes: number;
  size_on_disk: number;
  overview: string;
}

export interface SonarrQueueItem {
  title: string;
  series_title: string;
  status: string;
  size: number;
  sizeleft: number;
}

export interface SonarrCalendarItem {
  series_title: string;
  episode_title: string;
  season: number;
  episode: number;
  air_date: string;
  has_file: boolean;
}

export interface SonarrResponse {
  series: SonarrSeries[];
  queue: SonarrQueueItem[];
  calendar: SonarrCalendarItem[];
}

export interface RadarrMovie {
  id: number;
  title: string;
  year: number;
  tmdb_id: number;
  status: string;
  monitored: boolean;
  has_file: boolean;
  size_on_disk: number;
  overview: string;
  runtime: number;
}

export interface RadarrQueueItem {
  title: string;
  movie_title: string;
  status: string;
  size: number;
  sizeleft: number;
}

export interface RadarrResponse {
  movies: RadarrMovie[];
  queue: RadarrQueueItem[];
}

export interface JellyfinLatestItem {
  id: string;
  name: string;
  type: string;
  year: number;
  duration: string;
  series_name?: string;
  season?: number;
  episode?: number;
}

export interface JellyfinSession {
  device: string;
  client: string;
  user: string;
  playing: string;
  type: string;
  paused: boolean;
}

export interface JellyfinLibrary {
  name: string;
  type: string;
  item_id: string;
}

export interface JellyfinLibraryResponse {
  latest: JellyfinLatestItem[];
  sessions: JellyfinSession[];
  libraries: JellyfinLibrary[];
}

export interface JellyseerrRequest {
  id: number;
  media_type: string;
  status: number;
  title: string;
  requested_by: string;
  created_at: string;
}

export interface JellyseerrRequestsResponse {
  requests: JellyseerrRequest[];
  counts: { total?: number; pending?: number; approved?: number; available?: number };
}

export interface MediaSearchResultJellyseerr {
  id: number;
  title: string;
  media_type: string;
  year: string;
  overview: string;
  poster_path: string | null;
  status: string;
}

export interface MediaSearchResultProwlarr {
  title: string;
  indexer: string;
  size_mb: number;
  seeders: number;
  leechers: number;
  download_url: string;
  categories: string[];
}

export interface MediaSearchResultJellyfin {
  id: string;
  name: string;
  type: string;
  year: number;
  duration: string;
  genres: string[];
  overview: string;
}

export interface MediaSearchResponse {
  jellyseerr: MediaSearchResultJellyseerr[];
  prowlarr: MediaSearchResultProwlarr[];
  jellyfin: MediaSearchResultJellyfin[];
}

// --- Server / Tunnel types ---

export interface ServerContainer {
  name: string;
  image: string;
  status: string;
  health: string | null;
  ports: Record<string, number>;
  started_at: string;
  uptime: string;
}

export interface ServerContainersResponse {
  containers: ServerContainer[];
}

export interface TunnelRoute {
  hostname: string;
  service: string;
}

export interface TunnelRoutesResponse {
  routes: TunnelRoute[];
  domain: string;
}

// --- Backup types ---

export interface BackupArchive {
  name: string;
  size: string;
  date: string;
}

export interface BackupStatus {
  last_updated: string;
  local: {
    last_run: string | null;
    archives: BackupArchive[];
  };
  gdrive_mirror: {
    last_sync: string | null;
    size: string | null;
  };
  gdrive_snapshots: {
    snapshots: BackupArchive[];
  };
}

// --- Health data types ---

export interface HealthSensorReading {
  entity_id: string;
  state: string | null;
  unit: string;
  friendly_name: string;
  last_changed: string;
}

export interface HealthHistoryPoint {
  ts: string;
  value: number;
}

export interface HealthDataResponse {
  current: Record<string, HealthSensorReading>;
  history: Record<string, HealthHistoryPoint[]>;
  hours: number;
}
