"use client";

import { useEffect, useState, useCallback } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import StatusBadge from "@/components/StatusBadge";
import DashboardRenderer from "@/components/DashboardRenderer";
import DashboardAssistant from "@/components/DashboardAssistant";
import WidgetBuilder from "@/components/WidgetBuilder";
import WidgetEditModal from "@/components/WidgetEditModal";
import PresenceBar from "@/components/PresenceBar";
import { AiSummaryBanner } from "@/components/widgets";
import { getHealth, getDashboardConfig, saveDashboardConfig } from "@/lib/api";
import { useEntities } from "@/lib/hooks/useEntities";
import type { HealthResponse, DashboardConfig, DashboardWidget, WidgetSize, WidgetLayout } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: entitiesData, refresh: refreshEntities } = useEntities(15_000);

  const [builderOpen, setBuilderOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editingWidget, setEditingWidget] = useState<DashboardWidget | null>(null);

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

  const persistConfig = useCallback(
    async (updated: DashboardConfig) => {
      setConfig(updated);
      try {
        await saveDashboardConfig(updated);
      } catch {
        // revert on failure
        const fresh = await getDashboardConfig().catch(() => null);
        if (fresh) setConfig(fresh);
      }
    },
    [],
  );

  const handleLayoutChange = useCallback(
    (layouts: Record<string, WidgetLayout[]>) => {
      if (!config) return;
      persistConfig({ ...config, layouts });
    },
    [config, persistConfig],
  );

  const handleDelete = useCallback(
    (widgetId: string) => {
      if (!config) return;
      const filtered = config.widgets.filter((w) => w.id !== widgetId);
      const layouts = config.layouts
        ? Object.fromEntries(
            Object.entries(config.layouts).map(([bp, items]) => [
              bp,
              items.filter((l) => l.i !== widgetId),
            ]),
          )
        : undefined;
      persistConfig({ ...config, widgets: filtered, layouts });
    },
    [config, persistConfig],
  );

  const handleEditWidget = useCallback(
    (widgetId: string) => {
      if (!config) return;
      const widget = config.widgets.find((w) => w.id === widgetId);
      if (widget) setEditingWidget(widget);
    },
    [config],
  );

  const handleSaveWidget = useCallback(
    (update: { id: string; title: string; size: WidgetSize }) => {
      if (!config) return;
      const updated = config.widgets.map((w) =>
        w.id === update.id ? { ...w, title: update.title, size: update.size } : w,
      );
      persistConfig({ ...config, widgets: updated });
    },
    [config, persistConfig],
  );

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
          <div className="flex items-center gap-2">
            {config && config.widgets.length > 0 && (
              <button
                onClick={() => setEditMode((v) => !v)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                  editMode
                    ? "border-cyber-yellow/40 bg-cyber-yellow/15 text-cyber-yellow"
                    : "border-white/10 bg-white/5 text-neutral-400 hover:text-white hover:bg-white/10",
                )}
              >
                {editMode ? "Done" : "Edit"}
              </button>
            )}
            <button
              onClick={() => setBuilderOpen(true)}
              className="rounded-lg border border-cyber-yellow/20 bg-cyber-yellow/5 px-3 py-1.5 text-xs font-medium text-cyber-yellow hover:bg-cyber-yellow/15 transition-colors"
            >
              + Add Widget
            </button>
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

      <BlurFade delay={0.03}>
        <PresenceBar entitiesData={entitiesData} />
      </BlurFade>

      <BlurFade delay={0.05}>
        <AiSummaryBanner />
      </BlurFade>

      <BlurFade delay={0.1}>
        {config ? (
          <DashboardRenderer
            config={config}
            entitiesData={entitiesData}
            onRefresh={refreshEntities}
            editMode={editMode}
            onLayoutChange={handleLayoutChange}
            onDelete={handleDelete}
            onEditWidget={handleEditWidget}
          />
        ) : (
          <div className="flex items-center justify-center py-20 text-neutral-500">
            {error ? error : "Loading dashboard..."}
          </div>
        )}
      </BlurFade>

      <DashboardAssistant onConfigUpdate={handleConfigUpdate} />
      <WidgetBuilder
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        entitiesData={entitiesData}
        onConfigUpdate={handleConfigUpdate}
      />
      <WidgetEditModal
        widget={editingWidget}
        open={editingWidget !== null}
        onClose={() => setEditingWidget(null)}
        onSave={handleSaveWidget}
      />
    </div>
  );
}
