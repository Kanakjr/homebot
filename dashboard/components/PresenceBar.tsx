"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { EntityInfo, EntitiesResponse } from "@/lib/types";

interface PresencePillConfig {
  entity_id: string;
  label?: string;
  type?: "presence" | "battery" | "door" | "status";
  battery_entity?: string;
}

const DEFAULT_PILLS: PresencePillConfig[] = [
  { entity_id: "person.kanak", label: "Kanak", type: "presence" },
  { entity_id: "media_player.kanak_xbox", label: "Xbox", type: "status" },
  { entity_id: "device_tracker.pixel_9_pro", label: "Pixel Pro", type: "battery", battery_entity: "sensor.pixel_9_pro_battery_level" },
  { entity_id: "sensor.ipad_battery_level", label: "iPad", type: "battery" },
  { entity_id: "sensor.galaxy_watch8_classic_krbx_battery_level", label: "Watch 8", type: "battery" },
  { entity_id: "binary_sensor.room_door_door", label: "Room Door", type: "door" },
  { entity_id: "sensor.a1_03919d550407275_print_status", label: "Printo", type: "status" },
];

function flattenEntities(data: EntitiesResponse | null): EntityInfo[] {
  if (!data) return [];
  return Object.values(data.domains).flatMap((d) => d.entities);
}

function BatteryIcon({ level }: { level: number }) {
  const fill = level > 75 ? "text-green-400" : level > 30 ? "text-yellow-400" : "text-red-400";
  return (
    <svg viewBox="0 0 16 16" className={cn("h-3 w-3", fill)} fill="currentColor">
      <rect x="1" y="4" width="12" height="8" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="13" y="6" width="2" height="4" rx="0.5" fill="currentColor" />
      <rect x="2.5" y="5.5" width={Math.max(0.5, (level / 100) * 9)} height="5" rx="0.5" />
    </svg>
  );
}

function Pill({ config, entities }: { config: PresencePillConfig; entities: EntityInfo[] }) {
  const entity = entities.find((e) => e.entity_id === config.entity_id);
  if (!entity) return null;

  const state = entity.state;
  const label = config.label || entity.friendly_name;

  if (config.type === "presence") {
    const isHome = state === "home";
    return (
      <div className={cn(
        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium shrink-0",
        isHome ? "bg-green-500/15 text-green-400" : "bg-white/5 text-neutral-500",
      )}>
        <span className={cn("h-1.5 w-1.5 rounded-full", isHome ? "bg-green-400" : "bg-neutral-600")} />
        {label}
        <span className="text-[10px] opacity-70">{isHome ? "Home" : "Away"}</span>
      </div>
    );
  }

  if (config.type === "battery") {
    const batteryEntity = config.battery_entity
      ? entities.find((e) => e.entity_id === config.battery_entity)
      : entity;
    const level = batteryEntity ? parseInt(batteryEntity.state, 10) : NaN;
    if (isNaN(level)) return null;
    return (
      <div className="flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-1 text-[11px] font-medium text-neutral-300 shrink-0">
        <BatteryIcon level={level} />
        {label}
        <span className="font-mono text-[10px] text-neutral-400">{level}%</span>
      </div>
    );
  }

  if (config.type === "door") {
    const isOpen = state === "on";
    return (
      <div className={cn(
        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium shrink-0",
        isOpen ? "bg-amber-500/15 text-amber-400" : "bg-white/5 text-neutral-400",
      )}>
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.3">
          <rect x="3" y="2" width="10" height="12" rx="1" />
          <circle cx="10.5" cy="8" r="0.8" fill="currentColor" />
        </svg>
        {label}
        <span className="text-[10px] opacity-70">{isOpen ? "Open" : "Closed"}</span>
      </div>
    );
  }

  // status type (generic)
  const isActive = !["off", "unavailable", "unknown", "idle", "standby"].includes(state);
  return (
    <div className={cn(
      "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium shrink-0",
      isActive ? "bg-cyber-yellow/10 text-cyber-yellow" : "bg-white/5 text-neutral-500",
    )}>
      <span className={cn("h-1.5 w-1.5 rounded-full", isActive ? "bg-cyber-yellow" : "bg-neutral-600")} />
      {label}
      <span className="text-[10px] opacity-70 capitalize">{state}</span>
    </div>
  );
}

export default function PresenceBar({ entitiesData }: { entitiesData: EntitiesResponse | null }) {
  const entities = useMemo(() => flattenEntities(entitiesData), [entitiesData]);

  if (!entities.length) return null;

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
      {DEFAULT_PILLS.map((pill) => (
        <Pill key={pill.entity_id} config={pill} entities={entities} />
      ))}
    </div>
  );
}
