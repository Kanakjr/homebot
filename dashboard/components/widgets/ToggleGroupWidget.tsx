"use client";

import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { toggleEntity } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface ToggleGroupWidgetProps {
  config: { entities: string[] };
  entities: EntityInfo[];
  onRefresh?: () => void;
}

function ToggleRow({
  entity,
  onRefresh,
}: {
  entity: EntityInfo;
  onRefresh?: () => void;
}) {
  const [optimisticOn, setOptimisticOn] = useState<boolean | null>(null);
  const prevStateRef = useRef(entity.state);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (entity.state !== prevStateRef.current) {
      prevStateRef.current = entity.state;
      setOptimisticOn(null);
    }
  }, [entity.state]);

  const isOn = optimisticOn !== null ? optimisticOn : entity.state === "on";

  const handleToggle = async () => {
    if (busy) return;
    setBusy(true);
    setOptimisticOn(!isOn);
    try {
      await toggleEntity(entity.entity_id);
      setTimeout(() => onRefresh?.(), 1500);
    } catch {
      setOptimisticOn(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-center justify-between gap-2 rounded-md border border-white/5 bg-white/[0.02] px-2.5 py-2.5 sm:py-2 cursor-pointer hover:border-white/10 active:bg-white/5 transition-colors"
      onClick={handleToggle}
    >
      <span className="text-sm text-neutral-200 truncate">
        {entity.friendly_name}
      </span>
      <button
        disabled={busy}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          busy && "opacity-50",
          isOn ? "bg-green-500/30" : "bg-white/10",
        )}
        aria-label={isOn ? "Turn off" : "Turn on"}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full transition-all",
            isOn ? "left-[18px] bg-green-400" : "left-0.5 bg-neutral-500",
          )}
        />
      </button>
    </div>
  );
}

export default function ToggleGroupWidget({
  config,
  entities,
  onRefresh,
}: ToggleGroupWidgetProps) {
  const items = config.entities
    .map((eid) => entities.find((e) => e.entity_id === eid))
    .filter(Boolean) as EntityInfo[];

  if (items.length === 0) {
    return (
      <p className="text-xs text-neutral-500">No matching entities found.</p>
    );
  }

  return (
    <div className="space-y-1.5">
      {items.map((entity) => (
        <ToggleRow key={entity.entity_id} entity={entity} onRefresh={onRefresh} />
      ))}
    </div>
  );
}
