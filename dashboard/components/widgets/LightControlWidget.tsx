"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { setLightState } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";

interface LightControlWidgetProps {
  config: { entities: string[] };
  entities: EntityInfo[];
  onRefresh?: () => void;
}

const PRESET_COLORS: [number, number, number][] = [
  [255, 180, 107],
  [255, 220, 160],
  [255, 255, 255],
  [200, 220, 255],
  [255, 100, 100],
  [100, 255, 100],
  [100, 150, 255],
  [200, 100, 255],
];

function rgbToHex(r: number, g: number, b: number) {
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function LightRow({
  entity,
  onRefresh,
}: {
  entity: EntityInfo;
  onRefresh?: () => void;
}) {
  const isOn = entity.state === "on";
  const currentBrightness = entity.brightness != null ? Math.round((entity.brightness / 255) * 100) : 0;
  const [brightness, setBrightness] = useState(isOn ? currentBrightness : 0);
  const [activeColor, setActiveColor] = useState<[number, number, number] | null>(
    entity.rgb_color ?? null,
  );
  const [showColors, setShowColors] = useState(false);
  const [busy, setBusy] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevStateRef = useRef(entity.state);
  const supportsColor = entity.supported_color_modes?.some((m) =>
    ["rgb", "rgbw", "rgbww", "hs", "xy"].includes(m),
  );

  useEffect(() => {
    if (entity.state !== prevStateRef.current) {
      prevStateRef.current = entity.state;
      const newBrt = entity.state === "on" && entity.brightness != null
        ? Math.round((entity.brightness / 255) * 100)
        : entity.state === "on" ? 100 : 0;
      setBrightness(newBrt);
      if (entity.rgb_color) setActiveColor(entity.rgb_color);
    }
  }, [entity.state, entity.brightness, entity.rgb_color]);

  const sendBrightness = useCallback(
    (pct: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        setBusy(true);
        try {
          await setLightState(entity.entity_id, {
            brightness: Math.round((pct / 100) * 255),
          });
          setTimeout(() => onRefresh?.(), 800);
        } catch { /* ignore */ }
        finally { setBusy(false); }
      }, 200);
    },
    [entity.entity_id, onRefresh],
  );

  const handleBrightnessChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value, 10);
    setBrightness(val);
    sendBrightness(val);
  };

  const handleColorSelect = async (color: [number, number, number]) => {
    setActiveColor(color);
    setBusy(true);
    try {
      await setLightState(entity.entity_id, { rgb_color: color, brightness: Math.round((brightness / 100) * 255) || 128 });
      setTimeout(() => onRefresh?.(), 800);
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  const glowColor = activeColor
    ? `rgba(${activeColor[0]}, ${activeColor[1]}, ${activeColor[2]}, ${brightness / 200})`
    : `rgba(255, 215, 0, ${brightness / 200})`;

  const handleToggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { toggleEntity } = await import("@/lib/api");
      await toggleEntity(entity.entity_id);
      setBrightness(isOn ? 0 : (currentBrightness || 100));
      setTimeout(() => onRefresh?.(), 800);
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <motion.div
            className="h-3 w-3 rounded-full"
            animate={{
              backgroundColor: isOn || brightness > 0 ? glowColor : "rgba(255,255,255,0.1)",
              boxShadow: isOn || brightness > 0 ? `0 0 12px ${glowColor}` : "none",
            }}
            transition={{ duration: 0.3 }}
          />
          <span className="text-sm text-neutral-200">{entity.friendly_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("text-xs font-mono", brightness > 0 ? "text-cyber-yellow" : "text-neutral-600")}>
            {brightness}%
          </span>
          <button
            onClick={handleToggle}
            disabled={busy}
            className={cn(
              "relative h-5 w-9 shrink-0 rounded-full transition-colors",
              busy && "opacity-50",
              isOn ? "bg-cyber-yellow/30" : "bg-white/10",
            )}
            aria-label={isOn ? "Turn off" : "Turn on"}
          >
            <span
              className={cn(
                "absolute top-0.5 h-4 w-4 rounded-full transition-all",
                isOn ? "left-[18px] bg-cyber-yellow" : "left-0.5 bg-neutral-500",
              )}
            />
          </button>
        </div>
      </div>

      <div className="relative">
        <input
          type="range"
          min={0}
          max={100}
          value={brightness}
          onChange={handleBrightnessChange}
          disabled={busy}
          className="light-slider w-full"
          style={{
            background: `linear-gradient(to right, rgba(255,255,255,0.1) 0%, ${glowColor} ${brightness}%, rgba(255,255,255,0.06) ${brightness}%)`,
          }}
        />
      </div>

      {supportsColor && (
        <div>
          <button
            onClick={() => setShowColors(!showColors)}
            className="text-[11px] text-neutral-500 hover:text-neutral-300 transition-colors"
          >
            {showColors ? "Hide colors" : "Color"}
          </button>
          {showColors && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="flex flex-wrap gap-2 mt-2"
            >
              {PRESET_COLORS.map((color) => (
                <button
                  key={color.join(",")}
                  onClick={() => handleColorSelect(color)}
                  disabled={busy}
                  className={cn(
                    "h-7 w-7 rounded-full border-2 transition-transform hover:scale-110",
                    activeColor && activeColor[0] === color[0] && activeColor[1] === color[1] && activeColor[2] === color[2]
                      ? "border-white scale-110"
                      : "border-transparent",
                  )}
                  style={{ backgroundColor: rgbToHex(color[0], color[1], color[2]) }}
                />
              ))}
            </motion.div>
          )}
        </div>
      )}
    </div>
  );
}

export default function LightControlWidget({
  config,
  entities,
  onRefresh,
}: LightControlWidgetProps) {
  const items = config.entities
    .map((eid) => entities.find((e) => e.entity_id === eid))
    .filter(Boolean) as EntityInfo[];

  if (items.length === 0) {
    return <p className="text-xs text-neutral-500">No light entities found.</p>;
  }

  return (
    <div className="space-y-4">
      {items.map((entity) => (
        <LightRow key={entity.entity_id} entity={entity} onRefresh={onRefresh} />
      ))}
    </div>
  );
}
