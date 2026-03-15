"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { setClimateState, toggleEntity } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface ClimateControlWidgetProps {
  config: { entity_id: string };
  entities: EntityInfo[];
  onRefresh?: () => void;
}

export default function ClimateControlWidget({
  config,
  entities,
  onRefresh,
}: ClimateControlWidgetProps) {
  const entity = entities.find((e) => e.entity_id === config.entity_id);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const prevPresetRef = useRef(entity?.preset_mode);

  const isOn = entity?.state !== "off" && entity?.state !== "unavailable";
  const presetModes = entity?.preset_modes ?? [];
  const currentPreset = entity?.preset_mode ?? null;

  useEffect(() => {
    if (entity?.preset_mode !== prevPresetRef.current) {
      prevPresetRef.current = entity?.preset_mode;
      setActivePreset(entity?.preset_mode ?? null);
    }
  }, [entity?.preset_mode]);

  useEffect(() => {
    if (activePreset === null && currentPreset) {
      setActivePreset(currentPreset);
    }
  }, [activePreset, currentPreset]);

  const handleToggle = async () => {
    setBusy(true);
    try {
      await toggleEntity(config.entity_id, isOn ? "turn_off" : "turn_on");
      setTimeout(() => onRefresh?.(), 1000);
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  const handlePresetChange = async (mode: string) => {
    setActivePreset(mode);
    setBusy(true);
    try {
      if (!isOn) {
        await toggleEntity(config.entity_id, "turn_on");
        await new Promise((r) => setTimeout(r, 500));
      }
      await setClimateState(config.entity_id, { preset_mode: mode });
      setTimeout(() => onRefresh?.(), 1000);
    } catch {
      setActivePreset(currentPreset);
    } finally {
      setBusy(false);
    }
  };

  if (!entity) {
    return <p className="text-xs text-neutral-500">Entity not found.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <motion.div
            className="h-2.5 w-2.5 rounded-full"
            animate={{
              backgroundColor: isOn ? "#4ade80" : "rgba(255,255,255,0.15)",
              boxShadow: isOn ? "0 0 8px rgba(74,222,128,0.5)" : "none",
            }}
          />
          <span className="text-sm text-neutral-200">{entity.friendly_name}</span>
        </div>
        <button
          onClick={handleToggle}
          disabled={busy}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            isOn
              ? "bg-green-500/20 text-green-400 hover:bg-green-500/30"
              : "bg-white/5 text-neutral-500 hover:bg-white/10 hover:text-white",
            busy && "opacity-50",
          )}
        >
          {isOn ? "ON" : "OFF"}
        </button>
      </div>

      {presetModes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {presetModes.map((mode) => (
            <button
              key={mode}
              onClick={() => handlePresetChange(mode)}
              disabled={busy}
              className={cn(
                "rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all",
                activePreset === mode
                  ? "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30"
                  : "bg-white/5 text-neutral-400 border border-transparent hover:bg-white/10 hover:text-white",
                busy && "opacity-50",
              )}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
      )}

      {entity.current_temperature != null && (
        <div className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-2">
          <span className="text-xs text-neutral-500">Current</span>
          <span className="text-sm font-mono text-white">
            {entity.current_temperature}&deg;C
          </span>
        </div>
      )}
    </div>
  );
}
