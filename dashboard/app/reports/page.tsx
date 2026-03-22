"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getReportsSummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ReportSummary, ReportDailyPoint, ReportEntitySummary } from "@/lib/types";
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
  { label: "30d", hours: 720 },
  { label: "90d", hours: 2160 },
  { label: "1y", hours: 8760 },
];

const CHART_COLORS = [
  "#FFD700", "#4ade80", "#60a5fa", "#f472b6",
  "#a78bfa", "#fb923c", "#34d399", "#f87171",
];

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

function StatCard({
  label,
  value,
  unit,
  color,
  subtext,
}: {
  label: string;
  value: string;
  unit?: string;
  color: string;
  subtext?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className={cn("mt-1 text-2xl font-bold font-mono", color)}>
        {value}
        {unit && <span className="ml-1 text-sm text-neutral-500">{unit}</span>}
      </p>
      {subtext && (
        <p className="mt-0.5 text-[10px] text-neutral-600 font-mono">{subtext}</p>
      )}
    </div>
  );
}

function TrendBadge({ pct }: { pct: number }) {
  const up = pct > 0;
  const flat = Math.abs(pct) < 1;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono font-medium",
        flat
          ? "bg-neutral-800 text-neutral-400"
          : up
            ? "bg-red-500/10 text-red-400"
            : "bg-green-500/10 text-green-400",
      )}
    >
      {flat ? "~" : up ? "+" : ""}
      {pct.toFixed(1)}%
      {!flat && (
        <span className="text-[9px]">{up ? "vs prev" : "vs prev"}</span>
      )}
    </span>
  );
}

