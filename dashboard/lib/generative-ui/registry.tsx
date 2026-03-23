"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { defineRegistry } from "@json-render/react";
import { cn } from "@/lib/utils";
import { catalog } from "./catalog";
import { actionHandlers } from "./actions";

export type EntityLookup = (id: string) => {
  entity_id: string;
  state: string;
  friendly_name: string;
  brightness?: number | null;
  current_temperature?: number | null;
  preset_mode?: string | null;
  preset_modes?: string[];
} | undefined;

let _entityLookup: EntityLookup = () => undefined;

export function setEntityLookup(fn: EntityLookup) {
  _entityLookup = fn;
}

let _onRefresh: (() => void) | undefined;
export function setOnRefresh(fn: (() => void) | undefined) {
  _onRefresh = fn;
}

function DeviceToggleImpl({
  entity_id,
  label,
}: {
  entity_id: string;
  label: string | null;
}) {
  const entity = _entityLookup(entity_id);
  const [optimisticOn, setOptimisticOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const prevState = useRef(entity?.state);

  useEffect(() => {
    if (entity?.state !== prevState.current) {
      prevState.current = entity?.state;
      setOptimisticOn(null);
    }
  }, [entity?.state]);

  const isOn =
    optimisticOn !== null ? optimisticOn : entity?.state === "on";
  const name = label || entity?.friendly_name || entity_id;

  const handleToggle = async () => {
    if (busy) return;
    setBusy(true);
    setOptimisticOn(!isOn);
    try {
      await actionHandlers.toggle_entity({
        entity_id,
        action: "toggle",
      });
      setTimeout(() => _onRefresh?.(), 1500);
    } catch {
      setOptimisticOn(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-center justify-between gap-2 rounded-md border border-white/5 bg-white/[0.02] px-2.5 py-2.5 cursor-pointer hover:border-white/10 active:bg-white/5 transition-colors"
      onClick={handleToggle}
    >
      <span className="text-sm text-neutral-200 truncate">{name}</span>
      <button
        disabled={busy}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          busy && "opacity-50",
          isOn ? "bg-green-500/30" : "bg-white/10",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full transition-all",
            isOn ? "left-[18px] bg-green-400" : "left-0.5 bg-neutral-500",
          )}
        />
      </button>
    </div>
  );
}

function LightControlImpl({
  entity_id,
  label,
}: {
  entity_id: string;
  label: string | null;
}) {
  const entity = _entityLookup(entity_id);
  const isOn = entity?.state === "on";
  const currentBrt =
    entity?.brightness != null
      ? Math.round((entity.brightness / 255) * 100)
      : 0;
  const [brightness, setBrightness] = useState(isOn ? currentBrt : 0);
  const [busy, setBusy] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const name = label || entity?.friendly_name || entity_id;

  useEffect(() => {
    const brt =
      entity?.state === "on" && entity?.brightness != null
        ? Math.round((entity.brightness / 255) * 100)
        : entity?.state === "on"
          ? 100
          : 0;
    setBrightness(brt);
  }, [entity?.state, entity?.brightness]);

  const sendBrightness = useCallback(
    (pct: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        setBusy(true);
        try {
          await actionHandlers.set_light({
            entity_id,
            brightness: Math.round((pct / 100) * 255),
          });
          setTimeout(() => _onRefresh?.(), 800);
        } catch {
          /* ignore */
        } finally {
          setBusy(false);
        }
      }, 200);
    },
    [entity_id],
  );

  const handleToggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await actionHandlers.toggle_entity({
        entity_id,
        action: "toggle",
      });
      setBrightness(isOn ? 0 : currentBrt || 100);
      setTimeout(() => _onRefresh?.(), 800);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  const glowColor = `rgba(255, 215, 0, ${brightness / 200})`;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-neutral-200">{name}</span>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-mono",
              brightness > 0 ? "text-cyber-yellow" : "text-neutral-600",
            )}
          >
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
          >
            <span
              className={cn(
                "absolute top-0.5 h-4 w-4 rounded-full transition-all",
                isOn
                  ? "left-[18px] bg-cyber-yellow"
                  : "left-0.5 bg-neutral-500",
              )}
            />
          </button>
        </div>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={brightness}
        onChange={(e) => {
          const val = parseInt(e.target.value, 10);
          setBrightness(val);
          sendBrightness(val);
        }}
        disabled={busy}
        className="light-slider w-full"
        style={{
          background: `linear-gradient(to right, rgba(255,255,255,0.1) 0%, ${glowColor} ${brightness}%, rgba(255,255,255,0.06) ${brightness}%)`,
        }}
      />
    </div>
  );
}

