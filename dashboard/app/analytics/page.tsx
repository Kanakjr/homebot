"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getAnalytics } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AnalyticsResponse, AnalyticsDataPoint } from "@/lib/types";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
} from "recharts";

const METRICS = [
  { id: "activity", label: "Activity" },
  { id: "energy", label: "Energy" },
  { id: "presence", label: "Presence" },
  { id: "network", label: "Network" },
];

const TIME_RANGES = [
  { label: "7d", hours: 168 },
  { label: "14d", hours: 336 },
  { label: "30d", hours: 720 },
];

const CHART_COLORS = [
  "#FFD700", "#4ade80", "#60a5fa", "#f472b6",
  "#a78bfa", "#fb923c", "#34d399", "#f87171",
  "#818cf8", "#fbbf24", "#6ee7b7", "#93c5fd",
];

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm">
      <p className="mb-1 text-neutral-400">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toLocaleString() : p.value}
        </p>
      ))}
    </div>
  );
}

function ActivityChart({ data }: { data: AnalyticsDataPoint[] }) {
  const chartData = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.domain) continue;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![d.domain] = (byDay.get(d.day)![d.domain] || 0) + (d.events || 0);
    }
    return Array.from(byDay.entries())
      .map(([day, domains]) => ({ day: day.slice(5), ...domains }))
      .sort((a, b) => a.day.localeCompare(b.day));
  }, [data]);

  const domains = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k !== "day") keys.add(k);
      }
    }
    return Array.from(keys).sort((a, b) => {
      const totalA = chartData.reduce((s, r) => s + ((r as any)[a] || 0), 0);
      const totalB = chartData.reduce((s, r) => s + ((r as any)[b] || 0), 0);
      return totalB - totalA;
    }).slice(0, 8);
  }, [chartData]);

  if (!chartData.length) return <p className="text-sm text-neutral-500">No activity data yet.</p>;

  return (
    <div className="h-72 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} width={45} />
          <Tooltip content={<CustomTooltip />} />
          {domains.map((d, i) => (
            <Bar key={d} dataKey={d} name={d} stackId="a" fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EnergyChart({ data }: { data: AnalyticsDataPoint[] }) {
  const chartData = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![name] = d.avg || 0;
    }
    return Array.from(byDay.entries())
      .map(([day, values]) => ({ day: day.slice(5), ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));
  }, [data]);

  const series = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k !== "day") keys.add(k);
      }
    }
    return Array.from(keys).slice(0, 8);
  }, [chartData]);

  if (!chartData.length) return <p className="text-sm text-neutral-500">No energy data yet.</p>;

  return (
    <div className="h-72 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} width={45} />
          <Tooltip content={<CustomTooltip />} />
          {series.map((s, i) => (
            <Line key={s} type="monotone" dataKey={s} name={s} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2} dot={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function PresenceChart({ data }: { data: AnalyticsDataPoint[] }) {
  const chartData = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      const key = `${name}_${d.state || ""}`;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![key] = (byDay.get(d.day)![key] || 0) + (d.transitions || 0);
    }
    return Array.from(byDay.entries())
      .map(([day, values]) => ({ day: day.slice(5), ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));
  }, [data]);

  const series = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k !== "day") keys.add(k);
      }
    }
    return Array.from(keys).slice(0, 10);
  }, [chartData]);

  if (!chartData.length) return <p className="text-sm text-neutral-500">No presence data yet.</p>;

  return (
    <div className="h-72 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} width={45} />
          <Tooltip content={<CustomTooltip />} />
          {series.map((s, i) => (
            <Bar key={s} dataKey={s} name={s} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function NetworkChart({ data }: { data: AnalyticsDataPoint[] }) {
  const chartData = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![name] = d.avg || 0;
    }
    return Array.from(byDay.entries())
      .map(([day, values]) => ({ day: day.slice(5), ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));
  }, [data]);

  const series = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k !== "day") keys.add(k);
      }
    }
    return Array.from(keys);
  }, [chartData]);

  if (!chartData.length) return <p className="text-sm text-neutral-500">No network data yet.</p>;

  return (
    <div className="h-72 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#737373" }} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} width={55} label={{ value: "kB/s", angle: -90, position: "insideLeft", style: { fill: "#737373", fontSize: 11 } }} />
          <Tooltip content={<CustomTooltip />} />
          {series.map((s, i) => (
            <Line key={s} type="monotone" dataKey={s} name={s} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2} dot={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function AnalyticsPage() {
  const [metric, setMetric] = useState("activity");
  const [hours, setHours] = useState(168);
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getAnalytics(metric, hours);
      setData(result);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [metric, hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalEvents = useMemo(() => {
    if (!data?.data.length) return 0;
    return data.data.reduce((s, d) => s + (d.events || d.transitions || d.samples || 0), 0);
  }, [data]);

  const uniqueDays = useMemo(() => {
    if (!data?.data.length) return 0;
    return new Set(data.data.map((d) => d.day)).size;
  }, [data]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Analytics</h1>
            <p className="text-xs sm:text-sm text-neutral-400">
              Historical trends and patterns across your smart home
            </p>
          </div>
          <div className="flex gap-4">
            <div className="flex gap-1.5">
              {METRICS.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setMetric(m.id)}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-mono transition-colors",
                    metric === m.id
                      ? "bg-cyber-yellow/20 text-cyber-yellow"
                      : "bg-white/5 text-neutral-400 hover:text-white",
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="flex gap-1.5">
              {TIME_RANGES.map((r) => (
                <button
                  key={r.hours}
                  onClick={() => setHours(r.hours)}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-mono transition-colors",
                    hours === r.hours
                      ? "bg-white/15 text-white"
                      : "bg-white/5 text-neutral-400 hover:text-white",
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </BlurFade>

      <BlurFade delay={0.05}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Total Data Points</p>
            <p className="mt-1 text-2xl font-bold font-mono text-cyber-yellow">
              {totalEvents.toLocaleString()}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Days Covered</p>
            <p className="mt-1 text-2xl font-bold font-mono text-green-400">
              {uniqueDays}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Metric</p>
            <p className="mt-1 text-2xl font-bold font-mono text-blue-400 capitalize">
              {metric}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Time Range</p>
            <p className="mt-1 text-2xl font-bold font-mono text-amber-400">
              {hours / 24}d
            </p>
          </div>
        </div>
      </BlurFade>

      <BlurFade delay={0.1}>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <h2 className="mb-4 text-sm font-medium text-neutral-300 capitalize">
            {metric} Over Time
          </h2>
          {loading && !data ? (
            <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
              Loading analytics...
            </div>
          ) : data?.data.length ? (
            <>
              {metric === "activity" && <ActivityChart data={data.data} />}
              {metric === "energy" && <EnergyChart data={data.data} />}
              {metric === "presence" && <PresenceChart data={data.data} />}
              {metric === "network" && <NetworkChart data={data.data} />}
            </>
          ) : (
            <div className="flex items-center justify-center py-20 text-neutral-500">
              No data available for this time range. Data accumulates as the backend runs.
            </div>
          )}
        </div>
      </BlurFade>
    </div>
  );
}
