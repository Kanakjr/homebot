"use client";

import { useEffect, useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { cn } from "@/lib/utils";
import {
  getTranscoderHealth,
  getTranscoderStats,
  getTranscoderLibraries,
  createTranscoderLibrary,
  deleteTranscoderLibrary,
  scanTranscoderLibrary,
  getTranscoderPresets,
  getTranscoderJobs,
  startTranscoderJobs,
  cancelTranscoderJob,
  getTranscoderScans,
} from "@/lib/api";
import type {
  TranscoderHealth,
  TranscoderStats,
  TranscoderLibrary,
  TranscoderPreset,
  TranscoderJob,
  TranscoderScan,
} from "@/lib/types";

type TabId = "overview" | "libraries" | "jobs" | "presets";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "libraries", label: "Libraries" },
  { id: "jobs", label: "Jobs" },
  { id: "presets", label: "Presets" },
];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso + "Z").toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-500/20 text-yellow-400",
    running: "bg-blue-500/20 text-blue-400",
    completed: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
    skipped: "bg-zinc-500/20 text-zinc-400",
    cancelled: "bg-orange-500/20 text-orange-400",
  };
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium", colors[status] ?? "bg-zinc-700 text-zinc-300")}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Overview Tab
// ---------------------------------------------------------------------------

