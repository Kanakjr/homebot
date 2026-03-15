"use client";

import { motion } from "framer-motion";
import type { EntityInfo } from "@/lib/types";

interface WeatherCardWidgetProps {
  config: { entity_id: string };
  entities: EntityInfo[];
}

function SunIcon() {
  return (
    <motion.svg
      viewBox="0 0 64 64"
      className="h-14 w-14"
      initial={{ rotate: 0 }}
      animate={{ rotate: 360 }}
      transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
    >
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <motion.line
          key={angle}
          x1="32" y1="6" x2="32" y2="12"
          stroke="#fbbf24"
          strokeWidth="2.5"
          strokeLinecap="round"
          transform={`rotate(${angle} 32 32)`}
          initial={{ opacity: 0.4 }}
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 2, repeat: Infinity, delay: angle / 360 }}
        />
      ))}
      <circle cx="32" cy="32" r="12" fill="#fbbf24" />
    </motion.svg>
  );
}

function CloudIcon() {
  return (
    <motion.svg viewBox="0 0 64 64" className="h-14 w-14">
      <motion.g
        animate={{ x: [-2, 2, -2] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      >
        <ellipse cx="30" cy="36" rx="18" ry="10" fill="#94a3b8" opacity={0.8} />
        <circle cx="22" cy="30" r="10" fill="#94a3b8" opacity={0.9} />
        <circle cx="34" cy="26" r="12" fill="#cbd5e1" />
      </motion.g>
    </motion.svg>
  );
}

function RainIcon() {
  return (
    <svg viewBox="0 0 64 64" className="h-14 w-14">
      <g>
        <ellipse cx="30" cy="28" rx="16" ry="9" fill="#94a3b8" opacity={0.7} />
        <circle cx="22" cy="22" r="9" fill="#94a3b8" opacity={0.8} />
        <circle cx="33" cy="19" r="10" fill="#cbd5e1" />
      </g>
      {[20, 30, 40].map((x, i) => (
        <motion.line
          key={x}
          x1={x} y1="40" x2={x - 2} y2="50"
          stroke="#60a5fa" strokeWidth="2" strokeLinecap="round"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: [0, 1, 0], y: [0, 6, 12] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.3 }}
        />
      ))}
    </svg>
  );
}

function PartlyCloudyIcon() {
  return (
    <svg viewBox="0 0 64 64" className="h-14 w-14">
      <circle cx="24" cy="24" r="10" fill="#fbbf24" />
      {[0, 60, 120, 180, 240, 300].map((angle) => (
        <line
          key={angle}
          x1="24" y1="10" x2="24" y2="14"
          stroke="#fbbf24" strokeWidth="2" strokeLinecap="round"
          transform={`rotate(${angle} 24 24)`}
        />
      ))}
      <motion.g
        animate={{ x: [-1, 1, -1] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
      >
        <ellipse cx="36" cy="40" rx="16" ry="8" fill="#94a3b8" opacity={0.8} />
        <circle cx="28" cy="34" r="8" fill="#94a3b8" opacity={0.9} />
        <circle cx="38" cy="31" r="10" fill="#cbd5e1" />
      </motion.g>
    </svg>
  );
}

const WEATHER_ICONS: Record<string, React.FC> = {
  sunny: SunIcon,
  "clear-night": SunIcon,
  partlycloudy: PartlyCloudyIcon,
  cloudy: CloudIcon,
  rainy: RainIcon,
  pouring: RainIcon,
  snowy: CloudIcon,
  fog: CloudIcon,
  windy: CloudIcon,
  lightning: RainIcon,
};

export default function WeatherCardWidget({ config, entities }: WeatherCardWidgetProps) {
  const entity = entities.find((e) => e.entity_id === config.entity_id);
  const raw = entity as Record<string, unknown> | undefined;
  const state = entity?.state ?? "unknown";
  const temp = raw?.temperature ?? raw?.current_temperature;
  const humidity = raw?.humidity;
  const windSpeed = raw?.wind_speed;

  const IconComp = WEATHER_ICONS[state] ?? WEATHER_ICONS["sunny"] ?? SunIcon;

  return (
    <div className="flex flex-col items-center justify-center h-full gap-1">
      <IconComp />
      <p className="text-xl font-bold font-mono text-white capitalize mt-1">
        {state.replace(/-/g, " ").replace("partlycloudy", "Partly Cloudy")}
      </p>
      {temp != null && (
        <p className="text-3xl font-bold font-mono text-cyber-yellow">
          {typeof temp === "number" ? temp.toFixed(1) : String(temp)}&deg;C
        </p>
      )}
      <div className="flex gap-3 mt-1 text-xs text-neutral-500">
        {humidity != null && <span>Humidity {String(humidity)}%</span>}
        {windSpeed != null && <span>Wind {String(windSpeed)} km/h</span>}
      </div>
    </div>
  );
}
