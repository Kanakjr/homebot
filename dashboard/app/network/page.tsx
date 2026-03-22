"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getNetwork } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  NetworkResponse,
  MeshNode,
  NetworkClient,
  BandwidthSensor,
  BandwidthHistoryPoint,
} from "@/lib/types";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const TIME_RANGES = [
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
  { label: "48h", hours: 48 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
  { label: "90d", hours: 2160 },
  { label: "1y", hours: 8760 },
];

const CHART_COLORS = [
  "#FFD700", "#4ade80", "#60a5fa", "#f472b6",
  "#a78bfa", "#fb923c", "#34d399", "#f87171",
];

const BAND_LABELS: Record<string, string> = {
  band5: "5 GHz",
  band2_4: "2.4 GHz",
  wired: "Ethernet",
  UNKNOWN: "Unknown",
};

function formatTime(ts: string): string {
  const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(ts: string): string {
  const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
  return d.toLocaleString([], {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDate(ts: string): string {
  const d = new Date(ts.endsWith("Z") ? ts : ts + "Z");
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatBandwidth(kbps: number): string {
  if (kbps >= 1024) return `${(kbps / 1024).toFixed(1)} MB/s`;
  return `${kbps.toFixed(0)} kB/s`;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm">
      <p className="mb-1 text-neutral-400">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value?.toFixed(1)} kB/s
        </p>
      ))}
    </div>
  );
}

function MeshNodeCard({ node }: { node: MeshNode }) {
  const online = node.internet_online;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn(
            "h-2.5 w-2.5 rounded-full",
            online ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]" : "bg-red-400",
          )} />
          <span className="text-sm font-medium text-white">{node.friendly_name}</span>
        </div>
        {node.master && (
          <span className="rounded-full bg-cyber-yellow/15 px-2 py-0.5 text-[10px] font-mono text-cyber-yellow">
            MASTER
          </span>
        )}
      </div>
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between text-neutral-400">
          <span>IP</span>
          <span className="font-mono text-neutral-300">{node.ip}</span>
        </div>
        <div className="flex justify-between text-neutral-400">
          <span>Model</span>
          <span className="font-mono text-neutral-300">{node.model} v{node.hw_version}</span>
        </div>
        <div className="flex justify-between text-neutral-400">
          <span>Firmware</span>
          <span className="font-mono text-neutral-300 truncate ml-4">{node.sw_version.split(" Build")[0]}</span>
        </div>
        <div className="flex justify-between text-neutral-400">
          <span>Status</span>
          <span className={cn("font-mono", online ? "text-green-400" : "text-red-400")}>
            {online ? "Online" : "Offline"}
          </span>
        </div>
      </div>
    </div>
  );
}

function ClientRow({ client }: { client: NetworkClient }) {
  const isOnline = client.state === "home";
  const band = BAND_LABELS[client.connection_type] || client.connection_type;
  const hasTraffic = client.down_kbps > 0 || client.up_kbps > 0;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 hover:border-white/10 transition-colors">
      <div className={cn(
        "h-2 w-2 rounded-full shrink-0",
        isOnline ? "bg-green-400" : "bg-neutral-600",
      )} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-neutral-200 truncate">{client.friendly_name}</p>
          {hasTraffic && (
            <span className="shrink-0 rounded bg-cyber-yellow/10 px-1.5 py-0.5 text-[10px] font-mono text-cyber-yellow">
              ACTIVE
            </span>
          )}
        </div>
        <div className="flex gap-3 mt-0.5 text-[11px] text-neutral-500 font-mono">
          <span>{client.ip}</span>
          <span>{band}</span>
          {client.deco_device && <span>via {client.deco_device}</span>}
        </div>
      </div>
      {hasTraffic && (
        <div className="text-right shrink-0">
          <p className="text-[11px] font-mono text-green-400/80">
            {formatBandwidth(client.down_kbps)}
          </p>
          <p className="text-[11px] font-mono text-blue-400/80">
            {formatBandwidth(client.up_kbps)}
          </p>
        </div>
      )}
    </div>
  );
}

