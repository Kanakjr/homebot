"use client";

import { useState, useEffect, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { getEvents } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EventLogEntry } from "@/lib/types";

const EVENT_COLORS: Record<string, string> = {
  state_change: "border-blue-500/40 bg-blue-500/5",
  skill_trigger: "border-purple-500/40 bg-purple-500/5",
  automation: "border-orange-500/40 bg-orange-500/5",
  error: "border-red-500/40 bg-red-500/5",
};

const EVENT_DOT: Record<string, string> = {
  state_change: "bg-blue-400",
  skill_trigger: "bg-purple-400",
  automation: "bg-orange-400",
  error: "bg-red-400",
};

function formatTs(ts: string): string {
  const d = new Date(ts + "Z");
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatDate(ts: string): string {
  const d = new Date(ts + "Z");
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function groupByDate(events: EventLogEntry[]): Map<string, EventLogEntry[]> {
  const groups = new Map<string, EventLogEntry[]>();
  for (const ev of events) {
    const key = formatDate(ev.ts);
    const arr = groups.get(key) || [];
    arr.push(ev);
    groups.set(key, arr);
  }
  return groups;
}

function domainOf(entityId: string): string {
  return entityId.split(".")[0];
}

const HOUR_OPTIONS = [6, 12, 24, 48, 72];
const ALL_DOMAINS = [
  "light", "switch", "fan", "climate", "sensor", "binary_sensor",
  "media_player", "camera", "automation", "person",
];

export default function ActivityPage() {
  const [events, setEvents] = useState<EventLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [domainFilter, setDomainFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getEvents(hours, 500);
      setEvents(data.events);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filtered = events.filter((ev) => {
    if (domainFilter && domainOf(ev.entity_id) !== domainFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        ev.entity_id.toLowerCase().includes(q) ||
        ev.event_type.toLowerCase().includes(q) ||
        ev.details?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const activeDomains = [...new Set(events.map((e) => domainOf(e.entity_id)))].sort();
  const dateGroups = groupByDate(filtered);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-5xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">
              Activity
            </h1>
            <p className="text-sm text-neutral-400">
              {filtered.length} events in the last {hours}h
            </p>
          </div>
          <button
            onClick={refresh}
            className="text-xs text-neutral-500 hover:text-neutral-300 font-mono transition-colors"
          >
            Refresh
          </button>
        </div>
      </BlurFade>

      <BlurFade delay={0.05}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 p-0.5">
            {HOUR_OPTIONS.map((h) => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-mono transition-colors",
                  hours === h
                    ? "bg-cyber-yellow/20 text-cyber-yellow"
                    : "text-neutral-400 hover:text-white",
                )}
              >
                {h}h
              </button>
            ))}
          </div>

          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter events..."
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/50 transition-colors w-48"
          />
        </div>
      </BlurFade>

      <BlurFade delay={0.1}>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setDomainFilter(null)}
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-mono transition-colors",
              !domainFilter
                ? "bg-cyber-yellow/20 text-cyber-yellow"
                : "bg-white/5 text-neutral-400 hover:text-white",
            )}
          >
            All
          </button>
          {activeDomains.map((d) => (
            <button
              key={d}
              onClick={() => setDomainFilter(domainFilter === d ? null : d)}
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-mono transition-colors",
                domainFilter === d
                  ? "bg-cyber-yellow/20 text-cyber-yellow"
                  : "bg-white/5 text-neutral-400 hover:text-white",
              )}
            >
              {d}
            </button>
          ))}
        </div>
      </BlurFade>

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading events...
        </p>
      )}
      {error && <p className="text-sm text-red-400">Error: {error}</p>}

      {!loading && filtered.length === 0 && (
        <BlurFade delay={0.15}>
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center">
            <p className="text-neutral-400">No events found.</p>
            <p className="mt-2 text-sm text-neutral-500">
              Events appear when device states change in Home Assistant.
            </p>
          </div>
        </BlurFade>
      )}

      {[...dateGroups.entries()].map(([date, evts], gi) => (
        <BlurFade key={date} delay={0.15 + gi * 0.03}>
          <div>
            <h2 className="text-xs font-mono text-neutral-500 mb-3 sticky top-0 bg-true-black/80 backdrop-blur py-1">
              {date}
            </h2>
            <div className="relative ml-3 border-l border-white/10 pl-5 space-y-2">
              {evts.map((ev, i) => (
                <div
                  key={`${ev.ts}-${ev.entity_id}-${i}`}
                  className={cn(
                    "relative rounded-lg border px-3 py-2",
                    EVENT_COLORS[ev.event_type] || "border-white/10 bg-white/5",
                  )}
                >
                  <div
                    className={cn(
                      "absolute -left-[29px] top-3 h-2.5 w-2.5 rounded-full ring-2 ring-true-black",
                      EVENT_DOT[ev.event_type] || "bg-neutral-500",
                    )}
                  />
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-mono text-neutral-400 shrink-0">
                        {formatTs(ev.ts)}
                      </span>
                      <span className="text-sm text-neutral-200 truncate">
                        {ev.entity_id}
                      </span>
                    </div>
                    <span className="text-xs font-mono text-neutral-500 shrink-0">
                      {ev.event_type}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-xs">
                    <span className="text-neutral-500">{ev.old_state}</span>
                    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3 text-neutral-600 shrink-0">
                      <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                    </svg>
                    <span className="text-neutral-300">{ev.new_state}</span>
                  </div>
                  {ev.details && (
                    <p className="mt-1 text-xs text-neutral-500 truncate">
                      {ev.details}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </BlurFade>
      ))}
    </div>
  );
}
