"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { EntityInfo } from "@/lib/types";

interface HealthWidgetProps {
  config: {
    heart_rate_entity: string;
    steps_entity: string;
    activity_entity: string;
    sleep_entity?: string;
    battery_entity?: string;
    daily_distance_entity?: string;
    daily_floors_entity?: string;
    daily_calories_entity?: string;
    pressure_entity?: string;
    on_body_entity?: string;
  };
  entities: EntityInfo[];
}

function HeartRateDisplay({ bpm }: { bpm: number }) {
  const intensity = Math.max(0, Math.min(1, (bpm - 50) / 100));
  const color = bpm > 120 ? "#f87171" : bpm > 90 ? "#fbbf24" : "#4ade80";

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        <motion.svg
          viewBox="0 0 24 24"
          className="h-8 w-8"
          animate={{ scale: [1, 1.12, 1] }}
          transition={{ duration: 60 / Math.max(bpm, 40), repeat: Infinity, ease: "easeInOut" }}
        >
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill={color}
            opacity={0.15 + intensity * 0.3}
          />
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill="none"
            stroke={color}
            strokeWidth="1.5"
          />
        </motion.svg>
      </div>
      <span className="text-2xl font-bold font-mono mt-1" style={{ color }}>{bpm || "--"}</span>
      <span className="text-[10px] text-neutral-500">bpm</span>
    </div>
  );
}

function StatBlock({
  icon,
  value,
  unit,
  label,
}: {
  icon: React.ReactNode;
  value: string;
  unit: string;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-2">
      <div className="text-neutral-500">{icon}</div>
      <div>
        <div className="flex items-baseline gap-1">
          <span className="text-sm font-bold font-mono text-neutral-200">{value}</span>
          <span className="text-[10px] text-neutral-500">{unit}</span>
        </div>
        <span className="text-[10px] text-neutral-500">{label}</span>
      </div>
    </div>
  );
}

export default function HealthWidget({ config, entities }: HealthWidgetProps) {
  const find = (eid: string | undefined) => eid ? entities.find((e) => e.entity_id === eid) : undefined;
  const num = (eid: string | undefined) => {
    const v = parseFloat(find(eid)?.state ?? "");
    return isNaN(v) ? 0 : v;
  };
  const str = (eid: string | undefined) => find(eid)?.state ?? "--";

  const heartRate = num(config.heart_rate_entity);
  const steps = num(config.steps_entity);
  const activity = str(config.activity_entity);
  const sleep = config.sleep_entity ? num(config.sleep_entity) : null;
  const distance = config.daily_distance_entity ? num(config.daily_distance_entity) : null;
  const battery = config.battery_entity ? num(config.battery_entity) : null;
  const calories = config.daily_calories_entity ? num(config.daily_calories_entity) : null;
  const pressure = config.pressure_entity ? num(config.pressure_entity) : null;
  const onBody = config.on_body_entity ? str(config.on_body_entity) === "on" : null;

  const sleepStr = sleep
    ? sleep >= 60
      ? `${Math.floor(sleep / 60)}h ${Math.round(sleep % 60)}m`
      : `${Math.round(sleep)}m`
    : null;

  return (
    <div className="space-y-3">
      {/* Heart rate + activity */}
      <div className="flex items-center justify-between">
        <HeartRateDisplay bpm={heartRate} />
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize",
              activity === "still" || activity === "passive" ? "bg-blue-500/10 text-blue-400" :
              activity === "walking" ? "bg-green-500/10 text-green-400" :
              activity === "running" ? "bg-amber-500/10 text-amber-400" :
              "bg-white/5 text-neutral-400",
            )}>
              {activity}
            </span>
            {onBody !== null && (
              <span className={cn(
                "h-1.5 w-1.5 rounded-full",
                onBody ? "bg-green-400" : "bg-neutral-600",
              )} title={onBody ? "On wrist" : "Off wrist"} />
            )}
          </div>
          {battery !== null && (
            <span className="text-[10px] text-neutral-500 font-mono">
              {battery}% watch
            </span>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2">
        <StatBlock
          icon={
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
              <path d="M10 18a1 1 0 01-.707-.293l-3-3a1 1 0 011.414-1.414L10 15.586l2.293-2.293a1 1 0 011.414 1.414l-3 3A1 1 0 0110 18zM10 2a1 1 0 01.707.293l3 3a1 1 0 01-1.414 1.414L10 4.414 7.707 6.707a1 1 0 01-1.414-1.414l3-3A1 1 0 0110 2z" />
            </svg>
          }
          value={steps.toLocaleString()}
          unit="steps"
          label="Today"
        />
        {calories !== null && (
          <StatBlock
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
              </svg>
            }
            value={Math.round(calories).toLocaleString()}
            unit="kcal"
            label="Burned"
          />
        )}
        {sleepStr && (
          <StatBlock
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            }
            value={sleepStr}
            unit=""
            label="Sleep"
          />
        )}
        {pressure !== null && (
          <StatBlock
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
              </svg>
            }
            value={pressure.toFixed(0)}
            unit="hPa"
            label="Pressure"
          />
        )}
        {distance !== null && distance > 0 && (
          <StatBlock
            icon={
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
              </svg>
            }
            value={(distance / 1000).toFixed(1)}
            unit="km"
            label="Distance"
          />
        )}
      </div>
    </div>
  );
}
