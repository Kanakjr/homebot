"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import {
  getMediaOverview,
  getMediaDownloads,
  getMediaTV,
  getMediaMovies,
  getMediaLibrary,
  getMediaRequests,
  mediaSearch,
  addMediaDownload,
  mediaDownloadAction,
  streamChatEvents,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  MediaOverview,
  Torrent,
  SonarrResponse,
  RadarrResponse,
  JellyfinLibraryResponse,
  JellyseerrRequestsResponse,
  MediaSearchResponse,
  MediaSearchResultJellyseerr,
  MediaSearchResultProwlarr,
  MediaSearchResultJellyfin,
} from "@/lib/types";

type TabId = "downloads" | "tv" | "movies" | "library" | "requests";

const TABS: { id: TabId; label: string }[] = [
  { id: "downloads", label: "Downloads" },
  { id: "tv", label: "TV Shows" },
  { id: "movies", label: "Movies" },
  { id: "library", label: "Library" },
  { id: "requests", label: "Requests" },
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatSpeed(bps: number): string {
  if (bps < 1024) return `${bps} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
}

function formatEta(eta: number): string {
  if (eta < 0) return "--";
  if (eta < 60) return `${eta}s`;
  if (eta < 3600) return `${Math.floor(eta / 60)}m`;
  const h = Math.floor(eta / 3600);
  const m = Math.floor((eta % 3600) / 60);
  return `${h}h${m}m`;
}

function formatDate(isoOrUnix: string | number): string {
  const d = typeof isoOrUnix === "number" ? new Date(isoOrUnix * 1000) : new Date(isoOrUnix);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function requestStatusLabel(status: number): { label: string; color: string } {
  switch (status) {
    case 1: return { label: "Pending", color: "text-yellow-400" };
    case 2: return { label: "Approved", color: "text-blue-400" };
    case 3: return { label: "Declined", color: "text-red-400" };
    case 4: return { label: "Available", color: "text-green-400" };
    default: return { label: "Unknown", color: "text-neutral-400" };
  }
}

// ── AI Search / Command Bar ──────────────────────────────────

function AISearchBar({
  onSearchResults,
}: {
  onSearchResults: (results: MediaSearchResponse | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"search" | "ai">("search");
  const [loading, setLoading] = useState(false);
  const [aiResponse, setAiResponse] = useState("");
  const [aiStreaming, setAiStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        onSearchResults(null);
        return;
      }
      setLoading(true);
      try {
        const results = await mediaSearch(q);
        onSearchResults(results);
      } catch {
        onSearchResults(null);
      } finally {
        setLoading(false);
      }
    },
    [onSearchResults],
  );

  const handleAI = useCallback(async () => {
    if (!query.trim()) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setAiStreaming(true);
    setAiResponse("");
    try {
      for await (const event of streamChatEvents(
        { message: query, chat_id: -42 },
        ctrl.signal,
      )) {
        if (event.type === "response") {
          const data = JSON.parse(event.data);
          setAiResponse(data.content || "");
        }
      }
    } catch {
      /* aborted or error */
    } finally {
      setAiStreaming(false);
    }
  }, [query]);

  const onInput = useCallback(
    (value: string) => {
      setQuery(value);
      if (mode === "search") {
        if (debounceRef.current !== undefined) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => handleSearch(value), 300);
      }
    },
    [mode, handleSearch],
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (mode === "ai") handleAI();
      else handleSearch(query);
    },
    [mode, query, handleAI, handleSearch],
  );

  return (
    <div className="space-y-3">
      <form onSubmit={onSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => onInput(e.target.value)}
            placeholder={
              mode === "ai"
                ? "Ask AI: 'find me a sci-fi movie like Interstellar'..."
                : "Search movies, TV shows, torrents..."
            }
            className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 pl-10 text-sm text-white placeholder:text-neutral-500 focus:border-cyber-yellow/50 focus:outline-none transition-colors"
          />
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
            />
          </svg>
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-cyber-yellow/30 border-t-cyber-yellow" />
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            setMode((m) => (m === "search" ? "ai" : "search"));
            onSearchResults(null);
            setAiResponse("");
          }}
          className={cn(
            "rounded-xl border px-4 py-3 text-xs font-mono transition-colors shrink-0",
            mode === "ai"
              ? "border-cyber-yellow/30 bg-cyber-yellow/10 text-cyber-yellow"
              : "border-white/10 bg-white/[0.03] text-neutral-400 hover:text-white",
          )}
        >
          {mode === "ai" ? "AI" : "Search"}
        </button>
      </form>
      {aiResponse && (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-neutral-300 whitespace-pre-wrap">
          {aiResponse}
          {aiStreaming && (
            <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-cyber-yellow" />
          )}
        </div>
      )}
    </div>
  );
}

// ── Search Results Dropdown ──────────────────────────────────

function SearchResults({
  results,
  onClose,
  onAddTorrent,
}: {
  results: MediaSearchResponse;
  onClose: () => void;
  onAddTorrent: (url: string) => void;
}) {
  const hasResults =
    results.jellyseerr.length > 0 ||
    results.prowlarr.length > 0 ||
    results.jellyfin.length > 0;

  if (!hasResults) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-neutral-500">
        No results found.
        <button onClick={onClose} className="ml-2 text-cyber-yellow hover:underline">
          Clear
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-neutral-500 uppercase tracking-wider">
          Search Results
        </span>
        <button onClick={onClose} className="text-xs text-neutral-500 hover:text-white transition-colors">
          Clear
        </button>
      </div>

      {results.jellyseerr.length > 0 && (
        <SearchSection title="Movies / TV" items={results.jellyseerr} renderItem={(r: MediaSearchResultJellyseerr) => (
          <div key={r.id} className="flex gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-3 hover:border-white/10 transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-white truncate">{r.title}</span>
                {r.year && <span className="text-xs text-neutral-500">({r.year})</span>}
                <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-mono",
                  r.media_type === "movie" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                )}>{r.media_type}</span>
              </div>
              {r.overview && <p className="mt-1 text-xs text-neutral-500 line-clamp-2">{r.overview}</p>}
            </div>
            <span className={cn("text-[10px] font-mono shrink-0 self-start mt-1",
              r.status === "not_requested" ? "text-neutral-500" : "text-green-400"
            )}>{r.status === "not_requested" ? "Not Requested" : `Status: ${r.status}`}</span>
          </div>
        )} />
      )}

      {results.prowlarr.length > 0 && (
        <SearchSection title="Torrents" items={results.prowlarr} renderItem={(r: MediaSearchResultProwlarr) => (
          <div key={`${r.title}-${r.indexer}`} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-3 hover:border-white/10 transition-colors">
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white truncate">{r.title}</p>
              <div className="flex gap-3 mt-0.5 text-[11px] text-neutral-500 font-mono">
                <span>{r.indexer}</span>
                <span>{formatBytes(r.size_mb * 1024 * 1024)}</span>
                <span className="text-green-400/80">{r.seeders ?? 0} seeds</span>
              </div>
            </div>
            {r.download_url && (
              <button
                onClick={() => onAddTorrent(r.download_url)}
                className="rounded-lg bg-cyber-yellow/10 px-2.5 py-1 text-[11px] font-mono text-cyber-yellow hover:bg-cyber-yellow/20 transition-colors shrink-0"
              >
                Download
              </button>
            )}
          </div>
        )} />
      )}

      {results.jellyfin.length > 0 && (
        <SearchSection title="In Library" items={results.jellyfin} renderItem={(r: MediaSearchResultJellyfin) => (
          <div key={r.id} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-3 hover:border-white/10 transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-white truncate">{r.name}</span>
                {r.year && <span className="text-xs text-neutral-500">({r.year})</span>}
                <span className="text-[10px] font-mono text-neutral-500">{r.type}</span>
              </div>
              {r.duration && <span className="text-[11px] font-mono text-neutral-500">{r.duration}</span>}
            </div>
            <span className="rounded-full bg-green-500/10 px-1.5 py-0.5 text-[10px] font-mono text-green-400 shrink-0">
              In Library
            </span>
          </div>
        )} />
      )}
    </div>
  );
}

function SearchSection<T>({
  title,
  items,
  renderItem,
}: {
  title: string;
  items: T[];
  renderItem: (item: T) => React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">{title}</p>
      <div className="space-y-1.5">{items.map(renderItem)}</div>
    </div>
  );
}

// ── Overview Cards ───────────────────────────────────────────

function OverviewCards({ overview }: { overview: MediaOverview | null }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs text-neutral-500">Now Playing</p>
        <p className="mt-1 text-2xl font-bold font-mono text-cyber-yellow">
          {overview?.sessions.count ?? 0}
        </p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs text-neutral-500">Downloads</p>
        <p className="mt-1 text-2xl font-bold font-mono text-green-400">
          {overview?.downloads.active ?? 0}
          <span className="ml-1 text-sm text-neutral-500">/ {overview?.downloads.count ?? 0}</span>
        </p>
        {overview && overview.downloads.download_speed > 0 && (
          <p className="mt-0.5 text-[11px] font-mono text-green-400/70">
            {formatSpeed(overview.downloads.download_speed)}
          </p>
        )}
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs text-neutral-500">TV Queue</p>
        <p className="mt-1 text-2xl font-bold font-mono text-blue-400">
          {overview?.sonarr_queue ?? 0}
        </p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs text-neutral-500">Movie Queue</p>
        <p className="mt-1 text-2xl font-bold font-mono text-purple-400">
          {overview?.radarr_queue ?? 0}
        </p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="text-xs text-neutral-500">Requests</p>
        <p className="mt-1 text-2xl font-bold font-mono text-orange-400">
          {overview?.requests_pending ?? 0}
        </p>
      </div>
    </div>
  );
}

// ── Active Sessions ──────────────────────────────────────────

function ActiveSessions({ overview }: { overview: MediaOverview | null }) {
  const sessions = overview?.sessions.items ?? [];
  if (sessions.length === 0) return null;

  return (
    <div>
      <h2 className="mb-3 text-sm font-medium text-neutral-300">Now Playing</h2>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sessions.map((s, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className={cn("h-2.5 w-2.5 rounded-full", s.paused ? "bg-yellow-400" : "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]")} />
              <span className="text-sm font-medium text-white truncate">{s.playing}</span>
            </div>
            <div className="space-y-1 text-xs text-neutral-400">
              {s.series && (
                <p className="font-mono">
                  {s.series} S{String(s.season).padStart(2, "0")}E{String(s.episode).padStart(2, "0")}
                </p>
              )}
              <div className="flex gap-3">
                <span>{s.user}</span>
                <span className="text-neutral-500">{s.device}</span>
                <span className="text-neutral-500">{s.client}</span>
              </div>
              {s.paused && (
                <span className="text-yellow-400 font-mono text-[10px]">PAUSED</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Downloads Tab ────────────────────────────────────────────

function DownloadsTab({ torrents, onAction }: { torrents: Torrent[]; onAction: (id: number, action: "pause" | "resume") => void }) {
  if (torrents.length === 0) {
    return <p className="py-10 text-center text-sm text-neutral-500">No active torrents.</p>;
  }

  const sorted = [...torrents].sort((a, b) => {
    const statusOrder: Record<string, number> = { downloading: 0, queued_download: 1, seeding: 2, stopped: 3 };
    return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
  });

  return (
    <div className="space-y-2">
      {sorted.map((t) => {
        const isActive = t.status === "downloading" || t.status === "seeding";
        return (
          <div key={t.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{t.name}</p>
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] font-mono text-neutral-500">
                  <span className={cn(
                    isActive ? "text-green-400" : t.status === "stopped" ? "text-red-400" : "text-neutral-400",
                  )}>{t.status}</span>
                  <span>{formatBytes(t.size)}</span>
                  {t.download_speed > 0 && <span className="text-green-400/80">{formatSpeed(t.download_speed)}</span>}
                  {t.upload_speed > 0 && <span className="text-blue-400/80">{formatSpeed(t.upload_speed)}</span>}
                  {t.eta > 0 && <span>ETA {formatEta(t.eta)}</span>}
                </div>
              </div>
              <button
                onClick={() => onAction(t.id, isActive ? "pause" : "resume")}
                className={cn(
                  "rounded-lg px-2.5 py-1 text-[11px] font-mono transition-colors shrink-0",
                  isActive
                    ? "bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20"
                    : "bg-green-500/10 text-green-400 hover:bg-green-500/20",
                )}
              >
                {isActive ? "Pause" : "Resume"}
              </button>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  t.progress >= 100 ? "bg-green-400" : "bg-cyber-yellow",
                )}
                style={{ width: `${Math.min(t.progress, 100)}%` }}
              />
            </div>
            <p className="mt-1 text-right text-[10px] font-mono text-neutral-500">{t.progress.toFixed(1)}%</p>
          </div>
        );
      })}
    </div>
  );
}

// ── TV Shows Tab ─────────────────────────────────────────────

function TVTab({ data }: { data: SonarrResponse | null }) {
  const [filter, setFilter] = useState("");

  const filteredSeries = useMemo(() => {
    if (!data) return [];
    const q = filter.toLowerCase();
    return data.series.filter((s) => !q || s.title.toLowerCase().includes(q));
  }, [data, filter]);

  return (
    <div className="space-y-4">
      {data && data.queue.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Downloading ({data.queue.length})
          </h3>
          <div className="space-y-1.5">
            {data.queue.map((q, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{q.title}</p>
                  <p className="text-[11px] font-mono text-neutral-500">{q.series_title}</p>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[11px] font-mono text-neutral-400">{q.status}</span>
                  {q.size > 0 && (
                    <p className="text-[10px] font-mono text-neutral-500">
                      {formatBytes(q.size - q.sizeleft)} / {formatBytes(q.size)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data && data.calendar.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Upcoming (7 days)
          </h3>
          <div className="space-y-1.5">
            {data.calendar.map((ep, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{ep.series_title}</p>
                  <p className="text-[11px] text-neutral-500 truncate">
                    S{String(ep.season).padStart(2, "0")}E{String(ep.episode).padStart(2, "0")} - {ep.episode_title}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] font-mono text-neutral-500">{formatDate(ep.air_date)}</span>
                  {ep.has_file && (
                    <span className="rounded-full bg-green-500/10 px-1.5 py-0.5 text-[10px] font-mono text-green-400">
                      Downloaded
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Series ({filteredSeries.length})
          </h3>
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white placeholder:text-neutral-600 focus:outline-none focus:border-cyber-yellow/50 w-40"
          />
        </div>
        <div className="space-y-1.5 max-h-[500px] overflow-y-auto">
          {filteredSeries.map((s) => (
            <div key={s.id} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
              <div className={cn("h-2 w-2 rounded-full shrink-0", s.monitored ? "bg-green-400" : "bg-neutral-600")} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm text-neutral-200 truncate">{s.title}</p>
                  <span className="text-[10px] text-neutral-500">({s.year})</span>
                </div>
                <div className="flex gap-3 mt-0.5 text-[11px] text-neutral-500 font-mono">
                  <span>{s.seasons} seasons</span>
                  <span>{s.episodes_on_disk}/{s.total_episodes} episodes</span>
                  <span>{formatBytes(s.size_on_disk)}</span>
                </div>
              </div>
              <span className={cn("text-[10px] font-mono shrink-0",
                s.status === "continuing" ? "text-green-400" : "text-neutral-500"
              )}>{s.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Movies Tab ───────────────────────────────────────────────

function MoviesTab({ data }: { data: RadarrResponse | null }) {
  const [filter, setFilter] = useState("");

  const filteredMovies = useMemo(() => {
    if (!data) return [];
    const q = filter.toLowerCase();
    return data.movies.filter((m) => !q || m.title.toLowerCase().includes(q));
  }, [data, filter]);

  return (
    <div className="space-y-4">
      {data && data.queue.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Downloading ({data.queue.length})
          </h3>
          <div className="space-y-1.5">
            {data.queue.map((q, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{q.title || q.movie_title}</p>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[11px] font-mono text-neutral-400">{q.status}</span>
                  {q.size > 0 && (
                    <p className="text-[10px] font-mono text-neutral-500">
                      {formatBytes(q.size - q.sizeleft)} / {formatBytes(q.size)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Movies ({filteredMovies.length})
          </h3>
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter..."
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white placeholder:text-neutral-600 focus:outline-none focus:border-cyber-yellow/50 w-40"
          />
        </div>
        <div className="space-y-1.5 max-h-[500px] overflow-y-auto">
          {filteredMovies.map((m) => (
            <div key={m.id} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
              <div className={cn("h-2 w-2 rounded-full shrink-0",
                m.has_file ? "bg-green-400" : m.monitored ? "bg-yellow-400" : "bg-neutral-600"
              )} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm text-neutral-200 truncate">{m.title}</p>
                  <span className="text-[10px] text-neutral-500">({m.year})</span>
                </div>
                <div className="flex gap-3 mt-0.5 text-[11px] text-neutral-500 font-mono">
                  {m.runtime > 0 && <span>{Math.floor(m.runtime / 60)}h{m.runtime % 60}m</span>}
                  {m.has_file && <span>{formatBytes(m.size_on_disk)}</span>}
                </div>
              </div>
              <span className={cn("text-[10px] font-mono shrink-0",
                m.has_file ? "text-green-400" : m.monitored ? "text-yellow-400" : "text-neutral-500"
              )}>{m.has_file ? "Downloaded" : m.monitored ? "Monitored" : m.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Library Tab ──────────────────────────────────────────────

function LibraryTab({ data }: { data: JellyfinLibraryResponse | null }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      {data.sessions.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Active Sessions ({data.sessions.length})
          </h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {data.sessions.map((s, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5">
                <div className={cn("h-2 w-2 rounded-full shrink-0", s.paused ? "bg-yellow-400" : "bg-green-400")} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-white truncate">{s.playing}</p>
                  <p className="text-[11px] font-mono text-neutral-500">{s.user} on {s.device}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.libraries.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Libraries ({data.libraries.length})
          </h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {data.libraries.map((lib) => (
              <div key={lib.item_id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-center">
                <p className="text-sm font-medium text-white">{lib.name}</p>
                <p className="text-[11px] font-mono text-neutral-500 capitalize">{lib.type}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.latest.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
            Recently Added
          </h3>
          <div className="space-y-1.5">
            {data.latest.map((item) => (
              <div key={item.id} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-neutral-200 truncate">
                      {item.series_name
                        ? `${item.series_name} S${String(item.season).padStart(2, "0")}E${String(item.episode).padStart(2, "0")}`
                        : item.name}
                    </p>
                    {!item.series_name && item.year && (
                      <span className="text-[10px] text-neutral-500">({item.year})</span>
                    )}
                  </div>
                  {item.series_name && (
                    <p className="text-[11px] text-neutral-500 truncate">{item.name}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {item.duration && (
                    <span className="text-[11px] font-mono text-neutral-500">{item.duration}</span>
                  )}
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-mono",
                    item.type === "Movie" ? "bg-blue-500/10 text-blue-400"
                    : item.type === "Episode" ? "bg-purple-500/10 text-purple-400"
                    : "bg-neutral-500/10 text-neutral-400"
                  )}>{item.type}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Requests Tab ─────────────────────────────────────────────

function RequestsTab({ data }: { data: JellyseerrRequestsResponse | null }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      {data.counts && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total", value: data.counts.total ?? 0, color: "text-white" },
            { label: "Pending", value: data.counts.pending ?? 0, color: "text-yellow-400" },
            { label: "Approved", value: data.counts.approved ?? 0, color: "text-blue-400" },
            { label: "Available", value: data.counts.available ?? 0, color: "text-green-400" },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-center">
              <p className="text-xs text-neutral-500">{c.label}</p>
              <p className={cn("mt-1 text-xl font-bold font-mono", c.color)}>{c.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-1.5">
        {data.requests.map((r) => {
          const { label, color } = requestStatusLabel(r.status);
          return (
            <div key={r.id} className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm text-neutral-200 truncate">{r.title}</p>
                  <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-mono",
                    r.media_type === "movie" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                  )}>{r.media_type}</span>
                </div>
                <div className="flex gap-3 mt-0.5 text-[11px] text-neutral-500 font-mono">
                  {r.requested_by && <span>{r.requested_by}</span>}
                  {r.created_at && <span>{formatDate(r.created_at)}</span>}
                </div>
              </div>
              <span className={cn("text-[11px] font-mono shrink-0", color)}>{label}</span>
            </div>
          );
        })}
        {data.requests.length === 0 && (
          <p className="py-10 text-center text-sm text-neutral-500">No requests yet.</p>
        )}
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────

export default function MediaPage() {
  const [overview, setOverview] = useState<MediaOverview | null>(null);
  const [torrents, setTorrents] = useState<Torrent[]>([]);
  const [tvData, setTvData] = useState<SonarrResponse | null>(null);
  const [movieData, setMovieData] = useState<RadarrResponse | null>(null);
  const [libraryData, setLibraryData] = useState<JellyfinLibraryResponse | null>(null);
  const [requestsData, setRequestsData] = useState<JellyseerrRequestsResponse | null>(null);
  const [searchResults, setSearchResults] = useState<MediaSearchResponse | null>(null);

  const [activeTab, setActiveTab] = useState<TabId>("downloads");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = useCallback(async () => {
    try {
      const data = await getMediaOverview();
      setOverview(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const fetchTabData = useCallback(async (tab: TabId) => {
    try {
      switch (tab) {
        case "downloads": {
          const data = await getMediaDownloads();
          setTorrents(data.torrents);
          break;
        }
        case "tv": {
          const data = await getMediaTV();
          setTvData(data);
          break;
        }
        case "movies": {
          const data = await getMediaMovies();
          setMovieData(data);
          break;
        }
        case "library": {
          const data = await getMediaLibrary();
          setLibraryData(data);
          break;
        }
        case "requests": {
          const data = await getMediaRequests();
          setRequestsData(data);
          break;
        }
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchOverview(), fetchTabData(activeTab)]);
      setLoading(false);
    };
    init();
  }, [fetchOverview, fetchTabData, activeTab]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchOverview();
      if (activeTab === "downloads") fetchTabData("downloads");
    }, 10_000);
    return () => clearInterval(interval);
  }, [fetchOverview, fetchTabData, activeTab]);

  const handleTabChange = useCallback(
    (tab: TabId) => {
      setActiveTab(tab);
      fetchTabData(tab);
    },
    [fetchTabData],
  );

  const handleTorrentAction = useCallback(
    async (id: number, action: "pause" | "resume") => {
      try {
        await mediaDownloadAction(id, action);
        const data = await getMediaDownloads();
        setTorrents(data.torrents);
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const handleAddTorrent = useCallback(async (url: string) => {
    try {
      await addMediaDownload(url);
      setActiveTab("downloads");
      const data = await getMediaDownloads();
      setTorrents(data.torrents);
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Media</h1>
          <p className="text-xs sm:text-sm text-neutral-400">
            Torrents, TV shows, movies, library, and requests -- all in one place
          </p>
        </div>
      </BlurFade>

      {error && (
        <p className="text-sm text-red-400">
          Error: {error}
          <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
        </p>
      )}

      {/* AI Search Bar */}
      <BlurFade delay={0.05}>
        <AISearchBar onSearchResults={setSearchResults} />
      </BlurFade>

      {/* Search Results */}
      {searchResults && (
        <BlurFade delay={0}>
          <SearchResults
            results={searchResults}
            onClose={() => setSearchResults(null)}
            onAddTorrent={handleAddTorrent}
          />
        </BlurFade>
      )}

      {/* Overview Cards */}
      <BlurFade delay={0.1}>
        <OverviewCards overview={overview} />
      </BlurFade>

      {/* Active Sessions */}
      {overview && overview.sessions.count > 0 && (
        <BlurFade delay={0.15}>
          <ActiveSessions overview={overview} />
        </BlurFade>
      )}

      {/* Tabbed Detail Sections */}
      <BlurFade delay={0.2}>
        <div>
          <div className="mb-4 flex gap-1.5 overflow-x-auto pb-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "rounded-full px-3 py-1.5 text-xs font-mono transition-colors whitespace-nowrap",
                  activeTab === tab.id
                    ? "bg-cyber-yellow/20 text-cyber-yellow"
                    : "bg-white/5 text-neutral-400 hover:text-white",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === "downloads" && <DownloadsTab torrents={torrents} onAction={handleTorrentAction} />}
          {activeTab === "tv" && <TVTab data={tvData} />}
          {activeTab === "movies" && <MoviesTab data={movieData} />}
          {activeTab === "library" && <LibraryTab data={libraryData} />}
          {activeTab === "requests" && <RequestsTab data={requestsData} />}
        </div>
      </BlurFade>

      {loading && !overview && (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading media data...
        </div>
      )}
    </div>
  );
}