function DailyChart({
  daily,
  id,
}: {
  daily: ReportDailyPoint[];
  id: string;
}) {
  const { chartData, series } = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of daily) {
      const label = d.day.slice(5);
      if (!byDay.has(label)) byDay.set(label, {});
      const name = d.entity_id.split(".").pop() || d.entity_id;
      byDay.get(label)![name] = d.avg;
    }
    const chartData = Array.from(byDay.entries())
      .map(([day, values]) => ({ day, ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));

    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) if (k !== "day") keys.add(k);
    }
    return { chartData, series: Array.from(keys).slice(0, 8) };
  }, [daily]);

  if (!chartData.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-600">
        No data for this period
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData}>
        <defs>
          {series.map((name, i) => (
            <linearGradient key={name} id={`${id}-g-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.3} />
              <stop offset="100%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="day"
          tick={{ fontSize: 10, fill: "#525252" }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} width={45} />
        <Tooltip content={<CustomTooltip />} />
        {series.map((s, i) => (
          <Area
            key={s}
            type="monotone"
            dataKey={s}
            name={s}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            fill={`url(#${id}-g-${i})`}
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

function TopConsumersPanel({
  title,
  items,
  unit,
  accent,
}: {
  title: string;
  items: ReportEntitySummary[];
  unit: string;
  accent: string;
}) {
  const max = items[0]?.avg || 1;
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
          {items.map((item) => {
            const name = item.entity_id.split(".").pop() || item.entity_id;
            return (
              <div key={item.entity_id}>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[11px] text-neutral-400 truncate mr-2">{name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[10px] font-mono text-neutral-500">
                      avg {item.avg.toLocaleString(undefined, { maximumFractionDigits: 1 })} {unit}
                    </span>
                    <span className="text-[10px] font-mono text-neutral-600">
                      peak {item.peak.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                </div>
                <div className="h-1 w-full rounded-full bg-white/5 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.max((item.avg / max) * 100, 2)}%`,
                      backgroundColor: accent,
                      opacity: 0.7,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ActivitySummary({ data }: { data: any[] }) {
  const chartData = useMemo(() => {
    const byDay = new Map<string, Record<string, number>>();
    for (const d of data) {
      if (!d.day || !d.domain) continue;
      const label = d.day.slice(5);
      if (!byDay.has(label)) byDay.set(label, {});
      byDay.get(label)![d.domain] = (byDay.get(label)![d.domain] || 0) + (d.events || 0);
    }
    return Array.from(byDay.entries())
      .map(([day, values]) => ({ day, ...values }))
      .sort((a, b) => a.day.localeCompare(b.day));
  }, [data]);

  const series = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) if (k !== "day") keys.add(k);
    }
    return Array.from(keys)
      .sort((a, b) => {
        const tA = chartData.reduce((s, r) => s + ((r as any)[a] || 0), 0);
        const tB = chartData.reduce((s, r) => s + ((r as any)[b] || 0), 0);
        return tB - tA;
      })
      .slice(0, 8);
  }, [chartData]);

  if (!chartData.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-neutral-600">
        Activity data limited to 30 days
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "#525252" }} axisLine={false} tickLine={false} width={35} />
        <Tooltip content={<CustomTooltip />} />
        {series.map((d, i) => (
          <Bar
            key={d}
            dataKey={d}
            name={d}
            stackId="a"
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            radius={i === series.length - 1 ? [2, 2, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function ReportsPage() {
  const [hours, setHours] = useState(720);
  const [report, setReport] = useState<ReportSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getReportsSummary(hours);
      setReport(data);
    } catch {
      /* silently fail */
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const rangeLabel = TIME_RANGES.find((r) => r.hours === hours)?.label ?? `${hours}h`;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-5 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Reports</h1>
            <p className="text-xs sm:text-sm text-neutral-400">
              Long-term trends powered by Home Assistant statistics
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

      {loading && !report ? (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading report data...
        </div>
      ) : !report ? (
        <div className="flex items-center justify-center py-20 text-neutral-500">
          No report data available. Ensure Home Assistant is connected and has statistics data.
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <BlurFade delay={0.05}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard
                label="Total Energy"
                value={report.energy.total_kwh.toFixed(1)}
                unit="kWh"
                color="text-blue-400"
              />
              <StatCard
                label="Estimated Cost"
                value={`${report.energy.currency === "INR" ? "\u20B9" : "$"}${report.energy.estimated_cost.toFixed(2)}`}
                color="text-emerald-400"
                subtext={`@${report.energy.rate}/${report.energy.currency === "INR" ? "kWh" : "kWh"}`}
              />
              <StatCard
                label="Peak Power"
                value={report.energy.peak_power_w.toFixed(0)}
                unit="W"
                color="text-amber-400"
              />
              <StatCard
                label={`Avg Power (${rangeLabel})`}
                value={report.trend.recent_avg_w.toFixed(1)}
                unit="W"
                color="text-cyber-yellow"
              />
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-neutral-500">Trend</p>
                <div className="mt-2">
                  <TrendBadge pct={report.trend.change_pct} />
                </div>
                <p className="mt-1 text-[10px] text-neutral-600 font-mono">
                  recent vs earlier half
                </p>
              </div>
            </div>
          </BlurFade>

          {/* Energy daily chart */}
          <BlurFade delay={0.1}>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <h2 className="mb-4 text-sm font-medium text-neutral-300">
                Energy -- Daily Average ({rangeLabel})
              </h2>
              <div className="h-56 sm:h-72">
                <DailyChart daily={report.energy.daily} id="rpt-energy" />
              </div>
            </div>
          </BlurFade>

          {/* Network daily chart */}
          {report.network.daily.length > 0 && (
            <BlurFade delay={0.15}>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <h2 className="mb-4 text-sm font-medium text-neutral-300">
                  Network Bandwidth -- Daily Average ({rangeLabel})
                </h2>
                <div className="h-56 sm:h-72">
                  <DailyChart daily={report.network.daily} id="rpt-net" />
                </div>
              </div>
            </BlurFade>
          )}

          {/* Activity chart */}
          {report.activity.data.length > 0 && (
            <BlurFade delay={0.2}>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <h2 className="mb-4 text-sm font-medium text-neutral-300">
                  Activity by Domain (up to 30d)
                </h2>
                <div className="h-48 sm:h-56">
                  <ActivitySummary data={report.activity.data} />
                </div>
              </div>
            </BlurFade>
          )}

          {/* Top consumers */}
          <BlurFade delay={0.25}>
            <div>
              <h2 className="text-sm font-medium text-neutral-300 mb-3">
                Top Entities ({rangeLabel})
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <TopConsumersPanel
                  title="Energy Consumers"
                  items={report.energy.top_consumers}
                  unit="W"
                  accent="#60a5fa"
                />
                <TopConsumersPanel
                  title="Network Bandwidth"
                  items={report.network.top_entities}
                  unit="kB/s"
                  accent="#a78bfa"
                />
              </div>
            </div>
          </BlurFade>
        </>
      )}
    </div>
  );
}
