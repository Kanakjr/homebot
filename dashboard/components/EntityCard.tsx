"use client";

import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { toggleEntity } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

const DOMAIN_ICONS: Record<string, string> = {
  light: "💡",
  switch: "🔌",
  fan: "🌀",
  climate: "🌡",
  sensor: "📊",
  binary_sensor: "🔘",
  media_player: "🎵",
  camera: "📷",
  automation: "⚙",
  person: "👤",
  weather: "🌤",
};

const TOGGLEABLE_DOMAINS = new Set(["light", "switch", "fan", "automation"]);

function stateColor(state: string): string {
  switch (state) {
    case "on":
    case "playing":
    case "home":
      return "text-green-400";
    case "off":
    case "not_home":
      return "text-neutral-500";
    case "unavailable":
    case "unknown":
      return "text-red-400/50";
    default:
      return "text-cyan-400";
  }
}

interface EntityCardProps {
  entity: EntityInfo;
  domain: string;
  className?: string;
  onToggled?: () => void;
}

export default function EntityCard({
  entity,
  domain,
  className,
  onToggled,
}: EntityCardProps) {
  const icon = DOMAIN_ICONS[domain] || "📦";
  const canToggle = TOGGLEABLE_DOMAINS.has(domain) && entity.state !== "unavailable";
  const [optimisticOn, setOptimisticOn] = useState<boolean | null>(null);
  const prevStateRef = useRef(entity.state);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (entity.state !== prevStateRef.current) {
      prevStateRef.current = entity.state;
      setOptimisticOn(null);
    }
  }, [entity.state]);

  const isOn =
    optimisticOn !== null
      ? optimisticOn
      : entity.state === "on" || entity.state === "playing";

  const handleToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    setOptimisticOn(!isOn);
    try {
      await toggleEntity(entity.entity_id);
      setTimeout(() => onToggled?.(), 1500);
    } catch {
      setOptimisticOn(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-3 sm:py-2.5 transition-all hover:border-white/20 active:bg-white/10",
        canToggle && "cursor-pointer",
        className,
      )}
      onClick={canToggle ? handleToggle : undefined}
    >
      <span className="text-lg">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-neutral-200 truncate">
          {entity.friendly_name}
        </p>
        <p className="text-xs text-neutral-500 font-mono truncate">
          {entity.entity_id}
        </p>
      </div>

      {canToggle ? (
        <button
          onClick={handleToggle}
          disabled={busy}
          className={cn(
            "relative h-6 w-11 shrink-0 rounded-full transition-colors",
            busy && "opacity-50",
            isOn ? "bg-green-500/30" : "bg-white/10",
          )}
          aria-label={isOn ? "Turn off" : "Turn on"}
        >
          <span
            className={cn(
              "absolute top-0.5 h-5 w-5 rounded-full transition-all",
              isOn
                ? "left-[22px] bg-green-400"
                : "left-0.5 bg-neutral-500",
            )}
          />
        </button>
      ) : (
        <span className={cn("text-xs font-mono", stateColor(entity.state))}>
          {entity.state}
        </span>
      )}
    </div>
  );
}
