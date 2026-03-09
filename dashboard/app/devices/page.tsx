"use client";

import { useState } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import EntityCard from "@/components/EntityCard";
import { useEntities } from "@/lib/hooks/useEntities";
import { cn } from "@/lib/utils";

const PRIORITY_DOMAINS = [
  "light",
  "switch",
  "fan",
  "climate",
  "media_player",
  "sensor",
  "binary_sensor",
  "camera",
  "automation",
  "person",
  "weather",
];

export default function DevicesPage() {
  const { data, error, loading, refresh } = useEntities();
  const [search, setSearch] = useState("");
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  const domains = data
    ? Object.entries(data.domains).sort(([a], [b]) => {
        const ai = PRIORITY_DOMAINS.indexOf(a);
        const bi = PRIORITY_DOMAINS.indexOf(b);
        const aRank = ai === -1 ? 999 : ai;
        const bRank = bi === -1 ? 999 : bi;
        return aRank - bRank;
      })
    : [];

  const filteredDomains = domains
    .filter(([d]) => !selectedDomain || d === selectedDomain)
    .map(([domain, group]) => ({
      domain,
      entities: group.entities.filter(
        (e) =>
          !search ||
          e.friendly_name.toLowerCase().includes(search.toLowerCase()) ||
          e.entity_id.toLowerCase().includes(search.toLowerCase())
      ),
    }))
    .filter((d) => d.entities.length > 0);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">
              Devices
            </h1>
            <p className="text-sm text-neutral-400">
              {data
                ? `${data.total} entities across ${Object.keys(data.domains).length} domains`
                : "Loading..."}
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
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search entities..."
          className="w-full max-w-md rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/50 transition-colors"
        />
      </BlurFade>

      <BlurFade delay={0.1}>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedDomain(null)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-mono transition-colors",
              !selectedDomain
                ? "bg-cyber-yellow/20 text-cyber-yellow"
                : "bg-white/5 text-neutral-400 hover:text-white"
            )}
          >
            All
          </button>
          {domains.map(([domain, group]) => (
            <button
              key={domain}
              onClick={() =>
                setSelectedDomain(selectedDomain === domain ? null : domain)
              }
              className={cn(
                "rounded-full px-3 py-1 text-xs font-mono transition-colors",
                selectedDomain === domain
                  ? "bg-cyber-yellow/20 text-cyber-yellow"
                  : "bg-white/5 text-neutral-400 hover:text-white"
              )}
            >
              {domain} ({group.count})
            </button>
          ))}
        </div>
      </BlurFade>

      {loading && (
        <p className="text-sm text-neutral-500 animate-pulse">
          Loading entities...
        </p>
      )}
      {error && <p className="text-sm text-red-400">Error: {error}</p>}

      {filteredDomains.map(({ domain, entities }, i) => (
        <BlurFade key={domain} delay={0.15 + i * 0.03}>
          <div>
            <h2 className="text-sm font-mono text-neutral-400 mb-2">
              {domain}{" "}
              <span className="text-neutral-600">({entities.length})</span>
            </h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {entities.map((entity) => (
                <EntityCard
                  key={entity.entity_id}
                  entity={entity}
                  domain={domain}
                  onToggled={refresh}
                />
              ))}
            </div>
          </div>
        </BlurFade>
      ))}
    </div>
  );
}