function ClimateControlImpl({
  entity_id,
  label,
}: {
  entity_id: string;
  label: string | null;
}) {
  const entity = _entityLookup(entity_id);
  const isOn =
    entity?.state !== "off" && entity?.state !== "unavailable";
  const presetModes = entity?.preset_modes ?? [];
  const [activePreset, setActivePreset] = useState<string | null>(
    entity?.preset_mode ?? null,
  );
  const [busy, setBusy] = useState(false);
  const name = label || entity?.friendly_name || entity_id;

  useEffect(() => {
    if (entity?.preset_mode) setActivePreset(entity.preset_mode);
  }, [entity?.preset_mode]);

  const handleToggle = async () => {
    setBusy(true);
    try {
      await actionHandlers.toggle_entity({
        entity_id,
        action: isOn ? "turn_off" : "turn_on",
      });
      setTimeout(() => _onRefresh?.(), 1000);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  const handlePreset = async (mode: string) => {
    setActivePreset(mode);
    setBusy(true);
    try {
      await actionHandlers.set_climate({
        entity_id,
        preset_mode: mode,
        temperature: null,
      });
      setTimeout(() => _onRefresh?.(), 1000);
    } catch {
      setActivePreset(entity?.preset_mode ?? null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-neutral-200">{name}</span>
        <button
          onClick={handleToggle}
          disabled={busy}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            isOn
              ? "bg-green-500/20 text-green-400"
              : "bg-white/5 text-neutral-500",
            busy && "opacity-50",
          )}
        >
          {isOn ? "ON" : "OFF"}
        </button>
      </div>
      {presetModes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {presetModes.map((mode) => (
            <button
              key={mode}
              onClick={() => handlePreset(mode)}
              disabled={busy}
              className={cn(
                "rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all",
                activePreset === mode
                  ? "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30"
                  : "bg-white/5 text-neutral-400 border border-transparent hover:bg-white/10",
                busy && "opacity-50",
              )}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
      )}
      {entity?.current_temperature != null && (
        <div className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-2">
          <span className="text-xs text-neutral-500">Current</span>
          <span className="text-sm font-mono text-white">
            {entity.current_temperature}&deg;C
          </span>
        </div>
      )}
    </div>
  );
}

const GAP_MAP = { sm: "gap-1.5", md: "gap-3", lg: "gap-5" };

export const { registry, handlers } = defineRegistry(catalog, {
  components: {
    Card: ({ props, children }) => (
      <div
        className={cn(
          "rounded-xl border border-white/10 bg-white/[0.03]",
          props.padding === "sm" && "p-2",
          props.padding === "lg" && "p-6",
          (!props.padding || props.padding === "md") && "p-4",
        )}
      >
        {props.title && (
          <h3 className="mb-3 text-sm font-medium text-neutral-300">
            {props.title}
          </h3>
        )}
        {children}
      </div>
    ),

    Stack: ({ props, children }) => (
      <div
        className={cn(
          "flex",
          props.direction === "horizontal"
            ? "flex-row items-center"
            : "flex-col",
          GAP_MAP[props.gap ?? "md"],
        )}
      >
        {children}
      </div>
    ),

    Grid: ({ props, children }) => {
      const cols = props.columns ?? 2;
      return (
        <div
          className={cn("grid", GAP_MAP[props.gap ?? "md"])}
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          }}
        >
          {children}
        </div>
      );
    },

    DeviceToggle: ({ props }) => (
      <DeviceToggleImpl
        entity_id={props.entity_id}
        label={props.label}
      />
    ),

    LightControl: ({ props }) => (
      <LightControlImpl
        entity_id={props.entity_id}
        label={props.label}
      />
    ),

    ClimateControl: ({ props }) => (
      <ClimateControlImpl
        entity_id={props.entity_id}
        label={props.label}
      />
    ),

    StatCard: ({ props }) => (
      <div className="rounded-md border border-white/5 bg-white/[0.02] p-3">
        <p className="text-[11px] text-neutral-500 truncate">
          {props.label}
        </p>
        <div className="mt-1">
          <span className="text-2xl font-bold text-white font-mono">
            {props.value}
          </span>
          {props.unit && (
            <span className="ml-1 text-sm text-neutral-400">
              {props.unit}
            </span>
          )}
        </div>
      </div>
    ),

    SensorReading: ({ props }) => {
      const entity = _entityLookup(props.entity_id);
      const name = props.label || entity?.friendly_name || props.entity_id;
      return (
        <div className="rounded-md border border-white/5 bg-white/[0.02] p-2.5">
          <p className="text-[11px] text-neutral-500 truncate">{name}</p>
          <p className="mt-1 text-lg font-mono text-white">
            {entity?.state ?? "--"}
          </p>
        </div>
      );
    },

    ActionButton: ({ props }) => {
      const [busy, setBusy] = useState(false);
      const handleClick = async () => {
        if (busy) return;
        setBusy(true);
        try {
          const handler =
            actionHandlers[
              props.action_type as keyof typeof actionHandlers
            ];
          if (handler) {
            await (handler as (p: Record<string, unknown>) => Promise<void>)(
              (props.action_params as Record<string, unknown>) ?? {},
            );
            setTimeout(() => _onRefresh?.(), 1000);
          }
        } catch {
          /* ignore */
        } finally {
          setBusy(false);
        }
      };

      return (
        <button
          onClick={handleClick}
          disabled={busy}
          className={cn(
            "rounded-lg px-3 py-2 text-xs font-medium transition-colors",
            busy && "opacity-50",
            props.variant === "ghost"
              ? "bg-transparent text-neutral-400 hover:bg-white/5"
              : props.variant === "secondary"
                ? "bg-white/5 text-neutral-300 border border-white/10 hover:bg-white/10"
                : "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30 hover:bg-cyber-yellow/30",
          )}
        >
          {props.label}
        </button>
      );
    },

    DataTable: ({ props }) => (
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead className="border-b border-white/20">
            <tr>
              {props.columns.map((col, i) => (
                <th
                  key={i}
                  className="px-2 py-1 text-left font-semibold text-white"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className="px-2 py-1 border-t border-white/5 text-neutral-300"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),

    TextInput: ({ props }) => (
      <div>
        {props.label && (
          <label className="block text-xs text-neutral-400 mb-1">
            {props.label}
          </label>
        )}
        <input
          type={props.field_type ?? "text"}
          placeholder={props.placeholder ?? ""}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 transition-colors"
        />
      </div>
    ),

    SelectInput: ({ props }) => (
      <div>
        {props.label && (
          <label className="block text-xs text-neutral-400 mb-1">
            {props.label}
          </label>
        )}
        <select className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyber-yellow/40 transition-colors">
          {props.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    ),
  },

  actions: {
    toggle_entity: async (params) => {
      await actionHandlers.toggle_entity(
        params as {
          entity_id: string;
          action: "toggle" | "turn_on" | "turn_off";
        },
      );
    },
    set_light: async (params) => {
      await actionHandlers.set_light(
        params as { entity_id: string; brightness: number | null },
      );
    },
    set_climate: async (params) => {
      await actionHandlers.set_climate(
        params as {
          entity_id: string;
          preset_mode: string | null;
          temperature: number | null;
        },
      );
    },
    activate_scene: async (params) => {
      await actionHandlers.activate_scene(
        params as { scene_id: string },
      );
    },
  },
});
