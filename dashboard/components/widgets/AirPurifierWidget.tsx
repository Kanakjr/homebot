"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toggleEntity, setClimateState } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface AirPurifierWidgetProps {
  config: {
    fan_entity: string;
    pm25_entity: string;
    temperature_entity: string;
    humidity_entity: string;
    filter_life_entity: string;
    motor_speed_entity: string;
    climate_entity?: string;
  };
  entities: EntityInfo[];
  onRefresh?: () => void;
}

function AqiLevel(pm25: number): { label: string; color: string; bg: string } {
  if (pm25 <= 12) return { label: "Good", color: "text-green-400", bg: "bg-green-500" };
  if (pm25 <= 35) return { label: "Fair", color: "text-yellow-400", bg: "bg-yellow-500" };
  if (pm25 <= 55) return { label: "Moderate", color: "text-orange-400", bg: "bg-orange-500" };
  if (pm25 <= 150) return { label: "Poor", color: "text-red-400", bg: "bg-red-500" };
  return { label: "Hazardous", color: "text-red-600", bg: "bg-red-600" };
}

function CircularGauge({
  value,
  max,
  unit,
  label,
  color,
}: {
  value: number;
  max: number;
  unit: string;
  label: string;
  color: string;
}) {
  const pct = Math.min(value / max, 1);
  const circumference = 2 * Math.PI * 28;
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <div className="relative h-16 w-16">
        <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
          <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="4" />
          <motion.circle
            cx="32" cy="32" r="28" fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-sm font-bold font-mono text-white">{value}</span>
          <span className="text-[8px] text-neutral-500">{unit}</span>
        </div>
      </div>
      <span className="mt-1 text-[10px] text-neutral-500">{label}</span>
    </div>
  );
}

export default function AirPurifierWidget({
  config,
  entities,
  onRefresh,
}: AirPurifierWidgetProps) {
  const find = (eid: string) => entities.find((e) => e.entity_id === eid);
  const num = (eid: string) => {
    const v = parseFloat(find(eid)?.state ?? "");
    return isNaN(v) ? 0 : v;
  };

  const fanEntity = find(config.fan_entity);
  const climateEntity = config.climate_entity ? find(config.climate_entity) : null;
  const isOn = fanEntity?.state === "on";
  const pm25 = num(config.pm25_entity);
  const temp = num(config.temperature_entity);
  const humidity = num(config.humidity_entity);
  const filterLife = num(config.filter_life_entity);
  const motorSpeed = num(config.motor_speed_entity);
  const aqi = AqiLevel(pm25);

  const presetModes = climateEntity?.preset_modes ?? [];
  const currentPreset = climateEntity?.preset_mode ?? null;
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const prevPresetRef = useRef(currentPreset);

  useEffect(() => {
    if (currentPreset !== prevPresetRef.current) {
      prevPresetRef.current = currentPreset;
      setActivePreset(currentPreset);
    }
  }, [currentPreset]);

  useEffect(() => {
    if (activePreset === null && currentPreset) setActivePreset(currentPreset);
  }, [activePreset, currentPreset]);

  const handleToggle = async () => {
    setBusy(true);
    try {
      await toggleEntity(config.fan_entity, isOn ? "turn_off" : "turn_on");
      setTimeout(() => onRefresh?.(), 1000);
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  const handlePreset = async (mode: string) => {
    if (!config.climate_entity) return;
    setActivePreset(mode);
    setBusy(true);
    try {
      if (!isOn) {
        await toggleEntity(config.fan_entity, "turn_on");
        await new Promise((r) => setTimeout(r, 500));
      }
      await setClimateState(config.climate_entity, { preset_mode: mode });
      setTimeout(() => onRefresh?.(), 1000);
    } catch { setActivePreset(currentPreset); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <motion.div
            className="h-2.5 w-2.5 rounded-full"
            animate={{
              backgroundColor: isOn ? "#4ade80" : "rgba(255,255,255,0.15)",
              boxShadow: isOn ? "0 0 8px rgba(74,222,128,0.5)" : "none",
            }}
          />
          <span className="text-sm text-neutral-200">
            {fanEntity?.friendly_name ?? "Air Purifier"}
          </span>
        </div>
        <button
          onClick={handleToggle}
          disabled={busy}
          className={cn(
            "relative h-5 w-9 shrink-0 rounded-full transition-colors",
            busy && "opacity-50",
            isOn ? "bg-green-500/30" : "bg-white/10",
          )}
        >
          <span className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full transition-all",
            isOn ? "left-[18px] bg-green-400" : "left-0.5 bg-neutral-500",
          )} />
        </button>
      </div>

      {/* Main readings */}
      <div className="flex items-center justify-around">
        <div className="text-center">
          <p className={cn("text-3xl font-bold font-mono", aqi.color)}>{pm25}</p>
          <p className="text-[10px] text-neutral-500">PM2.5 ug/m3</p>
          <p className={cn("text-[10px] font-medium mt-0.5", aqi.color)}>{aqi.label}</p>
        </div>
        <CircularGauge value={Math.round(temp)} max={50} unit="C" label="Temp" color="#f59e0b" />
        <CircularGauge value={Math.round(humidity)} max={100} unit="%" label="Humidity" color="#3b82f6" />
      </div>

      {/* Filter + Motor */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-white/[0.03] p-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-500">Filter Life</span>
            <span className={cn(
              "text-xs font-mono",
              filterLife > 20 ? "text-green-400" : "text-amber-400",
            )}>
              {filterLife}%
            </span>
          </div>
          <div className="mt-1 h-1 rounded-full bg-white/5 overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", filterLife > 20 ? "bg-green-500" : "bg-amber-500")}
              style={{ width: `${filterLife}%` }}
            />
          </div>
        </div>
        <div className="rounded-lg bg-white/[0.03] p-2">
          <span className="text-[10px] text-neutral-500">Motor</span>
          <p className="text-xs font-mono text-neutral-200 mt-0.5">{motorSpeed} rpm</p>
        </div>
      </div>

      {/* Preset modes */}
      {presetModes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {presetModes.map((mode) => (
            <button
              key={mode}
              onClick={() => handlePreset(mode)}
              disabled={busy}
              className={cn(
                "rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all",
                activePreset === mode
                  ? "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30"
                  : "bg-white/5 text-neutral-400 border border-transparent hover:bg-white/10",
                busy && "opacity-50",
              )}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
