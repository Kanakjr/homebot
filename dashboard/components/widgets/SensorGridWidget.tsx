"use client";

import type { EntityInfo } from "@/lib/types";

interface SensorGridWidgetProps {
  config: { entities: string[] };
  entities: EntityInfo[];
}

export default function SensorGridWidget({ config, entities }: SensorGridWidgetProps) {
  const items = config.entities
    .map((eid) => entities.find((e) => e.entity_id === eid))
    .filter(Boolean) as EntityInfo[];

  if (items.length === 0) {
    return <p className="text-xs text-neutral-500">No sensors found.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((s) => (
        <div
          key={s.entity_id}
          className="rounded-md border border-white/5 bg-white/[0.02] p-2.5"
        >
          <p className="text-[11px] text-neutral-500 truncate">
            {s.friendly_name}
          </p>
          <p className="mt-1 text-lg font-mono text-white">{s.state}</p>
        </div>
      ))}
    </div>
  );
}
