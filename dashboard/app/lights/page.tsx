"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BlurFade } from "@/components/magicui/blur-fade";
import { useEntities } from "@/lib/hooks/useEntities";
import { setLightState, toggleEntity, callScript } from "@/lib/api";
import type { EntityInfo } from "@/lib/types";
import {
  MOODS,
  STRIP_COLORS,
  STRIP_COLOR_HEX,
  type Mood,
  type StripColor,
} from "@/lib/moods";
import { cn } from "@/lib/utils";

const BEDSIDE_ID = "light.bedside";
const TABLE_LAMP_ID = "light.table_lamp";
const STRIP_ID = "rgb_strip";

const STRIP_STORAGE_KEY = "homebot-rgb-strip-state";

// Helper entities in HA that gate the silent Alexa-routine path. Keep these
// in sync with configuration.yaml on the HA side.
const SILENT_MODE_ENTITY_ID = "input_boolean.rgb_strip_silent_mode";
const ROUTINE_PREFIX_ENTITY_ID = "input_text.alexa_rgb_strip_routine_prefix";
const STRIP_BRIGHTNESS_BUCKETS = [20, 40, 60, 80, 100] as const;

interface StripState {
  on: boolean;
  color: StripColor;
  brightness_pct: number;
}

function loadStripState(): StripState {
  if (typeof window === "undefined") {
    return { on: false, color: "warm white", brightness_pct: 80 };
  }
  try {
    const raw = localStorage.getItem(STRIP_STORAGE_KEY);
    if (raw) return { ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { on: false, color: "warm white", brightness_pct: 80 };
}

function saveStripState(s: StripState) {
  try {
    localStorage.setItem(STRIP_STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

function rgbToCss(rgb: [number, number, number] | null | undefined, opacity = 1): string {
  if (!rgb) return `rgba(255,215,0,${opacity})`;
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${opacity})`;
}

function kelvinToRgb(k: number | null | undefined): [number, number, number] {
  if (!k) return [255, 210, 140];
  const t = Math.max(1000, Math.min(40000, k)) / 100;
  let r: number, g: number, b: number;
  if (t <= 66) {
    r = 255;
    g = 99.4708025861 * Math.log(t) - 161.1195681661;
    b = t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  } else {
    r = 329.698727446 * Math.pow(t - 60, -0.1332047592);
    g = 288.1221695283 * Math.pow(t - 60, -0.0755148492);
    b = 255;
  }
  const clamp = (v: number) => Math.round(Math.max(0, Math.min(255, v)));
  return [clamp(r), clamp(g), clamp(b)];
}

function lightTargetColor(entity: EntityInfo | undefined): [number, number, number] {
  if (!entity) return [180, 180, 180];
  if (entity.rgb_color) return entity.rgb_color;
  if (entity.color_temp_kelvin) return kelvinToRgb(entity.color_temp_kelvin);
  return [255, 210, 140];
}

function lightGradient(rgb: [number, number, number], brightness_pct: number): string {
  const a = Math.max(0.25, brightness_pct / 100);
  return `linear-gradient(135deg, rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a}) 0%, rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a * 0.45}) 60%, rgba(0,0,0,0.35) 100%)`;
}

function brightnessPct(entity: EntityInfo | undefined): number {
  if (!entity || entity.state !== "on") return 0;
  if (entity.brightness == null) return 100;
  return Math.round((entity.brightness / 255) * 100);
}

// ---------- Icons ----------

function LampIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 3h8l2 7H6L8 3Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v7" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 17h8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 17v4h4v-4" />
    </svg>
  );
}

function BedIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 18V7" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 18v-5a3 3 0 0 0-3-3H3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 18h18" />
      <circle cx="7.5" cy="12" r="1.5" />
    </svg>
  );
}

function StripIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 8c3 3 3 5 0 8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 8c3 3 3 5 0 8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 8c3 3 3 5 0 8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 8c3 3 3 5 0 8" />
    </svg>
  );
}

function PowerIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v9" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 6.5A7 7 0 1 0 16.5 6.5" />
    </svg>
  );
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 1 1-3.3-6.9" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 4v5h-5" />
    </svg>
  );
}

// ---------- Sub-components ----------

interface MoodCardProps {
  mood: Mood;
  active: boolean;
  onClick: () => void;
  delay?: number;
}

function MoodCard({ mood, active, onClick, delay = 0 }: MoodCardProps) {
  // Tint the card with the scene's gradient veiled behind a dark overlay.
  // Inactive cards get a heavier veil (just a hint of colour); active cards
  // lift the veil so the scene tint pops.
  const veil = active ? "rgba(8,8,12,0.55)" : "rgba(10,10,14,0.82)";
  const cardBackground = `linear-gradient(${veil}, ${veil}), ${mood.gradient}`;

  return (
    <BlurFade delay={delay}>
      <motion.button
        whileTap={{ scale: 0.96 }}
        onClick={onClick}
        title={mood.description}
        className={cn(
          "group relative aspect-square w-full rounded-2xl border text-left transition-all overflow-hidden backdrop-blur-sm",
          active
            ? "border-white/60 ring-2 ring-white/40 shadow-lg shadow-black/50"
            : "border-white/10 hover:border-white/25",
        )}
        style={{ background: cardBackground }}
      >
        <div className="relative flex h-full w-full flex-col items-center justify-between p-3">
          <div className="flex-1 flex items-center justify-center w-full">
            <div
              className={cn(
                "relative aspect-square overflow-hidden rounded-full transition-transform",
                active ? "w-[68%] ring-2 ring-white/70" : "w-[62%] ring-1 ring-white/10",
                "group-hover:scale-105",
              )}
              style={{
                // Gradient lives on the wrapper so it acts as a fallback
                // while the photo loads (or if it fails to load entirely).
                background: mood.gradient,
                boxShadow: active
                  ? "0 0 24px rgba(255,255,255,0.15), inset 0 0 20px rgba(0,0,0,0.25)"
                  : "inset 0 0 20px rgba(0,0,0,0.35)",
              }}
            >
              {mood.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={mood.image}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="absolute inset-0 h-full w-full object-cover"
                  onError={(e) => {
                    // Hide broken images so the gradient fallback shows.
                    (e.currentTarget as HTMLImageElement).style.display = "none";
                  }}
                />
              )}
              {/* Subtle inner shadow to anchor the circle onto the card */}
              <div
                className="pointer-events-none absolute inset-0 rounded-full"
                style={{ boxShadow: "inset 0 0 18px rgba(0,0,0,0.35)" }}
              />
            </div>
          </div>
          <div className="pt-1 text-center text-[11px] sm:text-xs font-medium text-white/95 leading-tight line-clamp-2 w-full">
            {mood.name}
          </div>
        </div>
      </motion.button>
    </BlurFade>
  );
}

interface LightCardProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  isOn: boolean;
  brightnessPct: number;
  brightnessStep?: number;
  color: [number, number, number];
  unavailable?: boolean;
  badge?: string;
  onToggle: () => void;
  onBrightnessChange: (pct: number) => void;
  children?: React.ReactNode;
  expanded: boolean;
  onExpand: () => void;
}

function LightCard({
  title,
  subtitle,
  icon,
  isOn,
  brightnessPct,
  brightnessStep = 1,
  color,
  unavailable,
  badge,
  onToggle,
  onBrightnessChange,
  children,
  expanded,
  onExpand,
}: LightCardProps) {
  // Local slider state so the user's drag position isn't overwritten by
  // late-arriving server updates. Resync from the prop after the user has
  // stopped interacting for a beat.
  const [localPct, setLocalPct] = useState(brightnessPct);
  const lastTouchRef = useRef(0);

  useEffect(() => {
    if (Date.now() - lastTouchRef.current > 1500) {
      setLocalPct(brightnessPct);
    }
  }, [brightnessPct]);

  const handleSlider = (v: number) => {
    lastTouchRef.current = Date.now();
    setLocalPct(v);
    onBrightnessChange(v);
  };

  const displayPct = localPct;
  const bg = isOn ? lightGradient(color, displayPct) : "rgba(255,255,255,0.03)";
  const accent = rgbToCss(color, isOn ? 1 : 0.4);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border border-white/10 transition-all",
        unavailable && "opacity-50",
      )}
      style={{ background: bg }}
    >
      {isOn && (
        <div
          className="absolute -top-20 -right-10 h-56 w-56 rounded-full blur-3xl pointer-events-none"
          style={{ background: rgbToCss(color, 0.35) }}
        />
      )}
      <div className="relative flex items-center gap-3 p-4">
        <button
          type="button"
          onClick={onExpand}
          disabled={unavailable}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-expanded={expanded}
        >
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-colors"
            style={{
              borderColor: accent,
              color: isOn ? "#fff" : "rgba(255,255,255,0.55)",
              background: isOn ? rgbToCss(color, 0.35) : "rgba(255,255,255,0.04)",
            }}
          >
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="truncate text-sm font-semibold text-white">{title}</div>
              {badge && (
                <span className="shrink-0 rounded-full border border-white/20 bg-black/40 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider text-white/70">
                  {badge}
                </span>
              )}
            </div>
            <div className="truncate text-[11px] text-white/70">
              {unavailable ? "Unavailable" : subtitle}
            </div>
          </div>
        </button>
        <button
          type="button"
          onClick={() => {
            if (!unavailable) onToggle();
          }}
          disabled={unavailable}
          aria-label={isOn ? "Turn off" : "Turn on"}
          className={cn(
            "relative h-7 w-12 shrink-0 rounded-full transition-colors border border-white/15",
            isOn ? "" : "bg-white/10",
          )}
          style={isOn ? { background: accent } : undefined}
        >
          <span
            className={cn(
              "absolute top-0.5 h-6 w-6 rounded-full bg-white transition-all shadow",
              isOn ? "left-[22px]" : "left-0.5",
            )}
          />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {expanded && !unavailable && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="relative overflow-hidden"
          >
            <div className="px-4 pb-4 pt-0 space-y-3">
              <div>
                <div className="flex items-center justify-between text-[11px] text-white/70 mb-1">
                  <span>Brightness</span>
                  <span className="font-mono">{displayPct}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={brightnessStep}
                  value={displayPct}
                  onChange={(e) => handleSlider(parseInt(e.target.value, 10))}
                  className="light-slider w-full"
                  style={{
                    background: `linear-gradient(to right, ${accent} 0%, ${accent} ${displayPct}%, rgba(255,255,255,0.12) ${displayPct}%)`,
                  }}
                />
              </div>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const BULB_PRESETS: { label: string; rgb?: [number, number, number]; kelvin?: number }[] = [
  { label: "Warm", kelvin: 2700 },
  { label: "Reading", kelvin: 3200 },
  { label: "Neutral", kelvin: 4000 },
  { label: "Cool", kelvin: 5500 },
  { label: "Daylight", kelvin: 6500 },
  { label: "Red", rgb: [230, 40, 40] },
  { label: "Amber", rgb: [255, 140, 40] },
  { label: "Pink", rgb: [255, 105, 180] },
  { label: "Green", rgb: [70, 220, 110] },
  { label: "Blue", rgb: [60, 140, 255] },
  { label: "Purple", rgb: [160, 80, 255] },
  { label: "Teal", rgb: [40, 220, 210] },
];

// ---------- Silent-mode helpers ----------

/**
 * Full list of Alexa routine names the user must create (one-time, in the
 * Alexa app) so that silent mode can drive the strip without Alexa saying
 * "Okay".
 *
 * Each routine's only action is: smart home > "smart rgb led strip" > <action>.
 * The routine name in the Alexa app must match `<prefix> <suffix>` exactly;
 * the prefix is stored in HA as input_text.alexa_rgb_strip_routine_prefix
 * (default "Strip"), so the defaults below are e.g. "Strip On", "Strip Red".
 */
function routineChecklist(prefix: string): {
  group: string;
  items: { name: string; action: string }[];
}[] {
  const mk = (suffix: string, action: string) => ({
    name: `${prefix} ${suffix}`,
    action,
  });
  return [
    {
      group: "Power",
      items: [mk("On", "Turn on"), mk("Off", "Turn off")],
    },
    {
      group: "Colors",
      items: STRIP_COLORS.map((c) =>
        mk(
          c
            .split(" ")
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(" "),
          `Set color to ${c}`,
        ),
      ),
    },
    {
      group: "Brightness (snapped to 20% buckets)",
      items: STRIP_BRIGHTNESS_BUCKETS.map((b) =>
        mk(String(b), `Set brightness to ${b}%`),
      ),
    },
  ];
}

interface SilentSetupPanelProps {
  prefix: string;
  open: boolean;
  onToggle: () => void;
}

function SilentSetupPanel({ prefix, open, onToggle }: SilentSetupPanelProps) {
  const groups = routineChecklist(prefix);
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-black/30 overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-[11px] text-white/80">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-4 w-4 text-emerald-300">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" />
            <circle cx="12" cy="12" r="9" />
          </svg>
          Required Alexa routines
          <span className="ml-1 rounded-full bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-white/70">
            {total}
          </span>
        </span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.6}
          className={cn("h-4 w-4 text-white/60 transition-transform", open && "rotate-180")}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="space-y-3 border-t border-white/5 px-3 pt-3 pb-3 text-[11px] text-white/80">
          <p className="text-white/60">
            Create these in the Alexa app: <strong>Routines &rarr; +</strong>{" "}
            &rarr; name it exactly as shown &rarr; add action{" "}
            <em>&ldquo;Smart Home&rdquo;</em> &rarr; pick your RGB strip &rarr;
            set the action listed. No voice trigger is needed (HA triggers them
            via API).
          </p>
          {groups.map((g) => (
            <div key={g.group} className="space-y-1">
              <div className="text-[10px] uppercase tracking-widest text-white/40 font-mono">
                {g.group}
              </div>
              <ul className="space-y-1">
                {g.items.map((it) => (
                  <li
                    key={it.name}
                    className="flex items-start gap-2 rounded-md border border-white/5 bg-white/[0.03] px-2 py-1.5"
                  >
                    <code className="shrink-0 rounded bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-emerald-200/90">
                      {it.name}
                    </code>
                    <span className="text-white/60 leading-tight">{it.action}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <p className="text-[10px] text-white/40 leading-snug">
            Tip: change the prefix from &ldquo;Strip&rdquo; by editing{" "}
            <code className="bg-black/40 px-1 rounded">
              input_text.alexa_rgb_strip_routine_prefix
            </code>{" "}
            in HA if any of these names collide with existing routines.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------- Page ----------

export default function LightsPage() {
  const { data, refresh } = useEntities(10_000);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [activeMood, setActiveMood] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [strip, setStrip] = useState<StripState>({
    on: false,
    color: "warm white",
    brightness_pct: 80,
  });

  const stripBrightnessTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bedsideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Whether to show the Alexa routine setup checklist beneath the strip card.
  const [showSilentSetup, setShowSilentSetup] = useState(false);
  // Optimistic silent-mode state so the UI toggles instantly even before the
  // next entities poll lands.
  const [silentOptimistic, setSilentOptimistic] = useState<boolean | null>(null);

  useEffect(() => {
    setStrip(loadStripState());
  }, []);

  useEffect(() => {
    return () => {
      if (stripBrightnessTimer.current) clearTimeout(stripBrightnessTimer.current);
      if (bedsideTimer.current) clearTimeout(bedsideTimer.current);
      if (tableTimer.current) clearTimeout(tableTimer.current);
    };
  }, []);

  const bedside = data?.domains.light?.entities.find((e) => e.entity_id === BEDSIDE_ID);
  const tableLamp = data?.domains.light?.entities.find((e) => e.entity_id === TABLE_LAMP_ID);

  // Silent-mode state + routine prefix live in HA as helper entities, exposed
  // through the generic /api/entities endpoint.
  const silentEntity = data?.domains.input_boolean?.entities.find(
    (e) => e.entity_id === SILENT_MODE_ENTITY_ID,
  );
  const prefixEntity = data?.domains.input_text?.entities.find(
    (e) => e.entity_id === ROUTINE_PREFIX_ENTITY_ID,
  );
  const silentServer = silentEntity?.state === "on";
  const silentOn = silentOptimistic ?? silentServer;
  const routinePrefix = prefixEntity?.state?.trim() || "Strip";

  // Clear optimistic state once the server agrees.
  useEffect(() => {
    if (silentOptimistic !== null && silentOptimistic === silentServer) {
      setSilentOptimistic(null);
    }
  }, [silentOptimistic, silentServer]);

  const lightsOnCount =
    (bedside?.state === "on" ? 1 : 0) +
    (tableLamp?.state === "on" ? 1 : 0) +
    (strip.on ? 1 : 0);

  const masterOn = lightsOnCount > 0;

  const avgBrightness = useMemo(() => {
    const values: number[] = [];
    if (bedside?.state === "on") values.push(brightnessPct(bedside));
    if (tableLamp?.state === "on") values.push(brightnessPct(tableLamp));
    if (strip.on) values.push(strip.brightness_pct);
    if (values.length === 0) return 0;
    return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  }, [bedside, tableLamp, strip]);

  const updateStrip = useCallback((next: StripState) => {
    setStrip(next);
    saveStripState(next);
  }, []);

  // ------ silent mode toggle ------
  const toggleSilentMode = useCallback(async () => {
    const next = !silentOn;
    setSilentOptimistic(next);
    // If the user is turning silent mode ON for the first time, auto-expand
    // the setup checklist so they immediately see the routines they need to
    // create in the Alexa app.
    if (next && !silentServer) setShowSilentSetup(true);
    try {
      await toggleEntity(SILENT_MODE_ENTITY_ID, next ? "turn_on" : "turn_off");
      setTimeout(refresh, 400);
    } catch {
      // Roll back optimistic state on failure.
      setSilentOptimistic(!next);
    }
  }, [silentOn, silentServer, refresh]);

  // ------ strip commands ------
  const stripTurnOn = useCallback(async () => {
    await callScript("rgb_strip_on");
  }, []);

  const stripTurnOff = useCallback(async () => {
    await callScript("rgb_strip_off");
  }, []);

  const stripSetColor = useCallback(async (color: StripColor) => {
    await callScript("rgb_strip_color", { color });
  }, []);

  const stripSetBrightness = useCallback(async (level: number) => {
    await callScript("rgb_strip_brightness", { level });
  }, []);

  const toggleStrip = useCallback(async () => {
    try {
      setBusy(true);
      const next = { ...strip, on: !strip.on };
      updateStrip(next);
      // Single utterance – the strip remembers its color across on/off via
      // the Alexa routine, so no need to re-assert color here.
      if (next.on) {
        await stripTurnOn();
      } else {
        await stripTurnOff();
      }
    } finally {
      setBusy(false);
    }
  }, [strip, updateStrip, stripTurnOn, stripTurnOff]);

  const changeStripColor = useCallback(
    async (color: StripColor) => {
      try {
        setBusy(true);
        const wasOn = strip.on;
        const sameColor = strip.color === color;
        // Already on and already this color → don't wake Alexa at all.
        if (wasOn && sameColor) return;
        updateStrip({ ...strip, on: true, color });
        if (!wasOn) await stripTurnOn();
        if (!sameColor) await stripSetColor(color);
      } finally {
        setBusy(false);
      }
    },
    [strip, updateStrip, stripTurnOn, stripSetColor],
  );

  // Snap to the 5% step the Alexa script expects and debounce so we don't
  // spam Alexa while the user is dragging.
  const changeStripBrightness = useCallback(
    (pct: number) => {
      const snapped = Math.round(pct / 5) * 5;
      const next: StripState = { ...strip, on: snapped > 0, brightness_pct: snapped };
      updateStrip(next);
      if (stripBrightnessTimer.current) clearTimeout(stripBrightnessTimer.current);
      stripBrightnessTimer.current = setTimeout(async () => {
        try {
          if (snapped === 0) {
            await stripTurnOff();
          } else {
            await stripSetBrightness(snapped);
          }
        } catch {
          /* ignore */
        }
      }, 450);
    },
    [strip, updateStrip, stripSetBrightness, stripTurnOff],
  );

  // ------ bulb commands ------
  const toggleBulb = useCallback(
    async (entityId: string) => {
      try {
        setBusy(true);
        await toggleEntity(entityId);
        setTimeout(refresh, 700);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const setBulbBrightness = useCallback(
    (entityId: string, pct: number) => {
      const ref = entityId === BEDSIDE_ID ? bedsideTimer : tableTimer;
      if (ref.current) clearTimeout(ref.current);
      ref.current = setTimeout(async () => {
        try {
          await setLightState(entityId, { brightness: Math.round((pct / 100) * 255) });
          setTimeout(refresh, 700);
        } catch {
          /* ignore */
        }
      }, 200);
    },
    [refresh],
  );

  const setBulbPreset = useCallback(
    async (entityId: string, preset: (typeof BULB_PRESETS)[number], pct: number) => {
      try {
        const brightness = Math.max(1, Math.round((pct / 100) * 255));
        if (preset.rgb) {
          await setLightState(entityId, { rgb_color: preset.rgb, brightness });
        } else if (preset.kelvin) {
          await setLightState(entityId, { color_temp_kelvin: preset.kelvin, brightness });
        }
        setTimeout(refresh, 700);
      } catch {
        /* ignore */
      }
    },
    [refresh],
  );

  // ------ mood application ------
  const applyMood = useCallback(
    async (mood: Mood) => {
      setActiveMood(mood.id);
      setBusy(true);
      const jobs: Promise<unknown>[] = [];

      for (const [id, target] of [
        [BEDSIDE_ID, mood.bedside],
        [TABLE_LAMP_ID, mood.table_lamp],
      ] as const) {
        if (target.on) {
          const params: {
            brightness: number;
            rgb_color?: [number, number, number];
            color_temp_kelvin?: number;
          } = {
            brightness: Math.max(1, Math.round((target.brightness_pct / 100) * 255)),
          };
          if (target.rgb_color) params.rgb_color = target.rgb_color;
          if (target.color_temp_kelvin) params.color_temp_kelvin = target.color_temp_kelvin;
          jobs.push(setLightState(id, params));
        } else {
          jobs.push(toggleEntity(id, "turn_off"));
        }
      }

      // RGB strip -- only send scripts that actually change state.
      // Alexa answers "Okay" for every utterance, so this is our single
      // biggest lever to reduce noise. Snapshot `strip` so the comparisons
      // use the value before we optimistically update.
      const stripBefore = strip;
      const stripTarget = mood.rgb_strip;
      const stripJobs: Array<() => Promise<unknown>> = [];
      if (stripTarget.on) {
        if (!stripBefore.on) {
          stripJobs.push(() => callScript("rgb_strip_on"));
        }
        if (stripBefore.color !== stripTarget.color) {
          stripJobs.push(() =>
            callScript("rgb_strip_color", { color: stripTarget.color }),
          );
        }
        if (stripBefore.brightness_pct !== stripTarget.brightness_pct) {
          stripJobs.push(() =>
            callScript("rgb_strip_brightness", {
              level: stripTarget.brightness_pct,
            }),
          );
        }
        updateStrip({
          on: true,
          color: stripTarget.color,
          brightness_pct: stripTarget.brightness_pct,
        });
      } else if (stripBefore.on) {
        stripJobs.push(() => callScript("rgb_strip_off"));
        updateStrip({ ...stripBefore, on: false });
      }
      if (stripJobs.length > 0) {
        // Run sequentially – parallel Alexa utterances collide.
        jobs.push(
          (async () => {
            for (const job of stripJobs) {
              await job();
            }
          })(),
        );
      }

      try {
        await Promise.allSettled(jobs);
      } finally {
        setBusy(false);
        setTimeout(refresh, 900);
      }
    },
    [refresh, strip, updateStrip],
  );

  // ------ master controls ------
  const masterToggle = useCallback(async () => {
    setBusy(true);
    try {
      const jobs: Promise<unknown>[] = [];
      if (masterOn) {
        if (bedside?.state === "on") jobs.push(toggleEntity(BEDSIDE_ID, "turn_off"));
        if (tableLamp?.state === "on") jobs.push(toggleEntity(TABLE_LAMP_ID, "turn_off"));
        if (strip.on) {
          updateStrip({ ...strip, on: false });
          jobs.push(callScript("rgb_strip_off"));
        }
      } else {
        if (bedside && bedside.state !== "on") jobs.push(toggleEntity(BEDSIDE_ID, "turn_on"));
        if (tableLamp && tableLamp.state !== "on") jobs.push(toggleEntity(TABLE_LAMP_ID, "turn_on"));
        updateStrip({ ...strip, on: true });
        jobs.push(callScript("rgb_strip_on"));
      }
      await Promise.allSettled(jobs);
    } finally {
      setBusy(false);
      setTimeout(refresh, 900);
    }
  }, [bedside, tableLamp, strip, masterOn, refresh, updateStrip]);

  const masterBrightness = useCallback(
    (pct: number) => {
      if (bedside?.state === "on") setBulbBrightness(BEDSIDE_ID, pct);
      if (tableLamp?.state === "on") setBulbBrightness(TABLE_LAMP_ID, pct);
      if (strip.on) changeStripBrightness(pct);
    },
    [bedside, tableLamp, strip.on, setBulbBrightness, changeStripBrightness],
  );

  // Clear active mood when lights change by user outside the mood picker
  useEffect(() => {
    if (activeMood) {
      const t = setTimeout(() => setActiveMood(null), 15_000);
      return () => clearTimeout(t);
    }
  }, [activeMood]);

  const bedsideColor = lightTargetColor(bedside);
  const tableColor = lightTargetColor(tableLamp);
  const stripHex = STRIP_COLOR_HEX[strip.color];

  const masterAccentColor: [number, number, number] = masterOn
    ? bedside?.state === "on"
      ? bedsideColor
      : tableLamp?.state === "on"
        ? tableColor
        : [255, 215, 0]
    : [160, 160, 160];
  const masterAccent = rgbToCss(masterAccentColor, 0.95);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl space-y-6">
      <BlurFade delay={0}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-mono">
              Bedroom
            </div>
            <h1 className="text-2xl font-bold text-white font-mono">Lights & Moods</h1>
            <p className="mt-1 text-sm text-neutral-400">
              {lightsOnCount > 0
                ? `${lightsOnCount} on · ${avgBrightness}% avg`
                : "All lights off"}
            </p>
          </div>
          <button
            onClick={() => refresh()}
            aria-label="Refresh"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-neutral-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            <RefreshIcon className="h-4 w-4" />
          </button>
        </div>
      </BlurFade>

      {/* Master dimmer pill */}
      <BlurFade delay={0.05}>
        <div
          className="relative overflow-hidden rounded-full border border-white/10 px-4 py-3 flex items-center gap-3"
          style={{
            background: masterOn
              ? `linear-gradient(90deg, ${rgbToCss(masterAccentColor, 0.45)} 0%, ${rgbToCss(masterAccentColor, 0.18)} 100%)`
              : "rgba(255,255,255,0.04)",
          }}
        >
          <button
            onClick={masterToggle}
            disabled={busy}
            aria-label="Master power"
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-full border text-white transition-colors",
              masterOn ? "border-white/30 bg-white/15" : "border-white/10 bg-white/5",
            )}
          >
            <PowerIcon className="h-5 w-5" />
          </button>
          <div className="flex-1">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-white/70">All lights</span>
              <span className="text-xs font-mono text-white/80">{avgBrightness}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={avgBrightness}
              onChange={(e) => masterBrightness(parseInt(e.target.value, 10))}
              disabled={!masterOn}
              className="light-slider w-full"
              style={{
                background: `linear-gradient(to right, ${masterAccent} 0%, ${masterAccent} ${avgBrightness}%, rgba(255,255,255,0.1) ${avgBrightness}%)`,
              }}
            />
          </div>
        </div>
      </BlurFade>

      {/* Moods */}
      <div>
        <BlurFade delay={0.1}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] uppercase tracking-widest text-neutral-500 font-mono">
              Moods
            </h2>
            <span className="text-[11px] text-neutral-600 font-mono">
              {MOODS.length} presets
            </span>
          </div>
        </BlurFade>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {MOODS.map((mood, i) => (
            <MoodCard
              key={mood.id}
              mood={mood}
              active={activeMood === mood.id}
              onClick={() => applyMood(mood)}
              delay={0.12 + i * 0.02}
            />
          ))}
        </div>
      </div>

      {/* Individual lights */}
      <div>
        <BlurFade delay={0.2}>
          <h2 className="mb-3 text-[11px] uppercase tracking-widest text-neutral-500 font-mono">
            Lights
          </h2>
        </BlurFade>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* Bedside */}
          <BlurFade delay={0.22}>
            <LightCard
              title="Bedside lamp"
              subtitle={
                bedside?.state === "on"
                  ? `On · ${brightnessPct(bedside)}%`
                  : bedside
                    ? "Off"
                    : "Not found"
              }
              icon={<BedIcon className="h-5 w-5" />}
              isOn={bedside?.state === "on"}
              brightnessPct={brightnessPct(bedside)}
              color={bedsideColor}
              unavailable={!bedside || bedside.state === "unavailable"}
              onToggle={() => toggleBulb(BEDSIDE_ID)}
              onBrightnessChange={(pct) => setBulbBrightness(BEDSIDE_ID, pct)}
              expanded={expanded === BEDSIDE_ID}
              onExpand={() => setExpanded(expanded === BEDSIDE_ID ? null : BEDSIDE_ID)}
            >
              <ColorRow
                onPick={(preset) =>
                  setBulbPreset(BEDSIDE_ID, preset, brightnessPct(bedside) || 80)
                }
                supportsRgb={
                  bedside?.supported_color_modes?.some((m) =>
                    ["rgb", "rgbw", "rgbww", "hs", "xy"].includes(m),
                  ) ?? false
                }
              />
            </LightCard>
          </BlurFade>

          {/* Table lamp */}
          <BlurFade delay={0.25}>
            <LightCard
              title="Table lamp"
              subtitle={
                tableLamp?.state === "on"
                  ? `On · ${brightnessPct(tableLamp)}%`
                  : tableLamp
                    ? "Off"
                    : "Not found"
              }
              icon={<LampIcon className="h-5 w-5" />}
              isOn={tableLamp?.state === "on"}
              brightnessPct={brightnessPct(tableLamp)}
              color={tableColor}
              unavailable={!tableLamp || tableLamp.state === "unavailable"}
              onToggle={() => toggleBulb(TABLE_LAMP_ID)}
              onBrightnessChange={(pct) => setBulbBrightness(TABLE_LAMP_ID, pct)}
              expanded={expanded === TABLE_LAMP_ID}
              onExpand={() => setExpanded(expanded === TABLE_LAMP_ID ? null : TABLE_LAMP_ID)}
            >
              <ColorRow
                onPick={(preset) =>
                  setBulbPreset(TABLE_LAMP_ID, preset, brightnessPct(tableLamp) || 80)
                }
                supportsRgb={
                  tableLamp?.supported_color_modes?.some((m) =>
                    ["rgb", "rgbw", "rgbww", "hs", "xy"].includes(m),
                  ) ?? false
                }
              />
            </LightCard>
          </BlurFade>

          {/* RGB strip */}
          <BlurFade delay={0.28}>
            <LightCard
              title="RGB strip"
              badge="Alexa"
              subtitle={
                strip.on
                  ? `On · ${strip.color} · ${strip.brightness_pct}%`
                  : "Off"
              }
              icon={<StripIcon className="h-5 w-5" />}
              isOn={strip.on}
              brightnessPct={strip.on ? strip.brightness_pct : 0}
              brightnessStep={5}
              color={hexToRgb(stripHex)}
              onToggle={toggleStrip}
              onBrightnessChange={changeStripBrightness}
              expanded={expanded === STRIP_ID}
              onExpand={() => setExpanded(expanded === STRIP_ID ? null : STRIP_ID)}
            >
              <div>
                <div className="mb-1 flex items-center justify-between text-[11px] text-white/70">
                  <span>Color</span>
                  <span className="font-mono text-[10px] text-white/50">
                    10 presets
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {STRIP_COLORS.map((c) => {
                    const active = strip.on && strip.color === c;
                    return (
                      <button
                        key={c}
                        onClick={() => changeStripColor(c)}
                        className={cn(
                          "flex items-center gap-2 rounded-full border px-2 py-1 text-[11px] transition-colors",
                          active
                            ? "border-white/60 bg-white/15 text-white"
                            : "border-white/15 bg-black/30 text-white/80 hover:bg-white/10",
                        )}
                      >
                        <span
                          className="h-4 w-4 shrink-0 rounded-full border border-black/40"
                          style={{ background: STRIP_COLOR_HEX[c] }}
                        />
                        <span className="truncate capitalize">{c}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="mt-2 space-y-1">
                  <p className="text-[10px] text-white/50">
                    Alexa-controlled — 10 named colors, 5% brightness steps. State
                    cached locally, so repeat clicks don&apos;t re-trigger Alexa.
                  </p>
                </div>

                {/* Silent-mode toggle + routine setup */}
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-2.5">
                  <div className="flex items-start gap-3">
                    <button
                      type="button"
                      onClick={toggleSilentMode}
                      aria-pressed={silentOn}
                      className={cn(
                        "relative h-5 w-9 shrink-0 rounded-full border transition-colors",
                        silentOn
                          ? "border-emerald-300/70 bg-emerald-400/60"
                          : "border-white/20 bg-white/5",
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
                          silentOn ? "left-4" : "left-0.5",
                        )}
                      />
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-medium text-white/90">
                          Silent mode
                        </span>
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-0.5 font-mono text-[9px]",
                            silentOn
                              ? "bg-emerald-400/20 text-emerald-200"
                              : "bg-white/10 text-white/60",
                          )}
                        >
                          {silentOn ? "routines" : "TTS (Alexa says OK)"}
                        </span>
                      </div>
                      <p className="mt-1 text-[10px] leading-snug text-white/55">
                        {silentOn ? (
                          <>
                            HA triggers Alexa routines directly — no voice
                            command, no &ldquo;Okay&rdquo; reply. Brightness
                            snaps to the nearest 20% bucket.
                          </>
                        ) : (
                          <>
                            Sends TTS commands through the Echo. Turn this on
                            once the routines below are created in the Alexa
                            app.
                          </>
                        )}
                      </p>
                    </div>
                  </div>
                  <SilentSetupPanel
                    prefix={routinePrefix}
                    open={showSilentSetup}
                    onToggle={() => setShowSilentSetup((v) => !v)}
                  />
                </div>
              </div>
            </LightCard>
          </BlurFade>
        </div>
      </div>
    </div>
  );
}

function ColorRow({
  onPick,
  supportsRgb,
}: {
  onPick: (preset: (typeof BULB_PRESETS)[number]) => void;
  supportsRgb: boolean;
}) {
  const visible = supportsRgb ? BULB_PRESETS : BULB_PRESETS.filter((p) => p.kelvin);
  return (
    <div>
      <div className="mb-1 text-[11px] text-white/70">Color</div>
      <div className="flex flex-wrap gap-2">
        {visible.map((p) => {
          const hex = p.rgb
            ? `rgb(${p.rgb.join(",")})`
            : kelvinHex(p.kelvin || 3000);
          return (
            <button
              key={p.label}
              onClick={() => onPick(p)}
              title={p.label}
              className="h-7 w-7 rounded-full border border-white/20 transition-transform hover:scale-110"
              style={{ background: hex }}
            />
          );
        })}
      </div>
    </div>
  );
}

function kelvinHex(k: number): string {
  const [r, g, b] = kelvinToRgb(k);
  return `rgb(${r}, ${g}, ${b})`;
}

function hexToRgb(hex: string): [number, number, number] {
  const m = hex.replace("#", "");
  if (m.length !== 6) return [255, 215, 0];
  return [
    parseInt(m.slice(0, 2), 16),
    parseInt(m.slice(2, 4), 16),
    parseInt(m.slice(4, 6), 16),
  ];
}
