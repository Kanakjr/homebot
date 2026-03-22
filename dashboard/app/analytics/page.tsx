"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getAnalytics } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AnalyticsDataPoint } from "@/lib/types";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

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

const SECTION_COLORS: Record<string, string> = {
  activity: "#FFD700",
  energy: "#60a5fa",
  presence: "#4ade80",
  network: "#a78bfa",
};

interface AllMetrics {
  activity: AnalyticsDataPoint[];
  energy: AnalyticsDataPoint[];
  presence: AnalyticsDataPoint[];
  network: AnalyticsDataPoint[];
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm">
      <p className="mb-1 text-neutral-400">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : p.value}
        </p>
      ))}
    </div>
  );
}

function useActivityChart(data: AnalyticsDataPoint[]) {
  return useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.domain) continue;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![d.domain] = (byDay.get(d.day)![d.domain] || 0) + (d.events || 0);
    }
    const chartData = Array.from(byDay.entries())
      .map(([day, domains]) => ({ day: day.slice(5), ...domains }))
      .sort((a, b) => a.day.localeCompare(b.day));

    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) if (k !== "day") keys.add(k);
    }
    const series = Array.from(keys)
      .sort((a, b) => {
        const tA = chartData.reduce((s, r) => s + ((r as any)[a] || 0), 0);
        const tB = chartData.reduce((s, r) => s + ((r as any)[b] || 0), 0);
        return tB - tA;
      })
      .slice(0, 8);

    return { chartData, series };
  }, [data]);
}

function useEntityChart(data: AnalyticsDataPoint[], valueKey: "avg" | "transitions" = "avg") {
  return useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      const key = valueKey === "transitions" && d.state ? `${name}_${d.state}` : name;
      if (!byDay.has(d.day)) byDay.set(d.day, {});
      byDay.get(d.day)![key] = (byDay.get(d.day)![key] || 0) + ((d as any)[valueKey] || 0);
    }
    const chartData = Array.from(byDay.entries())
      .map(([day, values]) => ({ day: day.slice(5), ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));

    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) if (k !== "day") keys.add(k);
    }
    const series = Array.from(keys).slice(0, 8);
    return { chartData, series };
  }, [data, valueKey]);
}

