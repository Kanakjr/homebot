"use client";

import type { EntityInfo } from "@/lib/types";

interface WeatherWidgetProps {
  config: { entity_id: string };
  entities: EntityInfo[];
}

const WEATHER_ICONS: Record<string, string> = {
  sunny: "clear-day",
  "clear-night": "clear-night",
  partlycloudy: "partly-cloudy",
  cloudy: "cloudy",
  rainy: "rainy",
  snowy: "snowy",
  fog: "foggy",
  windy: "windy",
  lightning: "thunderstorm",
};

export default function WeatherWidget({ config, entities }: WeatherWidgetProps) {
  const entity = entities.find((e) => e.entity_id === config.entity_id);
  const state = entity?.state ?? "--";
  const name = entity?.friendly_name ?? "Weather";
  const label = WEATHER_ICONS[state] ?? state;

  return (
    <div className="flex flex-col justify-between h-full">
      <div className="mt-1">
        <p className="text-2xl font-bold text-white font-mono capitalize">
          {label.replace(/-/g, " ")}
        </p>
      </div>
    </div>
  );
}
