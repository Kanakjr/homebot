"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { takeCameraSnapshot, getSnapshotUrl } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface PrinterWidgetProps {
  config: {
    camera_entity: string;
    status_entity: string;
    progress_entity: string;
    nozzle_temp_entity: string;
    nozzle_target_entity: string;
    bed_temp_entity: string;
    bed_target_entity: string;
    remaining_time_entity: string;
    current_layer_entity: string;
    total_layers_entity: string;
    weight_entity: string;
    filament_entity?: string;
    online_entity?: string;
  };
  entities: EntityInfo[];
}

function TempBar({
  label,
  current,
  target,
  maxTemp,
  color,
}: {
  label: string;
  current: number;
  target: number;
  maxTemp: number;
  color: string;
}) {
  const pct = Math.min((current / maxTemp) * 100, 100);
  const targetPct = target > 0 ? Math.min((target / maxTemp) * 100, 100) : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-neutral-400">{label}</span>
        <span className="font-mono text-neutral-200">
          {current}&deg;C
          {target > 0 && (
            <span className="text-neutral-500"> / {target}&deg;C</span>
          )}
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
        {targetPct > 0 && (
          <div
            className="absolute top-0 h-full w-0.5 bg-white/40"
            style={{ left: `${targetPct}%` }}
          />
        )}
      </div>
    </div>
  );
}

export default function PrinterWidget({ config, entities }: PrinterWidgetProps) {
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  const find = (eid: string) => entities.find((e) => e.entity_id === eid);
  const val = (eid: string) => find(eid)?.state ?? "unknown";
  const num = (eid: string) => {
    const v = parseFloat(val(eid));
    return isNaN(v) ? 0 : v;
  };

  const status = val(config.status_entity);
  const progress = num(config.progress_entity);
  const nozzleTemp = num(config.nozzle_temp_entity);
  const nozzleTarget = num(config.nozzle_target_entity);
  const bedTemp = num(config.bed_temp_entity);
  const bedTarget = num(config.bed_target_entity);
  const remaining = num(config.remaining_time_entity);
  const currentLayer = num(config.current_layer_entity);
  const totalLayers = num(config.total_layers_entity);
  const weight = num(config.weight_entity);
  const filament = config.filament_entity ? val(config.filament_entity) : "";
  const isOnline = config.online_entity ? val(config.online_entity) === "on" : true;
  const isPrinting = ["printing", "preparing", "running"].includes(status);

  const refreshSnapshot = useCallback(async () => {
    setSnapshotLoading(true);
    try {
      const result = await takeCameraSnapshot(config.camera_entity);
      setSnapshotUrl(getSnapshotUrl(result.filename) + `?t=${Date.now()}`);
    } catch { /* ignore */ }
    finally { setSnapshotLoading(false); }
  }, [config.camera_entity]);

  useEffect(() => {
    refreshSnapshot();
  }, [refreshSnapshot]);

  const remainingStr = remaining > 0
    ? remaining >= 60
      ? `${Math.floor(remaining / 60)}h ${Math.round(remaining % 60)}m`
      : `${Math.round(remaining)}m`
    : "--";

  return (
    <div className="space-y-3">
      {/* Status header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn(
            "h-2 w-2 rounded-full",
            !isOnline ? "bg-red-500" : isPrinting ? "bg-green-400 animate-pulse" : "bg-neutral-500",
          )} />
          <span className="text-xs font-mono uppercase tracking-wide text-neutral-400">
            {status}
          </span>
        </div>
        {filament && (
          <span className="text-[10px] text-neutral-500">{filament}</span>
        )}
      </div>

      {/* Camera snapshot */}
      <div
        className="relative aspect-video rounded-lg overflow-hidden bg-black/50 cursor-pointer group"
        onClick={refreshSnapshot}
      >
        {snapshotUrl ? (
          <img
            src={snapshotUrl}
            alt="Printer camera"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-neutral-600">
            {snapshotLoading ? "Loading..." : "No snapshot"}
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity">
          <svg viewBox="0 0 24 24" className="h-6 w-6 text-white/70" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            <path d="M16 12l-4-3v6l4-3z" fill="currentColor" />
          </svg>
        </div>
      </div>

      {/* Progress bar (only when printing) */}
      {isPrinting && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-neutral-400">Progress</span>
            <span className="font-mono text-cyber-yellow">{progress}%</span>
          </div>
          <div className="relative h-2 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              className="absolute inset-y-0 left-0 rounded-full bg-cyber-yellow"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.8 }}
            />
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-white/[0.03] p-2 text-center">
          <p className="text-[10px] text-neutral-500">Time Left</p>
          <p className="text-xs font-mono text-neutral-200">{remainingStr}</p>
        </div>
        <div className="rounded-lg bg-white/[0.03] p-2 text-center">
          <p className="text-[10px] text-neutral-500">Layer</p>
          <p className="text-xs font-mono text-neutral-200">
            {currentLayer}{totalLayers > 0 ? `/${totalLayers}` : ""}
          </p>
        </div>
        <div className="rounded-lg bg-white/[0.03] p-2 text-center">
          <p className="text-[10px] text-neutral-500">Weight</p>
          <p className="text-xs font-mono text-neutral-200">{weight}g</p>
        </div>
      </div>

      {/* Temperature bars */}
      <TempBar label="Nozzle" current={nozzleTemp} target={nozzleTarget} maxTemp={300} color="#f97316" />
      <TempBar label="Bed" current={bedTemp} target={bedTarget} maxTemp={120} color="#3b82f6" />
    </div>
  );
}
