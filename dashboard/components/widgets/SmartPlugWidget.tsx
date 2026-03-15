"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toggleEntity } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface PlugConfig {
  name: string;
  switch_entity: string;
  power_entity: string;
  today_entity: string;
  month_entity: string;
  voltage_entity: string;
  current_entity: string;
  overheated_entity?: string;
  overloaded_entity?: string;
}

interface SmartPlugWidgetProps {
  config: { plugs: PlugConfig[] };
  entities: EntityInfo[];
  onRefresh?: () => void;
}

function MiniGauge({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(value / max, 1);
  return (
    <div className="h-1 w-full rounded-full bg-white/[0.05] overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{ backgroundColor: color }}
        initial={{ width: 0 }}
        animate={{ width: `${pct * 100}%` }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}

function PlugCard({
  plug,
  entities,
  onRefresh,
}: {
  plug: PlugConfig;
  entities: EntityInfo[];
  onRefresh?: () => void;
}) {
  const [toggling, setToggling] = useState(false);

  const find = (eid: string) => entities.find((e) => e.entity_id === eid);
  const num = (eid: string) => {
    const v = parseFloat(find(eid)?.state ?? "");
    return isNaN(v) ? 0 : v;
  };

  const switchEntity = find(plug.switch_entity);
  const isOn = switchEntity?.state === "on";
  const power = num(plug.power_entity);
  const todayKwh = num(plug.today_entity);
  const monthKwh = num(plug.month_entity);
  const voltage = num(plug.voltage_entity);
  const current = num(plug.current_entity);
  const overheated = plug.overheated_entity ? find(plug.overheated_entity)?.state === "on" : false;
  const overloaded = plug.overloaded_entity ? find(plug.overloaded_entity)?.state === "on" : false;

  const powerColor = power > 500 ? "#f87171" : power > 100 ? "#fbbf24" : power > 10 ? "#4ade80" : "#525252";
  const hasWarning = overheated || overloaded;

  const handleToggle = async () => {
    setToggling(true);
    try {
      await toggleEntity(plug.switch_entity);
      onRefresh?.();
    } finally {
      setTimeout(() => setToggling(false), 600);
    }
  };

  return (
    <div className={cn(
      "rounded-xl border p-4 transition-all",
      isOn ? "border-white/[0.08] bg-white/[0.03]" : "border-white/[0.04] bg-white/[0.01]",
      hasWarning && "border-red-500/30",
    )}>
      {/* Header: name + toggle */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 24 24" className={cn("h-4 w-4", isOn ? "text-amber-400" : "text-neutral-600")} fill="currentColor">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.87-3.13-7-7-7zm2 14H10v-1h4v1zm0-2H10v-1h4v1zm-3.5-3.19V13h-1v-2.19c-1.14-.46-2-1.54-2-2.81 0-1.65 1.35-3 3-3s3 1.35 3 3c0 1.27-.86 2.35-2 2.81V13h-1v-2.19z" />
          </svg>
          <span className="text-sm font-medium text-neutral-300">{plug.name}</span>
          {hasWarning && (
            <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] text-red-400 font-medium">
              {overheated ? "HOT" : "OVERLOAD"}
            </span>
          )}
        </div>
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={cn(
            "relative h-6 w-11 rounded-full transition-colors duration-200",
            isOn ? "bg-amber-500" : "bg-neutral-700",
            toggling && "opacity-50",
          )}
        >
          <motion.div
            className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm"
            animate={{ left: isOn ? 22 : 2 }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
          />
        </button>
      </div>

      {/* Power draw */}
      <div className="mb-3">
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold font-mono" style={{ color: isOn ? powerColor : "#525252" }}>
            {isOn ? (power >= 1 ? power.toFixed(1) : power.toFixed(2)) : "--"}
          </span>
          <span className="text-xs text-neutral-500">W</span>
        </div>
        {isOn && <MiniGauge value={power} max={1000} color={powerColor} />}
      </div>

      {/* Consumption row */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <span className="text-[10px] text-neutral-600 block">Today</span>
          <span className="text-sm font-mono text-neutral-300">
            {todayKwh.toFixed(3)} <span className="text-[10px] text-neutral-500">kWh</span>
          </span>
        </div>
        <div>
          <span className="text-[10px] text-neutral-600 block">This Month</span>
          <span className="text-sm font-mono text-neutral-300">
            {monthKwh.toFixed(2)} <span className="text-[10px] text-neutral-500">kWh</span>
          </span>
        </div>
      </div>

      {/* Voltage / Current footer */}
      <div className="flex items-center gap-3 pt-2 border-t border-white/[0.04]">
        <div className="flex items-center gap-1.5">
          <svg viewBox="0 0 16 16" className="h-3 w-3 text-neutral-600" fill="currentColor">
            <path d="M9 1L4 8h4l-1 7 5-7H8l1-7z" />
          </svg>
          <span className="text-[11px] font-mono text-neutral-500">
            {voltage.toFixed(1)} V
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <svg viewBox="0 0 16 16" className="h-3 w-3 text-neutral-600" fill="currentColor">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" />
            <path d="M8 4v4l3 1.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <span className="text-[11px] font-mono text-neutral-500">
            {current.toFixed(2)} A
          </span>
        </div>
      </div>
    </div>
  );
}

export default function SmartPlugWidget({ config, entities, onRefresh }: SmartPlugWidgetProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {config.plugs.map((plug) => (
        <PlugCard key={plug.switch_entity} plug={plug} entities={entities} onRefresh={onRefresh} />
      ))}
    </div>
  );
}
