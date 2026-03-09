"use client";

import type { EntityInfo } from "@/lib/types";

interface StatWidgetProps {
  config: { entity_id: string; unit?: string };
  entities: EntityInfo[];
}

export default function StatWidget({ config, entities }: StatWidgetProps) {
  const entity = entities.find((e) => e.entity_id === config.entity_id);
  const value = entity?.state ?? "--";
  const unit = config.unit ?? "";

  return (
    <div className="flex flex-col justify-between h-full">
      <div className="mt-1">
        <span className="text-3xl font-bold text-white font-mono">{value}</span>
        {unit && (
          <span className="ml-1 text-sm text-neutral-400">{unit}</span>
        )}
      </div>
    </div>
  );
}
