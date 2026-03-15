"use client";

import { useEffect, useState, useMemo } from "react";
import { getNetwork } from "@/lib/api";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

interface BandwidthChartWidgetProps {
  config: { hours?: number };
}

function MiniTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-white/10 bg-neutral-900/95 px-2 py-1.5 text-[10px] shadow-lg backdrop-blur-sm">
      <p className="text-neutral-500">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.value >= 1024 ? `${(p.value / 1024).toFixed(1)} MB/s` : `${p.value.toFixed(0)} kB/s`}
        </p>
      ))}
    </div>
  );
}

export default function BandwidthChartWidget({ config }: BandwidthChartWidgetProps) {
  const [data, setData] = useState<any>(null);
  const hours = config.hours || 6;

  useEffect(() => {
    getNetwork(hours).then(setData).catch(() => {});
  }, [hours]);

  const chartData = useMemo(() => {
    if (!data?.bandwidth_history?.length) return [];

    const downPoints = data.bandwidth_history.filter(
      (h: any) => h.entity_id === "sensor.total_down",
    );
    const upPoints = data.bandwidth_history.filter(
      (h: any) => h.entity_id === "sensor.total_up",
    );

    const buckets = new Map<string, { down: number; up: number; count: number }>();
    for (const p of downPoints) {
      const t = new Date(p.ts + "Z");
      const key = `${t.getHours().toString().padStart(2, "0")}:${(Math.floor(t.getMinutes() / 15) * 15).toString().padStart(2, "0")}`;
      const b = buckets.get(key) || { down: 0, up: 0, count: 0 };
      b.down += p.value;
      b.count += 1;
      buckets.set(key, b);
    }
    for (const p of upPoints) {
      const t = new Date(p.ts + "Z");
      const key = `${t.getHours().toString().padStart(2, "0")}:${(Math.floor(t.getMinutes() / 15) * 15).toString().padStart(2, "0")}`;
      const b = buckets.get(key) || { down: 0, up: 0, count: 0 };
      b.up += p.value;
      if (!b.count) b.count = 1;
      buckets.set(key, b);
    }

    return Array.from(buckets.entries())
      .map(([time, { down, up, count }]) => ({
        time,
        down: Math.round(down / count),
        up: Math.round(up / Math.max(count, 1)),
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [data]);

  const totalDown = data?.total_down_kbps ?? 0;
  const totalUp = data?.total_up_kbps ?? 0;

  return (
    <div>
      <div className="mb-2 flex items-baseline gap-3">
        <div className="flex items-baseline gap-1">
          <span className="text-lg font-bold font-mono text-green-400">
            {totalDown >= 1024 ? `${(totalDown / 1024).toFixed(1)}` : totalDown.toFixed(0)}
          </span>
          <span className="text-[10px] text-neutral-500">
            {totalDown >= 1024 ? "MB/s" : "kB/s"} down
          </span>
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-lg font-bold font-mono text-blue-400">
            {totalUp >= 1024 ? `${(totalUp / 1024).toFixed(1)}` : totalUp.toFixed(0)}
          </span>
          <span className="text-[10px] text-neutral-500">
            {totalUp >= 1024 ? "MB/s" : "kB/s"} up
          </span>
        </div>
      </div>
      {chartData.length > 1 ? (
        <div className="h-28">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="downGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="upGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
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
                dataKey="down"
                name="Download"
                stroke="#4ade80"
                strokeWidth={1.5}
                fill="url(#downGrad)"
              />
              <Area
                type="monotone"
                dataKey="up"
                name="Upload"
                stroke="#60a5fa"
                strokeWidth={1.5}
                fill="url(#upGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-xs text-neutral-600">Collecting bandwidth data...</p>
      )}
    </div>
  );
}
