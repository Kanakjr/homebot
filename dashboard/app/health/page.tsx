"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { BlurFade } from "@/components/magicui/blur-fade";
import { cn } from "@/lib/utils";
import { getHealthData } from "@/lib/api";
import type { HealthDataResponse, HealthHistoryPoint } from "@/lib/types";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

const HR_ZONES = [
  { name: "Rest", max: 60, color: "#60a5fa", bg: "bg-blue-500/10" },
  { name: "Light", max: 100, color: "#4ade80", bg: "bg-green-500/10" },
  { name: "Moderate", max: 130, color: "#fbbf24", bg: "bg-amber-500/10" },
  { name: "Hard", max: 160, color: "#fb923c", bg: "bg-orange-500/10" },
  { name: "Peak", max: 220, color: "#f87171", bg: "bg-red-500/10" },
];

function getHrZone(bpm: number) {
  return HR_ZONES.find((z) => bpm <= z.max) ?? HR_ZONES[HR_ZONES.length - 1];
}

function formatTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function HeartRateHero({ bpm, onBody }: { bpm: number; onBody: boolean | null }) {
  const zone = getHrZone(bpm);
  const pulseSpeed = bpm > 0 ? 60 / bpm : 1.5;

  return (
    <div className="relative flex flex-col items-center justify-center py-6">
      {/* Pulse ring */}
      <div className="relative">
        {bpm > 0 && (
          <motion.div
            className="absolute inset-0 rounded-full"
            style={{ border: `2px solid ${zone.color}` }}
            animate={{ scale: [1, 1.4, 1], opacity: [0.6, 0, 0.6] }}
            transition={{ duration: pulseSpeed, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <motion.svg
          viewBox="0 0 24 24"
          className="h-16 w-16"
          animate={bpm > 0 ? { scale: [1, 1.15, 1] } : {}}
          transition={{ duration: pulseSpeed, repeat: Infinity, ease: "easeInOut" }}
        >
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill={zone.color}
            opacity={0.2}
          />
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill="none"
            stroke={zone.color}
            strokeWidth="1.5"
          />
        </motion.svg>
      </div>
      <span className="text-5xl font-bold font-mono mt-3" style={{ color: zone.color }}>
        {bpm || "--"}
      </span>
      <span className="text-sm text-neutral-500 mt-1">bpm</span>
      <div className="flex items-center gap-2 mt-2">
        <span
          className={cn("rounded-full px-3 py-1 text-xs font-medium", zone.bg)}
          style={{ color: zone.color }}
        >
          {zone.name}
        </span>
        {onBody !== null && (
          <span className={cn(
            "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px]",
            onBody ? "bg-green-500/10 text-green-400" : "bg-neutral-800 text-neutral-500",
          )}>
            <span className={cn("h-1.5 w-1.5 rounded-full", onBody ? "bg-green-400" : "bg-neutral-600")} />
            {onBody ? "On wrist" : "Off wrist"}
          </span>
        )}
      </div>
    </div>
  );
}

function ActivityRing({
  value,
  goal,
  color,
  label,
  unit,
  size = 100,
}: {
  value: number;
  goal: number;
  color: string;
  label: string;
  unit: string;
  size?: number;
}) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(value / goal, 1);
  const strokeDashoffset = circumference * (1 - progress);

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={6}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
      </svg>
      <div className="flex flex-col items-center -mt-[calc(50%+12px)]" style={{ marginTop: -(size / 2 + 12) }}>
        <span className="text-lg font-bold font-mono text-neutral-200">
          {typeof value === "number" && value % 1 !== 0 ? value.toFixed(1) : Math.round(value).toLocaleString()}
        </span>
        <span className="text-[10px] text-neutral-500">{unit}</span>
      </div>
      <span className="text-xs text-neutral-400 mt-3">{label}</span>
      <span className="text-[10px] text-neutral-600">
        / {goal.toLocaleString()} {unit}
      </span>
    </div>
  );
}

function StatCard({
  icon,
  value,
  unit,
  label,
  sublabel,
  color = "text-neutral-200",
}: {
  icon: React.ReactNode;
  value: string;
  unit: string;
  label: string;
  sublabel?: string;
  color?: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className="text-neutral-500">{icon}</div>
        <span className="text-xs text-neutral-500">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={cn("text-2xl font-bold font-mono", color)}>{value}</span>
        <span className="text-xs text-neutral-500">{unit}</span>
      </div>
      {sublabel && <span className="text-[10px] text-neutral-600 mt-1 block">{sublabel}</span>}
    </div>
  );
}

function DeviceCard({
  name,
  battery,
  batteryState,
  charger,
  extra,
}: {
  name: string;
  battery: number | null;
  batteryState: string | null;
  charger: string | null;
  extra?: React.ReactNode;
}) {
  const batteryColor =
    battery === null ? "text-neutral-500" :
    battery > 60 ? "text-green-400" :
    battery > 20 ? "text-amber-400" : "text-red-400";

  const isCharging = batteryState === "charging" || (charger && charger !== "none");

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-neutral-300">{name}</span>
        {isCharging && (
          <svg viewBox="0 0 20 20" className="h-4 w-4 text-amber-400" fill="currentColor">
            <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
          </svg>
        )}
      </div>
      <div className="flex items-center gap-3">
        {/* Battery bar */}
        <div className="flex-1">
          <div className="flex items-baseline justify-between mb-1">
            <span className={cn("text-xl font-bold font-mono", batteryColor)}>
              {battery !== null ? `${battery}%` : "--"}
            </span>
            <span className="text-[10px] text-neutral-600 capitalize">
              {batteryState ?? "unknown"}
            </span>
          </div>
          <div className="h-2 rounded-full bg-white/[0.05] overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              style={{ backgroundColor: battery === null ? "#525252" : battery > 60 ? "#4ade80" : battery > 20 ? "#fbbf24" : "#f87171" }}
              initial={{ width: 0 }}
              animate={{ width: `${battery ?? 0}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
          </div>
        </div>
      </div>
      {extra && <div className="mt-3">{extra}</div>}
    </div>
  );
}

function HrChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-neutral-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm">
      <p className="text-neutral-400 mb-1">{label}</p>
      <p className="text-red-400 font-mono font-bold">{payload[0].value} bpm</p>
    </div>
  );
}

function HeartRateChart({ points }: { points: HealthHistoryPoint[] }) {
  const data = useMemo(() => {
    if (!points.length) return [];
    const sampled = points.length > 200
      ? points.filter((_, i) => i % Math.ceil(points.length / 200) === 0)
      : points;
    return sampled.map((p) => ({
      time: formatTime(p.ts),
      bpm: p.value,
    }));
  }, [points]);

  const avg = useMemo(
    () => data.length ? Math.round(data.reduce((s, d) => s + d.bpm, 0) / data.length) : 0,
    [data],
  );
  const min = useMemo(() => data.length ? Math.min(...data.map((d) => d.bpm)) : 0, [data]);
  const max = useMemo(() => data.length ? Math.max(...data.map((d) => d.bpm)) : 0, [data]);

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-48 text-neutral-600 text-sm">
        No heart rate history available yet. Data will appear as the watch reports readings.
      </div>
    );
  }

  return (
    <div>
      <div className="flex gap-4 mb-4 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-blue-400" />
          <span className="text-neutral-500">Min</span>
          <span className="font-mono text-neutral-300">{min}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-green-400" />
          <span className="text-neutral-500">Avg</span>
          <span className="font-mono text-neutral-300">{avg}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-red-400" />
          <span className="text-neutral-500">Max</span>
          <span className="font-mono text-neutral-300">{max}</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
          <defs>
            <linearGradient id="hrGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f87171" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#666" }} interval="preserveStartEnd" />
          <YAxis
            domain={["dataMin - 5", "dataMax + 5"]}
            tick={{ fontSize: 10, fill: "#666" }}
            width={40}
          />
          <Tooltip content={<HrChartTooltip />} />
          <ReferenceLine y={avg} stroke="#4ade80" strokeDasharray="4 4" strokeOpacity={0.5} />
          <Area
            type="monotone"
            dataKey="bpm"
            stroke="#f87171"
            strokeWidth={1.5}
            fill="url(#hrGradient)"
            dot={false}
            activeDot={{ r: 3, fill: "#f87171" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function SleepDisplay({ minutes }: { minutes: number }) {
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  const quality = minutes >= 420 ? "Good" : minutes >= 360 ? "Fair" : minutes >= 240 ? "Low" : "Very Low";
  const qualityColor = minutes >= 420 ? "text-green-400" : minutes >= 360 ? "text-amber-400" : "text-red-400";
  const progress = Math.min(minutes / 480, 1); // 8h = 100%

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold font-mono text-indigo-400">{hours}</span>
          <span className="text-sm text-neutral-500">h</span>
          <span className="text-3xl font-bold font-mono text-indigo-400 ml-1">{mins}</span>
          <span className="text-sm text-neutral-500">m</span>
        </div>
        <span className={cn("text-xs font-medium", qualityColor)}>{quality}</span>
      </div>
      <div className="h-3 rounded-full bg-white/[0.05] overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-indigo-400"
          initial={{ width: 0 }}
          animate={{ width: `${progress * 100}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-neutral-600">0h</span>
        <span className="text-[10px] text-neutral-600">8h goal</span>
      </div>
    </div>
  );
}

const TIME_OPTIONS = [
  { label: "6h", hours: 6 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
  { label: "48h", hours: 48 },
];

export default function HealthPage() {
  const [data, setData] = useState<HealthDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (h: number) => {
    try {
      const result = await getHealthData(h);
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
  }, [fetchData, hours]);

  const num = (key: string) => {
    const v = parseFloat(data?.current[key]?.state ?? "");
    return isNaN(v) ? 0 : v;
  };
  const str = (key: string) => data?.current[key]?.state ?? "--";

  const heartRate = num("heart_rate");
  const steps = num("steps") || num("steps_total");
  const calories = num("calories");
  const distance = num("distance");
  const floors = num("floors");
  const pressure = num("pressure");
  const activity = str("activity");
  const pixelActivity = str("pixel_activity");
  const onBody = data?.current.on_body ? str("on_body") === "on" : null;
  const watchBattery = data?.current.watch_battery ? num("watch_battery") : null;
  const watchBatteryState = data?.current.watch_battery_state?.state ?? null;
  const watchCharger = data?.current.watch_charger?.state ?? null;
  const pixelBattery = data?.current.pixel_battery ? num("pixel_battery") : null;
  const pixelBatteryState = data?.current.pixel_battery_state?.state ?? null;
  const pixelCharger = data?.current.pixel_battery_state?.state ?? null;
  const pixelSleep = num("pixel_sleep");
  const pixelSteps = num("pixel_steps");
  const pixelDistance = num("pixel_distance");
  const pixelLocation = str("pixel_location");

  const hrHistory = data?.history.heart_rate ?? [];

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-screen text-neutral-500">
        Loading health data...
      </div>
    );
  }

  return (
    <div className="relative p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl">
      {/* Header */}
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">Health</h1>
            <p className="text-sm text-neutral-400">
              Galaxy Watch 8 Classic + Pixel 9 Pro
            </p>
          </div>
          {error && (
            <span className="rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-400">
              {error}
            </span>
          )}
        </div>
      </BlurFade>

      {/* Hero: Heart Rate */}
      <BlurFade delay={0.05}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
          <HeartRateHero bpm={heartRate} onBody={onBody} />
        </div>
      </BlurFade>

      {/* Activity Rings */}
      <BlurFade delay={0.1}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-neutral-400 mb-5">Daily Activity</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 justify-items-center">
            <ActivityRing value={steps} goal={10000} color="#4ade80" label="Steps" unit="steps" />
            <ActivityRing value={calories} goal={2000} color="#fb923c" label="Calories" unit="kcal" />
            <ActivityRing value={distance} goal={5} color="#60a5fa" label="Distance" unit="km" />
            <ActivityRing value={floors} goal={10} color="#a78bfa" label="Floors" unit="floors" />
          </div>
        </div>
      </BlurFade>

      {/* Stats Cards */}
      <BlurFade delay={0.15}>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path d="M10 18a1 1 0 01-.707-.293l-3-3a1 1 0 011.414-1.414L10 15.586l2.293-2.293a1 1 0 011.414 1.414l-3 3A1 1 0 0110 18zM10 2a1 1 0 01.707.293l3 3a1 1 0 01-1.414 1.414L10 4.414 7.707 6.707a1 1 0 01-1.414-1.414l3-3A1 1 0 0110 2z" />
              </svg>
            }
            value={steps.toLocaleString()}
            unit="steps"
            label="Steps"
            sublabel={pixelSteps > 0 ? `Pixel: ${pixelSteps.toLocaleString()}` : undefined}
          />
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
              </svg>
            }
            value={Math.round(calories).toLocaleString()}
            unit="kcal"
            label="Calories"
            color="text-orange-400"
          />
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
              </svg>
            }
            value={distance > 0 ? (distance >= 1 ? distance.toFixed(1) : (distance * 1000).toFixed(0)) : "0"}
            unit={distance >= 1 ? "km" : "m"}
            label="Distance"
            sublabel={pixelDistance > 0 ? `Pixel: ${(pixelDistance / 1000).toFixed(1)} km` : undefined}
          />
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
              </svg>
            }
            value={pressure > 0 ? pressure.toFixed(1) : "--"}
            unit="hPa"
            label="Barometric Pressure"
          />
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path d="M2 4.5A2.5 2.5 0 014.5 2h11a2.5 2.5 0 010 5h-11A2.5 2.5 0 012 4.5zM2.5 9.72a.75.75 0 01.75-.22h5a.75.75 0 010 1.5h-5a.75.75 0 01-.75-.78V9.72zM2.5 14.72a.75.75 0 01.75-.22h8a.75.75 0 010 1.5h-8a.75.75 0 01-.75-.78V14.72z" />
              </svg>
            }
            value={floors > 0 ? floors.toFixed(0) : "0"}
            unit="floors"
            label="Floors Climbed"
          />
          <StatCard
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.788l1.599.799L9 4.323V3a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
            }
            value={activity !== "--" ? activity : pixelActivity}
            unit=""
            label="Activity State"
            sublabel={activity !== "--" && pixelActivity !== "--" ? `Pixel: ${pixelActivity}` : undefined}
          />
        </div>
      </BlurFade>

      {/* Heart Rate Chart */}
      <BlurFade delay={0.2}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-neutral-400">Heart Rate History</h2>
            <div className="flex gap-1">
              {TIME_OPTIONS.map((opt) => (
                <button
                  key={opt.hours}
                  onClick={() => setHours(opt.hours)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                    hours === opt.hours
                      ? "bg-red-500/10 text-red-400"
                      : "text-neutral-500 hover:bg-white/5 hover:text-neutral-300",
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <HeartRateChart points={hrHistory} />
        </div>
      </BlurFade>

      {/* Sleep */}
      <BlurFade delay={0.25}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 mb-4">
            <svg viewBox="0 0 20 20" className="h-4 w-4 text-indigo-400" fill="currentColor">
              <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
            </svg>
            <h2 className="text-sm font-medium text-neutral-400">Sleep</h2>
          </div>
          {pixelSleep > 0 ? (
            <SleepDisplay minutes={pixelSleep} />
          ) : (
            <p className="text-sm text-neutral-600">No sleep data recorded today.</p>
          )}
        </div>
      </BlurFade>

      {/* Location */}
      {pixelLocation && pixelLocation !== "--" && (
        <BlurFade delay={0.28}>
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="flex items-center gap-2">
              <svg viewBox="0 0 20 20" className="h-4 w-4 text-blue-400 shrink-0" fill="currentColor">
                <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
              </svg>
              <div className="min-w-0">
                <span className="text-xs text-neutral-500">Location</span>
                <p className="text-sm text-neutral-300 truncate">{pixelLocation}</p>
              </div>
            </div>
          </div>
        </BlurFade>
      )}

      {/* Device Status */}
      <BlurFade delay={0.3}>
        <h2 className="text-sm font-medium text-neutral-400 mb-3">Devices</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <DeviceCard
            name="Galaxy Watch 8 Classic"
            battery={watchBattery}
            batteryState={watchBatteryState}
            charger={watchCharger}
            extra={onBody !== null ? (
              <div className="flex items-center gap-1.5 text-xs">
                <span className={cn("h-2 w-2 rounded-full", onBody ? "bg-green-400" : "bg-neutral-600")} />
                <span className={onBody ? "text-green-400" : "text-neutral-500"}>
                  {onBody ? "On wrist" : "Off wrist"}
                </span>
              </div>
            ) : undefined}
          />
          <DeviceCard
            name="Pixel 9 Pro"
            battery={pixelBattery}
            batteryState={pixelBatteryState}
            charger={pixelCharger}
          />
        </div>
      </BlurFade>

      {/* HR Zone Legend */}
      <BlurFade delay={0.35}>
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
          <h3 className="text-xs text-neutral-500 mb-3">Heart Rate Zones</h3>
          <div className="flex flex-wrap gap-3">
            {HR_ZONES.map((z) => (
              <div key={z.name} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: z.color }} />
                <span className="text-xs text-neutral-400">{z.name}</span>
                <span className="text-[10px] text-neutral-600 font-mono">
                  {"<"}{z.max}
                </span>
              </div>
            ))}
          </div>
        </div>
      </BlurFade>
    </div>
  );
}
