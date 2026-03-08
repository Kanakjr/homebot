"use client";

import { useEffect, useState } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import MagicCard from "@/components/magicui/magic-card";
import ChatWidget from "@/components/ChatWidget";
import StatusBadge from "@/components/StatusBadge";
import { getHealth, getEntities } from "@/lib/api";
import type { HealthResponse, EntitiesResponse, EntityInfo } from "@/lib/types";

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <MagicCard className="p-4">
      <p className="text-xs text-neutral-500 font-mono uppercase tracking-wider">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold text-white font-mono">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-neutral-400">{sub}</p>}
    </MagicCard>
  );
}

function SensorRow({ entities }: { entities: EntityInfo[] }) {
  const sensors = entities.filter((e) => {
    const name = e.friendly_name.toLowerCase();
    return (
      name.includes("temperature") ||
      name.includes("humidity") ||
      name.includes("pm2.5")
    );
  });

  if (sensors.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {sensors.slice(0, 8).map((s) => (
        <div
          key={s.entity_id}
          className="rounded-lg border border-white/10 bg-white/5 p-3"
        >
          <p className="text-xs text-neutral-500 truncate">
            {s.friendly_name}
          </p>
          <p className="mt-1 text-lg font-mono text-white">{s.state}</p>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [entities, setEntities] = useState<EntitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getHealth(), getEntities()])
      .then(([h, e]) => {
        setHealth(h);
        setEntities(e);
      })
      .catch((err) => setError(err.message));
  }, []);

  const allEntities = entities
    ? Object.values(entities.domains).flatMap((d) => d.entities)
    : [];

  const activeLights = allEntities.filter(
    (e) => e.entity_id.startsWith("light.") && e.state === "on"
  );
  const playingMedia = allEntities.filter(
    (e) =>
      e.entity_id.startsWith("media_player.") &&
      (e.state === "playing" || e.state === "paused")
  );
  const sensorEntities = [
    ...(entities?.domains["sensor"]?.entities ?? []),
  ];

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">
              Dashboard
            </h1>
            <p className="text-sm text-neutral-400">
              HomeBotAI system overview
            </p>
          </div>
          {health && (
            <StatusBadge
              status={health.status === "ok" ? "ok" : "error"}
              label={health.status}
            />
          )}
          {error && <StatusBadge status="error" label="offline" />}
        </div>
      </BlurFade>

      <BlurFade delay={0.1}>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Entities"
            value={entities ? String(entities.total) : "--"}
            sub={
              entities
                ? `${Object.keys(entities.domains).length} domains`
                : undefined
            }
          />
          <StatCard
            label="Tools"
            value={health ? String(health.tools_registered) : "--"}
            sub="registered"
          />
          <StatCard
            label="Lights On"
            value={String(activeLights.length)}
            sub={
              activeLights.length > 0
                ? activeLights.map((l) => l.friendly_name).join(", ")
                : "all off"
            }
          />
          <StatCard
            label="Media"
            value={String(playingMedia.length)}
            sub={
              playingMedia.length > 0
                ? playingMedia.map((m) => m.friendly_name).join(", ")
                : "nothing playing"
            }
          />
        </div>
      </BlurFade>

      {sensorEntities.length > 0 && (
        <BlurFade delay={0.2}>
          <div>
            <h2 className="text-sm font-mono text-neutral-400 mb-3">
              Sensors
            </h2>
            <SensorRow entities={sensorEntities} />
          </div>
        </BlurFade>
      )}

      <BlurFade delay={0.3}>
        <div>
          <h2 className="text-sm font-mono text-neutral-400 mb-3">
            Quick Chat
          </h2>
          <ChatWidget compact />
        </div>
      </BlurFade>
    </div>
  );
}