function BandwidthGauge({ sensor }: { sensor: BandwidthSensor }) {
  const maxKbps = 10000;
  const pct = Math.min((sensor.state / maxKbps) * 100, 100);
  const isDown = sensor.entity_id.includes("down");

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-xs text-neutral-500 truncate">{sensor.friendly_name}</p>
      <div className="mt-2 flex items-end gap-2">
        <span className={cn(
          "text-2xl font-bold font-mono",
          isDown ? "text-green-400" : "text-blue-400",
        )}>
          {formatBandwidth(sensor.state)}
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            isDown ? "bg-green-400" : "bg-blue-400",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function NetworkPage() {
  const [data, setData] = useState<NetworkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [filter, setFilter] = useState<"all" | "active" | "offline">("all");

  const fetchData = useCallback(async (h: number) => {
    setLoading(true);
    try {
      const result = await getNetwork(h);
      setData(result);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(hours);
    const interval = setInterval(() => fetchData(hours), 15_000);
    return () => clearInterval(interval);
  }, [hours, fetchData]);

  const filteredClients = useMemo(() => {
    if (!data) return [];
    switch (filter) {
      case "active":
        return data.clients.filter((c) => c.down_kbps > 0 || c.up_kbps > 0);
      case "offline":
        return data.clients.filter((c) => c.state !== "home");
      default:
        return data.clients;
    }
  }, [data, filter]);

  const clientsByNode = useMemo(() => {
    const groups: Record<string, NetworkClient[]> = {};
    for (const c of filteredClients) {
      const node = c.deco_device || "Direct";
      if (!groups[node]) groups[node] = [];
      groups[node].push(c);
    }
    return groups;
  }, [filteredClients]);

  const chartData = useMemo(() => {
    if (!data?.bandwidth_history.length) return [];

    const buckets = new Map<string, Record<string, number>>();
    const entityNames = new Map<string, string>();

    for (const sensor of data.bandwidth_sensors) {
      entityNames.set(sensor.entity_id, sensor.friendly_name);
    }

    for (const point of data.bandwidth_history) {
      const key = hours <= 24
        ? formatTime(point.ts)
        : hours <= 168
          ? formatDateTime(point.ts)
          : formatDate(point.ts);
      if (!buckets.has(key)) buckets.set(key, {});
      const name = entityNames.get(point.entity_id) || point.entity_id.split(".").pop() || point.entity_id;
      buckets.get(key)![name] = point.value;
    }

    return Array.from(buckets.entries()).map(([time, values]) => ({
      time,
      ...values,
    }));
  }, [data, hours]);

  const chartSeries = useMemo(() => {
    if (!chartData.length) return [];
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k !== "time") keys.add(k);
      }
    }
    return Array.from(keys);
  }, [chartData]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Network</h1>
            <p className="text-xs sm:text-sm text-neutral-400">
              TP-Link Deco mesh status, connected devices, and bandwidth
            </p>
          </div>
          <div className="flex gap-1.5">
            {TIME_RANGES.map((r) => (
              <button
                key={r.hours}
                onClick={() => setHours(r.hours)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-mono transition-colors",
                  hours === r.hours
                    ? "bg-cyber-yellow/20 text-cyber-yellow"
                    : "bg-white/5 text-neutral-400 hover:text-white",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </BlurFade>

      {error && (
        <p className="text-sm text-red-400">Error: {error}</p>
      )}

      {/* Summary cards */}
      <BlurFade delay={0.05}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Mesh Nodes</p>
            <p className="mt-1 text-2xl font-bold font-mono text-cyber-yellow">
              {data?.mesh_nodes.length ?? 0}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Connected Devices</p>
            <p className="mt-1 text-2xl font-bold font-mono text-green-400">
              {data?.online_clients ?? 0}
              <span className="ml-1 text-sm text-neutral-500">/ {data?.total_clients ?? 0}</span>
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Total Download</p>
            <p className="mt-1 text-2xl font-bold font-mono text-green-400">
              {data ? formatBandwidth(data.total_down_kbps) : "0 kB/s"}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Total Upload</p>
            <p className="mt-1 text-2xl font-bold font-mono text-blue-400">
              {data ? formatBandwidth(data.total_up_kbps) : "0 kB/s"}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Internet</p>
            <p className={cn(
              "mt-1 text-2xl font-bold font-mono",
              data?.mesh_nodes.some((n) => n.internet_online) ? "text-green-400" : "text-red-400",
            )}>
              {data?.mesh_nodes.some((n) => n.internet_online) ? "Online" : "Offline"}
            </p>
          </div>
        </div>
      </BlurFade>

      {/* Mesh nodes */}
      {data && data.mesh_nodes.length > 0 && (
        <BlurFade delay={0.1}>
          <div>
            <h2 className="mb-3 text-sm font-medium text-neutral-300">Mesh Nodes</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.mesh_nodes.map((node) => (
                <MeshNodeCard key={node.entity_id} node={node} />
              ))}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Bandwidth gauges */}
      {data && data.bandwidth_sensors.length > 0 && (
        <BlurFade delay={0.15}>
          <div>
            <h2 className="mb-3 text-sm font-medium text-neutral-300">Live Bandwidth</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.bandwidth_sensors.map((s) => (
                <BandwidthGauge key={s.entity_id} sensor={s} />
              ))}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Bandwidth chart */}
      {chartData.length > 0 && (
        <BlurFade delay={0.2}>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h2 className="mb-4 text-sm font-medium text-neutral-300">
              Bandwidth Over Time
            </h2>
            <div className="h-64 sm:h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    {chartSeries.map((name, i) => (
                      <linearGradient key={name} id={`bw-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 11, fill: "#737373" }}
                    axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#737373" }}
                    axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                    tickLine={false}
                    width={50}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  {chartSeries.map((name, i) => (
                    <Area
                      key={name}
                      type="monotone"
                      dataKey={name}
                      name={name}
                      stroke={CHART_COLORS[i % CHART_COLORS.length]}
                      fill={`url(#bw-grad-${i})`}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </BlurFade>
      )}

      {/* Connected devices */}
      {data && data.clients.length > 0 && (
        <BlurFade delay={0.25}>
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-neutral-300">Connected Devices</h2>
              <div className="flex gap-1">
                {(["all", "active", "offline"] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={cn(
                      "rounded-full px-2.5 py-0.5 text-[11px] font-mono transition-colors capitalize",
                      filter === f
                        ? "bg-white/10 text-white"
                        : "text-neutral-500 hover:text-neutral-300",
                    )}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            {Object.entries(clientsByNode).map(([node, nodeClients]) => (
              <div key={node} className="mb-4">
                <p className="mb-2 text-xs font-mono text-neutral-500 uppercase tracking-wider">
                  {node} ({nodeClients.length})
                </p>
                <div className="space-y-1.5">
                  {nodeClients.map((c) => (
                    <ClientRow key={c.entity_id} client={c} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </BlurFade>
      )}

      {!loading && data && data.mesh_nodes.length === 0 && data.clients.length === 0 && (
        <div className="flex items-center justify-center py-20 text-neutral-500">
          No network devices found. Connect a TP-Link Deco integration in Home Assistant.
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading network data...
        </div>
      )}
    </div>
  );
}
