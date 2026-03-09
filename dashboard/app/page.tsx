"use client";

import { useEffect, useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import StatusBadge from "@/components/StatusBadge";
import DashboardRenderer from "@/components/DashboardRenderer";
import DashboardAssistant from "@/components/DashboardAssistant";
import { getHealth, getDashboardConfig } from "@/lib/api";
import { useEntities } from "@/lib/hooks/useEntities";
import type { HealthResponse, DashboardConfig } from "@/lib/types";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: entitiesData, refresh: refreshEntities } = useEntities(15_000);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setError("Backend unreachable"));

    getDashboardConfig()
      .then(setConfig)
      .catch((err) => setError(err.message));
  }, []);

  const handleConfigUpdate = useCallback((newConfig: DashboardConfig) => {
    setConfig(newConfig);
  }, []);

  return (
    <div className="relative p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl">
      <BlurFade delay={0}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white font-mono">
              Dashboard
            </h1>
            <p className="text-sm text-neutral-400">
              HomeBotAI
            </p>
          </div>
          <div className="flex items-center gap-3">
            {health && (
              <StatusBadge
                status={health.status === "ok" ? "ok" : "error"}
                label={health.status}
              />
            )}
            {error && <StatusBadge status="error" label="offline" />}
          </div>
        </div>
      </BlurFade>

      <BlurFade delay={0.1}>
        {config ? (
          <DashboardRenderer
            config={config}
            entitiesData={entitiesData}
            onRefresh={refreshEntities}
          />
        ) : (
          <div className="flex items-center justify-center py-20 text-neutral-500">
            {error ? error : "Loading dashboard..."}
          </div>
        )}
      </BlurFade>

      <DashboardAssistant onConfigUpdate={handleConfigUpdate} />
    </div>
  );
}
