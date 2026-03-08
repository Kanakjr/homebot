"use client";

import { cn } from "@/lib/utils";
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
}

export default function EntityCard({
  entity,
  domain,
  className,
}: EntityCardProps) {
  const icon = DOMAIN_ICONS[domain] || "📦";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 transition-all hover:border-white/20",
        className
      )}
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
      <span className={cn("text-xs font-mono", stateColor(entity.state))}>
        {entity.state}
      </span>
    </div>
  );
}
