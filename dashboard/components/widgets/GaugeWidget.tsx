"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { EntityInfo } from "@/lib/types";

interface GaugeWidgetProps {
  config: {
    entity_id: string;
    min: number;
    max: number;
    unit: string;
    thresholds: { warn: number; critical: number };
  };
  entities: EntityInfo[];
}

const GAUGE_RADIUS = 60;
const STROKE_WIDTH = 10;
const CENTER = 70;
const START_ANGLE = 135;
const END_ANGLE = 405;
const ARC_SPAN = END_ANGLE - START_ANGLE;

function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polarToXY(cx, cy, r, startDeg);
  const end = polarToXY(cx, cy, r, endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

function getColor(value: number, thresholds: { warn: number; critical: number }) {
  if (value >= thresholds.critical) return { stroke: "#f87171", text: "text-red-400" };
  if (value >= thresholds.warn) return { stroke: "#fbbf24", text: "text-amber-400" };
  return { stroke: "#4ade80", text: "text-green-400" };
}

export default function GaugeWidget({ config, entities }: GaugeWidgetProps) {
  const [animatedPct, setAnimatedPct] = useState(0);

  const entity = entities.find((e) => e.entity_id === config.entity_id);
  const rawValue = parseFloat(entity?.state ?? "0");
  const value = isNaN(rawValue) ? 0 : rawValue;
  const pct = Math.max(0, Math.min(1, (value - config.min) / (config.max - config.min)));
  const colors = getColor(value, config.thresholds);

  useEffect(() => {
    const timeout = setTimeout(() => setAnimatedPct(pct), 100);
    return () => clearTimeout(timeout);
  }, [pct]);

  const valueAngle = START_ANGLE + animatedPct * ARC_SPAN;
  const bgPath = describeArc(CENTER, CENTER, GAUGE_RADIUS, START_ANGLE, END_ANGLE);
  const fgPath =
    animatedPct > 0.01
      ? describeArc(CENTER, CENTER, GAUGE_RADIUS, START_ANGLE, Math.min(valueAngle, END_ANGLE - 0.1))
      : "";

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <svg viewBox="0 0 140 100" className="w-full max-w-[180px]">
        <defs>
          <linearGradient id={`gauge-grad-${config.entity_id}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={colors.stroke} stopOpacity={0.3} />
            <stop offset="100%" stopColor={colors.stroke} stopOpacity={1} />
          </linearGradient>
        </defs>
        <path
          d={bgPath}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={STROKE_WIDTH}
          strokeLinecap="round"
        />
        {fgPath && (
          <motion.path
            d={fgPath}
            fill="none"
            stroke={`url(#gauge-grad-${config.entity_id})`}
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          />
        )}
      </svg>
      <div className="flex flex-col items-center -mt-4">
        <span className={`text-2xl font-bold font-mono ${colors.text}`}>
          {entity ? (Number.isInteger(value) ? value : value.toFixed(1)) : "--"}
        </span>
        <span className="text-[11px] text-neutral-500">{config.unit}</span>
      </div>
    </div>
  );
}