function OverviewTab({ stats, health, jobs }: { stats: TranscoderStats | null; health: TranscoderHealth | null; jobs: TranscoderJob[] }) {
  const cards = [
    { label: "Files Processed", value: stats?.files_processed ?? 0 },
    { label: "Space Saved", value: stats ? formatBytes(stats.space_saved_bytes) : "--" },
    { label: "Avg Compression", value: stats ? `${stats.avg_compression_pct}%` : "--" },
    { label: "Active Jobs", value: health?.active_jobs ?? 0 },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <div className="text-xs text-zinc-500 uppercase tracking-wider">{c.label}</div>
            <div className="text-2xl font-semibold mt-1">{c.value}</div>
          </div>
        ))}
      </div>

      {stats?.job_counts && Object.keys(stats.job_counts).length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Jobs by Status</h3>
          <div className="flex gap-4 flex-wrap">
            {Object.entries(stats.job_counts).map(([status, count]) => (
              <div key={status} className="flex items-center gap-2">
                <StatusBadge status={status} />
                <span className="text-sm text-zinc-300">{count as number}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">Recent Jobs</h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-zinc-500">No jobs yet</p>
        ) : (
          <div className="space-y-2">
            {jobs.slice(0, 10).map((job) => (
              <div key={job.id} className="flex items-center justify-between text-sm py-1.5 border-b border-zinc-800 last:border-0">
                <div className="flex-1 min-w-0">
                  <span className="text-zinc-300 truncate block">{job.file_path.split("/").pop()}</span>
                  <span className="text-xs text-zinc-500">{job.library_name} -- {job.preset_name}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-3">
                  {job.status === "completed" && job.original_size_bytes && job.new_size_bytes && (
                    <span className="text-xs text-zinc-500">
                      {formatBytes(job.original_size_bytes)} -&gt; {formatBytes(job.new_size_bytes)}
                    </span>
                  )}
                  <StatusBadge status={job.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {health && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-zinc-400 mb-2">Service Info</h3>
          <div className="text-sm text-zinc-300 space-y-1">
            <div>Status: <span className="text-green-400">{health.status}</span></div>
            <div>HandBrakeCLI: <span className="text-zinc-400">{health.handbrake_cli}</span></div>
            <div>Port: {health.port}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Libraries Tab
// ---------------------------------------------------------------------------

function LibrariesTab({
  libraries,
  presets,
  onRefresh,
}: {
  libraries: TranscoderLibrary[];
  presets: TranscoderPreset[];
  onRefresh: () => void;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", path: "", scan_mode: "manual", transcode_mode: "manual", scan_cron: "" });
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!form.name || !form.path) return;
    setError("");
    try {
      await createTranscoderLibrary({
        ...form,
        scan_cron: form.scan_cron || undefined,
      } as unknown as Partial<TranscoderLibrary>);
      setForm({ name: "", path: "", scan_mode: "manual", transcode_mode: "manual", scan_cron: "" });
      setShowAdd(false);
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create library");
    }
  };

  const handleScan = async (id: number) => {
    setBusy(id);
    setError("");
    try {
      await scanTranscoderLibrary(id);
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setBusy(null);
    }
  };

  const handleTranscode = async (id: number) => {
    setBusy(id);
    setError("");
    try {
      await startTranscoderJobs(id);
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transcode failed");
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this library?")) return;
    setError("");
    try {
      await deleteTranscoderLibrary(id);
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-medium text-zinc-400">Media Libraries</h3>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 rounded-lg transition"
        >
          {showAdd ? "Cancel" : "Add Library"}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              placeholder="Library name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
            />
            <input
              placeholder="Path (e.g. /Volumes/SSD1T/Movies)"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
            />
            <select
              value={form.scan_mode}
              onChange={(e) => setForm({ ...form, scan_mode: e.target.value })}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
            >
              <option value="manual">Scan: Manual</option>
              <option value="auto">Scan: Auto (Cron)</option>
            </select>
            <select
              value={form.transcode_mode}
              onChange={(e) => setForm({ ...form, transcode_mode: e.target.value })}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
            >
              <option value="manual">Transcode: Manual</option>
              <option value="auto">Transcode: Auto</option>
            </select>
          </div>
          {form.scan_mode === "auto" && (
            <input
              placeholder="Cron expression (e.g. 0 3 * * *)"
              value={form.scan_cron}
              onChange={(e) => setForm({ ...form, scan_cron: e.target.value })}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
            />
          )}
          <button
            onClick={handleAdd}
            disabled={!form.name || !form.path}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm transition"
          >
            Create Library
          </button>
        </div>
      )}

      {libraries.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-sm">
          No libraries configured. Add one to get started.
        </div>
      ) : (
        <div className="grid gap-4">
          {libraries.map((lib) => (
            <div key={lib.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="font-medium text-zinc-200">{lib.name}</h4>
                  <p className="text-xs text-zinc-500 mt-0.5 font-mono">{lib.path}</p>
                  <div className="flex gap-3 mt-2 text-xs text-zinc-400">
                    <span>Scan: {lib.scan_mode}</span>
                    <span>Transcode: {lib.transcode_mode}</span>
                    {lib.scan_cron && <span>Cron: {lib.scan_cron}</span>}
                    <span className={lib.enabled ? "text-green-400" : "text-red-400"}>
                      {lib.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleScan(lib.id)}
                    disabled={busy === lib.id}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg disabled:opacity-50 transition"
                  >
                    {busy === lib.id ? "..." : "Scan"}
                  </button>
                  <button
                    onClick={() => handleTranscode(lib.id)}
                    disabled={busy === lib.id}
                    className="px-2.5 py-1 text-xs bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 rounded-lg disabled:opacity-50 transition"
                  >
                    Transcode
                  </button>
                  <button
                    onClick={() => handleDelete(lib.id)}
                    className="px-2.5 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded-lg transition"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Jobs Tab
// ---------------------------------------------------------------------------

function JobsTab({ jobs, onRefresh }: { jobs: TranscoderJob[]; onRefresh: () => void }) {
  const [filter, setFilter] = useState("");

  const filtered = filter ? jobs.filter((j) => j.status === filter) : jobs;

  const handleCancel = async (id: number) => {
    try {
      await cancelTranscoderJob(id);
      onRefresh();
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500">Filter:</span>
        {["", "pending", "running", "completed", "failed", "skipped", "cancelled"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "px-2 py-0.5 text-xs rounded-full border transition",
              filter === s
                ? "bg-blue-600/20 text-blue-400 border-blue-500/30"
                : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-600",
            )}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-sm">
          No jobs found
        </div>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-xs text-zinc-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-3">File</th>
                  <th className="text-left px-4 py-3">Library</th>
                  <th className="text-left px-4 py-3">Preset</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="text-right px-4 py-3">Original</th>
                  <th className="text-right px-4 py-3">New</th>
                  <th className="text-right px-4 py-3">Saved</th>
                  <th className="text-left px-4 py-3">Time</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((job) => {
                  const saved =
                    job.original_size_bytes && job.new_size_bytes
                      ? ((job.original_size_bytes - job.new_size_bytes) / job.original_size_bytes) * 100
                      : null;
                  return (
                    <tr key={job.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="px-4 py-2.5 max-w-[200px] truncate text-zinc-300" title={job.file_path}>
                        {job.file_path.split("/").pop()}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400">{job.library_name ?? "--"}</td>
                      <td className="px-4 py-2.5 text-zinc-400">{job.preset_name ?? "--"}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={job.status} /></td>
                      <td className="px-4 py-2.5 text-right text-zinc-400">
                        {job.original_size_bytes ? formatBytes(job.original_size_bytes) : "--"}
                      </td>
                      <td className="px-4 py-2.5 text-right text-zinc-400">
                        {job.new_size_bytes ? formatBytes(job.new_size_bytes) : "--"}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {saved !== null ? (
                          <span className={saved > 0 ? "text-green-400" : "text-red-400"}>
                            {saved.toFixed(1)}%
                          </span>
                        ) : "--"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-zinc-500 whitespace-nowrap">
                        {formatDate(job.completed_at ?? job.started_at ?? job.created_at)}
                      </td>
                      <td className="px-4 py-2.5">
                        {(job.status === "running" || job.status === "pending") && (
                          <button
                            onClick={() => handleCancel(job.id)}
                            className="text-xs text-red-400 hover:text-red-300 transition"
                          >
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Presets Tab
// ---------------------------------------------------------------------------

function PresetsTab({ presets }: { presets: TranscoderPreset[] }) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-zinc-400">Transcoding Presets</h3>
      {presets.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-sm">
          No presets configured
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {presets.map((p) => (
            <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-zinc-200">{p.name}</h4>
                {p.is_default ? (
                  <span className="text-[10px] px-1.5 py-0.5 bg-blue-600/20 text-blue-400 rounded">Default</span>
                ) : null}
              </div>
              <div className="text-xs text-zinc-400 space-y-1">
                <div className="flex justify-between">
                  <span>Encoder</span>
                  <span className="text-zinc-300">{p.encoder}</span>
                </div>
                <div className="flex justify-between">
                  <span>Container</span>
                  <span className="text-zinc-300">{p.container}</span>
                </div>
                <div className="flex justify-between">
                  <span>Encoder Preset</span>
                  <span className="text-zinc-300">{p.encoder_preset ?? "default"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Audio</span>
                  <span className="text-zinc-300">{p.audio_encoder} @ {p.audio_bitrate}k {p.audio_mixdown}</span>
                </div>
              </div>
              <div>
                <span className="text-xs text-zinc-500">Quality by Resolution</span>
                <div className="grid grid-cols-2 gap-1 mt-1.5">
                  {Object.entries(p.quality_rules)
                    .sort(([a], [b]) => Number(b) - Number(a))
                    .map(([res, q]) => (
                      <div key={res} className="flex justify-between text-xs bg-zinc-800 rounded px-2 py-1">
                        <span className="text-zinc-400">{res}p</span>
                        <span className="text-zinc-200">q{q}</span>
                      </div>
                    ))}
                </div>
              </div>
              {p.skip_codecs.length > 0 && (
                <div className="text-xs text-zinc-500">
                  Skip: {p.skip_codecs.join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function TranscoderPage() {
  const [tab, setTab] = useState<TabId>("overview");
  const [health, setHealth] = useState<TranscoderHealth | null>(null);
  const [stats, setStats] = useState<TranscoderStats | null>(null);
  const [libraries, setLibraries] = useState<TranscoderLibrary[]>([]);
  const [presets, setPresets] = useState<TranscoderPreset[]>([]);
  const [jobs, setJobs] = useState<TranscoderJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const [h, s, l, p, j] = await Promise.all([
        getTranscoderHealth().catch(() => null),
        getTranscoderStats().catch(() => null),
        getTranscoderLibraries().catch(() => []),
        getTranscoderPresets().catch(() => []),
        getTranscoderJobs({ limit: 100 }).catch(() => []),
      ]);
      setHealth(h);
      setStats(s);
      setLibraries(l);
      setPresets(p);
      setJobs(j);
      setError("");
    } catch (e) {
      setError("Failed to connect to Transcoder service");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 10_000);
    return () => clearInterval(iv);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <BlurFade delay={0.05}>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Transcoder</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Video transcoding with HandBrakeCLI &amp; VideoToolbox
            </p>
          </div>
          {health && (
            <div className="flex items-center gap-2">
              <div className={cn("w-2 h-2 rounded-full", health.status === "ok" ? "bg-green-400" : "bg-red-400")} />
              <span className="text-xs text-zinc-400">
                {health.status === "ok" ? "Connected" : "Error"}
              </span>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-1 bg-zinc-900 rounded-xl p-1 border border-zinc-800">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex-1 px-4 py-2 text-sm rounded-lg transition",
                tab === t.id
                  ? "bg-zinc-800 text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "overview" && <OverviewTab stats={stats} health={health} jobs={jobs} />}
        {tab === "libraries" && <LibrariesTab libraries={libraries} presets={presets} onRefresh={fetchData} />}
        {tab === "jobs" && <JobsTab jobs={jobs} onRefresh={fetchData} />}
        {tab === "presets" && <PresetsTab presets={presets} />}
      </div>
    </BlurFade>
  );
}
