"use client";

import { useEffect, useState, useMemo } from "react";
import { getEnergy } from "@/lib/api";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

interface PowerChartWidgetProps {
  config: { hours?: number; entity_filter?: string };
}

function MiniTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-white/10 bg-neutral-900/95 px-2 py-1.5 text-[10px] shadow-lg backdrop-blur-sm">
      <p className="text-neutral-500">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.value.toFixed(1)} {p.name}
        </p>
      ))}
    </div>
  );
}

export default function PowerChartWidget({ config }: PowerChartWidgetProps) {
  const [history, setHistory] = useState<{ ts: string; value: number; entity_id: string }[]>([]);
  const [currentPower, setCurrentPower] = useState<number | null>(null);
  const hours = config.hours || 6;

  useEffect(() => {
    getEnergy(hours)
      .then((data) => {
        setHistory(data.history);
        const powerSensors = data.current.filter((s) => s.device_class === "power");
        const total = powerSensors.reduce((sum, s) => sum + s.state, 0);
        setCurrentPower(total);
      })
      .catch(() => {});
  }, [hours]);

  const chartData = useMemo(() => {
    const filter = config.entity_filter || "power";
    const filtered = history.filter((h) => h.entity_id.includes(filter));

    const buckets = new Map<string, { sum: number; count: number }>();
    for (const point of filtered) {
      const t = new Date(point.ts + "Z");
      const key = `${t.getHours().toString().padStart(2, "0")}:${(Math.floor(t.getMinutes() / 15) * 15).toString().padStart(2, "0")}`;
      const existing = buckets.get(key) || { sum: 0, count: 0 };
      existing.sum += point.value;
      existing.count += 1;
      buckets.set(key, existing);
    }

    return Array.from(buckets.entries())
      .map(([time, { sum, count }]) => ({ time, W: Math.round(sum / count) }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [history, config.entity_filter]);

  return (
    <div>
      {currentPower !== null && (
        <div className="mb-2 flex items-baseline gap-1.5">
          <span className="text-2xl font-bold font-mono text-cyber-yellow">
            {currentPower.toFixed(0)}
          </span>
          <span className="text-xs text-neutral-500">W now</span>
        </div>
      )}
      {chartData.length > 1 ? (
        <div className="h-28">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="powerGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#FFD700" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#FFD700" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 9, fill: "#525252" }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis hide />
              <Tooltip content={<MiniTooltip />} />
              <Area
                type="monotone"
                dataKey="W"
                name="W"
                stroke="#FFD700"
                strokeWidth={1.5}
                fill="url(#powerGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-xs text-neutral-600">Collecting power data...</p>
      )}
    </div>
  );
}
