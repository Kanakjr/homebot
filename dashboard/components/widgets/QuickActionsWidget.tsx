"use client";

import { useState } from "react";
import { toggleEntity } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Action {
  label: string;
  entity_id: string;
  domain: string;
  service: string;
}

interface QuickActionsWidgetProps {
  config: { actions: Action[] };
  onRefresh?: () => void;
}

export default function QuickActionsWidget({ config, onRefresh }: QuickActionsWidgetProps) {
  const [busyIdx, setBusyIdx] = useState<number | null>(null);

  const handleAction = async (action: Action, idx: number) => {
    if (busyIdx !== null) return;
    setBusyIdx(idx);
    try {
      const svc = action.service as "toggle" | "turn_on" | "turn_off";
      await toggleEntity(action.entity_id, svc);
      setTimeout(() => onRefresh?.(), 1500);
    } catch {
      // ignore
    } finally {
      setBusyIdx(null);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {config.actions.map((action, i) => (
        <button
          key={`${action.entity_id}-${action.service}-${i}`}
          onClick={() => handleAction(action, i)}
          disabled={busyIdx !== null}
          className={cn(
            "rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-neutral-300 hover:bg-white/10 hover:text-white transition-colors",
            busyIdx === i && "opacity-50",
          )}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
