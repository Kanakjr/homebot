"use client";

import { motion } from "framer-motion";
import type { EntityInfo } from "@/lib/types";

interface RoomEnvironmentWidgetProps {
  config: {
    temperature_entity: string;
    humidity_entity: string;
    temp_thresholds?: { warn: number; critical: number };
    humidity_thresholds?: { warn: number; critical: number };
  };
  entities: EntityInfo[];
}

function MiniArc({
  value,
  min,
  max,
  color,
  size = 56,
}: {
  value: number;
  min: number;
  max: number;
  color: string;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const r = (size - 8) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = Math.PI * r;
  const offset = circumference * (1 - pct);

  return (
    <svg width={size} height={size / 2 + 4} viewBox={`0 0 ${size} ${size / 2 + 4}`}>
      <path
        d={`M 4 ${cy} A ${r} ${r} 0 0 1 ${size - 4} ${cy}`}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <motion.path
        d={`M 4 ${cy} A ${r} ${r} 0 0 1 ${size - 4} ${cy}`}
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1, ease: "easeOut" }}
      />
    </svg>
  );
}

function getColor(
  value: number,
  thresholds: { warn: number; critical: number },
): string {
  if (value >= thresholds.critical) return "#f87171";
  if (value >= thresholds.warn) return "#fbbf24";
  return "#4ade80";
}

export default function RoomEnvironmentWidget({
  config,
  entities,
}: RoomEnvironmentWidgetProps) {
  const tempEntity = entities.find((e) => e.entity_id === config.temperature_entity);
  const humEntity = entities.find((e) => e.entity_id === config.humidity_entity);

  const temp = parseFloat(tempEntity?.state ?? "0");
  const hum = parseFloat(humEntity?.state ?? "0");
  const tempThresh = config.temp_thresholds ?? { warn: 32, critical: 38 };
  const humThresh = config.humidity_thresholds ?? { warn: 60, critical: 80 };
  const tempColor = getColor(temp, tempThresh);
  const humColor = getColor(hum, humThresh);

  return (
    <div className="flex items-center justify-around py-2">
      <div className="flex flex-col items-center">
        <MiniArc value={temp} min={15} max={45} color={tempColor} />
        <span
          className="text-2xl font-bold font-mono -mt-1"
          style={{ color: tempColor }}
        >
          {isNaN(temp) ? "--" : temp.toFixed(1)}
        </span>
        <span className="text-[10px] text-neutral-500 mt-0.5">°C</span>
      </div>

      <div className="h-12 w-px bg-white/10" />

      <div className="flex flex-col items-center">
        <MiniArc value={hum} min={0} max={100} color={humColor} />
        <span
          className="text-2xl font-bold font-mono -mt-1"
          style={{ color: humColor }}
        >
          {isNaN(hum) ? "--" : Math.round(hum)}
        </span>
        <span className="text-[10px] text-neutral-500 mt-0.5">% RH</span>
      </div>
    </div>
  );
}
