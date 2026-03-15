"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getEnergy, getNetwork } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EnergyResponse, EnergySensor, EnergyHistoryPoint, NetworkResponse, BandwidthSensor } from "@/lib/types";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  AreaChart,
  Area,
  BarChart,
  Bar,
} from "recharts";

const TIME_RANGES = [
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
  { label: "48h", hours: 48 },
  { label: "7d", hours: 168 },
];

const CHART_COLORS = [
  "#FFD700", "#4ade80", "#60a5fa", "#f472b6",
  "#a78bfa", "#fb923c", "#34d399", "#f87171",
];

function formatTime(ts: string): string {
  const d = new Date(ts + "Z");
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(ts: string): string {
  const d = new Date(ts + "Z");
  return d.toLocaleString([], {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm">
      <p className="mb-1 text-neutral-400">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value?.toFixed(1)} {p.unit || ""}
        </p>
      ))}
    </div>
  );
}

interface PowerGaugeProps {
  sensor: EnergySensor;
}

function PowerGauge({ sensor }: PowerGaugeProps) {
  const maxWatts = 3000;
  const pct = Math.min((sensor.state / maxWatts) * 100, 100);
  const isHigh = sensor.state > 500;
  const isCritical = sensor.state > 1500;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-xs text-neutral-500 truncate">{sensor.friendly_name}</p>
      <div className="mt-2 flex items-end gap-2">
        <span className={cn(
          "text-2xl font-bold font-mono",
          isCritical ? "text-red-400" : isHigh ? "text-amber-400" : "text-green-400",
        )}>
          {sensor.state.toFixed(0)}
        </span>
        <span className="mb-0.5 text-sm text-neutral-500">{sensor.unit}</span>
      </div>
      <div className="mt-2 h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            isCritical ? "bg-red-400" : isHigh ? "bg-amber-400" : "bg-green-400",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function BandwidthGauge({ sensor }: { sensor: BandwidthSensor }) {
  const maxKbps = 10000;
  const pct = Math.min((sensor.state / maxKbps) * 100, 100);
  const isDown = sensor.entity_id.includes("down");
  const label = sensor.state >= 1024
    ? `${(sensor.state / 1024).toFixed(1)} MB/s`
    : `${sensor.state.toFixed(0)} kB/s`;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-xs text-neutral-500 truncate">{sensor.friendly_name}</p>
      <div className="mt-2 flex items-end gap-2">
        <span className={cn(
          "text-2xl font-bold font-mono",
          isDown ? "text-green-400" : "text-blue-400",
        )}>
          {label}
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

function BatteryCard({ sensor }: { sensor: EnergySensor }) {
  const level = sensor.state;
  const isLow = level < 20;
  const isMed = level < 50;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="flex h-8 w-5 items-center justify-center rounded border border-white/20 relative overflow-hidden">
        <div
          className={cn(
            "absolute bottom-0 left-0 right-0 transition-all",
            isLow ? "bg-red-400" : isMed ? "bg-amber-400" : "bg-green-400",
          )}
          style={{ height: `${level}%` }}
        />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-neutral-200 truncate">{sensor.friendly_name}</p>
        <p className={cn(
          "text-xs font-mono",
          isLow ? "text-red-400" : isMed ? "text-amber-400" : "text-green-400",
        )}>
          {level.toFixed(0)}%
        </p>
      </div>
    </div>
  );
}

