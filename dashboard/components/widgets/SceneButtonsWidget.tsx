"use client";

import { useState } from "react";
import { toggleEntity } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Scene {
  entity_id: string;
  label: string;
}

interface SceneButtonsWidgetProps {
  config: { scenes: Scene[] };
}

export default function SceneButtonsWidget({ config }: SceneButtonsWidgetProps) {
  const [busyIdx, setBusyIdx] = useState<number | null>(null);

  const handleActivate = async (scene: Scene, idx: number) => {
    if (busyIdx !== null) return;
    setBusyIdx(idx);
    try {
      await toggleEntity(scene.entity_id, "turn_on");
    } catch {
      // ignore
    } finally {
      setBusyIdx(null);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {config.scenes.map((scene, i) => (
        <button
          key={scene.entity_id}
          onClick={() => handleActivate(scene, i)}
          disabled={busyIdx !== null}
          className={cn(
            "rounded-lg border border-cyber-yellow/20 bg-cyber-yellow/5 px-3 py-2 text-xs text-cyber-yellow hover:bg-cyber-yellow/15 transition-colors",
            busyIdx === i && "opacity-50",
          )}
        >
          {scene.label}
        </button>
      ))}
    </div>
  );
}
