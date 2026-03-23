"use client";

import { useState, useCallback, useMemo, useEffect } from "react";
import {
  generateWidget,
  suggestWidget,
  saveDashboardConfig,
  getDashboardConfig,
} from "@/lib/api";
import { GenUIRenderer } from "@/lib/generative-ui";
import type { EntityLookup } from "@/lib/generative-ui";
import type {
  EntitiesResponse,
  EntityInfo,
  DashboardConfig,
  WidgetSize,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "entities" | "prompt" | "preview";

interface WidgetBuilderProps {
  open: boolean;
  onClose: () => void;
  entitiesData: EntitiesResponse | null;
  onConfigUpdate: (config: DashboardConfig) => void;
}

const SIZE_OPTIONS: { value: WidgetSize; label: string }[] = [
  { value: "sm", label: "Small (1 col)" },
  { value: "md", label: "Medium (2 col)" },
  { value: "lg", label: "Large (3 col)" },
  { value: "full", label: "Full width" },
];

export default function WidgetBuilder({
  open,
  onClose,
  entitiesData,
  onConfigUpdate,
}: WidgetBuilderProps) {
  const [step, setStep] = useState<Step>("entities");
  const [selectedEntities, setSelectedEntities] = useState<Set<string>>(
    new Set(),
  );
  const [description, setDescription] = useState("");
  const [widgetTitle, setWidgetTitle] = useState("");
  const [widgetSize, setWidgetSize] = useState<WidgetSize>("md");
  const [spec, setSpec] = useState<{
    root: string;
    elements: Record<string, unknown>;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [domainFilter, setDomainFilter] = useState<string>("all");

  useEffect(() => {
    if (!open) {
      setStep("entities");
      setSelectedEntities(new Set());
      setDescription("");
      setWidgetTitle("");
      setWidgetSize("md");
      setSpec(null);
      setError(null);
    }
  }, [open]);

  const entitiesByDomain = useMemo(() => {
    if (!entitiesData) return {};
    const map: Record<string, EntityInfo[]> = {};
    for (const [domain, group] of Object.entries(entitiesData.domains)) {
      if (group.entities.length > 0) {
        map[domain] = group.entities;
      }
    }
    return map;
  }, [entitiesData]);

  const domains = useMemo(
    () => Object.keys(entitiesByDomain).sort(),
    [entitiesByDomain],
  );

  const filteredEntities = useMemo(() => {
    if (domainFilter === "all") {
      return Object.values(entitiesByDomain).flat();
    }
    return entitiesByDomain[domainFilter] ?? [];
  }, [entitiesByDomain, domainFilter]);

  const entityLookup: EntityLookup = useCallback(
    (id: string) => {
      if (!entitiesData) return undefined;
      for (const group of Object.values(entitiesData.domains)) {
        const found = group.entities.find((e) => e.entity_id === id);
        if (found) return found;
      }
      return undefined;
    },
    [entitiesData],
  );

  const toggleEntity = useCallback((eid: string) => {
    setSelectedEntities((prev) => {
      const next = new Set(prev);
      if (next.has(eid)) next.delete(eid);
      else next.add(eid);
      return next;
    });
  }, []);

  const handleSuggest = useCallback(async () => {
    if (selectedEntities.size === 0 || suggesting) return;
    setSuggesting(true);
    try {
      const result = await suggestWidget(Array.from(selectedEntities));
      if (!widgetTitle) setWidgetTitle(result.title);
      if (!description) setDescription(result.description);
    } catch {
      // silent -- user can still type manually
    } finally {
      setSuggesting(false);
    }
  }, [selectedEntities, suggesting, widgetTitle, description]);

  const handleGenerate = useCallback(async () => {
    if (selectedEntities.size === 0 || !description.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await generateWidget(
        Array.from(selectedEntities),
        description,
        widgetSize,
      );
      setSpec(result.spec);
      setStep("preview");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedEntities, description, widgetSize]);

  const handleTryAnother = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await generateWidget(
        Array.from(selectedEntities),
        description,
        widgetSize,
      );
      setSpec(result.spec);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedEntities, description, widgetSize]);

  const handleSave = useCallback(async () => {
    if (!spec) return;
    setLoading(true);
    setError(null);
    try {
      const current = await getDashboardConfig();
      const newWidget = {
        id: `gen-${Date.now().toString(36)}`,
        type: "generative" as const,
        title: widgetTitle || "Custom Widget",
        size: widgetSize,
        config: {
          spec,
          entity_ids: Array.from(selectedEntities),
          prompt: description,
        },
      };
      const updated: DashboardConfig = {
        widgets: [...(current.widgets ?? []), newWidget],
      };
      await saveDashboardConfig(updated);
      onConfigUpdate(updated);
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [
    spec,
    widgetTitle,
    widgetSize,
    selectedEntities,
    description,
    onConfigUpdate,
    onClose,
  ]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-t-2xl sm:rounded-2xl border border-white/10 bg-neutral-950/95 shadow-2xl backdrop-blur-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="h-2 w-2 rounded-full bg-cyber-yellow" />
            <h3 className="text-sm font-medium text-white">
              Widget Builder
            </h3>
            <div className="flex gap-1">
              {(["entities", "prompt", "preview"] as Step[]).map(
                (s, i) => (
                  <div
                    key={s}
                    className={cn(
                      "h-1 w-6 rounded-full transition-colors",
                      step === s || (s === "entities" && step !== "entities") || (s === "prompt" && step === "preview")
                        ? "bg-cyber-yellow"
                        : "bg-white/10",
                    )}
                  />
                ),
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-neutral-400 hover:text-white transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              className="h-4 w-4"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {step === "entities" && (
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-white mb-1">
                  Select entities for your widget
                </h4>
                <p className="text-xs text-neutral-500">
                  Choose the devices and sensors to include.
                </p>
              </div>

              {/* Domain filter */}
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setDomainFilter("all")}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs transition-colors",
                    domainFilter === "all"
                      ? "bg-cyber-yellow/20 text-cyber-yellow"
                      : "bg-white/5 text-neutral-400 hover:bg-white/10",
                  )}
                >
                  All
                </button>
                {domains.map((d) => (
                  <button
                    key={d}
                    onClick={() => setDomainFilter(d)}
                    className={cn(
                      "rounded-md px-2.5 py-1 text-xs transition-colors",
                      domainFilter === d
                        ? "bg-cyber-yellow/20 text-cyber-yellow"
                        : "bg-white/5 text-neutral-400 hover:bg-white/10",
                    )}
                  >
                    {d}
                  </button>
                ))}
              </div>

              {/* Entity list */}
              <div className="max-h-64 overflow-y-auto space-y-1 rounded-lg border border-white/5 p-2">
                {filteredEntities.map((entity) => (
                  <label
                    key={entity.entity_id}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-white/5 cursor-pointer transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedEntities.has(entity.entity_id)}
                      onChange={() => toggleEntity(entity.entity_id)}
                      className="rounded border-white/20 bg-white/5 text-cyber-yellow focus:ring-cyber-yellow/30"
                    />
                    <span className="text-sm text-neutral-200 truncate">
                      {entity.friendly_name}
                    </span>
                    <span className="ml-auto text-[10px] text-neutral-600 font-mono">
                      {entity.state}
                    </span>
                  </label>
                ))}
              </div>

              {selectedEntities.size > 0 && (
                <p className="text-xs text-neutral-400">
                  {selectedEntities.size} selected
                </p>
              )}
            </div>
          )}

          {step === "prompt" && (
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-white mb-1">
                  Describe your widget
                </h4>
                <p className="text-xs text-neutral-500">
                  Tell the AI what kind of widget you want.
                </p>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-1">
                  Widget title
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={widgetTitle}
                    onChange={(e) => setWidgetTitle(e.target.value)}
                    placeholder="e.g. Bedroom Controls"
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 pr-9 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 transition-colors"
                  />
                  <button
                    type="button"
                    onClick={handleSuggest}
                    disabled={suggesting || selectedEntities.size === 0}
                    className={cn(
                      "absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1 transition-colors",
                      suggesting
                        ? "text-cyber-yellow/50 animate-pulse"
                        : "text-neutral-500 hover:text-cyber-yellow",
                      selectedEntities.size === 0 && "opacity-30 cursor-not-allowed",
                    )}
                    title="Auto-generate title and description"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                      <path d="M12 3l1.912 5.813a2 2 0 001.272 1.278L21 12l-5.816 1.91a2 2 0 00-1.272 1.277L12 21l-1.912-5.813a2 2 0 00-1.272-1.278L3 12l5.816-1.91a2 2 0 001.272-1.277z" />
                    </svg>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-1">
                  Description
                </label>
                <div className="relative">
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="e.g. Show toggle switches for the lights and a brightness slider, with current temperature reading"
                    rows={3}
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 pr-9 text-sm text-white placeholder-neutral-500 outline-none focus:border-cyber-yellow/40 transition-colors resize-none"
                  />
                  <button
                    type="button"
                    onClick={handleSuggest}
                    disabled={suggesting || selectedEntities.size === 0}
                    className={cn(
                      "absolute right-1.5 top-2.5 rounded-md p-1 transition-colors",
                      suggesting
                        ? "text-cyber-yellow/50 animate-pulse"
                        : "text-neutral-500 hover:text-cyber-yellow",
                      selectedEntities.size === 0 && "opacity-30 cursor-not-allowed",
                    )}
                    title="Auto-generate title and description"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                      <path d="M12 3l1.912 5.813a2 2 0 001.272 1.278L21 12l-5.816 1.91a2 2 0 00-1.272 1.277L12 21l-1.912-5.813a2 2 0 00-1.272-1.278L3 12l5.816-1.91a2 2 0 001.272-1.277z" />
                    </svg>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-1">
                  Widget size
                </label>
                <div className="flex gap-2">
                  {SIZE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setWidgetSize(opt.value)}
                      className={cn(
                        "rounded-lg px-3 py-1.5 text-xs transition-all",
                        widgetSize === opt.value
                          ? "bg-cyber-yellow/20 text-cyber-yellow border border-cyber-yellow/30"
                          : "bg-white/5 text-neutral-400 border border-transparent hover:bg-white/10",
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === "preview" && (
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-white mb-1">
                  Preview
                </h4>
                <p className="text-xs text-neutral-500">
                  Here is your generated widget. Try another variation or
                  save it.
                </p>
              </div>

              {spec ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <GenUIRenderer
                    spec={spec}
                    entityLookup={entityLookup}
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center py-12 text-neutral-500 text-sm">
                  No preview available.
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="mt-3 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-400">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-white/10 px-5 py-3">
          <div>
            {step !== "entities" && (
              <button
                onClick={() =>
                  setStep(step === "preview" ? "prompt" : "entities")
                }
                disabled={loading}
                className="text-xs text-neutral-400 hover:text-white transition-colors"
              >
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {step === "entities" && (
              <button
                onClick={() => setStep("prompt")}
                disabled={selectedEntities.size === 0}
                className={cn(
                  "rounded-lg bg-cyber-yellow/90 px-4 py-2 text-sm font-medium text-black hover:bg-cyber-yellow transition-colors",
                  selectedEntities.size === 0 &&
                    "opacity-40 cursor-not-allowed",
                )}
              >
                Next
              </button>
            )}
            {step === "prompt" && (
              <button
                onClick={handleGenerate}
                disabled={
                  loading ||
                  !description.trim() ||
                  selectedEntities.size === 0
                }
                className={cn(
                  "rounded-lg bg-cyber-yellow/90 px-4 py-2 text-sm font-medium text-black hover:bg-cyber-yellow transition-colors",
                  (loading || !description.trim()) &&
                    "opacity-40 cursor-not-allowed",
                )}
              >
                {loading ? "Generating..." : "Generate"}
              </button>
            )}
            {step === "preview" && (
              <>
                <button
                  onClick={handleTryAnother}
                  disabled={loading}
                  className={cn(
                    "rounded-lg bg-white/5 px-4 py-2 text-sm text-neutral-300 border border-white/10 hover:bg-white/10 transition-colors",
                    loading && "opacity-40 cursor-not-allowed",
                  )}
                >
                  {loading ? "Generating..." : "Try Another"}
                </button>
                <button
                  onClick={handleSave}
                  disabled={loading || !spec}
                  className={cn(
                    "rounded-lg bg-cyber-yellow/90 px-4 py-2 text-sm font-medium text-black hover:bg-cyber-yellow transition-colors",
                    (loading || !spec) &&
                      "opacity-40 cursor-not-allowed",
                  )}
                >
                  Save to Dashboard
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
