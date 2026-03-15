"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toggleEntity } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface SmartPlugWidgetProps {
  config: {
    switch_entity: string;
    power_entity: string;
    today_entity: string;
    month_entity: string;
    voltage_entity: string;
    current_entity: string;
    overheated_entity?: string;
    overloaded_entity?: string;
  };
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

export default function SmartPlugWidget({ config, entities, onRefresh }: SmartPlugWidgetProps) {
  const [toggling, setToggling] = useState(false);

  const find = (eid: string) => entities.find((e) => e.entity_id === eid);
  const num = (eid: string) => {
    const v = parseFloat(find(eid)?.state ?? "");
    return isNaN(v) ? 0 : v;
  };

  const switchEntity = find(config.switch_entity);
  const isOn = switchEntity?.state === "on";
  const power = num(config.power_entity);
  const todayKwh = num(config.today_entity);
  const monthKwh = num(config.month_entity);
  const voltage = num(config.voltage_entity);
  const current = num(config.current_entity);
  const overheated = config.overheated_entity ? find(config.overheated_entity)?.state === "on" : false;
  const overloaded = config.overloaded_entity ? find(config.overloaded_entity)?.state === "on" : false;

  const powerColor = power > 500 ? "#f87171" : power > 100 ? "#fbbf24" : power > 10 ? "#4ade80" : "#525252";
  const hasWarning = overheated || overloaded;

  const handleToggle = async () => {
    setToggling(true);
    try {
      await toggleEntity(config.switch_entity);
      onRefresh?.();
    } finally {
      setTimeout(() => setToggling(false), 600);
    }
  };

  return (
    <div className="space-y-3">
      {/* Toggle + warnings */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {hasWarning && (
            <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] text-red-400 font-medium">
              {overheated ? "HOT" : "OVERLOAD"}
            </span>
          )}
          <span className={cn(
            "text-xs capitalize",
            isOn ? "text-green-400" : "text-neutral-500",
          )}>
            {isOn ? "On" : "Off"}
          </span>
        </div>
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={cn(
            "relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200",
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
      <div>
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold font-mono" style={{ color: isOn ? powerColor : "#525252" }}>
            {isOn ? (power >= 1 ? power.toFixed(1) : power.toFixed(2)) : "--"}
          </span>
          <span className="text-xs text-neutral-500">W</span>
        </div>
        {isOn && <MiniGauge value={power} max={1000} color={powerColor} />}
      </div>

      {/* Consumption */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[10px] text-neutral-600 block">Today</span>
          <span className="text-sm font-mono text-neutral-300">{todayKwh.toFixed(3)}</span>
          <span className="text-[10px] text-neutral-500 ml-0.5">kWh</span>
        </div>
        <div className="text-right">
          <span className="text-[10px] text-neutral-600 block">Month</span>
          <span className="text-sm font-mono text-neutral-300">{monthKwh.toFixed(2)}</span>
          <span className="text-[10px] text-neutral-500 ml-0.5">kWh</span>
        </div>
      </div>

      {/* Voltage / Current */}
      <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
        <span className="text-[11px] font-mono text-neutral-500">{voltage.toFixed(1)} V</span>
        <span className="text-[11px] font-mono text-neutral-500">{current.toFixed(2)} A</span>
      </div>
    </div>
  );
}
