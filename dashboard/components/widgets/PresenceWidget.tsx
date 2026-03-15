"use client";

import { cn } from "@/lib/utils";
import type { EntityInfo } from "@/lib/types";

interface PresenceWidgetProps {
  config: { entities: string[] };
  entities: EntityInfo[];
}

function PresencePill({ entity }: { entity: EntityInfo }) {
  const isHome = entity.state === "home";
  const name = entity.friendly_name || entity.entity_id.split(".").pop() || "";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
        isHome
          ? "bg-green-500/15 text-green-400 border border-green-500/20"
          : "bg-white/5 text-neutral-500 border border-white/5",
      )}
    >
      <span
        className={cn(
          "h-2 w-2 shrink-0 rounded-full",
          isHome ? "bg-green-400 animate-pulse" : "bg-neutral-600",
        )}
      />
      <span className="truncate">{name}</span>
      <span className={cn("text-[10px]", isHome ? "text-green-500/70" : "text-neutral-600")}>
        {isHome ? "Home" : "Away"}
      </span>
    </div>
  );
}

export default function PresenceWidget({ config, entities }: PresenceWidgetProps) {
  const items = config.entities
    .map((eid) => entities.find((e) => e.entity_id === eid))
    .filter(Boolean) as EntityInfo[];

  if (items.length === 0) {
    return <p className="text-xs text-neutral-500">No presence entities found.</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((entity) => (
        <PresencePill key={entity.entity_id} entity={entity} />
      ))}
    </div>
  );
}