function ActivityChartCard({ data }: { data: AnalyticsDataPoint[] }) {
  const { chartData, series } = useActivityChart(data);
  if (!chartData.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} width={35} />
        <Tooltip content={<CustomTooltip />} />
        {series.map((d, i) => (
          <Bar key={d} dataKey={d} name={d} stackId="a" fill={CHART_COLORS[i % CHART_COLORS.length]} radius={i === series.length - 1 ? [2, 2, 0, 0] : undefined} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function GradientAreaChart({ data, series, id }: { data: any[]; series: string[]; id: string }) {
  if (!data.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data}>
        <defs>
          {series.map((name, i) => (
            <linearGradient key={name} id={`${id}-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.3} />
              <stop offset="100%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} width={35} />
        <Tooltip content={<CustomTooltip />} />
        {series.map((s, i) => (
          <Area key={s} type="monotone" dataKey={s} name={s} stroke={CHART_COLORS[i % CHART_COLORS.length]} fill={`url(#${id}-grad-${i})`} strokeWidth={1.5} dot={false} connectNulls />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

function PresenceChartCard({ data }: { data: AnalyticsDataPoint[] }) {
  const { chartData, series } = useEntityChart(data, "transitions");
  if (!chartData.length) return <EmptyChart />;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} width={35} />
        <Tooltip content={<CustomTooltip />} />
        {series.map((s, i) => (
          <Bar key={s} dataKey={s} name={s} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[2, 2, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center text-xs text-neutral-600">
      No data yet
    </div>
  );
}

function ChartCard({
  title,
  accent,
  count,
  children,
}: {
  title: string;
  accent: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: accent }} />
          <h3 className="text-sm font-medium text-neutral-300">{title}</h3>
        </div>
        <span className="text-[10px] font-mono text-neutral-500">
          {count.toLocaleString()} pts
        </span>
      </div>
      <div className="h-48 sm:h-56 flex-1">{children}</div>
    </div>
  );
}

interface RankedItem {
  label: string;
  value: number;
}

function TopEntitiesPanel({
  title,
  accent,
  items,
  unit,
}: {
  title: string;
  accent: string;
  items: RankedItem[];
  unit?: string;
}) {
  const max = items[0]?.value || 1;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: accent }} />
        <h3 className="text-xs font-medium text-neutral-300">{title}</h3>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-neutral-600">No data</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.label}>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-[11px] text-neutral-400 truncate mr-2">{item.label}</span>
                <span className="text-[10px] font-mono text-neutral-500 shrink-0">
                  {item.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  {unit ? ` ${unit}` : ""}
                </span>
              </div>
              <div className="h-1 w-full rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max((item.value / max) * 100, 2)}%`,
                    backgroundColor: accent,
                    opacity: 0.7,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function useTopEntities(data: AllMetrics) {
  return useMemo(() => {
    const topActivity: RankedItem[] = [];
    const domainTotals = new Map<string, number>();
    for (const d of data.activity) {
      if (!d.domain) continue;
      domainTotals.set(d.domain, (domainTotals.get(d.domain) || 0) + (d.events || 0));
    }
    for (const [label, value] of Array.from(domainTotals.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5)) {
      topActivity.push({ label, value });
    }

    const topEnergy: RankedItem[] = [];
    const energyTotals = new Map<string, { sum: number; count: number }>();
    for (const d of data.energy) {
      if (!d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      const prev = energyTotals.get(name) || { sum: 0, count: 0 };
      energyTotals.set(name, { sum: prev.sum + (d.avg || 0), count: prev.count + 1 });
    }
    for (const [label, { sum, count }] of Array.from(energyTotals.entries())
      .sort((a, b) => b[1].sum / b[1].count - a[1].sum / a[1].count)
      .slice(0, 5)) {
      topEnergy.push({ label, value: Math.round((sum / count) * 10) / 10 });
    }

    const topPresence: RankedItem[] = [];
    const presenceTotals = new Map<string, number>();
    for (const d of data.presence) {
      if (!d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      presenceTotals.set(name, (presenceTotals.get(name) || 0) + (d.transitions || 0));
    }
    for (const [label, value] of Array.from(presenceTotals.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5)) {
      topPresence.push({ label, value });
    }

    const topNetwork: RankedItem[] = [];
    const netTotals = new Map<string, { sum: number; count: number }>();
    for (const d of data.network) {
      if (!d.entity_id) continue;
      const name = d.entity_id.split(".").pop() || d.entity_id;
      const prev = netTotals.get(name) || { sum: 0, count: 0 };
      netTotals.set(name, { sum: prev.sum + (d.avg || 0), count: prev.count + 1 });
    }
    for (const [label, { sum, count }] of Array.from(netTotals.entries())
      .sort((a, b) => b[1].sum / b[1].count - a[1].sum / a[1].count)
      .slice(0, 5)) {
      topNetwork.push({ label, value: Math.round((sum / count) * 10) / 10 });
    }

    return { topActivity, topEnergy, topPresence, topNetwork };
  }, [data]);
}

function useStats(data: AllMetrics) {
  return useMemo(() => {
    const totalEvents = data.activity.reduce((s, d) => s + (d.events || 0), 0);

    const entityIds = new Set<string>();
    for (const d of [...data.energy, ...data.presence, ...data.network]) {
      if (d.entity_id) entityIds.add(d.entity_id);
    }

    const dayEvents = new Map<string, number>();
    for (const d of data.activity) {
      if (!d.day) continue;
      dayEvents.set(d.day, (dayEvents.get(d.day) || 0) + (d.events || 0));
    }
    let busiestDay = "";
    let busiestCount = 0;
    for (const [day, count] of dayEvents) {
      if (count > busiestCount) {
        busiestDay = day;
        busiestCount = count;
      }
    }

    const allDays = new Set<string>();
    for (const list of [data.activity, data.energy, data.presence, data.network]) {
      for (const d of list) if (d.day) allDays.add(d.day);
    }
    const dayCount = allDays.size || 1;
    const avgDaily = Math.round(totalEvents / dayCount);

    return {
      totalEvents,
      uniqueEntities: entityIds.size,
      busiestDay: busiestDay ? busiestDay.slice(5) : "--",
      avgDaily,
    };
  }, [data]);
}

export default function AnalyticsPage() {
  const [hours, setHours] = useState(168);
  const [metrics, setMetrics] = useState<AllMetrics>({
    activity: [],
    energy: [],
    presence: [],
    network: [],
  });
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [activity, energy, presence, network] = await Promise.all([
        getAnalytics("activity", hours),
        getAnalytics("energy", hours),
        getAnalytics("presence", hours),
        getAnalytics("network", hours),
      ]);
      setMetrics({
        activity: activity.data,
        energy: energy.data,
        presence: presence.data,
        network: network.data,
      });
    } catch {
      /* silently fail */
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const stats = useStats(metrics);
  const { topActivity, topEnergy, topPresence, topNetwork } = useTopEntities(metrics);

  const energyChart = useEntityChart(metrics.energy, "avg");
  const networkChart = useEntityChart(metrics.network, "avg");

  const hasAnyData =
    metrics.activity.length > 0 ||
    metrics.energy.length > 0 ||
    metrics.presence.length > 0 ||
    metrics.network.length > 0;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-5 max-w-7xl">
      {/* Header */}
      <BlurFade delay={0}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Analytics</h1>
            <p className="text-xs sm:text-sm text-neutral-400">
              Historical trends and patterns across your smart home
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

      {loading && !hasAnyData ? (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading analytics...
        </div>
      ) : !hasAnyData ? (
        <div className="flex items-center justify-center py-20 text-neutral-500">
          No data available for this time range. Data accumulates as the backend runs.
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <BlurFade delay={0.05}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-neutral-500">Total Events</p>
                <p className="mt-1 text-2xl font-bold font-mono text-cyber-yellow">
                  {stats.totalEvents.toLocaleString()}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-neutral-500">Unique Entities</p>
                <p className="mt-1 text-2xl font-bold font-mono text-blue-400">
                  {stats.uniqueEntities}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-neutral-500">Most Active Day</p>
                <p className="mt-1 text-2xl font-bold font-mono text-green-400">
                  {stats.busiestDay}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-neutral-500">Avg Daily Events</p>
                <p className="mt-1 text-2xl font-bold font-mono text-amber-400">
                  {stats.avgDaily.toLocaleString()}
                </p>
              </div>
            </div>
          </BlurFade>

          {/* 2x2 chart grid */}
          <BlurFade delay={0.1}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <ChartCard title="Activity" accent={SECTION_COLORS.activity} count={metrics.activity.length}>
                <ActivityChartCard data={metrics.activity} />
              </ChartCard>
              <ChartCard title="Energy" accent={SECTION_COLORS.energy} count={metrics.energy.length}>
                <GradientAreaChart data={energyChart.chartData} series={energyChart.series} id="energy" />
              </ChartCard>
              <ChartCard title="Presence" accent={SECTION_COLORS.presence} count={metrics.presence.length}>
                <PresenceChartCard data={metrics.presence} />
              </ChartCard>
              <ChartCard title="Network" accent={SECTION_COLORS.network} count={metrics.network.length}>
                <GradientAreaChart data={networkChart.chartData} series={networkChart.series} id="network" />
              </ChartCard>
            </div>
          </BlurFade>

          {/* Top entities breakdown */}
          <BlurFade delay={0.15}>
            <div>
              <h2 className="text-sm font-medium text-neutral-300 mb-3">Top Entities</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <TopEntitiesPanel title="Activity" accent={SECTION_COLORS.activity} items={topActivity} unit="events" />
                <TopEntitiesPanel title="Energy" accent={SECTION_COLORS.energy} items={topEnergy} unit="avg" />
                <TopEntitiesPanel title="Presence" accent={SECTION_COLORS.presence} items={topPresence} unit="trans." />
                <TopEntitiesPanel title="Network" accent={SECTION_COLORS.network} items={topNetwork} unit="kB/s" />
              </div>
            </div>
          </BlurFade>
        </>
      )}
    </div>
  );
}