export default function EnergyPage() {
  const [data, setData] = useState<EnergyResponse | null>(null);
  const [networkData, setNetworkData] = useState<NetworkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);

  const fetchData = useCallback(async (h: number) => {
    setLoading(true);
    try {
      const [energyResult, networkResult] = await Promise.all([
        getEnergy(h),
        getNetwork(h).catch(() => null),
      ]);
      setData(energyResult);
      setNetworkData(networkResult);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(hours);
    const interval = setInterval(() => fetchData(hours), 30_000);
    return () => clearInterval(interval);
  }, [hours, fetchData]);

  const { powerSensors, energySensors, batteries } = useMemo(() => {
    if (!data) return { powerSensors: [], energySensors: [], batteries: [] };
    return {
      powerSensors: data.current.filter((s) => s.device_class === "power"),
      energySensors: data.current.filter((s) => s.device_class === "energy"),
      batteries: data.current.filter((s) => s.device_class === "battery").sort((a, b) => a.state - b.state),
    };
  }, [data]);

  const totalPower = useMemo(
    () => powerSensors.reduce((sum, s) => sum + s.state, 0),
    [powerSensors],
  );

  const chartData = useMemo(() => {
    if (!data?.history.length) return [];

    const buckets = new Map<string, Record<string, number>>();
    const entityNames = new Map<string, string>();

    for (const sensor of data.current) {
      entityNames.set(sensor.entity_id, sensor.friendly_name);
    }

    for (const point of data.history) {
      const key = hours <= 24
        ? formatTime(point.ts)
        : formatDateTime(point.ts);
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

  const totalEnergy = useMemo(
    () => energySensors.reduce((sum, s) => sum + s.state, 0),
    [energySensors],
  );

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white font-mono">Energy</h1>
            <p className="text-xs sm:text-sm text-neutral-400">
              Power consumption, energy usage, and battery levels
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
            <p className="text-xs text-neutral-500">Total Power</p>
            <p className="mt-1 text-2xl font-bold font-mono text-cyber-yellow">
              {totalPower.toFixed(0)}
              <span className="ml-1 text-sm text-neutral-500">W</span>
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Total Energy</p>
            <p className="mt-1 text-2xl font-bold font-mono text-blue-400">
              {totalEnergy.toFixed(1)}
              <span className="ml-1 text-sm text-neutral-500">kWh</span>
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Estimated Cost</p>
            <p className="mt-1 text-2xl font-bold font-mono text-emerald-400">
              {data?.cost.currency === "INR" ? "\u20B9" : "$"}{data?.cost.total.toFixed(2) ?? "0.00"}
            </p>
            <p className="mt-0.5 text-[10px] text-neutral-600 font-mono">
              @{data?.cost.rate ?? 0}/{data?.cost.currency === "INR" ? "kWh" : "kWh"}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Power Sensors</p>
            <p className="mt-1 text-2xl font-bold font-mono text-green-400">
              {powerSensors.length}
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-neutral-500">Battery Devices</p>
            <p className="mt-1 text-2xl font-bold font-mono text-amber-400">
              {batteries.length}
            </p>
          </div>
        </div>
      </BlurFade>

      {/* Power consumption chart */}
      {chartData.length > 0 && (
        <BlurFade delay={0.1}>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h2 className="mb-4 text-sm font-medium text-neutral-300">
              Power Over Time
            </h2>
            <div className="h-64 sm:h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    {chartSeries.map((name, i) => (
                      <linearGradient key={name} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
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
                      fill={`url(#grad-${i})`}
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

      {/* Live power gauges */}
      {powerSensors.length > 0 && (
        <BlurFade delay={0.15}>
          <div>
            <h2 className="mb-3 text-sm font-medium text-neutral-300">
              Live Power
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {powerSensors.map((s) => (
                <PowerGauge key={s.entity_id} sensor={s} />
              ))}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Energy totals */}
      {energySensors.length > 0 && (
        <BlurFade delay={0.2}>
          <div>
            <h2 className="mb-3 text-sm font-medium text-neutral-300">
              Energy Consumption
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {energySensors.map((s) => {
                const cost = s.unit === "kWh" && data?.cost
                  ? s.state * data.cost.rate
                  : null;
                return (
                  <div
                    key={s.entity_id}
                    className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
                  >
                    <p className="text-xs text-neutral-500 truncate">{s.friendly_name}</p>
                    <p className="mt-2 text-2xl font-bold font-mono text-blue-400">
                      {s.state.toFixed(2)}
                      <span className="ml-1 text-sm text-neutral-500">{s.unit}</span>
                    </p>
                    {cost !== null && cost > 0 && (
                      <p className="mt-1 text-xs font-mono text-emerald-400/70">
                        {data?.cost.currency === "INR" ? "\u20B9" : "$"}{cost.toFixed(2)}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Battery levels */}
      {batteries.length > 0 && (
        <BlurFade delay={0.25}>
          <div>
            <h2 className="mb-3 text-sm font-medium text-neutral-300">
              Battery Levels
            </h2>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {batteries.map((s) => (
                <BatteryCard key={s.entity_id} sensor={s} />
              ))}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Network bandwidth */}
      {networkData && networkData.bandwidth_sensors.length > 0 && (
        <BlurFade delay={0.3}>
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-neutral-300">
                Network Bandwidth
              </h2>
              <div className="flex items-center gap-2 text-xs font-mono">
                <span className="text-green-400">
                  {networkData.total_down_kbps >= 1024
                    ? `${(networkData.total_down_kbps / 1024).toFixed(1)} MB/s`
                    : `${networkData.total_down_kbps.toFixed(0)} kB/s`}
                </span>
                <span className="text-neutral-600">/</span>
                <span className="text-blue-400">
                  {networkData.total_up_kbps >= 1024
                    ? `${(networkData.total_up_kbps / 1024).toFixed(1)} MB/s`
                    : `${networkData.total_up_kbps.toFixed(0)} kB/s`}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {networkData.bandwidth_sensors.map((s) => (
                <BandwidthGauge key={s.entity_id} sensor={s} />
              ))}
            </div>
          </div>
        </BlurFade>
      )}

      {/* Empty state */}
      {!loading && data && powerSensors.length === 0 && energySensors.length === 0 && batteries.length === 0 && (
        <div className="flex items-center justify-center py-20 text-neutral-500">
          No energy sensors found. Connect power/energy/battery sensors in Home Assistant.
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center justify-center py-20 text-neutral-500 animate-pulse">
          Loading energy data...
        </div>
      )}
    </div>
  );
}
